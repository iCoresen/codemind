"""
多级超时与柔性降级控制器 - 策略三
实现 Design for Failure 模式：
- 软超时（Soft Timeout）预警：记录日志，准备通用占位文本
- 硬超时（Hard Timeout）熔断：cancel 协程，触发降级策略
- 优雅降级（Graceful Degradation）：返回降级文本而非报错
"""
import asyncio
import logging
import time
from app.agents.base_agent import BaseAgent, AgentResult, AgentStatus
logger = logging.getLogger("codemind.timeout")
class TimeoutController:
    """
    包装 Agent.execute() 的调用，实现多级超时。
    
    工作流程:
    1. 创建 agent.execute(context) 的 Task
    2. 用 asyncio.wait_for 设置硬超时
    3. 同时启动软超时监控协程
    4. 根据完成状态返回对应的 AgentResult
    """
    async def run_with_timeout(self, agent: BaseAgent, context) -> AgentResult:
        """
        执行 Agent 并监控超时。
        
        Args:
            agent: 待执行的 Agent 实例
            context: Agent 对应的上下文
            
        Returns:
            AgentResult: 正常结果 / 软超时结果 / 降级结果
        """
        start_time = time.time()
        soft_timeout_reached = False
        async def _soft_timeout_watcher():
            """软超时监控：记录预警日志"""
            nonlocal soft_timeout_reached
            await asyncio.sleep(agent.soft_timeout)
            soft_timeout_reached = True
            elapsed = round(time.time() - start_time, 2)
            logger.warning(
                f"Agent '{agent.name}' reached soft timeout ({agent.soft_timeout}s) "
                f"after {elapsed}s. Preparing fallback..."
            )
        # 启动软超时监控（fire-and-forget）
        watcher_task = asyncio.create_task(_soft_timeout_watcher())
        try:
            # 硬超时包装
            result: AgentResult = await asyncio.wait_for(
                agent.execute(context),
                timeout=agent.hard_timeout,
            )
            # 取消软超时监控
            watcher_task.cancel()
            # 如果在软超时后才完成，标记状态
            if soft_timeout_reached and result.status == AgentStatus.COMPLETED:
                result = AgentResult(
                    agent_name=result.agent_name,
                    status=AgentStatus.SOFT_TIMEOUT,
                    content=result.content,
                    elapsed_seconds=round(time.time() - start_time, 2),
                    error=None,
                )
                logger.info(
                    f"Agent '{agent.name}' completed after soft timeout "
                    f"in {result.elapsed_seconds}s"
                )
            return result
        except asyncio.TimeoutError:
            # 硬超时熔断
            watcher_task.cancel()
            elapsed = round(time.time() - start_time, 2)
            logger.error(
                f"Agent '{agent.name}' hit hard timeout ({agent.hard_timeout}s) "
                f"after {elapsed}s. Triggering graceful degradation."
            )
            return AgentResult(
                agent_name=agent.name,
                status=AgentStatus.DEGRADED,
                content=agent.fallback_message,
                elapsed_seconds=elapsed,
                error=f"Hard timeout after {elapsed}s",
            )
        except Exception as e:
            # 执行异常
            watcher_task.cancel()
            elapsed = round(time.time() - start_time, 2)
            logger.error(
                f"Agent '{agent.name}' failed after {elapsed}s: {e}",
                exc_info=True,
            )
            return AgentResult(
                agent_name=agent.name,
                status=AgentStatus.FAILED,
                content=agent.fallback_message,
                elapsed_seconds=elapsed,
                error=str(e),
            )
