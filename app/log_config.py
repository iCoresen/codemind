import logging
import logging.config
import os
from typing import Any, Dict

from app.config import Settings

def get_logging_config(settings: Settings, service_name: str) -> Dict[str, Any]:
    """获取集中式日志配置，同时输出到控制台和文件"""
    os.makedirs("logs", exist_ok=True)
    
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    log_file = f"logs/{service_name}.log"
    
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S"
            },
        },
        "handlers": {
            "console": {
                "level": log_level,
                "formatter": "standard",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
            "file": {
                "level": log_level,
                "formatter": "standard",
                "class": "logging.handlers.RotatingFileHandler",
                "filename": log_file,
                "maxBytes": 10485760,  # 10MB
                "backupCount": 5,
                "encoding": "utf8"
            },
        },
        "loggers": {
            "": {  # root logger
                "handlers": ["console", "file"],
                "level": log_level,
                "propagate": True,
            },
            "codemind": {  # codemind specific logger
                "handlers": ["console", "file"],
                "level": log_level,
                "propagate": False,
            },
            "uvicorn": {
                "handlers": ["console", "file"],
                "level": "INFO",
                "propagate": False,
            },
            "celery": {
                "handlers": ["console", "file"],
                "level": log_level,
                "propagate": False,
            }
        }
    }

def setup_logging(settings: Settings, service_name: str):
    """初始化日志系统"""
    config = get_logging_config(settings, service_name)
    logging.config.dictConfig(config)
