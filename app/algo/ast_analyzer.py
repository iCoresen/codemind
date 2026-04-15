"""
AST 解析器 - 使用 tree-sitter 进行代码结构提取

从 Diff 涉及的源文件中提取函数/类签名，为 UnitTest Agent
提供精确的代码结构上下文，而非完整文件内容。

支持语言: Python, JavaScript, TypeScript, Go, Java

═══════════════════════════════════════════════════════════════════════════════
                              整体架构图
═══════════════════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────────────┐
│                           调用入口分层                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ extract_signatures_from_source()                                 │    │
│  │                                                                 │    │
│  │   用途: 从完整源码中提取所有函数/类签名                            │    │
│  │   策略: tree-sitter → 正则回退                                   │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ extract_changed_signatures_from_diff()                           │    │
│  │                                                                 │    │
│  │   用途: 基于变更精准提取相关代码片段                               │    │
│  │   策略: 语义化切片（Python AST）→ 正则回退                        │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                         三层降级策略（容错设计）                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  第1层: tree-sitter 解析（精准 AST）                                    │
│         │ 失败                                                         │
│         ▼                                                              │
│  第2层: 正则回退（快速匹配）                                             │
│         │ 失败                                                         │
│         ▼                                                              │
│  第3层: Diff 文本回退（最终保底）                                        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════════
"""
import logging
import re
import ast
from pathlib import Path

logger = logging.getLogger("codemind.ast")


# ════════════════════════════════════════════════════════════════════════════
# 第一节：配置区 - 语言映射表
# ════════════════════════════════════════════════════════════════════════════
#
# 语言映射表定义了文件扩展名与 tree-sitter 语言模块的对应关系。
#
# 映射结构 (ext → (language_id, module_name)):
#   - ext: 文件扩展名（小写，用于匹配）
#   - language_id: tree-sitter 语言标识符，用于初始化 Parser
#   - module_name: Python 模块名，用于 importlib 动态导入
#
# 支持的语言:
#   ┌────────┬───────────────────┬─────────────────────────┐
#   │  扩展名 │  语言标识符         │  tree-sitter 模块        │
#   ├────────┼───────────────────┼─────────────────────────┤
#   │  .py   │  python            │  tree_sitter_python     │
#   │  .js   │  javascript        │  tree_sitter_javascript │
#   │  .jsx  │  javascript        │  tree_sitter_javascript │
#   │  .ts   │  typescript        │  tree_sitter_typescript │
#   │  .tsx  │  typescript        │  tree_sitter_typescript │
#   │  .go   │  go                │  tree_sitter_go         │
#   │  .java │  java              │  tree_sitter_java       │
#   └────────┴───────────────────┴─────────────────────────┘

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
    """
    根据文件名检测语言类型。
    
    Args:
        filename: 源文件名（如 "foo.py", "bar.js"）
        
    Returns:
        - 成功: (语言标识符, 模块名) 元组，如 ("python", "tree_sitter_python")
        - 失败: None（不支持的语言）
        
    示例:
        >>> _detect_language("test.py")
        ('python', 'tree_sitter_python')
        >>> _detect_language("test.txt")
        None
    """
    ext = Path(filename).suffix.lower()
    return LANGUAGE_MAP.get(ext)


def _get_parser(language: str, module_name: str):
    """
    动态加载并初始化指定语言的 tree-sitter Parser。
    
    工作原理:
    1. 使用 importlib 动态导入 tree_sitter_xxx 模块
    2. 从模块中获取 language 对象（tree-sitter 预编译的语法定义）
    3. 创建并返回 Parser 实例
    
    异常处理策略:
    - ImportError: 语言包未安装，返回 (None, None) 实现优雅降级
    - 其他异常: 初始化失败，同样返回 (None, None)
    
    Args:
        language: 语言标识符（如 "python"）
        module_name: Python 模块名（如 "tree_sitter_python"）
        
    Returns:
        - 成功: (parser, lang) 元组
        - 失败: (None, None)
    """
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
    """
    递归遍历 AST 节点，提取函数和类定义。
    
    这是一个深度优先遍历（DFS）的实现。通过识别不同语言的 AST 节点类型，
    提取对应的定义信息。
    
    节点类型映射表:
    
    ┌───────────────┬──────────────────────────────────────────────────────────┐
    │ 语言           │ 识别的节点类型                                               │
    ├───────────────┼──────────────────────────────────────────────────────────┤
    │ python         │ function_definition, class_definition                      │
    │ javascript     │ function_declaration, function, class_declaration,          │
    │                │ method_definition                                         │
    │ go             │ function_declaration, method_declaration,                  │
    │                │ type_declaration                                          │
    │ java           │ method_declaration, class_declaration,                     │
    │                │ constructor_declaration                                   │
    └───────────────┴──────────────────────────────────────────────────────────┘
    
    Args:
        node: 当前遍历的 AST 节点
        lines: 源代码行列表（索引=行号-1）
        language: 语言标识符
        signatures: 签名收集列表（in-place 修改）
        depth: 当前递归深度（用于调试/日志）
    """
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
    基于变更依赖图（Change-Dependency Graph）的精准组装入口。
    
    这是本文件的核心功能之一，实现"精准代码切片"。
    
    语义切片的核心思想:
    ┌─────────────────────────────────────────────────────────────────────────┐
    │                                                                         │
    │   Target Node (被修改的函数)         Dependency Signature (依赖签名)     │
    │         │                                    │                          │
    │         │         calls                       │                          │
    │         ◀─────────────────────────────────────┘                          │
    │                                                                         │
    │   提取: 完整方法体                     提取: 仅签名（不含函数体）         │
    │                                                                         │
    └─────────────────────────────────────────────────────────────────────────┘
    
    Args:
        diff: process_pr_files 处理后的 Diff 文本
        file_contents: 文件路径 -> 文件内容 的映射
        
    Returns:
        所有变更文件的语义化片段汇总（包含目标方法体及依赖签名，剔除噪音）
    """
    
    all_context = []
    
    # 遍历每个文件的源码，调用语义化切片核心逻辑
    for filepath, content in file_contents.items():
        slice_result = _semantic_slice_extract(content, filepath, diff)
        if slice_result:
            all_context.append(slice_result)
    
    # 如果所有解析都失败，返回最简单的 diff 摘要
    if not all_context:
        return _extract_signatures_from_diff_text(diff)
    
    return "\n\n".join(all_context)

def _parse_diff_added_lines(diff: str, target_filename: str) -> set[int]:
    """
    从 unified diff 格式中提取特定文件新增或修改的行号集合。
    
    Diff 格式示例:
        --- a/foo.py              ← 旧文件
        +++ b/foo.py              ← 新文件
        @@ -10,5 +10,7 @@       ← 行号范围标记
        -old line                 ← 删除的行
        +new line                 ← 新增的行
         unchanged                ← 上下文行
    
    解析规则:
    1. "+++ b/path" → 记录当前处理的文件
    2. "@@ +N, M @@" → 提取新文件起始行号 N
    3. 以 "+" 开头的行（非 "+++"）→ 该行被新增/修改，计入 added_lines
    4. "-" 开头的行（非 "---"）→ 不计入（行号计算基于新文件）
    5. 其他行 → 行号递增
    
    Args:
        diff: 完整的 unified diff 文本
        target_filename: 目标文件名（用于过滤，只处理目标文件的变更）
        
    Returns:
        新增/修改的行号集合（1-based，即从 1 开始计数）
    """
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
    语义化提取的路由函数。
    
    根据文件类型选择合适的提取策略：
    - Python: 使用 Python 内置 ast 模块（精准）
    - 其他: 使用正则回退方案
    
    Args:
        source_code: 源文件内容
        filename: 文件名
        diff: Diff 文本
        
    Returns:
        语义化切片结果，或空字符串
    """
    if filename.endswith(".py"):
        return _semantic_slice_extract_python(source_code, filename, diff)
    else:
        return _semantic_slice_extract_fallback(source_code, filename, diff)

def _semantic_slice_extract_python(source_code: str, filename: str, diff: str) -> str:
    """
    Python 文件的语义化切片核心实现。
    
    使用 Python 内置 ast 模块实现"Change-Dependency Graph"（变更依赖图）。
    
    ══════════════════════════════════════════════════════════════════════════
    Change-Dependency Graph 详解
    ══════════════════════════════════════════════════════════════════════════
    
    核心问题: Diff 可能只修改了一个函数的某几行，如何知道:
    - 哪个函数被修改了？（Target Node）
    - 这个函数依赖哪些其他函数？（Dependency）
    
    解决方案: 两轮 AST 遍历
    
    ┌────────────────────────────────────────────────────────────────────────┐
    │ 第一轮: 寻找 Target Nodes（被修改的函数）                              │
    │                                                                        │
    │  1. _parse_diff_added_lines() 从 Diff 提取"+"的行号                   │
    │  2. ast.parse() 解析源码成 AST                                         │
    │  3. ast.walk() 遍历所有函数定义节点                                    │
    │  4. 检查函数行范围是否与 added_lines 重叠                              │
    │  5. 如果重叠 → 标记为 Target Node，提取完整方法体                       │
    │  6. 遍历该函数内部的 ast.Call 节点，收集被调用函数名                    │
    └────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
    ┌────────────────────────────────────────────────────────────────────────┐
    │ 第二轮: 寻找 Dependency Signatures（被调用的函数签名）                  │
    │                                                                        │
    │  1. 遍历所有函数/类定义节点                                             │
    │  2. 检查函数名是否在 target_deps 集合中                                │
    │  3. 确认该函数没有被修改（不在 added_lines 中）                         │
    │  4. 提取多行签名（从 def 行到函数体第一行之间）                         │
    └────────────────────────────────────────────────────────────────────────┘
    
    Args:
        source_code: Python 源文件内容
        filename: 文件名
        diff: Diff 文本
        
    Returns:
        Markdown 格式的语义化切片结果
    """
    
    # ─────────────────────────────────────────────────────────────────────────
    # 预处理：解析 Diff 获取新增行号
    # ─────────────────────────────────────────────────────────────────────────
    added_lines = _parse_diff_added_lines(diff, filename)
    if not added_lines:
        return ""
    
    # 解析源码为 AST
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return ""
        
    source_lines = source_code.split("\n")
    target_nodes_code = []      # 存储 Target Node 的完整方法体
    target_deps = set()         # 存储被调用的函数名集合
    
    # ══════════════════════════════════════════════════════════════════════════
    # 辅助函数：获取包含装饰器的真实起始行
    # ══════════════════════════════════════════════════════════════════════════
    #
    # Python 中函数定义可能有多行签名和装饰器：
    #
    #   @decorator1
    #   @decorator2
    #   async def foo(              ← 函数定义行的 lineno 指向这里
    #       param1: int,             ← 但装饰器在更前面
    #       param2: str
    #   ) -> None:
    #
    # 如果直接用 node.lineno，会丢失装饰器。
    # 所以需要检查 decorator_list，使用最前面的装饰器行号。
    
    def _get_true_start_line(node):
        if getattr(node, 'decorator_list', None):
            return node.decorator_list[0].lineno
        return getattr(node, 'lineno', -1)

    # ══════════════════════════════════════════════════════════════════════════
    # 第一轮遍历：寻找 Target Nodes（被修改的函数）
    # ══════════════════════════════════════════════════════════════════════════
    #
    # 策略：只关注函数/方法，忽略大类整体变更，防止 Context 爆炸
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = _get_true_start_line(node)
            end = getattr(node, "end_lineno", -1)
            
            if start != -1 and end != -1 and any(start <= ln <= end for ln in added_lines):
                # 完美提取：包含装饰器、多行签名和完整方法体 (需 Python 3.8+)
                body_text = ast.get_source_segment(source_code, node)
                if not body_text:
                    continue
                
                # 添加到 Target Nodes 列表
                target_nodes_code.append(
                    f"  - [Target Node Body] {node.__class__.__name__} `{node.name}`:\n```python\n{body_text}\n```"
                )
                
                # 收集依赖：从该函数内部遍历所有 Call 节点
                # 区分简单调用 foo() 和方法调用 obj.bar()
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        if isinstance(child.func, ast.Name):
                            target_deps.add(child.func.id)        # foo()
                        elif isinstance(child.func, ast.Attribute):
                            target_deps.add(child.func.attr)       # obj.bar()

    # ══════════════════════════════════════════════════════════════════════════
    # 第二轮遍历：提取 Dependency Signatures（被调用的函数签名）
    # ══════════════════════════════════════════════════════════════════════════
    #
    # 目的：提取被 Target 调用但自身没有被修改的函数签名
    # 这样做是为了让 LLM 理解 Target 函数需要调用哪些其他函数
    
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
                    
                    # 清理末尾冒号（多行签名的情况下可能有多个冒号）
                    if sig_text.endswith(":"):
                        sig_text = sig_text[:-1].strip()
                    
                    # 截断保护，避免输出过长
                    if len(sig_text) > 300:
                        sig_text = sig_text[:300] + "\n    ...[Truncated]"
                        
                    dependency_signatures.append(f"  - [Dependency Signature] `{node.name}`:\n```python\n{sig_text}\n```")
                    
                    # 从集合中移除，避免重复处理
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
