# src/dpp/routers/part.py
from __future__ import annotations

import logging
from typing import Any, List

from beanie import Link
from fastapi import APIRouter, HTTPException, status
from pymongo.errors import DuplicateKeyError

from ..models.material import MaterialInstance
from ..models.part import PartInstance, PartStatic
from ..models.partstatistics import (
    CombinedMaterialSummary,
    RareEarthSummary,
    compute_combined_material_summary_by_name,
    compute_rare_earth_metrics_rare_only,
)
from ..models.processstep import ProcessUnion

logger = logging.getLogger(__name__)
router = APIRouter()


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


async def _resolve_part_name(part_inst: PartInstance) -> str:
    """Display name for a PartInstance via its static link."""
    try:
        static_part = (
            await part_inst.partStaticLink.fetch()
            if isinstance(part_inst.partStaticLink, Link)
            else part_inst.partStaticLink
        )
        return (
            getattr(static_part, "name", None) or getattr(part_inst, "name", None) or str(getattr(part_inst, "id", ""))
        )
    except Exception:
        return getattr(part_inst, "name", None) or str(getattr(part_inst, "id", ""))


async def _resolve_place_links_on_step(step: Any) -> None:
    """Fetch place links on a process step."""
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
# PartStatic CRUD
# ──────────────────────────────────────────────────────────────────────────────


@router.post(
    "/",
    response_model=PartStatic,
    status_code=status.HTTP_201_CREATED,
    response_model_by_alias=True,
    summary="Create a new static part",
)
async def create_part(part: PartStatic) -> PartStatic:
    try:
        await part.insert()
    except HTTPException:
        raise
    except DuplicateKeyError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"PartStatic with id {part.id} already exists",
        ) from err
    except Exception as error:
        logger.error("Error inserting PartStatic: %s", error, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while creating the part.",
        ) from error

    logger.info("Created PartStatic %s (%s)", getattr(part, "name", None), part.id)
    return part


# ──────────────────────────────────────────────────────────────────────────────
# PartInstance CRUD
# ──────────────────────────────────────────────────────────────────────────────


@router.get(
    "/instance/{instance_id}",
    response_model=PartInstance,
    response_model_by_alias=True,
    summary="Get a part instance (links resolved for process steps)",
)
async def get_part_instance(instance_id: str) -> PartInstance:
    """
    Return a specific PartInstance by id.
    """
    instance = await PartInstance.get(instance_id, fetch_links=True, with_children=True)
    if not instance:
        raise HTTPException(status_code=404, detail="Part instance not found")

    # Resolve places on part-level steps
    for step in getattr(instance, "partProcessTracking", []) or []:
        await _resolve_place_links_on_step(step)

    # Resolve places on material-level steps
    for material in getattr(instance, "compositeMaterials", []) or []:
        for step in getattr(material, "materialProcessTracking", []) or []:
            await _resolve_place_links_on_step(step)

    return instance


@router.post(
    "/instance/",
    response_model=PartInstance,
    status_code=status.HTTP_201_CREATED,
    response_model_by_alias=True,
    summary="Create a new part instance",
)
async def create_part_instance(part_instance: PartInstance) -> PartInstance:
    try:
        await part_instance.insert()
    except HTTPException:
        raise
    except DuplicateKeyError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"PartInstance with id {part_instance.id} already exists",
        ) from err
    except Exception as error:
        logger.error("Error inserting PartInstance: %s", error, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while creating the part instance.",
        ) from error

    logger.info("Created PartInstance %s", part_instance.id)
    return part_instance


@router.get(
    "/instance/{instance_id}/children",
    response_model=List[dict],
    response_model_by_alias=True,
    summary="List direct children of a part instance",
)
async def get_part_children_min(instance_id: str) -> List[dict]:
    """Return direct children (id, name, flags) of a PartInstance (sorted by name)."""
    instance = await PartInstance.get(instance_id, fetch_links=True, with_children=True)
    if not instance:
        raise HTTPException(status_code=404, detail="Part instance not found")

    children_info: List[dict] = []
    for child_part in getattr(instance, "compositeParts", []) or []:
        children_info.append(
            {
                "id": child_part.id,
                "name": await _resolve_part_name(child_part),
                "isModular": bool(getattr(child_part, "isModular", False)),
                "hasFailstate": bool(getattr(child_part, "hasFailstate", False)),
            }
        )
    children_info.sort(key=lambda x: (x.get("name") or ""))
    return children_info


# ──────────────────────────────────────────────────────────────────────────────
# Analytics
# ──────────────────────────────────────────────────────────────────────────────


@router.get(
    "/instance/{part_id}/rare_earth_metrics",
    response_model=RareEarthSummary,
    response_model_by_alias=True,
    summary="Rare earth metrics for a part instance",
)
async def get_rare_earth_metrics_for_part(part_id: str) -> RareEarthSummary:
    part = await PartInstance.get(part_id, fetch_links=True)
    if not part:
        raise HTTPException(status_code=404, detail="Part instance not found")
    return await compute_rare_earth_metrics_rare_only(part)


@router.get(
    "/instance/{instance_id}/combined_material_summary_by_name",
    response_model=CombinedMaterialSummary,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
    summary="Combined material summary for a part instance (by name)",
)
async def get_combined_summary_by_name(instance_id: str) -> CombinedMaterialSummary:
    """
    Aggregate material weights, recycled shares, and flags (rare/hazardous) by material *name*
    for the given `PartInstance`.
    """
    instance = await PartInstance.get(instance_id, fetch_links=True, with_children=True)
    if not instance:
        raise HTTPException(status_code=404, detail="Part instance not found")

    return await compute_combined_material_summary_by_name(instance)


# ──────────────────────────────────────────────────────────────────────────────
# Mutations on PartInstance
# ──────────────────────────────────────────────────────────────────────────────


@router.post(
    "/instance/{instance_id}/material/",
    response_model=PartInstance,
    response_model_by_alias=True,
    summary="Append a material to a part instance",
)
async def add_material_to_part_instance(instance_id: str, material: MaterialInstance) -> PartInstance:
    """
    Append a `MaterialInstance` to `compositeMaterials` of a given `PartInstance`.
    """
    instance = await PartInstance.get(instance_id, fetch_links=True, with_children=True)
    if not instance:
        raise HTTPException(status_code=404, detail="Part instance not found")

    try:
        instance.compositeMaterials.append(material)
        await instance.save()
    except HTTPException:
        raise
    except Exception as error:
        logger.error("Error adding material to PartInstance %s: %s", instance_id, error, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while adding the material.",
        ) from error

    logger.info("Added MaterialInstance %s to PartInstance %s", getattr(material, "id", "<no-id>"), instance_id)
    return instance


@router.post(
    "/instance/{instance_id}/process/",
    response_model=PartInstance,
    response_model_by_alias=True,
    summary="Append a process step to a part instance",
)
async def add_process_to_part_instance(instance_id: str, process_step: ProcessUnion) -> PartInstance:
    """
    Append a `ProcessUnion` step to `partProcessTracking` of a `PartInstance`.
    """
    instance = await PartInstance.get(instance_id, fetch_links=True, with_children=True)
    if not instance:
        raise HTTPException(status_code=404, detail="Part instance not found")

    try:
        instance.partProcessTracking.append(process_step)
        await instance.save()
    except HTTPException:
        raise
    except Exception as error:
        logger.error("Error adding process step to PartInstance %s: %s", instance_id, error, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while adding the process step.",
        ) from error

    logger.info("Appended process step %s to PartInstance %s", getattr(process_step, "type_", "<unknown>"), instance_id)
    return instance


@router.post(
    "/instance/{instance_id}/composite/",
    response_model=PartInstance,
    response_model_by_alias=True,
    summary="Append a composite part to a part instance",
)
async def add_composite_to_part_instance(instance_id: str, composite_part: PartInstance) -> PartInstance:
    """
    Append a composite `PartInstance` to another `PartInstance`.
    """
    instance = await PartInstance.get(instance_id, fetch_links=True, with_children=True)
    if not instance:
        raise HTTPException(status_code=404, detail="Part instance not found")

    # Ensure the composite child exists
    existing_part = await PartInstance.get(composite_part.id, fetch_links=True, with_children=True)
    if not existing_part:
        raise HTTPException(status_code=404, detail="Composite part not found")

    # Prevent duplicates
    if any(getattr(child, "id", None) == composite_part.id for child in getattr(instance, "compositeParts", []) or []):
        raise HTTPException(status_code=400, detail=f"Composite part {composite_part.id} already attached")

    try:
        instance.compositeParts.append(composite_part)
        await instance.save()
    except HTTPException:
        raise
    except Exception as error:
        logger.error("Error adding composite part to PartInstance %s: %s", instance_id, error, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while adding the composite part.",
        ) from error

    logger.info("Added composite part %s to PartInstance %s", composite_part.id, instance_id)
    return instance
