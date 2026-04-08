import pytest
from app.algo.pr_router import determine_review_level

def test_docs_only_pr():
    pr_files = [
        {"filename": "README.md", "status": "modified", "additions": 10, "deletions": 5},
        {"filename": "config.json", "status": "added", "additions": 20, "deletions": 0}
    ]
    core_keywords = ["auth", "payment", "database"]
    
    level = determine_review_level(pr_files, default_level=3, core_keywords=core_keywords)
    assert level == 1

def test_core_keywords_pr():
    pr_files = [
        {"filename": "src/payment_gateway.py", "status": "modified", "patch": "import payment\ndef pay():\n  pass", "additions": 5, "deletions": 1}
    ]
    core_keywords = ["auth", "payment", "database"]
    
    level = determine_review_level(pr_files, default_level=2, core_keywords=core_keywords)
    assert level == 3

def test_small_pr():
    pr_files = [
        {"filename": "src/utils.py", "status": "modified", "patch": "def hello():\n  return 'world'", "additions": 10, "deletions": 10}
    ]
    core_keywords = ["auth", "payment", "database"]
    
    level = determine_review_level(pr_files, default_level=3, core_keywords=core_keywords)
    assert level == 2

def test_large_pr():
    pr_files = [
        {"filename": "src/major_refactor.py", "status": "modified", "patch": "def new_feature():\n  pass", "additions": 60, "deletions": 10}
    ]
    core_keywords = ["auth", "payment", "database"]
    
    level = determine_review_level(pr_files, default_level=3, core_keywords=core_keywords)
    assert level == 3
