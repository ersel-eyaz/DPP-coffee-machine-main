# src/dpp/routers/place.py
from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, HTTPException, status
from pymongo.errors import DuplicateKeyError

from ..models.location import Place

logger = logging.getLogger(__name__)
router = APIRouter()


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


async def _get_or_404(place_id: str) -> Place:
    """Fetch a Place by id (with links/children); raise 404 if missing."""
    doc = await Place.get(place_id, fetch_links=True, with_children=True)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Place not found")
    return doc


# ──────────────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────────────


@router.get(
    "/",
    response_model=List[Place],
    response_model_by_alias=True,
    summary="List all places",
)
async def list_places() -> List[Place]:
    """Return all places with linked documents."""
    return await Place.find_all(with_children=True, fetch_links=True).to_list()


@router.get(
    "/{place_id}",
    response_model=Place,
    response_model_by_alias=True,
    summary="Get a place by id",
)
async def get_place(place_id: str) -> Place:
    """Return a single place."""
    return await _get_or_404(place_id)


@router.post(
    "/",
    response_model=Place,
    response_model_by_alias=True,  # ensure "id" alias in the response
    status_code=status.HTTP_201_CREATED,
    summary="Create a new place",
)
async def create_place(place: Place) -> Place:
    """Persist a new place."""
    try:
        await place.insert()
    except HTTPException:
        raise
    except DuplicateKeyError as dup_error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Place with id {place.id} already exists",
        ) from dup_error
    except Exception as error:
        logger.error("Error inserting Place: %s", error, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while creating the place.",
        ) from error

    logger.info("Created Place %s (%s)", getattr(place, "name", None), place.id)
    return place
