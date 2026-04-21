"""
Logic Reviewer - 核心层 (~15s)

包装原有的 Security + Performance + Reducer 流程。
接收 Diff 与 PR 元数据，内部并发执行安全与性能分析，
然后通过 Reducer 综合生成最终的逻辑审查报告。

保留了原有 pr_reviewer.py 中的完整多 Reviewer 架构设计。
"""

import time
import asyncio
import logging
import yaml
from pathlib import Path

from jinja2 import Template

from app.reviewers.base_reviewer import BaseReviewer, ReviewResult, ReviewerStatus
from app.reviewers.reviewer_context import LogicReviewerContext
from app.ai_handlers.litellm_ai_handler import LiteLLMAIHandler
from app.config import Settings
from app.rag.embedding_service import EmbeddingService
from app.rag.vector_store import ChromaVectorStore
from app.rag.retriever import RAGRetriever
from app.rag.evaluation import RAGEvaluator

try:
    import tomllib
except ImportError:
    pass

logger = logging.getLogger("codemind.reviewer.logic")


class LogicReviewer(BaseReviewer):
    """
    核心层 Reviewer：包装原有的 Security + Performance + Reducer 流程。

    内部仍然并发执行 Security Reviewer 和 Performance Reviewer，
    然后通过 Reducer 综合分析，生成最终的逻辑审查报告。

    输入：LogicReviewerContext（Diff + PR 元数据）
    输出：格式化的 Markdown 审查报告
    """

    name = "logic"
    fallback_message = (
        "⚠️ 逻辑审查因超时跳过，建议人工关注核心变动的边界条件与异常处理。"
    )

    def __init__(
        self,
        ai: LiteLLMAIHandler,
        settings: Settings,
        soft_timeout: float = 15.0,
        hard_timeout: float = 25.0,
        enable_rag: bool = True,
    ):
        self.ai = ai
        self.settings = settings
        self.soft_timeout = soft_timeout
        self.hard_timeout = hard_timeout
        self.prompts_dir = Path(__file__).parent.parent / "prompts"
        self.enable_rag = enable_rag

        if self.enable_rag:
            try:
                self.vector_store = ChromaVectorStore()
                self.embedding_service = EmbeddingService(self.ai)
                self.retriever = RAGRetriever(self.vector_store, self.embedding_service)
                self.evaluator = RAGEvaluator()
                # Initialize BM25 index on start for Hybrid search
                from app.rag.knowledge_manager import KnowledgeManager
                from app.rag.document_parser import DocumentParser

                self.knowledge_manager = KnowledgeManager(
                    self.vector_store, self.embedding_service, DocumentParser()
                )
                docs = self.knowledge_manager.load_all_docs_for_bm25()
                if docs:
                    self.retriever.build_bm25_index(docs)
                else:
                    self.enable_rag = False
                    logger.warning(
                        "No docs found for Logic RAG, disabling Hybrid RAG features"
                    )
            except Exception as e:
                logger.error(f"Failed to initialize Logic RAG components: {e}")
                self.enable_rag = False

    async def execute(self, context: LogicReviewerContext) -> ReviewResult:
        start_time = time.time()
        pr = context.pr

        logger.info(f"Logic Reviewer starting for {pr.owner}/{pr.repo}#{pr.pr_number}")

        # ── Phase 1: 并发执行 Security + Performance 子 Reviewer ──
        reviewer_names = ["security", "performance"]

        async def run_sub_reviewer(name: str, max_retries: int = 2) -> str:
            """执行单个子 Reviewer（保留原有逻辑）"""
            path = self.prompts_dir / f"{name}_prompt.toml"
            with open(path, "rb") as f:
                prompts = tomllib.load(f)["pr_review_prompt"]

            system_prompt = prompts["system"]

            if self.enable_rag:
                try:
                    query = f"{name} {pr.title} {pr.description}"
                    retrieved_docs = await self.retriever.hybrid_search_docs(
                        query=query[:200], top_k=2
                    )

                    if retrieved_docs:
                        self.evaluator.evaluate_retrieval(
                            query[:200], retrieved_docs, metadata={"agent": name}
                        )
                        historical_rules = "\n".join(
                            [f"- {doc}" for doc in retrieved_docs]
                        )
                        system_prompt += f"\n\n## 团队规范与历史文档参考 (RAG):\n{historical_rules}\n请务必参考并遵守以上规范。"
                except Exception as e:
                    logger.error(
                        f"Hybrid search failed during {name} sub reviewer execution: {e}"
                    )

            user_prompt_template = Template(prompts["user"])
            user_prompt = user_prompt_template.render(
                title=pr.title,
                branch=pr.branch,
                description=pr.description,
                language="auto",
                diff=context.diff[: max(0, 30000)],
            )

            for attempt in range(max_retries):
                try:
                    response_text, _ = await self.ai.async_chat_completion(
                        system_prompt, user_prompt
                    )
                    return response_text
                except Exception as e:
                    logger.warning(
                        f"Sub-reviewer {name} attempt {attempt + 1} failed: {e}"
                    )
                    if attempt == max_retries - 1:
                        logger.error(
                            f"Sub-reviewer {name} failed after {max_retries} attempts."
                        )
                        return f"Error during {name} analysis: {str(e)}"
                    await asyncio.sleep(1)
            return ""

        logger.info("Executing concurrent sub-reviewers: Security, Performance")
        tasks = [run_sub_reviewer(name) for name in reviewer_names]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        reviewer_results = {
            "security": results[0]
            if not isinstance(results[0], Exception)
            else f"Error: {str(results[0])}",
            "performance": results[1]
            if not isinstance(results[1], Exception)
            else f"Error: {str(results[1])}",
            "style": "⏳ 代码规范（Flake8/ESLint 等 CI 流程）正在后台扫描中，结果稍后将自动更新。",
        }

        # ── Phase 2: Reducer 综合分析 ──
        logger.info("Summarizing results with Reducer Reviewer")
        reducer_path = self.prompts_dir / "reducer_prompt.toml"

        try:
            with open(reducer_path, "rb") as f:
                reducer_prompts = tomllib.load(f)["pr_review_prompt"]
        except Exception as e:
            logger.error(f"Failed to load reducer prompt: {e}")
            # 如果 Reducer 模板加载失败，直接拼接子 Reviewer 结果
            fallback = self._build_fallback_content(reviewer_results)
            return self._make_result(ReviewerStatus.COMPLETED, fallback, start_time)

        r_system = reducer_prompts["system"]
        r_user_template = Template(reducer_prompts["user"])
        r_user = r_user_template.render(
            title=pr.title,
            branch=pr.branch,
            description=pr.description,
            security_report=reviewer_results["security"],
            performance_report=reviewer_results["performance"],
            style_report=reviewer_results["style"],
        )

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response_text, finish_reason = await self.ai.async_chat_completion(
                    r_system, r_user
                )
                logger.info(
                    f"Reducer response received (Attempt {attempt + 1}). Finish reason: {finish_reason}"
                )

                # 尝试格式化
                formatted = self._format_review_content(
                    response_text, pr.owner, pr.repo, pr.head_sha
                )
                return self._make_result(
                    ReviewerStatus.COMPLETED, formatted, start_time
                )

            except Exception as e:
                logger.warning(f"Reducer attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    logger.error("Max retries reached for Reducer. Using fallback.")
                    fallback = self._build_fallback_content(reviewer_results)
                    return self._make_result(
                        ReviewerStatus.COMPLETED, fallback, start_time
                    )

        return self._make_result(
            ReviewerStatus.FAILED, self.fallback_message, start_time
        )

    def _build_fallback_content(self, reviewer_results: dict) -> str:
        """当 Reducer 失败时，直接拼接子 Reviewer 原始结果"""
        return (
            "**⚠️ Reducer 格式化失败，展示各层原始输出：**\n\n"
            "#### 🔒 Security Analysis\n"
            f"{reviewer_results['security']}\n\n"
            "#### ⚡ Performance Analysis\n"
            f"{reviewer_results['performance']}\n\n"
            "#### 🎨 Style Analysis\n"
            f"{reviewer_results['style']}\n"
        )


    def _format_review_content(
        self, ai_response: str, owner: str, repo: str, head_sha: str
    ) -> str:
        """
        解析 Reducer 的 YAML 输出，格式化为 Markdown。
        保留原有 pr_reviewer.py 的格式化逻辑。
        """
        text_to_parse = ai_response.strip()
        if text_to_parse.startswith("```yaml"):
            text_to_parse = text_to_parse[7:]
        if text_to_parse.startswith("```"):
            text_to_parse = text_to_parse[3:]
        if text_to_parse.endswith("```"):
            text_to_parse = text_to_parse[:-3]

        parsed = yaml.safe_load(text_to_parse)

        if "final_review" not in parsed:
            # 如果不是预期格式，返回原始文本
            return f"```yaml\n{ai_response}\n```"

        review = parsed["final_review"]
        metrics = review.get("metrics", {})
        prioritized_issues = review.get("prioritized_issues", {})
        executive_summary = review.get("executive_summary", "")

        md = ""

        # 执行摘要
        if executive_summary:
            md += f"*{executive_summary}*\n\n---\n\n"

        # 指标
        effort = metrics.get("estimated_review_effort", 2)
        try:
            effort_int = int(effort)
        except (ValueError, TypeError):
            effort_int = 2
        blue_bars = "🔵" * effort_int
        white_bars = "⚪" * (5 - effort_int)
        md += (
            f"⏱️ **Estimated effort to review:** {effort_int} {blue_bars}{white_bars}\n"
        )

        security_score = metrics.get("security_score", 10)
        try:
            sec_score = float(security_score)
            if sec_score >= 9:
                md += "🔒 **No security concerns identified**\n"
            else:
                md += "🔒 **Security concerns detected!** ⚠️\n"
        except (ValueError, TypeError):
            pass

        md += "\n"

        # 问题列表
        blocker_issues = prioritized_issues.get("blocker_issues", [])
        high_priority = prioritized_issues.get("high_priority_issues", [])
        medium_priority = prioritized_issues.get("medium_priority_issues", [])
        low_priority = prioritized_issues.get("low_priority_suggestions", [])

        has_issues = bool(blocker_issues or high_priority or medium_priority)

        if has_issues:
            md += "⚡ **Recommended focus areas for review**\n\n"

        if blocker_issues:
            md += "#### 🚨 阻断性问题 (Blockers)\n"
            for issue in blocker_issues:
                md += self._format_issue_item(issue, owner, repo, head_sha)

        if high_priority:
            md += "#### ⚠️ 高优先级问题 (High Priority)\n"
            for issue in high_priority:
                md += self._format_issue_item(issue, owner, repo, head_sha)

        if medium_priority:
            md += "#### 📝 中优先级问题 (Medium Priority)\n"
            for issue in medium_priority:
                md += self._format_issue_item(issue, owner, repo, head_sha)

        if low_priority:
            md += "#### 💡 代码建议 (Suggestions)\n"
            for issue in low_priority:
                md += self._format_issue_item(issue, owner, repo, head_sha)

        return md

    def _format_issue_item(
        self, issue: dict, owner: str, repo: str, head_sha: str
    ) -> str:
        """格式化单个问题条目（保留原有逻辑）"""
        title = issue.get("title") or issue.get("description", "")[:20]
        desc = issue.get("description", "")
        raw_file = issue.get("file", "")
        raw_line = issue.get("line", "")
        action = (
            issue.get("immediate_action")
            or issue.get("recommended_action")
            or issue.get("improvement_suggestion")
        )

        # 解析文件链接
        files = []
        if isinstance(raw_file, list):
            files = [str(f).strip() for f in raw_file if str(f).strip()]
        elif isinstance(raw_file, str) and raw_file:
            files = [f.strip() for f in raw_file.split(",") if f.strip()]

        # 解析行号
        line_anchor = ""
        display_line = ""
        if raw_line:
            line_str = str(raw_line).strip()
            if isinstance(raw_line, list):
                line_str = "-".join([str(l).strip() for l in raw_line])

            if "-" in line_str:
                parts = [p.strip() for p in line_str.split("-")]
                valid_num = [p for p in parts if p.isdigit()]
                if len(valid_num) >= 2:
                    line_anchor = f"#L{valid_num[0]}-L{valid_num[-1]}"
                    display_line = f" (Lines {valid_num[0]}-{valid_num[-1]})"
                elif len(valid_num) == 1:
                    line_anchor = f"#L{valid_num[0]}"
                    display_line = f" (Line {valid_num[0]})"
            elif line_str.isdigit():
                line_anchor = f"#L{line_str}"
                display_line = f" (Line {line_str})"

        # 构建文件链接
        file_links = []
        snippet_links = []
        if head_sha:
            for file_path in files:
                link = f"https://github.com/{owner}/{repo}/blob/{head_sha}/{file_path}{line_anchor}"
                file_links.append(
                    f"<a href='{link}'><code>{file_path}</code>{display_line}</a>"
                )
                if line_anchor:
                    snippet_links.append(link)

        header = f"<strong>{title}</strong>"
        md_part = f"<details><summary>{header}</summary>\n\n"
        if file_links:
            md_part += f"📁 **相关位置**: {', '.join(file_links)}\n\n"
            for sl in snippet_links:
                md_part += f"{sl}\n\n"

        md_part += f"> {desc}\n"
        if action:
            md_part += f">\n> 💡 **建议修复**: {action}\n"
        md_part += "</details>\n\n"

        return md_part
