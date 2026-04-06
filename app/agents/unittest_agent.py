"""
UnitTest Agent - 深度层 (~30s)

基于 tree-sitter AST 解析结果和 Diff 生成高质量单测建议。
接收精确的函数/类结构信息而非完整文件，实现上下文隔离。

Token 消耗中等，但因需要理解代码结构所以耗时较长。
"""
import time
import logging
from pathlib import Path

from jinja2 import Template

from app.agents.base_agent import BaseAgent, AgentResult, AgentStatus
from app.agents.agent_context import UnitTestAgentContext
from app.ai_handlers.litellm_ai_handler import LiteLLMAIHandler

try:
    import tomllib
except ImportError:
    pass

logger = logging.getLogger("codemind.agent.unittest")


class UnitTestAgent(BaseAgent):
    """
    深度层 Agent：基于 AST 结构和 Diff 生成单测建议。
    
    输入：UnitTestAgentContext（AST 签名 + Diff）
    输出：Markdown 格式的单测建议
    """
    
    name = "unittest"
    fallback_message = "⚠️ 详细测试分析因超时跳过，建议关注核心变动的边界条件与异常抛出。"

    def __init__(self, ai: LiteLLMAIHandler, soft_timeout: float = 20.0, hard_timeout: float = 30.0):
        self.ai = ai
        self.soft_timeout = soft_timeout
        self.hard_timeout = hard_timeout

    async def execute(self, context: UnitTestAgentContext) -> AgentResult:
        start_time = time.time()
        pr = context.pr
        
        logger.info(f"UnitTest Agent starting for {pr.owner}/{pr.repo}#{pr.pr_number}")
        
        # 检查是否有有效的 AST 签名
        if not context.ast_signatures or context.ast_signatures.strip() == "":
            logger.info("No AST signatures found, skipping unit test generation")
            return self._make_result(
                AgentStatus.COMPLETED,
                "ℹ️ 本次变更未检测到可测试的函数/类定义，跳过单测建议。",
                start_time,
            )
        
        # 加载 Prompt 模板
        prompts_dir = Path(__file__).parent.parent / "prompts"
        prompt_path = prompts_dir / "unittest_prompt.toml"
        
        try:
            with open(prompt_path, "rb") as f:
                prompts = tomllib.load(f)["pr_review_prompt"]
        except Exception as e:
            logger.error(f"Failed to load unittest prompt: {e}")
            return self._make_result(
                AgentStatus.FAILED, self.fallback_message, start_time, str(e)
            )
        
        system_prompt = prompts["system"]
        user_template = Template(prompts["user"])
        user_prompt = user_template.render(
            title=pr.title,
            branch=pr.branch,
            description=pr.description,
            ast_signatures=context.ast_signatures[:15000],  # 限制 AST 输入量
            diff=context.diff[:20000],  # 限制 Diff 输入量
        )
        
        # 调用 LLM（使用稍高温度以生成更多样化的测试用例）
        max_retries = 2
        for attempt in range(max_retries):
            try:
                response_text, finish_reason = await self.ai.async_chat_completion(
                    system_prompt, user_prompt, temperature=0.4
                )
                logger.info(
                    f"UnitTest Agent completed in {round(time.time() - start_time, 2)}s "
                    f"(attempt {attempt + 1})"
                )
                return self._make_result(AgentStatus.COMPLETED, response_text, start_time)
            
            except Exception as e:
                logger.warning(f"UnitTest Agent attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    logger.error(f"UnitTest Agent failed after {max_retries} attempts.")
                    return self._make_result(
                        AgentStatus.FAILED, self.fallback_message, start_time, str(e)
                    )
        
        return self._make_result(AgentStatus.FAILED, self.fallback_message, start_time)
