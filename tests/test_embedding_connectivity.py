"""简单的 Embedding 模型连通性测试"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import Settings
from app.ai_handlers.litellm_ai_handler import LiteLLMAIHandler

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "openai/BAAI/bge-m3")
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", "")
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "")


async def test_connectivity():
    settings = Settings(
        github_token=os.getenv("GITHUB_TOKEN", ""),
        ai_api_key="",
        ai_base_url="",
        ai_model="",
        ai_embedding_model=EMBEDDING_MODEL,
        ai_embedding_api_key=EMBEDDING_API_KEY,
        ai_embedding_base_url=EMBEDDING_BASE_URL,
        ai_fallback_models="",
        ai_timeout=60,
        github_webhook_secret="",
        server_host="0.0.0.0",
        server_port=8080,
        log_level="INFO",
        redis_url="redis://localhost:6379/0",
        changelog_soft_timeout=5.0,
        changelog_hard_timeout=10.0,
        logic_soft_timeout=45.0,
        logic_hard_timeout=90.0,
        unittest_soft_timeout=45.0,
        unittest_hard_timeout=90.0,
        default_review_level=3,
        core_keywords=["auth", "payment", "database"],
    )

    handler = LiteLLMAIHandler(settings)

    print(f"Testing embedding with model: {EMBEDDING_MODEL}")
    print(f"API Key: {'*' * 20}{EMBEDDING_API_KEY[-10:] if EMBEDDING_API_KEY else 'NOT SET'}")
    print(f"Base URL: {EMBEDDING_BASE_URL}")

    try:
        result = await handler.async_embedding(
            texts=["Hello world"],
            api_key=EMBEDDING_API_KEY,
            base_url=EMBEDDING_BASE_URL,
        )
        print(f"✓ Success! Embedding dimension: {len(result[0])}")
        print(f"First 5 values: {result[0][:5]}")
    except Exception as e:
        print(f"✗ Failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(test_connectivity())
