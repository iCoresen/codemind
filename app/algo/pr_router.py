import logging

logger = logging.getLogger("codemind.router")

def determine_review_level(pr_files: list[dict], default_level: int, core_keywords: list[str]) -> int:
    """
    根据文件类型和行数，动态决定要运行的 Agent 级别：
    - 级别 1 (Level 1): 仅 Changelog
    - 级别 2 (Level 2): 快速通道 (单文件/少量行数，目前映射为 Changelog + Logic)
    - 级别 3 (Level 3): Changelog + Logic + UnitTest
    """
    docs_extensions = {".md", ".json", ".css", ".txt", ".yaml", ".yml", ".ini", ".conf", ".toml"}
    
    only_docs = True
    added_lines = 0
    deleted_lines = 0
    touches_core = False
    
    for file in pr_files:
        filename = file.get("filename", "")
        patch = file.get("patch", "")
        status = file.get("status", "modified")
        additions = file.get("additions", 0)
        deletions = file.get("deletions", 0)
        
        # Check if non-doc file
        ext_matched = any(filename.endswith(ext) for ext in docs_extensions)
        if not ext_matched and status != "removed":
            only_docs = False
            
        added_lines += additions
        deleted_lines += deletions
        
        # Check core keywords in path or patch
        file_content_to_check = (filename + "\n" + patch).lower()
        if any(kw.lower() in file_content_to_check for kw in core_keywords):
            touches_core = True

    total_changes = added_lines + deleted_lines
    logger.info(f"PR Router metrics: only_docs={only_docs}, total_changes={total_changes}, touches_core={touches_core}")

    if only_docs:
        logger.info("Docs only PR, returning Level 1.")
        return 1
        
    if touches_core:
        logger.info("Core keywords matched, forcing Deep Review (Level 3).")
        return 3
        
    if total_changes < 50:
        logger.info("Small PR (<50 lines), returning Level 2.")
        return 2
        
    return default_level

