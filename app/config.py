import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    github_webhook_secret: str
    github_token: str
    deepseek_api_key: str
    deepseek_model: str
    ai_timeout: int
    server_host: str
    server_port: int
    log_level: str

def load_settings() -> Settings:
    return Settings(
        github_webhook_secret=os.getenv("GITHUB_WEBHOOK_SECRET", ""),
        github_token=os.getenv("GITHUB_TOKEN", ""),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek/deepseek-chat"),
        ai_timeout=int(os.getenv("AI_TIMEOUT", "60")),
        server_host=os.getenv("SERVER_HOST", "0.0.0.0"),
        server_port=int(os.getenv("SERVER_PORT", "8080")),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )
