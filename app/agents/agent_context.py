"""
Agent 上下文数据模型 - 策略一：按需上下文隔离
每个 Agent 仅接收所需的最小数据集，避免 Token 膨胀与注意力分散。
"""
from dataclasses import dataclass
@dataclass(frozen=True)
class PRContext:
    """公共 PR 元数据（所有 Agent 共享的只读数据）"""
    owner: str
    repo: str
    pr_number: int
    title: str
    description: str
    branch: str
    head_sha: str
@dataclass(frozen=True)
class LogicAgentContext:
    """Logic Agent 专用上下文：Diff + 关联文件
    
    Logic Agent 内部仍然执行 Security + Performance + Reducer 流程，
    仅接收经过 process_pr_files 处理的语义化 Diff。
    """
    pr: PRContext
    diff: str  # 经过 process_pr_files 处理的语义化 Diff
@dataclass(frozen=True)
class ChangelogAgentContext:
    """Changelog Agent 专用上下文：仅 Git commit 历史
    
    极速层 Agent，不需要完整 Diff，只需 commit messages
    即可生成变更日志摘要。后期将通过 RAG 数据库增强。
    """
    pr: PRContext
    commits: list  # PR 的 commit 列表 (message, sha, author)
@dataclass(frozen=True)
class UnitTestAgentContext:
    """UnitTest Agent 专用上下文：AST 解析树 + Diff
    
    深度层 Agent，接收 tree-sitter AST 解析出的函数/类结构
    与精简 Diff，用于生成高质量单测建议。
    """
    pr: PRContext
    diff: str           # 精简的 Diff
    ast_signatures: str  # tree-sitter AST 解析出的函数/类结构