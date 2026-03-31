from app.algo.pr_processing import process_pr_files, clip_patch_to_hunks

def test_clip_patch_to_hunks():
    patch = "@@ -1,4 +1,5 @@\n- old\n+ new\n@@ -20,3 +21,3 @@\n- foo\n+ bar"
    # Should fit both
    assert "foo" in clip_patch_to_hunks(patch, max_chars=100)
    # Should clip after first hunk
    clipped = clip_patch_to_hunks(patch, max_chars=40)
    assert "old" in clipped
    assert "foo" not in clipped

def test_process_pr_files():
    files = [
        {"filename": "test.txt", "status": "modified", "patch": "@@ -1,4 +1,5 @@\n- old\n+ new"},
        {"filename": "deleted.py", "status": "removed", "patch": "- something"},
        {"filename": "large.py", "status": "modified", "patch": "@@ -1 +1 @@\n" + "x" * 50000},
        {"filename": "skipped.py", "status": "modified", "patch": "@@ -1 +1 @@\n" + "x" * 500},
    ]
    # max_total_chars low enough so skipped.py and large.py gets skipped
    result = process_pr_files(files, max_total_chars=150)
    
    assert "test.txt" in result
    assert "deleted.py" in result
    assert "已删除文件" in result
    assert "额外的已修改文件" in result
    assert "skipped.py" in result
    assert "large.py" in result
