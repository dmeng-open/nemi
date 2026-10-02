import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import app.models  # noqa: F401
from app.api.router import api_router
from app.api.routes.health import router as health_router
from app.core.config import Settings, get_settings
from app.core.exceptions import AppError
from app.core.logging import configure_logging, safe_error_text
from app.db.base import Base
from app.db.session import create_engine, create_session_factory
from app.providers.health import get_provider_health
from app.repositories.users import ensure_local_user
from app.services.planning.orchestrator import PlanningOrchestrator

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    configure_logging(settings.log_level)
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    app.state.engine = engine
    app.state.session_factory = factory
    app.state.provider_health = get_provider_health()
    if settings.auto_create_schema or settings.database_url.startswith("sqlite"):
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    try:
        async with factory() as session:
            await ensure_local_user(session)
            await session.commit()
    except Exception as exc:
        logger.warning("database_not_ready", extra={"detail": safe_error_text(exc)})
    app.state.orchestrator = PlanningOrchestrator(factory, settings)
    yield
    await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Nemi", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(api_router, prefix="/api")
    _register_handlers(app)
    return app


def _register_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        message = "Check the fields and try again."
        errors = exc.errors()
        if errors:
            first = errors[0]
            loc = [str(part) for part in first.get("loc", []) if part not in {"body", "query"}]
            detail = str(first.get("msg", "Invalid value"))
            message = f"{'.'.join(loc)}: {detail}" if loc else detail
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "validation_error", "message": message}},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(_request: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled_error", extra={"detail": safe_error_text(exc)})
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "Something went wrong. Please try again.",
                }
            },
        )


app = create_app()
