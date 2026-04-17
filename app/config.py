import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    github_webhook_secret: str
    github_token: str
    ai_api_key: str
    ai_base_url: str
    ai_model: str
    ai_embedding_model: str
    ai_embedding_api_key: str
    ai_embedding_base_url: str
    ai_fallback_models: str
    ai_timeout: int
    server_host: str
    server_port: int
    log_level: str
    redis_url: str
    changelog_soft_timeout: float
    changelog_hard_timeout: float
    logic_soft_timeout: float
    logic_hard_timeout: float
    unittest_soft_timeout: float
    unittest_hard_timeout: float
    default_review_level: int
    core_keywords: list[str]

# 全局设置缓存，避免每次调用重新解析环境变量
_settings_cache: Settings | None = None

def load_settings() -> Settings:
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = Settings(
            github_webhook_secret=os.getenv("GITHUB_WEBHOOK_SECRET", ""),
            github_token=os.getenv("GITHUB_TOKEN", ""),
            ai_api_key=os.getenv("AI_API_KEY", ""),
            ai_base_url=os.getenv("AI_BASE_URL", ""),
            ai_model=os.getenv("AI_MODEL", "deepseek/deepseek-chat"),
            ai_embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
            ai_embedding_api_key=os.getenv("EMBEDDING_API_KEY", ""),
            ai_embedding_base_url=os.getenv("EMBEDDING_BASE_URL", ""),
            ai_fallback_models=os.getenv("AI_FALLBACK_MODELS", ""),
            ai_timeout=int(os.getenv("AI_TIMEOUT", "60")),
            server_host=os.getenv("SERVER_HOST", "0.0.0.0"),
            server_port=int(os.getenv("SERVER_PORT", "8080")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            changelog_soft_timeout=float(os.getenv("CHANGELOG_SOFT_TIMEOUT", "5.0")),
            changelog_hard_timeout=float(os.getenv("CHANGELOG_HARD_TIMEOUT", "10.0")),
            logic_soft_timeout=float(os.getenv("LOGIC_SOFT_TIMEOUT", "45.0")),
            logic_hard_timeout=float(os.getenv("LOGIC_HARD_TIMEOUT", "90.0")),
            unittest_soft_timeout=float(os.getenv("UNITTEST_SOFT_TIMEOUT", "45.0")),
            unittest_hard_timeout=float(os.getenv("UNITTEST_HARD_TIMEOUT", "90.0")),
            default_review_level=int(os.getenv("DEFAULT_REVIEW_LEVEL", "3")),
            core_keywords=os.getenv("CORE_KEYWORDS", "auth,payment,database").split(","),
        )
    return _settings_cache
