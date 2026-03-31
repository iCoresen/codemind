import re

def is_generated_or_ignored_file(filename: str) -> bool:
    ignored_extensions = {
        ".svg", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".tar", ".gz",
        ".lock", ".min.js", ".min.css", "package-lock.json", "poetry.lock", "yarn.lock",
        "pnpm-lock.yaml", "Gemfile.lock", ".pyc"
    }
    ignored_directories = {"vendor/", "node_modules/", "dist/", "build/", ".git/", "__pycache__/"}
    
    if any(filename.endswith(ext) for ext in ignored_extensions):
        return True
    
    if any(dir_name in filename for dir_name in ignored_directories):
        return True

    return False

def clip_patch_to_hunks(patch: str, max_chars: int = 15000) -> str:
    """Soft truncate a patch but only at hunk boundaries to maintain diff structure."""
    if len(patch) <= max_chars:
        return patch
        
    # Split by hunk delimiter, standard diff hunk start like "@@ -1,4 +1,5 @@"
    hunks = re.split(r'(?=\n@@ )', "\n" + patch)
    
    if hunks and not hunks[0].strip():
        hunks = hunks[1:]
        
    clipped_patch = ""
    for hunk in hunks:
        if len(clipped_patch) + len(hunk) > max_chars and clipped_patch:
            # Reached limit and we already have at least one hunk
            clipped_patch += "\n\n... [Patch truncated due to file size to prevent context loss]"
            break
        clipped_patch += hunk
        
    if not clipped_patch.strip():
        # Even the first hunk was too big, fallback to soft truncate by latest line
        last_newline = patch.rfind('\n', 0, max_chars)
        if last_newline != -1:
            clipped_patch = patch[:last_newline]
        else:
            clipped_patch = patch[:max_chars]
        clipped_patch += "\n\n... [Patch truncated due to file size to prevent context loss]"
        
    return clipped_patch.lstrip("\n")


def process_pr_files(files: list[dict], max_total_chars: int = 40000) -> str:
    """
    Format PR files into a readable diff format, filtering out unnecessary files
    and preventing semantic truncation in the middle of a hunk.
    """
    formatted_diffs = []
    
    deleted_files = []
    skipped_files = []
    
    current_total_chars = 0
    
    for file in files:
        filename = file.get("filename", "")
        
        # Filter files that won't help the AI understand logic changes
        if is_generated_or_ignored_file(filename):
            continue
            
        status = file.get("status", "modified")
        if status == "removed":
            deleted_files.append(filename)
            continue
            
        patch = file.get("patch")
        
        if not patch:
            # Maybe binary or renamed
            patch = "No diff available (or binary/renamed file)."
            
        # Protect against single extremely large file diffs breaking context
        clipped_patch = clip_patch_to_hunks(patch, max_chars=15000)
        
        file_diff = f"## File: {filename} ({status})\n```diff\n{clipped_patch}\n```"
        
        if current_total_chars + len(file_diff) > max_total_chars:
            skipped_files.append(filename)
            continue
            
        formatted_diffs.append(file_diff)
        current_total_chars += len(file_diff)
        
    # Append summaries for files we missed
    if skipped_files:
        formatted_diffs.append(f"## 额外的已修改文件 (因超出长度限制未提供内容):\n" + "\n".join([f"- {f}" for f in skipped_files]))
        
    if deleted_files:
        formatted_diffs.append(f"## 已删除文件:\n" + "\n".join([f"- {f}" for f in deleted_files]))
        
    return "\n\n".join(formatted_diffs)
