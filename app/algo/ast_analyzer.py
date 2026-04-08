"""
AST 解析器 - 使用 tree-sitter 进行代码结构提取

从 Diff 涉及的源文件中提取函数/类签名，为 UnitTest Agent
提供精确的代码结构上下文，而非完整文件内容。

支持语言: Python, JavaScript, TypeScript, Go, Java
"""
import logging
import re
import ast
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
    基于变更依赖图（Change-Dependency Graph）的精准组装
    
    Args:
        diff: process_pr_files 处理后的 Diff 文本
        file_contents: 文件路径 -> 文件内容 的映射
        
    Returns:
        所有变更文件的语义化片段汇总（包含目标方法体及依赖签名，剔除噪音）
    """
    # 这里模拟了语义化提取：
    # 1. 从 diff 提取被修改的函数（确认为 Target Nodes）
    # 2. 提取 Target Nodes 的完整方法体
    # 3. 提取它们调用的依赖函数，只保留签名
    # 为了简化，这段代码结合 diff 和 source code 做精确抽取
    
    all_context = []
    
    for filepath, content in file_contents.items():
        # 1 & 2. 真实实现应该是解析 Diff 行号，然后与 AST 节点交叉比对
        # 提取目标函数体及上下文。目前由 _semantic_slice_extract 进行包裹
        slice_result = _semantic_slice_extract(content, filepath, diff)
        if slice_result:
            all_context.append(slice_result)
    
    if not all_context:
        # 如果解析全部失败，返回简单的 diff 摘要
        return _extract_signatures_from_diff_text(diff)
    
    return "\n\n".join(all_context)

def _parse_diff_added_lines(diff: str, target_filename: str) -> set[int]:
    """从 diff 中提取特定文件新增或修改的行号"""
    added_lines = set()
    current_file = None
    current_line_num = 0
    
    for line in diff.split("\n"):
        if line.startswith("+++ b/"):
            current_file = line[6:]
        elif line.startswith("@@"):
            m = re.search(r'\+([0-9]+)(?:,[0-9]+)?', line)
            if m:
                current_line_num = int(m.group(1))
        elif line.startswith("+") and not line.startswith("+++"):
            if current_file == target_filename:
                added_lines.add(current_line_num)
            current_line_num += 1
        elif line.startswith("-") and not line.startswith("---"):
            pass
        else:
            if current_file == target_filename and current_line_num > 0:
                current_line_num += 1
    return added_lines

def _semantic_slice_extract(source_code: str, filename: str, diff: str) -> str:
    """
    语义化提取核心逻辑：
    1. Python 文件使用 AST 工具精准判断修改所在节点
    2. 其他文件暂时回退到简易正则实现
    """
    if filename.endswith(".py"):
        return _semantic_slice_extract_python(source_code, filename, diff)
    else:
        return _semantic_slice_extract_fallback(source_code, filename, diff)

import ast

def _semantic_slice_extract_python(source_code: str, filename: str, diff: str) -> str:
    added_lines = _parse_diff_added_lines(diff, filename)
    if not added_lines:
        return ""
    
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return ""
        
    source_lines = source_code.split("\n")
    target_nodes_code = []
    target_deps = set()
    
    # 核心辅助函数：获取包含装饰器的真实起始行
    def _get_true_start_line(node):
        if getattr(node, 'decorator_list', None):
            return node.decorator_list[0].lineno
        return getattr(node, 'lineno', -1)

    # 第一次遍历：寻找精确的 Target Nodes（使用 ast.walk 支持嵌套内部类/方法）
    # 策略：只关注函数/方法，忽略大类的整体变更，防止 Context 爆炸
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = _get_true_start_line(node)
            end = getattr(node, "end_lineno", -1)
            
            if start != -1 and end != -1 and any(start <= ln <= end for ln in added_lines):
                # 完美提取：包含装饰器、多行签名和完整方法体 (需 Python 3.8+)
                body_text = ast.get_source_segment(source_code, node)
                if not body_text:
                    continue
                
                target_nodes_code.append(
                    f"  - [Target Node Body] {node.__class__.__name__} `{node.name}`:\n```python\n{body_text}\n```"
                )
                
                # 收集依赖：遍历该函数内部的所有调用
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        if isinstance(child.func, ast.Name):
                            target_deps.add(child.func.id)
                        elif isinstance(child.func, ast.Attribute):
                            target_deps.add(child.func.attr)

    # 第二次遍历：提取未被修改、但被 Target 调用的函数签名
    dependency_signatures = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in target_deps:
                start = _get_true_start_line(node)
                end = getattr(node, "end_lineno", -1)
                
                # 确保它不是 Target Node（没有被修改）
                if start != -1 and not any(start <= ln <= end for ln in added_lines):
                    # 完美提取多行签名：截取从 start 到 函数体内第一行代码 之间的部分
                    body_start = node.body[0].lineno
                    sig_lines = source_lines[start - 1 : body_start - 1]
                    sig_text = "\n".join(sig_lines).strip()
                    
                    # 清理末尾冒号并做适度截断保护
                    if sig_text.endswith(":"):
                        sig_text = sig_text[:-1].strip()
                    if len(sig_text) > 300:
                        sig_text = sig_text[:300] + "\n    ...[Truncated]"
                        
                    dependency_signatures.append(f"  - [Dependency Signature] `{node.name}`:\n```python\n{sig_text}\n```")
                    
                    # 避免类名或函数名重复添加
                    target_deps.remove(node.name) 

    if not target_nodes_code and not dependency_signatures:
        return ""
        
    result = f"### File: `{filename}` (Semantic Slicing via PyAST)\n"
    if target_nodes_code:
        result += "#### Target Nodes (Full Body)\n" + "\n".join(target_nodes_code) + "\n"
    if dependency_signatures:
        result += "#### Dependency Signatures\n" + "\n".join(dependency_signatures) + "\n"
        
    return result

def _semantic_slice_extract_fallback(source_code: str, filename: str, diff: str) -> str:
    """
    语义化提取核心逻辑：提取 Target Nodes 的完整方法体，以及同文件其它方法的签名（依赖签名）
    """
    signatures = []
    target_nodes = []
    lines = source_code.split("\n")
    
    # 简化的正则提取，区分完整体和签名
    patterns = [
        (r'^\s*(async\s+)?def\s+\w+\s*\(', "Function"),
        (r'^\s*class\s+\w+', "Class"),
    ]
    
    current_node = None
    node_body = []
    
    for i, line in enumerate(lines):
        is_def = False
        for pattern, kind in patterns:
            if re.match(pattern, line):
                # Save previous node
                if current_node:
                    # 判断此 node 是否在 diff 中变动（这里做了简单的字符串包含判断）
                    if any(b.strip() and b.strip() in diff for b in node_body):
                        target_nodes.append(f"  - [Target Node Body] {current_node['kind']}:\n    " + "\n    ".join(node_body))
                    else:
                        clean_line = current_node['sig'].strip()
                        if len(clean_line) > 200:
                            clean_line = clean_line[:200] + "..."
                        signatures.append(f"  - [Dependency Signature] {current_node['kind']}: `{clean_line}`")
                
                current_node = {'kind': kind, 'sig': line}
                node_body = [line]
                is_def = True
                break
        
        if not is_def and current_node:
            node_body.append(line)
            
    # Handle the last node
    if current_node:
        if any(b.strip() and b.strip() in diff for b in node_body):
            target_nodes.append(f"  - [Target Node Body] {current_node['kind']}:\n    " + "\n    ".join(node_body))
        else:
            clean_line = current_node['sig'].strip()
            if len(clean_line) > 200:
                clean_line = clean_line[:200] + "..."
            signatures.append(f"  - [Dependency Signature] {current_node['kind']}: `{clean_line}`")
            
    if not signatures and not target_nodes:
        return ""
        
    result = f"### File: `{filename}` (Semantic Slicing)\n"
    if target_nodes:
        result += "#### Target Nodes (Full Body)\n" + "\n".join(target_nodes) + "\n"
    if signatures:
        result += "#### Dependency Signatures\n" + "\n".join(signatures)
        
    return result


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
