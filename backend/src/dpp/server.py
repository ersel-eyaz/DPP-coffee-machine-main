# src/dpp/server.py
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorGridFSBucket

from dpp.models.db import mongodb
from dpp.models.init import init_db_with_beanie

from .routers.dpp import router as dpp_router
from .routers.jsonld_export import router as jsonld_router
from .routers.material import router as material_router
from .routers.organisation import router as organization_router
from .routers.part import router as part_router
from .routers.place import router as place_router

from .data_quality.router import router as data_quality_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---- CORS config -----------------------------------------
DEFAULT_ORIGINS = [
    "https://wise-partly-alpaca.ngrok-free.app",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
]
ENV_ORIGINS = [o.strip() for o in os.getenv("CORS_ALLOW_ORIGINS", "").split(",") if o.strip()]
ALLOW_ORIGIN_REGEX = os.getenv("CORS_ALLOW_ORIGIN_REGEX", r"https://.*\.ngrok-free\.app")

ALLOWED_ORIGINS = ENV_ORIGINS if ENV_ORIGINS else DEFAULT_ORIGINS


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Beanie + MongoDB + GridFS…")
    try:
        await init_db_with_beanie()
        app.state.fs = AsyncIOMotorGridFSBucket(mongodb)
        logger.info("Startup complete.")
        yield
    finally:
        logger.info("Shutting down FastAPI application.")


app = FastAPI(
    title="DPP API",
    version=os.getenv("DPP_API_VERSION", "0.1.0"),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=ALLOW_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(place_router, prefix="/place", tags=["place"])
app.include_router(organization_router, prefix="/organisation", tags=["organisation"])
app.include_router(material_router, prefix="/material", tags=["material"])
app.include_router(part_router, prefix="/part", tags=["part"])
app.include_router(dpp_router, prefix="/dpp", tags=["dpp"])
app.include_router(jsonld_router, prefix="/jsonld", tags=["jsonld"])
app.include_router(data_quality_router, prefix="/data-quality", tags=["data-quality"])


@app.get("/")
async def root() -> Dict[str, Any]:
    """Simple health check endpoint."""
    return {"message": "hello"}


@app.get("/health")
async def health() -> Dict[str, str]:
    """Liveness probe that also verifies MongoDB connectivity."""
    try:
        await mongodb.command("ping")
        return {"status": "ok"}
    except Exception as exc:
        logger.exception("Health check failed: %s", exc)
        raise HTTPException(status_code=503, detail="database unavailable") from exc
