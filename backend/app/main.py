from __future__ import annotations

# pyright: reportUnusedFunction=false
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.platform_router import platform_router
from app.api.router import api_router
from app.core.config import get_settings
from app.core.errors import ApiError, browser_safe_error_details, request_validation_to_details
from app.core.telemetry import configure_logfire
from app.db.engine import get_engine
from app.db.session import init_db

READINESS_UNAVAILABLE_STATUS = status.HTTP_503_SERVICE_UNAVAILABLE


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


def _database_is_ready() -> bool:
    try:
        with get_engine().connect() as connection:
            _ = connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return False
    return True


def create_app(*, init_database: bool = True) -> FastAPI:
    settings = get_settings()
    configure_logfire()
    app = FastAPI(
        title="SignalDeck Backend", version="0.1.0", lifespan=lifespan if init_database else None
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(ApiError)
    async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code,
                "message": exc.message,
                "details": browser_safe_error_details(exc.details),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "code": "validation_error",
                "message": "Request validation failed",
                "details": request_validation_to_details(exc),
            },
        )

    @app.get("/health", tags=["health"])
    def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready", tags=["health"])
    def readinesscheck() -> JSONResponse:
        if not _database_is_ready():
            return JSONResponse(
                status_code=READINESS_UNAVAILABLE_STATUS,
                content={"status": "unavailable", "database": "unavailable"},
            )
        return JSONResponse(content={"status": "ok", "database": "ok"})

    app.include_router(platform_router)
    app.include_router(api_router)
    return app


app = create_app()


def main() -> None:
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
