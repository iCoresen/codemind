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
from app.reviewers.base_reviewer import BaseReviewer, ReviewResult, ReviewerStatus

logger = logging.getLogger("codemind.timeout")


class TimeoutController:
    """
    包装 Reviewer.execute() 的调用，实现多级超时。

    工作流程:
    1. 创建 reviewer.execute(context) 的 Task
    2. 用 asyncio.wait_for 设置硬超时
    3. 同时启动软超时监控协程
    4. 根据完成状态返回对应的 ReviewResult
    """

    async def run_with_timeout(self, reviewer: BaseReviewer, context) -> ReviewResult:
        """
        执行 Reviewer 并监控超时。

        Args:
            reviewer: 待执行的 Reviewer 实例
            context: Reviewer 对应的上下文

        Returns:
            ReviewResult: 正常结果 / 软超时结果 / 降级结果
        """
        start_time = time.time()
        soft_timeout_reached = False

        async def _soft_timeout_watcher():
            """软超时监控：记录预警日志"""
            nonlocal soft_timeout_reached
            await asyncio.sleep(reviewer.soft_timeout)
            soft_timeout_reached = True
            elapsed = round(time.time() - start_time, 2)
            logger.warning(
                f"Reviewer '{reviewer.name}' reached soft timeout ({reviewer.soft_timeout}s) "
                f"after {elapsed}s. Preparing fallback..."
            )

        # 启动软超时监控（fire-and-forget）
        watcher_task = asyncio.create_task(_soft_timeout_watcher())
        try:
            # 硬超时包装
            result: ReviewResult = await asyncio.wait_for(
                reviewer.execute(context),
                timeout=reviewer.hard_timeout,
            )
            # 取消软超时监控
            watcher_task.cancel()
            # 如果在软超时后才完成，标记状态
            if soft_timeout_reached and result.status == ReviewerStatus.COMPLETED:
                result = ReviewResult(
                    reviewer_name=result.reviewer_name,
                    status=ReviewerStatus.SOFT_TIMEOUT,
                    content=result.content,
                    elapsed_seconds=round(time.time() - start_time, 2),
                    error=None,
                )
                logger.info(
                    f"Reviewer '{reviewer.name}' completed after soft timeout "
                    f"in {result.elapsed_seconds}s"
                )
            return result
        except asyncio.TimeoutError:
            # 硬超时熔断
            watcher_task.cancel()
            elapsed = round(time.time() - start_time, 2)
            logger.error(
                f"Reviewer '{reviewer.name}' hit hard timeout ({reviewer.hard_timeout}s) "
                f"after {elapsed}s. Triggering graceful degradation."
            )
            return ReviewResult(
                reviewer_name=reviewer.name,
                status=ReviewerStatus.DEGRADED,
                content=reviewer.fallback_message,
                elapsed_seconds=elapsed,
                error=f"Hard timeout after {elapsed}s",
            )
        except Exception as e:
            # 执行异常
            watcher_task.cancel()
            elapsed = round(time.time() - start_time, 2)
            logger.error(
                f"Reviewer '{reviewer.name}' failed after {elapsed}s: {e}",
                exc_info=True,
            )
            return ReviewResult(
                reviewer_name=reviewer.name,
                status=ReviewerStatus.FAILED,
                content=reviewer.fallback_message,
                elapsed_seconds=elapsed,
                error=str(e),
            )
