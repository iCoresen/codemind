"""
Changelog Agent - 极速层 (~5s)

仅接收 Git commit 历史，生成结构化变更日志摘要。
Token 消耗极低，响应速度最快。

后期计划通过 RAG 数据库增强，存储 PR 历史与团队规范。
"""
import time
import logging
from pathlib import Path

from jinja2 import Template

from app.agents.base_agent import BaseAgent, AgentResult, AgentStatus
from app.agents.agent_context import ChangelogAgentContext
from app.ai_handlers.litellm_ai_handler import LiteLLMAIHandler

try:
    import tomllib
except ImportError:
    pass

logger = logging.getLogger("codemind.agent.changelog")


class ChangelogAgent(BaseAgent):
    """
    极速层 Agent：基于 commit 历史生成变更日志。
    
    输入：ChangelogAgentContext（仅 commit messages）
    输出：Markdown 格式的变更摘要
    """
    
    name = "changelog"
    fallback_message = "⚠️ 变更日志分析因超时跳过。请查看 PR 提交记录了解变更详情。"

    def __init__(self, ai: LiteLLMAIHandler, soft_timeout: float = 5.0, hard_timeout: float = 10.0):
        self.ai = ai
        self.soft_timeout = soft_timeout
        self.hard_timeout = hard_timeout

    async def execute(self, context: ChangelogAgentContext) -> AgentResult:
        start_time = time.time()
        
        logger.info(f"Changelog Agent starting for {context.pr.owner}/{context.pr.repo}#{context.pr.pr_number}")
        
        # 加载 Prompt 模板
        prompts_dir = Path(__file__).parent.parent / "prompts"
        prompt_path = prompts_dir / "changelog_prompt.toml"
        
        try:
            with open(prompt_path, "rb") as f:
                prompts = tomllib.load(f)["pr_review_prompt"]
        except Exception as e:
            logger.error(f"Failed to load changelog prompt: {e}")
            return self._make_result(
                AgentStatus.FAILED, self.fallback_message, start_time, str(e)
            )
        
        system_prompt = prompts["system"]
        user_template = Template(prompts["user"])
        user_prompt = user_template.render(
            title=context.pr.title,
            branch=context.pr.branch,
            description=context.pr.description,
            commits=context.commits,
        )
        
        # 调用 LLM
        try:
            response_text, finish_reason = await self.ai.async_chat_completion(
                system_prompt, user_prompt, temperature=0.3
            )
            logger.info(f"Changelog Agent completed in {round(time.time() - start_time, 2)}s")
            return self._make_result(AgentStatus.COMPLETED, response_text, start_time)
        
        except Exception as e:
            logger.error(f"Changelog Agent LLM call failed: {e}")
            return self._make_result(
                AgentStatus.FAILED, self.fallback_message, start_time, str(e)
            )
