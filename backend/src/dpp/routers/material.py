# src/dpp/routers/material.py
from __future__ import annotations

import logging
from typing import Any, Type, TypeVar

from beanie import Link
from fastapi import APIRouter, HTTPException, status
from pymongo.errors import DuplicateKeyError

from ..models.material import MaterialInstance, MaterialStatic
from ..models.processstep import ProcessUnion

logger = logging.getLogger(__name__)
router = APIRouter()

T = TypeVar("T")


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


async def _get_or_404(model: Type[T], obj_id: str, *, with_children: bool = False) -> T:
    """
    Fetch a Beanie document by ID
    """
    doc = await model.get(obj_id, fetch_links=True, with_children=with_children)  # type: ignore[arg-type]
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{model.__name__} not found")
    return doc


async def _resolve_place_links_on_step(step: Any) -> None:
    """
    Resolution of place references on a process step.
    """
    try:
        if hasattr(step, "processedAt") and isinstance(step.processedAt, Link):
            step.processedAt = await step.processedAt.fetch()
    except Exception:
        pass
    try:
        if hasattr(step, "destination") and isinstance(step.destination, Link):
            step.destination = await step.destination.fetch()
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────────────


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    response_model=MaterialStatic,
    response_model_by_alias=True,
    summary="Create a new MaterialStatic",
)
async def create_material(material: MaterialStatic) -> MaterialStatic:
    """
    Create a new static material definition.
    """
    try:
        await material.insert()
    except HTTPException:
        raise
    except DuplicateKeyError as err:
        logger.warning("Duplicate MaterialStatic insert attempt (id=%s)", material.id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"MaterialStatic with id {material.id} already exists",
        ) from err
    except Exception as error:
        logger.error("Error inserting MaterialStatic: %s", error, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while creating the material.",
        ) from error
    return material


@router.get(
    "/instance/{instance_id}",
    response_model=MaterialInstance,
    response_model_by_alias=True,
    summary="Get a MaterialInstance by ID",
)
async def get_material_instance(instance_id: str) -> MaterialInstance:
    """
    Retrieve a `MaterialInstance` by its ID
    """
    instance = await _get_or_404(MaterialInstance, instance_id, with_children=True)

    for step in getattr(instance, "materialProcessTracking", []) or []:
        await _resolve_place_links_on_step(step)

    return instance


@router.post(
    "/instance/",
    response_model=MaterialInstance,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new MaterialInstance",
)
async def create_material_instance(material_instance: MaterialInstance) -> MaterialInstance:
    """
    Create a new `MaterialInstance`.
    """
    try:
        await material_instance.insert()
    except HTTPException:
        raise
    except DuplicateKeyError as err:
        logger.warning("Duplicate MaterialInstance insert attempt (id=%s)", material_instance.id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"MaterialInstance with id {material_instance.id} already exists",
        ) from err
    except Exception as error:
        logger.error("Error inserting MaterialInstance: %s", error, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while creating the material instance.",
        ) from error
    return material_instance


@router.post(
    "/instance/{instance_id}/process/",
    response_model=MaterialInstance,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
    summary="Append a process step to a MaterialInstance",
)
async def process_material_instance(instance_id: str, process_step: ProcessUnion) -> MaterialInstance:
    """
    Append a `ProcessUnion` step to the `materialProcessTracking` of a `MaterialInstance`.
    """
    instance = await _get_or_404(MaterialInstance, instance_id, with_children=True)

    try:
        instance.materialProcessTracking.append(process_step)
        await instance.save()
        logger.info(
            "Appended process step %s to MaterialInstance %s", getattr(process_step, "type_", None), instance_id
        )
    except HTTPException:
        raise
    except Exception as error:
        logger.error("Error appending process step to MaterialInstance: %s", error, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing the material instance.",
        ) from error

    updated = await _get_or_404(MaterialInstance, instance_id, with_children=True)
    for step in getattr(updated, "materialProcessTracking", []) or []:
        await _resolve_place_links_on_step(step)
    return updated
