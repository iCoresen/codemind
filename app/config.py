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

def load_settings() -> Settings:
    return Settings(
        github_webhook_secret=os.getenv("GITHUB_WEBHOOK_SECRET", ""),
        github_token=os.getenv("GITHUB_TOKEN", ""),
        ai_api_key=os.getenv("AI_API_KEY", ""),
        ai_base_url=os.getenv("AI_BASE_URL", ""),
        ai_model=os.getenv("AI_MODEL", "deepseek/deepseek-chat"),
        ai_fallback_models=os.getenv("AI_FALLBACK_MODELS", ""),
        ai_timeout=int(os.getenv("AI_TIMEOUT", "60")),
        server_host=os.getenv("SERVER_HOST", "0.0.0.0"),
        server_port=int(os.getenv("SERVER_PORT", "8080")),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        changelog_soft_timeout=float(os.getenv("CHANGELOG_SOFT_TIMEOUT", "5.0")),
        changelog_hard_timeout=float(os.getenv("CHANGELOG_HARD_TIMEOUT", "10.0")),
        logic_soft_timeout=float(os.getenv("LOGIC_SOFT_TIMEOUT", "15.0")),
        logic_hard_timeout=float(os.getenv("LOGIC_HARD_TIMEOUT", "25.0")),
        unittest_soft_timeout=float(os.getenv("UNITTEST_SOFT_TIMEOUT", "30.0")),
        unittest_hard_timeout=float(os.getenv("UNITTEST_HARD_TIMEOUT", "45.0")),
    )
