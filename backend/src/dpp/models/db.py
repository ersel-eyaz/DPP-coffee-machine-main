# src/dpp/models/db.py
from __future__ import annotations

import logging
import os
from typing import Optional
from urllib.parse import urlparse, urlunparse

from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorDatabase,
    AsyncIOMotorGridFSBucket,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _sanitize(uri: str) -> str:
    """Hide password in logs"""
    try:
        parsed = urlparse(uri)
        if parsed.password:
            username = (parsed.username or "").replace(":", "%3A")
            hostport = parsed.hostname or ""
            if parsed.port:
                hostport = f"{hostport}:{parsed.port}"
            masked = f"{username}:******@{hostport}" if username else f"******@{hostport}"
            parsed = parsed._replace(netloc=masked)
            return urlunparse(parsed)
    except Exception:
        pass
    return uri


def _db_name_from_uri(uri: str) -> Optional[str]:
    """Extract DB name from mongodb or mongodb+srv URIs."""
    try:
        p = urlparse(uri)
        if p.path and len(p.path) > 1:
            return p.path.lstrip("/").split("/", 1)[0] or None
    except Exception:
        pass
    return None


def _build_uri_from_env() -> str:
    """Construct a MongoDB URI from granular env vars if MONGODB_URI is not set."""
    user = os.getenv("MONGO_USER")
    pwd = os.getenv("MONGO_PASSWORD")
    host = os.getenv("MONGO_HOST", "mongo")
    port = os.getenv("MONGO_PORT", "27017")
    db = os.getenv("MONGO_DB", "dpp_prototype")
    auth_src = os.getenv("MONGO_AUTH_SOURCE", "admin")

    auth = f"{user}:{pwd}@" if user and pwd else ""
    suffix = f"?authSource={auth_src}" if auth else ""
    return f"mongodb://{auth}{host}:{port}/{db}{suffix}"


# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

MONGODB_URI: str = os.getenv("MONGODB_URI") or _build_uri_from_env()
DB_NAME: str = os.getenv("MONGO_DB") or _db_name_from_uri(MONGODB_URI) or "dpp_prototype"

CONNECT_TIMEOUT_MS = int(os.getenv("MONGO_CONNECT_TIMEOUT_MS", "10000"))
SOCKET_TIMEOUT_MS = int(os.getenv("MONGO_SOCKET_TIMEOUT_MS", "10000"))
MAX_POOL_SIZE = int(os.getenv("MONGO_MAX_POOL_SIZE", "100"))
MIN_POOL_SIZE = int(os.getenv("MONGO_MIN_POOL_SIZE", "0"))

logger.info("Using MongoDB: %s (db=%s)", _sanitize(MONGODB_URI), DB_NAME)

# ──────────────────────────────────────────────────────────────────────────────
# Client / DB singletons
# ──────────────────────────────────────────────────────────────────────────────

client: AsyncIOMotorClient = AsyncIOMotorClient(
    MONGODB_URI,
    uuidRepresentation="standard",
    tz_aware=True,
    connectTimeoutMS=CONNECT_TIMEOUT_MS,
    socketTimeoutMS=SOCKET_TIMEOUT_MS,
    maxPoolSize=MAX_POOL_SIZE,
    minPoolSize=MIN_POOL_SIZE,
)
mongodb: AsyncIOMotorDatabase = client[DB_NAME]


def get_client() -> AsyncIOMotorClient:
    """Return Motor client."""
    return client


def get_database() -> AsyncIOMotorDatabase:
    """Return Motor database."""
    return mongodb


def get_gridfs_bucket() -> AsyncIOMotorGridFSBucket:
    """Create a GridFS bucket."""
    return AsyncIOMotorGridFSBucket(mongodb)


# ──────────────────────────────────────────────────────────────────────────────
# Connectivity check
# ──────────────────────────────────────────────────────────────────────────────


async def verify_connection() -> None:
    """
    Connectivity check for startup.
    """
    try:
        await client.admin.command("ping")
        logger.info("MongoDB ping successful for %s", _sanitize(MONGODB_URI))
    except Exception as exc:
        logger.exception("MongoDB ping failed: %s", exc)
        raise


__all__ = [
    "MONGODB_URI",
    "DB_NAME",
    "client",
    "mongodb",
    "get_client",
    "get_database",
    "get_gridfs_bucket",
    "verify_connection",
]
