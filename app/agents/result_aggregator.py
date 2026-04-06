"""
结果聚合器 - 策略二（渐进式流式交付）+ 策略四（增量合并）
核心职责：
1. 组装带占位符的初始评论模板（骨架评论）
2. 监听 Agent 回调，增量替换占位符
3. 通过 GitHub API 实时更新评论内容
增量覆写机制：使用 HTML 注释锚点定位各模块区域，
正则替换时只替换对应区域，保留已完成模块的内容。
"""
import re
import logging
from app.agents.base_agent import AgentResult, AgentStatus
from app.agents.agent_context import PRContext
from app.git_providers.github_provider import GitHubProvider
logger = logging.getLogger("codemind.aggregator")
class ResultAggregator:
    """
    状态机合并器。
    维护三大 Agent 的执行状态，通过 HTML 注释占位符
    实现增量更新 GitHub 评论。
    """
    # 占位符：HTML 注释 + 人类可读文本
    SECTION_START = "<!-- CODEMIND_{name}_START -->"
    SECTION_END = "<!-- CODEMIND_{name}_END -->"
    PENDING_TEXTS = {
        "changelog": "⏳ Changelog 分析中...",
        "logic": "⏳ 逻辑审查进行中（含安全与性能分析）...",
        "unittest": "⏳ 单测生成中...",
    }
    SECTION_TITLES = {
        "changelog": "📋 变更日志 (Changelog)",
        "logic": "🔍 逻辑审查 (Logic Review)",
        "unittest": "🧪 单元测试建议 (Unit Test Suggestions)",
    }
    DEGRADED_TEXTS = {
        "changelog": "⚠️ 变更日志分析因超时跳过。请查看 PR 提交记录了解变更详情。",
        "logic": "⚠️ 逻辑审查因超时跳过，建议人工关注核心变动的边界条件与异常处理。",
        "unittest": "⚠️ 详细测试分析因超时跳过，建议关注核心变动的边界条件与异常抛出。",
    }
    def __init__(self, github: GitHubProvider):
        self.github = github
        self._agent_statuses: dict[str, AgentStatus] = {
            "changelog": AgentStatus.PENDING,
            "logic": AgentStatus.PENDING,
            "unittest": AgentStatus.PENDING,
        }
    def _make_section(self, name: str, content: str) -> str:
        """构建带 HTML 注释锚点的模块区域"""
        start = self.SECTION_START.format(name=name.upper())
        end = self.SECTION_END.format(name=name.upper())
        title = self.SECTION_TITLES.get(name, name)
        return f"{start}\n### {title}\n\n{content}\n\n{end}"
    def build_initial_comment(self, pr_ctx: PRContext) -> str:
        """
        构建带占位符的骨架评论。
        
        在所有 Agent 启动前立即发布，让用户知道审查已开始。
        """
        header = (
            f"## CodeMind PR Reviewer Guide 🔍\n\n"
            f"**PR:** {pr_ctx.title}\n"
            f"**分支:** {pr_ctx.branch}\n\n"
            f"---\n\n"
        )
        sections = []
        for name in ["changelog", "logic", "unittest"]:
            pending_text = self.PENDING_TEXTS[name]
            sections.append(self._make_section(name, pending_text))
        footer = (
            "\n---\n"
            "*🤖 Powered by CodeMind — 异构并发审查引擎*"
        )
        return header + "\n\n".join(sections) + footer
    def update_section(self, comment_body: str, agent_name: str, result: AgentResult) -> str:
        """
        用实际结果替换指定 Agent 的占位符区域。
        
        使用正则匹配 HTML 注释锚点之间的内容进行替换，
        不影响其他已完成模块。
        
        Args:
            comment_body: 当前评论完整内容
            agent_name: Agent 名称 (changelog/logic/unittest)
            result: Agent 执行结果
            
        Returns:
            更新后的评论内容
        """
        self._agent_statuses[agent_name] = result.status
        # 根据状态确定显示内容
        if result.status in (AgentStatus.COMPLETED, AgentStatus.SOFT_TIMEOUT):
            display_content = result.content
            if result.status == AgentStatus.SOFT_TIMEOUT:
                display_content += f"\n\n*⏱️ 该分析耗时 {result.elapsed_seconds}s（超过软超时阈值）*"
        elif result.status == AgentStatus.DEGRADED:
            display_content = self.DEGRADED_TEXTS.get(agent_name, result.content)
        elif result.status == AgentStatus.FAILED:
            display_content = (
                f"⚠️ {self.SECTION_TITLES.get(agent_name, agent_name)} 分析失败。\n\n"
                f"错误信息: `{result.error}`"
            )
        else:
            display_content = result.content
        # 构建新的模块区域
        new_section = self._make_section(agent_name, display_content)
        # 正则替换：匹配 START 到 END 之间的所有内容
        start_marker = re.escape(self.SECTION_START.format(name=agent_name.upper()))
        end_marker = re.escape(self.SECTION_END.format(name=agent_name.upper()))
        pattern = f"{start_marker}.*?{end_marker}"
        updated = re.sub(pattern, new_section, comment_body, flags=re.DOTALL)
        if updated == comment_body:
            logger.warning(f"Failed to replace section for agent '{agent_name}' - markers not found")
        return updated
    async def publish_update(self, owner: str, repo: str, comment_id: int, body: str) -> None:
        """
        通过 GitHub API 增量更新评论。
        
        仅在内容变化时调用 API，避免不必要的请求。
        """
        try:
            await self.github.update_pr_comment(owner, repo, comment_id, body)
            logger.info(f"Updated PR comment {comment_id} successfully")
        except Exception as e:
            logger.error(f"Failed to update PR comment {comment_id}: {e}")