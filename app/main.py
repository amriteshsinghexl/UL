"""
ULP Actuarial Engine — unified FastAPI backend.

Start with:  python start_backend.py
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import setup_logging
from app.routes import health, model, outputs, param_tables, policies, scripts, sensitivity


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    import logging
    logging.getLogger(__name__).info(
        "ULP backend started — base_dir=%s", settings.base_dir
    )
    yield


app = FastAPI(
    title="ULP Actuarial Engine API",
    description=(
        "Production FastAPI backend for the Universal Life Policy (ULP) "
        "actuarial cashflow model. Supports async job submission, result "
        "retrieval, and data browsing."
    ),
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# CORS — allow the React dev server and any configured origins
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(health.router)
app.include_router(model.router)
app.include_router(param_tables.router)
app.include_router(policies.router)
app.include_router(sensitivity.router)
app.include_router(outputs.router)
app.include_router(scripts.router)
