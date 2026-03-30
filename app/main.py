import logging

import uvicorn
from fastapi import FastAPI

from app.config import load_settings
from app.github_webhook import router as github_router


def create_app() -> FastAPI:
    settings = load_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))

    app = FastAPI(title="CodeMind MVP", version="0.1.0")
    app.include_router(github_router)

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    return app


app = create_app()


if __name__ == "__main__":
    settings = load_settings()
    uvicorn.run("app.main:app", host=settings.server_host, port=settings.server_port, reload=False)
