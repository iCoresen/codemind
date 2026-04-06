import logging

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import load_settings
from app.log_config import setup_logging
from app.github_webhook import router as github_router
from app.exceptions import CodeMindError

def create_app() -> FastAPI:
    settings = load_settings()
    setup_logging(settings, "fastapi")  # 设置统一日志，输出到 logs/fastapi.log

    app = FastAPI(title="CodeMind MVP", version="0.1.0")
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
        return {"ok": True}

    return app

app = create_app()

if __name__ == "__main__":
    settings = load_settings()
    uvicorn.run("app.main:app", host=settings.server_host, port=settings.server_port, reload=False)
