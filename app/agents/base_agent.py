"""
Agent 基类与结果模型。
定义标准化的 Agent 接口，所有 Agent（Logic、Changelog、UnitTest）
必须实现 execute() 方法，并返回统一的 AgentResult。
"""
import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
logger = logging.getLogger("codemind.agent")
class AgentStatus(Enum):
    """Agent 执行状态"""
    PENDING = "pending"
    RUNNING = "running"
    SOFT_TIMEOUT = "soft_timeout"     # 已达软超时，仍在执行
    COMPLETED = "completed"           # 正常完成
    FAILED = "failed"                 # 执行失败
    DEGRADED = "degraded"             # 硬超时或异常，已降级
@dataclass
class AgentResult:
    """Agent 执行结果"""
    agent_name: str
    status: AgentStatus
    content: str            # 成功时的 Markdown 内容，降级时的占位文本
    elapsed_seconds: float
    error: str | None = None
class BaseAgent(ABC):
    """
    Agent 基类。
    
    所有并发 Agent 必须实现此接口。TimeoutController 通过
    soft_timeout / hard_timeout 属性控制执行时限。
    """
    
    name: str = "base"
    soft_timeout: float = 10.0   # 软超时（秒），触发预警
    hard_timeout: float = 20.0   # 硬超时（秒），触发熔断
    fallback_message: str = "⚠️ 该分析因超时跳过。"
    @abstractmethod
    async def execute(self, context) -> AgentResult:
        """
        执行 Agent 分析。
        
        Args:
            context: 对应的 AgentContext 子类实例
            
        Returns:
            AgentResult: 包含状态、内容和耗时信息
        """
        pass
    def _make_result(self, status: AgentStatus, content: str, start_time: float, error: str | None = None) -> AgentResult:
        """便捷方法：构建 AgentResult"""
        return AgentResult(
            agent_name=self.name,
            status=status,
            content=content,
            elapsed_seconds=round(time.time() - start_time, 2),
            error=error,
        )
