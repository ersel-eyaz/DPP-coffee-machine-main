# /backend/src/dpp/data/clear_db.py
from __future__ import annotations

import asyncio
import logging
from typing import Sequence

from motor.motor_asyncio import AsyncIOMotorGridFSBucket

from dpp.models.db import mongodb

logger = logging.getLogger(__name__)

COLLECTIONS_TO_CLEAR: Sequence[str] = (
    "organisation",
    "place",
    "material_static",
    "material_instance",
    "part_static",
    "part_instance",
    "dpp_static",
    "dpp_instance",
    "fs.files",
    "fs.chunks",
)


async def _clear_gridfs() -> int:
    """Delete all files from GridFS and return the number deleted."""
    bucket = AsyncIOMotorGridFSBucket(mongodb)
    deleted_count = 0
    async for grid_file in bucket.find():
        try:
            await bucket.delete(grid_file._id)
            deleted_count += 1
        except Exception as gridfs_error:
            grid_file_id = getattr(grid_file, "_id", "unknown")
            logger.warning("Failed to delete GridFS file %s due to %s", grid_file_id, gridfs_error)
    logger.info("Deleted %s files from GridFS", deleted_count)
    return deleted_count


async def _drop_collections(collection_names: Sequence[str]) -> None:
    """Drop the given collections if they exist."""
    existing_collections = set(await mongodb.list_collection_names())
    for collection_name in collection_names:
        if collection_name not in existing_collections:
            logger.debug("Collection %s not present, skipping drop", collection_name)
            continue
        try:
            await mongodb[collection_name].drop()
            logger.info("Dropped collection %s", collection_name)
        except Exception as drop_error:
            logger.warning("Failed to drop collection %s due to %s", collection_name, drop_error)


async def clear_db() -> None:
    """Run full database cleanup: GridFS + targeted collections."""
    logger.info("Starting database cleanup")
    await _clear_gridfs()
    await _drop_collections(COLLECTIONS_TO_CLEAR)
    logger.info("Database cleanup finished")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    asyncio.run(clear_db())
