"""FastAPI entrypoint."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api.chat import router as chat_router
from app.config import get_settings


def create_app() -> FastAPI:
    # Fail-fast: catch a missing API key at boot instead of waiting for the
    # first /api/chat request to return "Missing credentials" 500.
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is empty. Set it in .env (or export OPENAI_API_KEY=...). "
            "The variable name is kept as OPENAI_API_KEY because GLM / DeepSeek / "
            "OpenAI all share the OpenAI-compatible protocol via langchain_openai."
        )

    app = FastAPI(title="Agentic RAG Demo", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(chat_router, prefix="/api")

    @app.get("/health")
    async def health():
        return {"ok": True}

    ui_dir = Path(__file__).parent / "ui"
    if ui_dir.exists():
        @app.get("/")
        async def index():
            return FileResponse(ui_dir / "index.html")

    return app


app = create_app()


def main() -> None:
    import uvicorn

    s = get_settings()  # already validated by create_app() at module import time
    uvicorn.run("app.main:app", host=s.host, port=s.port, reload=False)


if __name__ == "__main__":
    main()
