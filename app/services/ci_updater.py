import logging
import asyncio
from typing import Any

from app.git_providers.github_provider import GitHubProvider
from app.agents.result_aggregator import ResultAggregator

logger = logging.getLogger("codemind.ci_updater")

class CIUpdaterService:
    """
    负责查询 PR 的 CI (check_runs) 状态并以最佳格式追加到 CodeMind 评论中。
    解耦了后台任务调度与呈现逻辑。
    """
    def __init__(self, github_provider: GitHubProvider):
        self.provider = github_provider
        self.aggregator = ResultAggregator(self.provider)

    async def execute(self, owner: str, repo: str, head_sha: str) -> None:
        """
        核心执行逻辑：
        1. 通过 head_sha 查找关联的 PR。
        2. 获取这个 sha 的全部 check_runs。
        3. 如果还未全部完成，直接返回（等待下一个 check_run completed 事件）。
        4. 如果完成，获取 CodeMind 发布的最后一条评论，并通过 aggregator 追加展示 CI 信息。
        """
        # 1. 查找关联 PR
        prs = await self._get_prs_for_commit(owner, repo, head_sha)
        if not prs:
            logger.info("No PR found associated with commit %s", head_sha)
            return

        # 2. 获取并过滤 linter 相关 check_runs
        check_runs = await self.provider.get_pr_check_runs(owner, repo, head_sha)
        relevant_checks = [
            c for c in check_runs
            if any(l in c.get("name", "").lower() for l in ["flake8", "eslint", "sonar", "lint", "style"])
        ]

        if not relevant_checks:
            logger.info("No relevant linter CI checks found for %s/%s@%s", owner, repo, head_sha)
            return

        # 只要还有在 pending 状态的，就退出等待下一个 webhook 触发
        pending = any(check.get("status") != "completed" for check in relevant_checks)
        if pending:
            logger.info("Some CI checks are still pending, skipping update for now.")
            return

        has_failures = any(
            check.get("conclusion") in ["failure", "timed_out", "action_required"]
            for check in relevant_checks
        )

        # 3. 为所有找到的 PR 更新评论
        for pr_data in prs:
            pr_number = pr_data.get("number")
            if not pr_number:
                continue

            bot_comments = await self._get_bot_comments(owner, repo, pr_number)
            if not bot_comments:
                continue

            # 使用最新的一条评论追加
            latest_comment = bot_comments[-1]
            comment_id = latest_comment.get("id")
            current_body = latest_comment.get("body", "")

            # 检查是否已经追加过（使用 ResultAggregator 统一判断机制）
            if self.aggregator.has_ci_results(current_body):
                logger.info("CI result already appended to PR #%d comment %d", pr_number, comment_id)
                continue

            # 通过 Aggregator 追加内容
            updated_body = self.aggregator.append_ci_results(current_body, relevant_checks, has_failures)
            
            # 发布更新
            await self.provider.update_pr_comment(owner, repo, comment_id, updated_body)
            logger.info("Successfully appended CI results to PR #%d comment %d", pr_number, comment_id)

    async def _get_prs_for_commit(self, owner: str, repo: str, head_sha: str) -> list[dict[str, Any]]:
        """获取与指定提交相关的 PR 列表"""
        try:
            prs = await self.provider.client.get(f"/repos/{owner}/{repo}/commits/{head_sha}/pulls")
            return prs.json()
        except Exception as e:
            logger.error("Failed to get PRs for commit %s: %e", head_sha, e)
            return []

    async def _get_bot_comments(self, owner: str, repo: str, pr_number: int) -> list[dict[str, Any]]:
        """获取由 CodeMind Bot 发布的评论"""
        try:
            comments = await self.provider.get_pr_comments(owner, repo, pr_number)
            return [c for c in comments if "CodeMind" in c.get("body", "")]
        except Exception as e:
            logger.error("Failed to get comments for PR #%d: %e", pr_number, e)
            return []
