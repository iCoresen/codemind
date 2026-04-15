"""
Reviewer 基类与结果模型。
定义标准化的 Reviewer 接口，所有 Reviewer（Logic、Changelog、UnitTest）
必须实现 execute() 方法，并返回统一的 ReviewResult。
"""

import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("codemind.reviewer")


class ReviewerStatus(Enum):
    """Reviewer 执行状态"""

    PENDING = "pending"
    RUNNING = "running"
    SOFT_TIMEOUT = "soft_timeout"  # 已达软超时，仍在执行
    COMPLETED = "completed"  # 正常完成
    FAILED = "failed"  # 执行失败
    DEGRADED = "degraded"  # 硬超时或异常，已降级


@dataclass
class ReviewResult:
    """Reviewer 执行结果"""

    reviewer_name: str
    status: ReviewerStatus
    content: str  # 成功时的 Markdown 内容，降级时的占位文本
    elapsed_seconds: float
    error: str | None = None


class BaseReviewer(ABC):
    """
    Reviewer 基类。

    所有并发 Reviewer 必须实现此接口。TimeoutController 通过
    soft_timeout / hard_timeout 属性控制执行时限。
    """

    name: str = "base"
    soft_timeout: float = 10.0  # 软超时（秒），触发预警
    hard_timeout: float = 20.0  # 硬超时（秒），触发熔断
    fallback_message: str = "⚠️ 该分析因超时跳过。"

    @abstractmethod
    async def execute(self, context) -> ReviewResult:
        """
        执行 Reviewer 分析。

        Args:
            context: 对应的 ReviewerContext 子类实例

        Returns:
            ReviewResult: 包含状态、内容和耗时信息
        """
        pass

    def _make_result(
        self,
        status: ReviewerStatus,
        content: str,
        start_time: float,
        error: str | None = None,
    ) -> ReviewResult:
        """便捷方法：构建 ReviewResult"""
        return ReviewResult(
            reviewer_name=self.name,
            status=status,
            content=content,
            elapsed_seconds=round(time.time() - start_time, 2),
            error=error,
        )
