"""
PR Reviewer - Orchestrator

协调三大异构并发 Agent（Changelog, Logic, UnitTest）的执行，
实现渐进式流式交付与优雅降级。

核心流程：
1. 并发获取 PR 数据（info, files, commits）
2. 构建隔离上下文（每个 Agent 只获取所需数据）
3. 发布骨架评论（立即可见）
4. 并发启动三大 Agent（各自带超时控制）
5. 按完成顺序增量更新评论
6. CI 轮询并最终更新
"""
import logging
import asyncio
from pathlib import Path

from app.config import Settings
from app.git_providers.github_provider import GitHubProvider
from app.ai_handlers.litellm_ai_handler import LiteLLMAIHandler
from app.algo.pr_processing import process_pr_files
from app.algo.ast_analyzer import extract_changed_signatures_from_diff
from app.agents.agent_context import (
    PRContext,
    LogicAgentContext,
    ChangelogAgentContext,
    UnitTestAgentContext,
)
from app.agents.changelog_agent import ChangelogAgent
from app.agents.logic_agent import LogicAgent
from app.agents.unittest_agent import UnitTestAgent
from app.agents.timeout_controller import TimeoutController
from app.agents.result_aggregator import ResultAggregator
from app.agents.base_agent import AgentResult
from app.exceptions import GitHubAPIError

logger = logging.getLogger("codemind.reviewer")


class PRReviewer:
    """
    PR 审查编排器。
    
    协调 Changelog（极速层）、Logic（核心层）、UnitTest（深度层）
    三大 Agent 的并发执行，实现渐进式交付。
    """

    def __init__(self, settings: Settings, event_payload: dict):
        self.settings = settings
        self.event_payload = event_payload
        self.github = GitHubProvider(settings.github_token)
        self.ai = LiteLLMAIHandler(settings)

    async def run(self):
        owner = self.event_payload["owner"]
        repo = self.event_payload["repo"]
        pr_number = self.event_payload["pr_number"]

        logger.info(f"Starting orchestrated review for {owner}/{repo}#{pr_number}")

        # ── Phase 1: 并发获取 PR 数据 ──
        try:
            pr_info, pr_files, commits = await asyncio.gather(
                self.github.get_pr_info(owner, repo, pr_number),
                self.github.list_pr_files(owner, repo, pr_number),
                self.github.get_pr_commits(owner, repo, pr_number),
            )
        except GitHubAPIError as e:
            logger.error(f"Failed to fetch PR data from GitHub: {e}")
            raise

        title = pr_info.get("title", "")
        description = pr_info.get("body", "") or ""
        head_ref = pr_info.get("head", {}).get("ref", "")
        head_sha = pr_info.get("head", {}).get("sha", "")
        base_ref = pr_info.get("base", {}).get("ref", "")
        branch = f"{base_ref} -> {head_ref}"

        # 处理 Diff
        diff = process_pr_files(pr_files)

        # ── Phase 2: 构建隔离上下文 ──
        pr_ctx = PRContext(
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            title=title,
            description=description,
            branch=branch,
            head_sha=head_sha,
        )

        changelog_ctx = ChangelogAgentContext(pr=pr_ctx, commits=commits)
        logic_ctx = LogicAgentContext(pr=pr_ctx, diff=diff)

        # AST 签名提取（用于 UnitTest Agent）
        ast_signatures = await self._extract_ast_signatures(
            owner, repo, head_sha, pr_files, diff
        )
        unittest_ctx = UnitTestAgentContext(
            pr=pr_ctx, diff=diff, ast_signatures=ast_signatures
        )

        # ── Phase 3: 发布骨架评论 ──
        aggregator = ResultAggregator(self.github)
        initial_comment = aggregator.build_initial_comment(pr_ctx)

        try:
            comment_id = await self.github.publish_pr_comment(
                owner, repo, pr_number, initial_comment
            )
            logger.info(
                f"Skeleton comment published for {owner}/{repo}#{pr_number}, "
                f"comment_id={comment_id}"
            )
        except GitHubAPIError as e:
            logger.error(f"Failed to publish skeleton comment: {e}")
            raise

        # ── Phase 4: 并发启动三大 Agent ──
        controller = TimeoutController()

        changelog_agent = ChangelogAgent(
            ai=self.ai,
            soft_timeout=self.settings.changelog_soft_timeout,
            hard_timeout=self.settings.changelog_hard_timeout,
        )
        logic_agent = LogicAgent(
            ai=self.ai,
            settings=self.settings,
            soft_timeout=self.settings.logic_soft_timeout,
            hard_timeout=self.settings.logic_hard_timeout,
        )
        unittest_agent = UnitTestAgent(
            ai=self.ai,
            soft_timeout=self.settings.unittest_soft_timeout,
            hard_timeout=self.settings.unittest_hard_timeout,
        )

        changelog_task = asyncio.create_task(
            controller.run_with_timeout(changelog_agent, changelog_ctx)
        )
        logic_task = asyncio.create_task(
            controller.run_with_timeout(logic_agent, logic_ctx)
        )
        unittest_task = asyncio.create_task(
            controller.run_with_timeout(unittest_agent, unittest_ctx)
        )

        # ── Phase 5: 渐进式交付 - 按完成顺序增量更新 ──
        current_body = initial_comment
        
        for coro in asyncio.as_completed([changelog_task, logic_task, unittest_task]):
            try:
                result: AgentResult = await coro
                logger.info(
                    f"Agent '{result.agent_name}' completed with status "
                    f"{result.status.value} in {result.elapsed_seconds}s"
                )

                current_body = aggregator.update_section(
                    current_body, result.agent_name, result
                )
                await aggregator.publish_update(owner, repo, comment_id, current_body)

            except Exception as e:
                logger.error(f"Error processing agent result: {e}", exc_info=True)

        # ── Phase 6: CI 轮询 ──
        await self._poll_and_update_ci_results(
            owner, repo, head_sha, comment_id, current_body
        )

    async def _extract_ast_signatures(
        self,
        owner: str,
        repo: str,
        head_sha: str,
        pr_files: list[dict],
        diff: str,
    ) -> str:
        """
        从 PR 变更文件中提取 AST 签名。
        
        并发获取变更文件的源内容，然后通过 tree-sitter 解析。
        对获取失败的文件使用 diff 文本回退。
        """
        from app.algo.pr_processing import is_generated_or_ignored_file

        # 筛选需要 AST 分析的文件（非生成/忽略文件，且有内容变更）
        target_files = []
        for f in pr_files:
            filename = f.get("filename", "")
            status = f.get("status", "")
            if status == "removed" or is_generated_or_ignored_file(filename):
                continue
            # 仅分析支持的语言
            ext = Path(filename).suffix.lower()
            if ext in (".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".java"):
                target_files.append(filename)

        if not target_files:
            logger.info("No AST-analyzable files in PR")
            return ""

        # 限制并发文件获取数量（避免 API 限流）
        max_files = 10
        target_files = target_files[:max_files]

        # 并发获取文件内容
        file_contents = {}

        async def fetch_file(filepath: str):
            try:
                content = await self.github.get_file_content(
                    owner, repo, filepath, head_sha
                )
                file_contents[filepath] = content
            except Exception as e:
                logger.warning(f"Failed to fetch {filepath} for AST analysis: {e}")

        await asyncio.gather(*[fetch_file(fp) for fp in target_files])

        if not file_contents:
            logger.info("No file contents fetched for AST analysis, using diff fallback")

        # 提取签名
        return extract_changed_signatures_from_diff(diff, file_contents)

    async def _poll_and_update_ci_results(
        self,
        owner: str,
        repo: str,
        head_sha: str,
        comment_id: int,
        current_comment_body: str,
    ):
        """轮询 CI 结果并增量更新评论（保留原有逻辑）"""
        logger.info(f"Starting CI polling for {owner}/{repo} branch {head_sha}")
        max_retries = 30  # 30 * 10 = 300 seconds (5 minutes timeout)

        ci_placeholder = "\n\n---\n*⏳ 正在等待后台 CI 规范扫描结果，稍后将自动更新...*"
        
        # 追加 CI 等待占位符
        current_comment_body += ci_placeholder
        try:
            await self.github.update_pr_comment(owner, repo, comment_id, current_comment_body)
        except Exception:
            pass

        for attempt in range(max_retries):
            await asyncio.sleep(10)
            try:
                check_runs = await self.github.get_pr_check_runs(
                    owner, repo, head_sha
                )

                relevant_checks = [
                    c
                    for c in check_runs
                    if any(
                        l in c.get("name", "").lower()
                        for l in ["flake8", "eslint", "sonar", "lint", "style"]
                    )
                ]

                if not relevant_checks:
                    if attempt > 5:
                        final_append = "\n\n---\n*✅ 未检测到后台排队的 CI 规范扫描 (Flake8/ESLint 等)，本次审查结束。*"
                        new_comment = current_comment_body.replace(
                            ci_placeholder, final_append
                        )
                        await self.github.update_pr_comment(
                            owner, repo, comment_id, new_comment
                        )
                        return
                    continue

                pending = any(
                    check.get("status") != "completed" for check in relevant_checks
                )
                if pending:
                    logger.info(
                        f"CI linter still running... (Attempt {attempt+1}/{max_retries})"
                    )
                    continue

                # 全部完成，格式化结果
                linter_output = []
                has_failures = False
                for check in relevant_checks:
                    name = check.get("name", "Linter")
                    conclusion = check.get("conclusion")
                    if conclusion in ["failure", "timed_out", "action_required"]:
                        has_failures = True

                    output = check.get("output") or {}
                    sn = str(output.get("summary", ""))[:1000]
                    txt = str(output.get("text", ""))[:4000]
                    if len(str(output.get("text", ""))) > 4000:
                        txt += "\n...[CI输出过长，已截断]..."

                    linter_output.append(
                        f"<details><summary>CI Check: {name} (<strong>{conclusion}</strong>)</summary>\n\n"
                        f"**Summary:**\n{sn}\n\n**Details:**\n```text\n{txt}\n```\n</details>"
                    )

                header = (
                    "### ❌ 代码规范扫描未通过"
                    if has_failures
                    else "### ✅ 代码规范扫描通过"
                )
                final_append = "\n\n---\n" + header + "\n" + "\n\n".join(linter_output)

                new_comment = current_comment_body.replace(ci_placeholder, final_append)
                await self.github.update_pr_comment(
                    owner, repo, comment_id, new_comment
                )
                logger.info(f"Updated PR comment {comment_id} with CI conclusion.")
                return

            except Exception as e:
                logger.warning(f"Error polling CI results: {e}")

        # 超时
        timeout_append = "\n\n---\n*⚠️ CI 代码规范扫描加载超时（超过5分钟），请移步 GitHub Checks 页面查看实时的 Linter 报告详情。*"
        new_comment = current_comment_body.replace(ci_placeholder, timeout_append)
        try:
            await self.github.update_pr_comment(owner, repo, comment_id, new_comment)
        except Exception:
            pass
