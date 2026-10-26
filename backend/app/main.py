import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from app.api.legacy import router as legacy_router
from app.api.v1.router import router as v1_router
from app.core.config import settings
from app.core.errors import AppError, error_body
from app.core.logging import configure_logging, correlation_id
from app.db.client import close_db, get_db
from app.db.indexes import ensure_indexes
from app.services.settings import SettingsService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)
    if not settings.dry_run:
        logger.warning("DRY_RUN=false is ignored. Live submission is not available in this phase.")
    app.state.db_startup_error = None
    try:
        await ensure_indexes()
        await SettingsService().get()
    except (PyMongoError, AppError) as exc:
        logger.error("database startup failed: %s", type(exc).__name__)
        app.state.db_startup_error = "database_unavailable"
    yield
    await close_db()


app = FastAPI(title="AI Job Application Agent", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Correlation-ID"],
)


@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    incoming = request.headers.get("x-correlation-id") or uuid.uuid4().hex
    request.state.correlation_id = incoming
    token = correlation_id.set(incoming)
    try:
        response = await call_next(request)
    finally:
        correlation_id.reset(token)
    response.headers["X-Correlation-ID"] = incoming
    return response


def _cid(request: Request) -> str:
    return getattr(request.state, "correlation_id", "") or correlation_id.get() or uuid.uuid4().hex


@app.exception_handler(AppError)
async def handle_app_error(request: Request, exc: AppError):
    cid = _cid(request)
    response = JSONResponse(status_code=exc.http_status, content=error_body(exc.code, exc.message, cid, exc.details))
    response.headers["X-Correlation-ID"] = cid
    return response


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    cid = _cid(request)
    safe_errors = [{key: value for key, value in err.items() if key != "input"} for err in exc.errors()]
    response = JSONResponse(
        status_code=422,
        content=error_body("validation_error", "Request validation failed", cid, {"errors": jsonable_encoder(safe_errors)}),
    )
    response.headers["X-Correlation-ID"] = cid
    return response


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception):
    logger.exception("unhandled error")
    cid = _cid(request)
    response = JSONResponse(status_code=500, content=error_body("internal_error", "Internal error", cid))
    response.headers["X-Correlation-ID"] = cid
    return response


@app.get("/health")
async def health():
    mongo = "unavailable"
    dry_run = True
    try:
        await get_db().command("ping")
        mongo = "ok"
        dry_run = (await SettingsService().get()).dry_run
    except (PyMongoError, AppError):
        mongo = "unavailable"
    return {"status": "ok" if mongo == "ok" else "degraded", "mongodb": mongo, "dry_run": dry_run}


app.include_router(v1_router)
app.include_router(legacy_router)
