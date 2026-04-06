"""
AST 解析器 - 使用 tree-sitter 进行代码结构提取

从 Diff 涉及的源文件中提取函数/类签名，为 UnitTest Agent
提供精确的代码结构上下文，而非完整文件内容。

支持语言: Python, JavaScript, TypeScript, Go, Java
"""
import logging
import re
from pathlib import Path

logger = logging.getLogger("codemind.ast")

# tree-sitter 语言映射
LANGUAGE_MAP = {
    ".py": ("python", "tree_sitter_python"),
    ".js": ("javascript", "tree_sitter_javascript"),
    ".jsx": ("javascript", "tree_sitter_javascript"),
    ".ts": ("typescript", "tree_sitter_typescript"),
    ".tsx": ("typescript", "tree_sitter_typescript"),
    ".go": ("go", "tree_sitter_go"),
    ".java": ("java", "tree_sitter_java"),
}

def _detect_language(filename: str) -> tuple[str, str] | None:
    """检测文件语言和对应的 tree-sitter 模块名"""
    ext = Path(filename).suffix.lower()
    return LANGUAGE_MAP.get(ext)


def _get_parser(language: str, module_name: str):
    """获取对应语言的 tree-sitter parser"""
    try:
        import tree_sitter
        import importlib
        
        lang_module = importlib.import_module(module_name)
        lang = tree_sitter.Language(lang_module.language())
        parser = tree_sitter.Parser(lang)
        return parser, lang
    except ImportError as e:
        logger.warning(f"tree-sitter language module '{module_name}' not available: {e}")
        return None, None
    except Exception as e:
        logger.warning(f"Failed to initialize tree-sitter for {language}: {e}")
        return None, None


def extract_signatures_from_source(source_code: str, filename: str) -> str:
    """
    使用 tree-sitter 解析源代码 AST，提取函数/类签名。
    
    Args:
        source_code: 源文件内容
        filename: 文件名（用于语言检测）
        
    Returns:
        结构化的签名列表文本，或空字符串
    """
    lang_info = _detect_language(filename)
    if not lang_info:
        return _fallback_extract(source_code, filename)
    
    language, module_name = lang_info
    parser, lang = _get_parser(language, module_name)
    
    if parser is None:
        return _fallback_extract(source_code, filename)
    
    try:
        tree = parser.parse(bytes(source_code, "utf-8"))
        return _extract_from_tree(tree, source_code, language, filename)
    except Exception as e:
        logger.warning(f"AST parsing failed for {filename}: {e}")
        return _fallback_extract(source_code, filename)


def _extract_from_tree(tree, source_code: str, language: str, filename: str) -> str:
    """从 AST 树中提取签名信息"""
    lines = source_code.split("\n")
    signatures = []
    root = tree.root_node
    
    # 递归遍历 AST 节点
    _walk_node(root, lines, language, signatures, depth=0)
    
    if not signatures:
        return ""
    
    result = f"### File: `{filename}` ({language})\n"
    result += "\n".join(signatures)
    return result


def _walk_node(node, lines: list[str], language: str, signatures: list[str], depth: int):
    """递归遍历 AST 节点，提取函数和类定义"""
    node_type = node.type
    
    # Python
    if language == "python":
        if node_type == "function_definition":
            sig = _extract_line_text(lines, node.start_point[0])
            signatures.append(f"  - Function (L{node.start_point[0]+1}): `{sig.strip()}`")
        elif node_type == "class_definition":
            sig = _extract_line_text(lines, node.start_point[0])
            signatures.append(f"  - Class (L{node.start_point[0]+1}): `{sig.strip()}`")
    
    # JavaScript / TypeScript
    elif language in ("javascript", "typescript"):
        if node_type in ("function_declaration", "function"):
            sig = _extract_line_text(lines, node.start_point[0])
            signatures.append(f"  - Function (L{node.start_point[0]+1}): `{sig.strip()}`")
        elif node_type == "class_declaration":
            sig = _extract_line_text(lines, node.start_point[0])
            signatures.append(f"  - Class (L{node.start_point[0]+1}): `{sig.strip()}`")
        elif node_type == "method_definition":
            sig = _extract_line_text(lines, node.start_point[0])
            signatures.append(f"  - Method (L{node.start_point[0]+1}): `{sig.strip()}`")
    
    # Go
    elif language == "go":
        if node_type == "function_declaration":
            sig = _extract_line_text(lines, node.start_point[0])
            signatures.append(f"  - Function (L{node.start_point[0]+1}): `{sig.strip()}`")
        elif node_type == "method_declaration":
            sig = _extract_line_text(lines, node.start_point[0])
            signatures.append(f"  - Method (L{node.start_point[0]+1}): `{sig.strip()}`")
        elif node_type == "type_declaration":
            sig = _extract_line_text(lines, node.start_point[0])
            signatures.append(f"  - Type (L{node.start_point[0]+1}): `{sig.strip()}`")
    
    # Java
    elif language == "java":
        if node_type == "method_declaration":
            sig = _extract_line_text(lines, node.start_point[0])
            signatures.append(f"  - Method (L{node.start_point[0]+1}): `{sig.strip()}`")
        elif node_type == "class_declaration":
            sig = _extract_line_text(lines, node.start_point[0])
            signatures.append(f"  - Class (L{node.start_point[0]+1}): `{sig.strip()}`")
        elif node_type == "constructor_declaration":
            sig = _extract_line_text(lines, node.start_point[0])
            signatures.append(f"  - Constructor (L{node.start_point[0]+1}): `{sig.strip()}`")
    
    # 递归子节点
    for child in node.children:
        _walk_node(child, lines, language, signatures, depth + 1)


def _extract_line_text(lines: list[str], line_idx: int) -> str:
    """提取指定行的文本，截断过长内容"""
    if 0 <= line_idx < len(lines):
        text = lines[line_idx]
        # 截断过长的行（只保留签名部分）
        if len(text) > 200:
            text = text[:200] + "..."
        return text
    return ""


def _fallback_extract(source_code: str, filename: str) -> str:
    """
    正则回退方案：当 tree-sitter 不可用时，
    通过正则从源代码中提取函数/类定义。
    """
    signatures = []
    lines = source_code.split("\n")
    
    patterns = [
        # Python
        (r'^\s*(async\s+)?def\s+\w+\s*\(', "Function"),
        (r'^\s*class\s+\w+', "Class"),
        # JavaScript/TypeScript
        (r'^\s*(export\s+)?(async\s+)?function\s+\w+\s*\(', "Function"),
        (r'^\s*(export\s+)?class\s+\w+', "Class"),
        (r'^\s*(export\s+)?(const|let|var)\s+\w+\s*=\s*(async\s+)?\(.*\)\s*=>', "Arrow Function"),
        # Go
        (r'^\s*func\s+(\(\w+\s+\*?\w+\)\s+)?\w+\s*\(', "Function"),
        (r'^\s*type\s+\w+\s+struct\s*\{', "Struct"),
        # Java
        (r'^\s*(public|private|protected)\s+(static\s+)?\w+\s+\w+\s*\(', "Method"),
        (r'^\s*(public|private|protected)?\s*class\s+\w+', "Class"),
    ]
    
    for i, line in enumerate(lines):
        for pattern, kind in patterns:
            if re.match(pattern, line):
                clean_line = line.strip()
                if len(clean_line) > 200:
                    clean_line = clean_line[:200] + "..."
                signatures.append(f"  - {kind} (L{i+1}): `{clean_line}`")
                break
    
    if not signatures:
        return ""
    
    result = f"### File: `{filename}` (regex fallback)\n"
    result += "\n".join(signatures)
    return result


def extract_changed_signatures_from_diff(diff: str, file_contents: dict[str, str]) -> str:
    """
    结合 Diff 和文件内容，提取变更涉及的函数/类签名。
    
    Args:
        diff: process_pr_files 处理后的 Diff 文本
        file_contents: 文件路径 -> 文件内容 的映射
        
    Returns:
        所有变更文件的签名汇总
    """
    all_signatures = []
    
    for filepath, content in file_contents.items():
        sigs = extract_signatures_from_source(content, filepath)
        if sigs:
            all_signatures.append(sigs)
    
    if not all_signatures:
        # 如果 AST 解析全部失败，返回简单的 diff 摘要
        return _extract_signatures_from_diff_text(diff)
    
    return "\n\n".join(all_signatures)


def _extract_signatures_from_diff_text(diff: str) -> str:
    """
    从 diff 文本本身提取新增的函数/类定义（最终回退方案）。
    只提取以 + 开头的行中的定义。
    """
    signatures = []
    patterns = [
        (r'^\+\s*(async\s+)?def\s+\w+\s*\(', "Function"),
        (r'^\+\s*class\s+\w+', "Class"),
        (r'^\+\s*(export\s+)?(async\s+)?function\s+\w+\s*\(', "Function"),
        (r'^\+\s*(export\s+)?class\s+\w+', "Class"),
        (r'^\+\s*func\s+', "Function"),
    ]
    
    for line in diff.split("\n"):
        for pattern, kind in patterns:
            if re.match(pattern, line):
                clean = line.lstrip("+").strip()
                if len(clean) > 200:
                    clean = clean[:200] + "..."
                signatures.append(f"  - {kind}: `{clean}`")
                break
    
    if not signatures:
        return "No identifiable function/class signatures found in the diff."
    
    return "### Changed Signatures (from diff)\n" + "\n".join(signatures)
