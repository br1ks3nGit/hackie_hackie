import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.dashboard_auth import SESSION_MAX_AGE_S, LoginRequired, login_required_handler
from app.model import load_model
from app.routers import (
    admin,
    dashboard,
    dashboard_drivers,
    dashboard_trips,
    driver,
    incidents,
    ingestion,
    insurer,
)

settings = get_settings()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting DriveScore API")
    load_model()
    logger.info("Model loaded successfully")

    yield

    # Shutdown
    logger.info("Shutting down DriveScore API")


app = FastAPI(
    title="DriveScore API",
    description="Usage-based car insurance backend",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
origins = [origin.strip() for origin in settings.cors_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dashboard staff session (signed cookie; stores `user` and `csrf_token`)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    max_age=SESSION_MAX_AGE_S,
    same_site="lax",
    https_only=settings.session_https_only,
)
app.add_exception_handler(LoginRequired, login_required_handler)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

# Include routers
app.include_router(ingestion.router, prefix="/v1", tags=["ingestion"])
app.include_router(driver.router, prefix="/v1", tags=["reports"])
app.include_router(insurer.router, prefix="/v1", tags=["reports"])
app.include_router(incidents.router, prefix="/v1", tags=["reports"])
app.include_router(admin.router, prefix="/v1", tags=["admin"])
app.include_router(dashboard.router)
app.include_router(dashboard_drivers.router)
app.include_router(dashboard_trips.router)


@app.get("/health")
def health():
    return {"status": "ok"}
