import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import load_settings
from app.log_config import setup_logging
from app.github_webhook import router as github_router, init_pools
from app.exceptions import CodeMindError
import redis.asyncio as redis
from arq import create_pool
from arq.connections import RedisSettings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """管理 Redis 和 ARQ 连接池的生命周期"""
    settings = load_settings()
    redis_client = redis.from_url(settings.redis_url)
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    arq_pool = await create_pool(redis_settings)
    init_pools(redis_client, arq_pool)
    logging.info("Redis and ARQ pools initialized")
    yield
    # 清理
    await redis_client.aclose()
    await arq_pool.close()
    logging.info("Redis and ARQ pools closed")


def create_app() -> FastAPI:
    settings = load_settings()
    setup_logging(settings, "fastapi")

    app = FastAPI(title="CodeMind MVP", version="0.1.0", lifespan=lifespan)
    app.include_router(github_router)

    @app.exception_handler(CodeMindError)
    async def codemind_exception_handler(request: Request, exc: CodeMindError):
        logging.error(f"CodeMindError at {request.url}: {exc}")
        return JSONResponse(
            status_code=500,
            content={"message": str(exc), "type": type(exc).__name__},
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logging.error(f"Unhandled exception at {request.url}: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"message": "Internal server error"},
        )

    @app.get("/healthz")
    async def healthz():
        """增强的健康检查，包含 Redis 和 AI 服务依赖检查"""
        from app.github_webhook import get_redis
        health = {"ok": True, "checks": {}}

        # Redis 检查
        try:
            redis_client = get_redis()
            if redis_client:
                await redis_client.ping()
                health["checks"]["redis"] = "connected"
            else:
                health["checks"]["redis"] = "not initialized"
        except Exception as e:
            health["ok"] = False
            health["checks"]["redis"] = f"error: {e}"

        # AI 模型检查（轻量级探测）
        try:
            from app.ai_handlers.litellm_ai_handler import LiteLLMAIHandler
            ai_handler = LiteLLMAIHandler(settings)
            # 使用 embedding 接口做轻量探测
            await ai_handler.async_embedding(texts=["health_check"], model=settings.ai_embedding_model)
            health["checks"]["ai"] = "available"
        except Exception as e:
            health["checks"]["ai"] = f"unavailable: {e}"

        if not health["ok"]:
            return JSONResponse(status_code=503, content=health)
        return health

    return app

app = create_app()

if __name__ == "__main__":
    settings = load_settings()
    uvicorn.run("app.main:app", host=settings.server_host, port=settings.server_port, reload=False)
