# src/dpp/routers/dpp.py
from __future__ import annotations

import asyncio
import io
import logging
from collections import Counter, defaultdict
from datetime import date as _date_cls
from datetime import datetime
from datetime import timezone as _tz_cls
from time import monotonic
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, TypeAlias

from beanie import Link, PydanticObjectId
from beanie.operators import In
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorGridFSBucket
from pymongo.errors import DuplicateKeyError

from dpp.models.dpp import DPPInstance, DPPStatic
from dpp.models.dppstatistics import (
    DiagnosisSummaryResponse,
    MapEdge,
    MapNode,
    PlaceLocationSummary,
    ProcessMapResponse,
    SecondaryStepAggregateEntry,
    SecondaryStepInstanceEntry,
    SecondaryStepsAggregateResponse,
    ServiceModularSummary,
    StaticServiceAggregateSummary,
    SymptomDiagnosisSummaryEntry,
    _classify_step,
    _coords_from_place,
    _gather_secondary_steps_from_part,
    _place_key,
    aggregate_ghg_for_dpp_instance,
    compute_service_and_modular_counts,
)
from dpp.models.ghg import GHGCategoryBreakdown, GHGFootprintAggregated
from dpp.models.location import Place, ReturningPlaceSummary
from dpp.models.material import MaterialStatic
from dpp.models.part import PartInstance, PartStatic
from dpp.models.partstatistics import (
    CombinedMaterialSummary,
    RareEarthSummary,
    compute_combined_material_summary_by_name,
    compute_rare_earth_metrics_rare_only,
)
from dpp.models.processstep import (
    CleaningServiceStep,
    ProductionStep,
    RecyclingStep,
    RefurbishmentServiceStep,
    RemanufacturingServiceStep,
    RepairServiceStep,
    ReplaceServiceStep,
    SecondaryValueStep,
    TransportStep,
)
from dpp.models.quantitativqualitativvalue import ImageMetadata, ImageReference

logger = logging.getLogger(__name__)
router = APIRouter()


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _extract_id_from_link(link_or_object: Any) -> Optional[str]:
    """Return a string ID from a Link[T] or object with an `id`."""
    if link_or_object is None:
        return None
    if isinstance(link_or_object, Link):
        link_id = getattr(link_or_object, "id", None) or getattr(link_or_object, "ref_id", None)
        if link_id is None:
            ref = getattr(link_or_object, "ref", None)
            link_id = getattr(ref, "id", None) if ref is not None else None
        return str(link_id) if link_id is not None else None
    return str(getattr(link_or_object, "id", None) or "") or None


async def _resolve_org(link_or_object: Any) -> Optional[dict]:
    """Resolve an organisation to a minimal dict used consistently in responses."""
    if not link_or_object:
        return None
    try:
        organisation = await link_or_object.fetch() if isinstance(link_or_object, Link) else link_or_object
    except Exception:
        organisation = None
    if not organisation:
        return None

    data = {
        "id": getattr(organisation, "id", None),
        "name": getattr(organisation, "name", None),
        "url": getattr(organisation, "url", None),
        "type": getattr(organisation, "type_", None) or getattr(organisation, "type", None),
    }
    if hasattr(organisation, "eoriNumber"):
        data["eoriNumber"] = getattr(organisation, "eoriNumber", None)
    if hasattr(organisation, "lucidNumber"):
        data["lucidNumber"] = getattr(organisation, "lucidNumber", None)
    return data


async def _part_name_from_instance(part_instance: PartInstance) -> Optional[str]:
    """Resolution for a PartInstance display name via its static link."""
    static_link = getattr(part_instance, "partStaticLink", None)
    if static_link is None:
        return None
    try:
        static_part = await static_link.fetch() if isinstance(static_link, Link) else static_link
    except Exception:
        static_part = getattr(static_link, "document", None)
    return getattr(static_part, "name", None) if static_part is not None else None


def _count_subtree(node: PartInstance) -> int:
    """Count a node and its entire descendant subtree."""
    total = 1
    for child in getattr(node, "compositeParts", []) or []:
        total += _count_subtree(child)
    return total


async def _build_part_paths(
    node: PartInstance,
    parent_names: List[str],
    part_id_to_name_path: Dict[str, Tuple[str, str]],
) -> None:
    """Populate partId: for a part subtree."""
    display_name = await _part_name_from_instance(node) or getattr(node, "name", None) or node.id
    path_list = [*parent_names, display_name]
    part_id_to_name_path[str(node.id)] = (display_name, " \u2192 ".join(path_list))
    for child in getattr(node, "compositeParts", []) or []:
        await _build_part_paths(child, path_list, part_id_to_name_path)


def _grams_from_material_instance(material_instance: Any) -> float:
    """Extract grams from a material instance."""
    for field_name in ("weightGRM", "weight_g", "weightGrm", "weightgrm"):
        value = getattr(material_instance, field_name, None)
        if isinstance(value, (int, float)):
            return float(value)
    try:
        return float(getattr(material_instance, "weightGRM", 0.0) or 0.0)
    except Exception:
        return 0.0


async def _collect_material_flags_for_part(
    part_node: PartInstance,
    rare_bucket: Dict[str, dict],
    hazardous_bucket: Dict[str, dict],
    part_id_to_name_path: Dict[str, Tuple[str, str]],
) -> None:
    """Fill per-material rare/hazardous buckets with locations and grams."""
    for material_instance in getattr(part_node, "compositeMaterials", []) or []:
        try:
            material_static: MaterialStatic = await material_instance.materialStaticLink.fetch()
        except Exception:
            material_static = None
        if not material_static:
            continue

        part_id = str(part_node.id)
        part_name, part_path = part_id_to_name_path.get(part_id, (part_id, part_id))
        grams = _grams_from_material_instance(material_instance)

        if getattr(material_static, "rareEarth", False):
            agg = rare_bucket.setdefault(material_static.name, {"parts": {}, "gramsTotal": 0.0})
            if part_id not in agg["parts"]:
                agg["parts"][part_id] = {"id": part_id, "name": part_name, "path": part_path, "grams": 0.0}
            agg["parts"][part_id]["grams"] += grams
            agg["gramsTotal"] += grams

        if getattr(material_static, "hazardous", False):
            hazard = hazardous_bucket.setdefault(
                material_static.name, {"warnings": set(), "parts": {}, "gramsTotal": 0.0}
            )
            for warning in getattr(material_static, "warnings", []) or []:
                hazard["warnings"].add(warning)
            if part_id not in hazard["parts"]:
                hazard["parts"][part_id] = {"id": part_id, "name": part_name, "path": part_path, "grams": 0.0}
            hazard["parts"][part_id]["grams"] += grams
            hazard["gramsTotal"] += grams

    for child in getattr(part_node, "compositeParts", []) or []:
        await _collect_material_flags_for_part(child, rare_bucket, hazardous_bucket, part_id_to_name_path)


def _doc_minimal(document_obj: Any) -> Optional[dict]:
    """Return document mapping {name, url}."""
    if document_obj is None:
        return None
    return {
        "name": getattr(document_obj, "name", None) or getattr(document_obj, "url", None),
        "url": getattr(document_obj, "url", None),
    }


def _coerce_datetime(value: Any) -> Optional[datetime]:
    """Make datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=_tz_cls.utc)
    if isinstance(value, _date_cls):
        return datetime(value.year, value.month, value.day, tzinfo=_tz_cls.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=_tz_cls.utc)
        except Exception:
            return None
    return None


def _days_between(later_value: Any, earlier_value: Any) -> Optional[float]:
    """Return whole days between two date-like values."""
    later_dt = _coerce_datetime(later_value)
    earlier_dt = _coerce_datetime(earlier_value)
    if later_dt is None or earlier_dt is None:
        return None
    return float((later_dt - earlier_dt).days)


def _iter_secondary_steps(part_root: PartInstance) -> Iterable[SecondaryValueStep]:
    """Yield SecondaryValueStep-like entries from a root node."""
    for step in getattr(part_root, "partProcessTracking", []) or []:
        yield step


def _get_gridfs_bucket(request: Request) -> AsyncIOMotorGridFSBucket:
    """Access GridFS bucket."""
    return request.app.state.fs


def _qnum(value: Any, default: float = 0.0) -> float:
    """Extract numeric value."""
    try:
        inner = getattr(value, "value", value)
        return float(inner if inner is not None else default)
    except Exception:
        return default


FILES_PARAM = File(..., description="List of image files to upload")
FS_DEPENDENCY = Depends(_get_gridfs_bucket)


# ──────────────────────────────────────────────────────────────────────────────
# DPP Static CRUD
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/", response_model=DPPStatic, response_model_by_alias=True)
async def create_dpp_static(dpp_static: DPPStatic) -> DPPStatic:
    """Create a new DPPStatic."""
    try:
        await dpp_static.insert()
    except HTTPException:
        raise
    except DuplicateKeyError as dup_error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"DPPStatic with id {dpp_static.id} already exists",
        ) from dup_error
    except Exception as exc:
        logger.error("Error inserting DPPStatic: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error while creating DPPStatic.",
        ) from exc

    logger.info("Created DPPStatic %s", dpp_static.id)
    return dpp_static


@router.post("/{dpp_id}/returning-place/", response_model=Place, response_model_by_alias=True)
async def add_returning_place(dpp_id: str, place: Place) -> Place:
    """Create and link a returning place to a DPPStatic."""
    dpp_static = await DPPStatic.get(dpp_id, fetch_links=True)
    if not dpp_static:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"DPPStatic {dpp_id} not found")

    existing_place = await Place.find_one(Place.id == place.id)
    selected_place = existing_place or place
    if not existing_place:
        await place.insert()

    dpp_static.returningPlaces.append(selected_place)
    await dpp_static.save()
    logger.info("Linked returning place %s to DPPStatic %s", selected_place.id, dpp_static.id)
    return selected_place


@router.get(
    "/{dpp_id}/returning-places/",
    response_model=List[ReturningPlaceSummary],
    response_model_by_alias=True,
)
async def get_returning_places_summary(dpp_id: str) -> List[ReturningPlaceSummary]:
    """Summarize returning places for a DPPStatic."""
    dpp_static = await DPPStatic.get(dpp_id, fetch_links=True)
    if not dpp_static:
        return []

    summaries: List[ReturningPlaceSummary] = []
    for link in getattr(dpp_static, "returningPlaces", []) or []:
        try:
            place_obj = await link.fetch() if isinstance(link, Link) else link
            if not place_obj:
                continue
            lat = getattr(place_obj, "latitude", None)
            lon = getattr(place_obj, "longitude", None)
            summaries.append(
                ReturningPlaceSummary(
                    id=getattr(place_obj, "id", None),
                    name=getattr(place_obj, "name", None),
                    gln=str(getattr(place_obj, "id", None)),
                    latitude=lat if isinstance(lat, (int, float)) else None,
                    longitude=lon if isinstance(lon, (int, float)) else None,
                )
            )
        except Exception:
            continue

    return summaries


@router.post("/{dpp_id}/spare/{part_id}", response_model=PartStatic, response_model_by_alias=True)
async def add_spare_part(dpp_id: str, part_id: str) -> PartStatic:
    """Link a spare PartStatic to a DPPStatic."""
    dpp_static = await DPPStatic.get(dpp_id, fetch_links=True)
    if not dpp_static:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"DPPStatic {dpp_id} not found")

    part_static = await PartStatic.get(part_id, fetch_links=True)
    if not part_static:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"PartStatic {part_id} not found")

    if part_static in dpp_static.has_spare_parts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"PartStatic {part_id} is already a spare for DPPStatic {dpp_id}",
        )

    dpp_static.has_spare_parts.append(part_static)
    await dpp_static.save()
    logger.info("Linked spare part %s to DPPStatic %s", part_static.id, dpp_static.id)
    return part_static


# ──────────────────────────────────────────────────────────────────────────────
# DPP Instance CRUD
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/instance/", response_model=List[DPPInstance], response_model_by_alias=True)
async def list_dpp_instances() -> List[DPPInstance]:
    """List all DPPInstance documents."""
    return await DPPInstance.find_all(fetch_links=True).to_list()


@router.post("/instance/", response_model=DPPInstance, response_model_by_alias=True)
async def create_dpp_instance(dpp_instance: DPPInstance) -> DPPInstance:
    """Create a DPPInstance."""
    try:
        await dpp_instance.insert()
    except HTTPException:
        raise
    except DuplicateKeyError as dup_error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"DPPInstance with id {dpp_instance.id} already exists",
        ) from dup_error
    except Exception as exc:
        logger.error("Error inserting DPPInstance: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error while creating DPPInstance.",
        ) from exc

    logger.info("Created DPPInstance %s", dpp_instance.id)
    return dpp_instance


@router.get("/instance/{instance_id}", response_model=DPPInstance, response_model_by_alias=True)
async def get_dpp_instance(instance_id: str) -> DPPInstance:
    """Fetch a DPPInstance by id."""
    instance = await DPPInstance.get(instance_id, fetch_links=True)
    if not instance:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"DPPInstance {instance_id} not found")
    return instance


# ──────────────────────────────────────────────────────────────────────────────
# User summary
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/instance/{instance_id}/user-summary")
async def get_user_summary(instance_id: str, request: Request) -> Dict[str, Any]:
    """
    User summary of the dpp frontend
    """
    instance = await DPPInstance.get(instance_id, fetch_links=["dppStaticLink", "partInstanceLink"])
    if not instance:
        raise HTTPException(status_code=404, detail="DPPInstance not found")

    dpp_static: Optional[DPPStatic] = instance.dppStaticLink
    root_part: Optional[PartInstance] = instance.partInstanceLink

    importer = await _resolve_org(getattr(dpp_static, "importer", None)) if dpp_static else None
    manufacturer = await _resolve_org(getattr(dpp_static, "productManufacturer", None)) if dpp_static else None
    responsible = await _resolve_org(getattr(dpp_static, "responsibleOperator", None)) if dpp_static else None

    part_static_name_cache: Dict[str, str] = {}
    material_static_cache: Dict[str, MaterialStatic] = {}

    async def _part_static_name(part_inst: PartInstance) -> Optional[str]:
        try:
            static_link = getattr(part_inst, "partStaticLink", None)
            if static_link is None:
                return None
            static_obj = await static_link.fetch() if isinstance(static_link, Link) else static_link
            if not static_obj:
                return None
            static_id = getattr(static_obj, "id", None)
            if static_id and static_id in part_static_name_cache:
                return part_static_name_cache[static_id]
            name = getattr(static_obj, "name", None)
            if static_id and name:
                part_static_name_cache[static_id] = name
            return name
        except Exception:
            return None

    async def _material_static(material_instance: Any) -> Optional[MaterialStatic]:
        try:
            link_or_object = getattr(material_instance, "materialStaticLink", None)
            material_static_obj = await link_or_object.fetch() if isinstance(link_or_object, Link) else link_or_object
            if not material_static_obj:
                return None
            static_id = getattr(material_static_obj, "id", None)
            if static_id:
                cached = material_static_cache.get(static_id)
                if cached:
                    return cached
                material_static_cache[static_id] = material_static_obj
            return material_static_obj
        except Exception:
            return None

    linked_sub_dpps_by_part_id: Dict[str, dict] = {}

    total_parts_count = 0
    first_level_parts: List[dict] = []
    fail_state_count = 0

    process_counts: Dict[str, int] = {"transport": 0, "production": 0, "secondary": 0, "total": 0}
    transport_km_parts = 0.0
    transport_km_materials = 0.0

    material_weight_by_name_g: Dict[str, float] = {}
    material_recycled_weight_by_name_g: Dict[str, float] = {}
    material_flag_rare: Dict[str, bool] = {}
    material_flag_hazardous: Dict[str, bool] = {}

    ghg_scopes: Dict[str, Dict[str, Dict[str, float] | float]] = {}

    if root_part:
        for child in getattr(root_part, "compositeParts", []) or []:
            display_name = await _part_static_name(child)
            first_level_parts.append(
                {
                    "id": child.id,
                    "name": display_name,
                    "isModular": bool(getattr(child, "isModular", False)),
                    "hasFailstate": bool(getattr(child, "hasFailstate", False)),
                }
            )

    async def _find_dpp_for_part_id(part_id: str) -> Optional[DPPInstance]:
        try:
            return await DPPInstance.find_one(DPPInstance.partInstanceLink.id == part_id)  # type: ignore[attr-defined]
        except Exception:
            return None

    async def _walk_parts(node_or_link: Any) -> None:
        nonlocal total_parts_count, fail_state_count, transport_km_parts, transport_km_materials

        part_node = await node_or_link.fetch() if isinstance(node_or_link, Link) else node_or_link
        if not isinstance(part_node, PartInstance):
            return

        total_parts_count += 1
        if bool(getattr(part_node, "hasFailstate", False)):
            fail_state_count += 1

        try:
            if root_part and getattr(part_node, "id", None) and part_node.id != root_part.id:
                maybe_instance = await _find_dpp_for_part_id(part_node.id)
                if maybe_instance and maybe_instance.id != instance.id:
                    part_name = await _part_static_name(part_node) or getattr(part_node, "name", None) or part_node.id
                    product_name = None
                    try:
                        static = (
                            await maybe_instance.dppStaticLink.fetch()
                            if isinstance(maybe_instance.dppStaticLink, Link)
                            else maybe_instance.dppStaticLink
                        )
                        product_name = getattr(static, "name", None)
                    except Exception:
                        pass
                    linked_sub_dpps_by_part_id[part_node.id] = {
                        "partId": part_node.id,
                        "partName": part_name,
                        "dppId": maybe_instance.id,
                        "productName": product_name,
                    }
        except Exception:
            pass

        for step in getattr(part_node, "partProcessTracking", []) or []:
            category = _classify_step(step)
            process_counts[category] = process_counts.get(category, 0) + 1
            process_counts["total"] += 1

            if hasattr(step, "distanceKM"):
                transport_km_parts += _qnum(getattr(step, "distanceKM", 0.0))

            for record in getattr(step, "ghgEmissionRecords", []) or []:
                scope = getattr(record, "scope", None)
                scope_key = scope.value if hasattr(scope, "value") else (str(scope) if scope else "Unknown")
                bucket = ghg_scopes.setdefault(scope_key, {"total": 0.0, "byCategory": {}})
                value = _qnum(getattr(record, "emissions_kg_co2e", 0.0))
                bucket["total"] = float(bucket["total"]) + value
                if scope_key == "Scope 3" or (hasattr(scope, "name") and "3" in str(scope)):
                    scope3_category = getattr(record, "scope3_category", None)
                    category_key = (
                        scope3_category.value
                        if hasattr(scope3_category, "value")
                        else (str(scope3_category) if scope3_category else "Uncategorized")
                    )
                else:
                    category_key = "direct"
                by_category = bucket["byCategory"]
                by_category[category_key] = float(by_category.get(category_key, 0.0)) + value

        for material_instance in getattr(part_node, "compositeMaterials", []) or []:
            material_static_obj = await _material_static(material_instance)
            material_name = getattr(material_static_obj, "name", None) or "Unknown"
            grams = _grams_from_material_instance(material_instance)
            recycled_percent = _qnum(getattr(material_instance, "percentRecycled", 0.0))

            material_weight_by_name_g[material_name] = material_weight_by_name_g.get(material_name, 0.0) + grams
            material_recycled_weight_by_name_g[material_name] = material_recycled_weight_by_name_g.get(
                material_name, 0.0
            ) + (grams * (recycled_percent / 100.0))

            if material_static_obj is not None:
                if getattr(material_static_obj, "rareEarth", False):
                    material_flag_rare[material_name] = True
                if getattr(material_static_obj, "hazardous", False):
                    material_flag_hazardous[material_name] = True

            for step in getattr(material_instance, "materialProcessTracking", []) or []:
                category = _classify_step(step)
                process_counts[category] = process_counts.get(category, 0) + 1
                process_counts["total"] += 1

                if hasattr(step, "distanceKM"):
                    transport_km_materials += _qnum(getattr(step, "distanceKM", 0.0))

                for record in getattr(step, "ghgEmissionRecords", []) or []:
                    scope = getattr(record, "scope", None)
                    scope_key = scope.value if hasattr(scope, "value") else (str(scope) if scope else "Unknown")
                    bucket = ghg_scopes.setdefault(scope_key, {"total": 0.0, "byCategory": {}})
                    value = _qnum(getattr(record, "emissions_kg_co2e", 0.0))
                    bucket["total"] = float(bucket["total"]) + value
                    if scope_key == "Scope 3" or (hasattr(scope, "name") and "3" in str(scope)):
                        scope3_category = getattr(record, "scope3_category", None)
                        category_key = (
                            scope3_category.value
                            if hasattr(scope3_category, "value")
                            else (str(scope3_category) if scope3_category else "Uncategorized")
                        )
                    else:
                        category_key = "direct"
                    by_category = bucket["byCategory"]
                    by_category[category_key] = float(by_category.get(category_key, 0.0)) + value

        for child in getattr(part_node, "compositeParts", []) or []:
            await _walk_parts(child)

    if root_part:
        await _walk_parts(root_part)

    total_weight_g = sum(material_weight_by_name_g.values()) or 0.0
    total_recycled_weight_g = sum(material_recycled_weight_by_name_g.values()) or 0.0

    materials_by_name = [
        {
            "name": material_name,
            "mass": float(weight_g),
            "percent": float((weight_g / total_weight_g) * 100.0) if total_weight_g > 0 else 0.0,
        }
        for material_name, weight_g in material_weight_by_name_g.items()
    ]
    materials_by_name.sort(key=lambda entry: entry["mass"], reverse=True)

    materials_by_name_recycled = [
        {
            "name": material_name,
            "recycledPercent": float((material_recycled_weight_by_name_g.get(material_name, 0.0) / weight_g) * 100.0)
            if weight_g > 0
            else 0.0,
            "virginPercent": float(
                100.0 - ((material_recycled_weight_by_name_g.get(material_name, 0.0) / weight_g) * 100.0)
            )
            if weight_g > 0
            else 100.0,
        }
        for material_name, weight_g in material_weight_by_name_g.items()
    ]
    materials_by_name_recycled.sort(key=lambda entry: material_weight_by_name_g.get(entry["name"], 0.0), reverse=True)

    overall_recycled_percent = float((total_recycled_weight_g / total_weight_g) * 100.0) if total_weight_g > 0 else 0.0
    total_rare_weight = sum(material_weight_by_name_g[name] for name, is_rare in material_flag_rare.items() if is_rare)
    rare_earth_percent = float((total_rare_weight / total_weight_g) * 100.0) if total_weight_g > 0 else 0.0

    ghg_block: Dict[str, Any] = {"unit": "kgCO2e", "scopes": {}, "byCategory": {}}
    for scope_key, bucket in ghg_scopes.items():
        total_val = round(float(bucket.get("total", 0.0)), 3)
        ghg_block["scopes"][scope_key] = total_val
        for cat_name, value in (bucket.get("byCategory", {}) or {}).items():
            ghg_block["byCategory"][cat_name] = ghg_block["byCategory"].get(cat_name, 0.0) + float(value)
    ghg_block["byCategory"] = {k: round(v, 3) for k, v in ghg_block["byCategory"].items()}
    ghg_block["total"] = round(sum(ghg_block["scopes"].values()), 3)

    documents: List[dict] = []
    compliance: Optional[dict] = None
    if dpp_static:
        docs_list = [
            _doc_minimal(getattr(dpp_static, "dataSheet", None)),
            _doc_minimal(getattr(dpp_static, "installationOperatingGuide", None)),
            _doc_minimal(getattr(dpp_static, "repairAndServiceManual", None)),
            _doc_minimal(getattr(dpp_static, "DisassemblyInstructions", None)),
            _doc_minimal(getattr(dpp_static, "recyclingEOLInstructions", None)),
        ]
        documents = [entry for entry in docs_list if entry]
        compliance = {
            "ceConformityDeclaration": _doc_minimal(getattr(dpp_static, "ceConformityDeclaration", None)),
            "ecodesignConformityDeclaration": _doc_minimal(getattr(dpp_static, "ecodesignConformityDeclaration", None)),
        }

    returning_places: List[dict] = []
    if dpp_static:
        for link in getattr(dpp_static, "returningPlaces", []) or []:
            try:
                place_obj = await link.fetch() if isinstance(link, Link) else link
                if not place_obj:
                    continue
                lat = getattr(place_obj, "latitude", None)
                lon = getattr(place_obj, "longitude", None)
                returning_places.append(
                    {
                        "id": getattr(place_obj, "id", None),
                        "name": getattr(place_obj, "name", None),
                        "gln": str(getattr(place_obj, "id", None)),
                        "latitude": float(lat) if isinstance(lat, (int, float)) else None,
                        "longitude": float(lon) if isinstance(lon, (int, float)) else None,
                    }
                )
            except Exception:
                continue

    images_for_web: List[dict] = []
    if dpp_static:
        for ref in getattr(dpp_static, "image_file_ids", []) or []:
            try:
                images_for_web.append(
                    {
                        "file_id": str(ref.file_id),
                        "filename": ref.filename,
                        "url": str(request.url_for("get_image", dpp_id=dpp_static.id, file_id=str(ref.file_id))),
                    }
                )
            except Exception:
                continue

    counters = {
        "cleaning": getattr(instance, "cleaningCount", 0.0),
        "chalk": getattr(instance, "chalkCount", 0.0),
        "brewing": getattr(instance, "brewingCount", 0.0),
        "grinding": getattr(instance, "coffeeGrindingCount", 0.0),
        "operatingHRS": getattr(instance, "operatingHRS", 0.0),
    }
    extra_static = {
        "heightCM": getattr(dpp_static, "heightCM", None) if dpp_static else None,
        "widthCM": getattr(dpp_static, "widthCM", None) if dpp_static else None,
        "depthCM": getattr(dpp_static, "depthCM", None) if dpp_static else None,
        "weightGRM": getattr(dpp_static, "weightGRM", None) if dpp_static else None,
        "taricCode": getattr(dpp_static, "taricCode", None) if dpp_static else None,
    }

    transport_distance = {
        "totalKM": round(transport_km_parts + transport_km_materials, 3),
        "partsKM": round(transport_km_parts, 3),
        "materialsKM": round(transport_km_materials, 3),
    }

    return {
        "id": instance.id,
        "staticId": dpp_static.id if dpp_static else None,
        "gtin": getattr(dpp_static, "id", None) if dpp_static else None,
        "gs1DigitalLink": getattr(dpp_static, "GS1DigitalLink", None) if dpp_static else None,
        "productName": getattr(dpp_static, "name", None) if dpp_static else None,
        "importer": importer,
        "manufacturer": manufacturer,
        "responsibleOperator": responsible,
        "importerName": importer["name"] if importer else None,
        "manufacturerName": manufacturer["name"] if manufacturer else None,
        "responsibleOperatorName": responsible["name"] if responsible else None,
        "dateOfPublication": getattr(dpp_static, "dateOfPublication", None) if dpp_static else None,
        "dateOfDeclaration": getattr(instance, "dateOfDeclaration", None),
        "endOfGuarantee": getattr(instance, "endOfGuarantee", None),
        "guaranteeDescription": getattr(dpp_static, "guaranteeDescription", None) if dpp_static else None,
        "extraStatic": extra_static,
        "parts": {"firstLevel": first_level_parts, "totalCount": total_parts_count},
        "materials": {
            "byName": materials_by_name,
            "byNameRecycled": materials_by_name_recycled,
            "overallRecycledPercent": round(overall_recycled_percent, 2),
            "rareEarthPercent": round(rare_earth_percent, 2),
        },
        "processSteps": process_counts,
        "transportDistance": transport_distance,
        "ghg": ghg_block,
        "returningPlaces": returning_places,
        "images": images_for_web,
        "counters": counters,
        "backupLink": getattr(dpp_static, "backupLink", None) if dpp_static else getattr(instance, "backupLink", None),
        "compliance": compliance,
        "documents": documents,
        "failState": {"count": int(fail_state_count), "hasAny": bool(fail_state_count > 0)},
        "linkedDpps": sorted(list(linked_sub_dpps_by_part_id.values()), key=lambda x: (x.get("partName") or "")),
    }


# ──────────────────────────────────────────────────────────────────────────────
# EoL summary
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/instance/{instance_id}/eol-summary")
async def get_eol_summary(instance_id: str, request: Request) -> Dict[str, Any]:
    """Summarize rare/hazardous materials and locations to support EoL handling."""
    instance = await DPPInstance.get(instance_id, fetch_links=["dppStaticLink", "partInstanceLink"])
    if not instance:
        raise HTTPException(status_code=404, detail="DPPInstance not found")

    dpp_static: Optional[DPPStatic] = instance.dppStaticLink
    root_part: Optional[PartInstance] = instance.partInstanceLink

    responsible = await _resolve_org(getattr(dpp_static, "responsibleOperator", None)) if dpp_static else None
    linked_sub_dpps_by_part_id: Dict[str, dict] = {}

    async def _find_dpp_for_part_id(part_id: str) -> Optional[DPPInstance]:
        try:
            return await DPPInstance.find_one(DPPInstance.partInstanceLink.id == part_id)
        except Exception:
            return None

    part_id_to_name_path: Dict[str, Tuple[str, str]] = {}
    if root_part:
        await _build_part_paths(root_part, [], part_id_to_name_path)

    first_level: List[dict] = []
    total_parts_count = 0
    if root_part:
        for child in getattr(root_part, "compositeParts", []) or []:
            display_name = await _part_name_from_instance(child)
            first_level.append(
                {
                    "id": child.id,
                    "name": display_name,
                    "isModular": bool(getattr(child, "isModular", False)),
                    "hasFailstate": bool(getattr(child, "hasFailstate", False)),
                }
            )
        total_parts_count = _count_subtree(root_part)

    material_weight_by_name_g: Dict[str, float] = {}
    material_recycled_weight_by_name_g: Dict[str, float] = {}
    material_purity_weighted_sum: Dict[str, float] = {}
    material_purity_mass_sum: Dict[str, float] = {}
    rare_bucket: Dict[str, dict] = {}
    hazardous_bucket: Dict[str, dict] = {}
    material_static_cache: Dict[str, MaterialStatic] = {}

    async def _material_static(material_instance: Any) -> Optional[MaterialStatic]:
        link_or_object = getattr(material_instance, "materialStaticLink", None)
        if not link_or_object:
            return None
        static_id = _extract_id_from_link(link_or_object) or getattr(link_or_object, "id", None)
        static_id = str(static_id) if static_id else None

        if static_id and static_id in material_static_cache:
            return material_static_cache[static_id]

        try:
            material_static_obj = await (link_or_object.fetch() if isinstance(link_or_object, Link) else link_or_object)
        except Exception:
            material_static_obj = None

        if material_static_obj is not None and static_id:
            material_static_cache[static_id] = material_static_obj
        return material_static_obj

    async def _walk_collect(part_node: PartInstance) -> None:
        part_id = str(part_node.id)
        part_name, part_path = part_id_to_name_path.get(part_id, (part_id, part_id))

        try:
            if root_part and part_id != str(root_part.id):
                maybe_instance = await _find_dpp_for_part_id(part_id)
                if maybe_instance and maybe_instance.id != instance.id:
                    product_name = None
                    try:
                        static = await (
                            maybe_instance.dppStaticLink.fetch()
                            if isinstance(maybe_instance.dppStaticLink, Link)
                            else maybe_instance.dppStaticLink
                        )
                        product_name = getattr(static, "name", None)
                    except Exception:
                        pass
                    linked_sub_dpps_by_part_id[part_id] = {
                        "partId": part_id,
                        "partName": part_name,
                        "dppId": maybe_instance.id,
                        "productName": product_name,
                    }
        except Exception:
            pass

        for material_instance in getattr(part_node, "compositeMaterials", []) or []:
            material_static_obj = await _material_static(material_instance)
            material_name = getattr(material_static_obj, "name", None) or "Unknown"
            grams = _grams_from_material_instance(material_instance)
            recycled_percent = _qnum(getattr(material_instance, "percentRecycled", 0.0))
            purity_raw = getattr(material_instance, "purityLevel", None)

            try:
                purity = float(purity_raw) if purity_raw is not None else None
                if purity is not None and purity > 1.5:
                    purity = purity / 100.0
                if purity is not None:
                    purity = max(0.0, min(1.0, purity))
            except Exception:
                purity = None

            material_weight_by_name_g[material_name] = material_weight_by_name_g.get(material_name, 0.0) + grams
            material_recycled_weight_by_name_g[material_name] = material_recycled_weight_by_name_g.get(
                material_name, 0.0
            ) + grams * (recycled_percent / 100.0)
            if purity is not None and grams > 0:
                material_purity_weighted_sum[material_name] = material_purity_weighted_sum.get(material_name, 0.0) + (
                    purity * grams
                )
                material_purity_mass_sum[material_name] = material_purity_mass_sum.get(material_name, 0.0) + grams

            if material_static_obj is not None and getattr(material_static_obj, "rareEarth", False):
                rare_info = rare_bucket.setdefault(material_name, {"parts": {}, "gramsTotal": 0.0})
                if part_id not in rare_info["parts"]:
                    rare_info["parts"][part_id] = {"id": part_id, "name": part_name, "path": part_path, "grams": 0.0}
                rare_info["parts"][part_id]["grams"] += grams
                rare_info["gramsTotal"] += grams

            if material_static_obj is not None and getattr(material_static_obj, "hazardous", False):
                hazardous_info = hazardous_bucket.setdefault(
                    material_name, {"warnings": set(), "parts": {}, "gramsTotal": 0.0}
                )
                for warning in getattr(material_static_obj, "warnings", []) or []:
                    hazardous_info["warnings"].add(warning)
                if part_id not in hazardous_info["parts"]:
                    hazardous_info["parts"][part_id] = {
                        "id": part_id,
                        "name": part_name,
                        "path": part_path,
                        "grams": 0.0,
                    }
                hazardous_info["parts"][part_id]["grams"] += grams
                hazardous_info["gramsTotal"] += grams

        for child in getattr(part_node, "compositeParts", []) or []:
            await _walk_collect(child)

    if root_part:
        await _walk_collect(root_part)

    total_weight = sum(material_weight_by_name_g.values()) or 0.0
    total_recycled = sum(material_recycled_weight_by_name_g.values()) or 0.0

    materials_by_name = [
        {
            "name": name,
            "mass": float(weight_g),
            "percent": float((weight_g / total_weight) * 100.0) if total_weight > 0 else 0.0,
        }
        for name, weight_g in material_weight_by_name_g.items()
    ]
    materials_by_name.sort(key=lambda entry: entry["mass"], reverse=True)

    materials_by_name_recycled: List[dict] = []
    for name, weight_g in material_weight_by_name_g.items():
        recycled_pct = (
            float((material_recycled_weight_by_name_g.get(name, 0.0) / weight_g) * 100.0) if weight_g > 0 else 0.0
        )
        virgin_pct = float(100.0 - recycled_pct) if weight_g > 0 else 100.0
        mass_sum = material_purity_mass_sum.get(name, 0.0)
        if mass_sum > 0:
            purity_pct = float(material_purity_weighted_sum.get(name, 0.0) / mass_sum) * 100.0
        else:
            purity_pct = None
        materials_by_name_recycled.append(
            {"name": name, "recycledPercent": recycled_pct, "virginPercent": virgin_pct, "purityPercent": purity_pct}
        )
    materials_by_name_recycled.sort(key=lambda entry: material_weight_by_name_g.get(entry["name"], 0.0), reverse=True)

    overall_recycled_percent = float((total_recycled / total_weight) * 100.0) if total_weight > 0 else 0.0
    rare_names = set(rare_bucket.keys())
    rare_weight = sum(material_weight_by_name_g.get(name, 0.0) for name in rare_names)
    rare_earth_percent = float((rare_weight / total_weight) * 100.0) if total_weight > 0 else 0.0

    mass_by_material = {entry["name"]: float(entry.get("mass") or 0.0) for entry in materials_by_name}

    rare_parts_grouped: List[dict] = []
    for material_name in sorted(rare_bucket.keys()):
        info = rare_bucket[material_name]
        parts_list = list(info["parts"].values())
        grams_total = info["gramsTotal"] if info["gramsTotal"] > 0 else mass_by_material.get(material_name, 0.0)
        rare_parts_grouped.append({"material": material_name, "gramsTotal": float(grams_total), "parts": parts_list})

    hazardous_list: List[dict] = []
    for material_name in sorted(hazardous_bucket.keys()):
        info = hazardous_bucket[material_name]
        hazardous_list.append(
            {
                "material": material_name,
                "warnings": sorted(list(info["warnings"])),
                "gramsTotal": float(info["gramsTotal"]),
                "parts": list(info["parts"].values()),
            }
        )
    hazardous_list.sort(key=lambda entry: entry["material"])

    documents_block = {
        "disassembly": _doc_minimal(getattr(dpp_static, "DisassemblyInstructions", None)) if dpp_static else None,
        "recycling": _doc_minimal(getattr(dpp_static, "recyclingEOLInstructions", None)) if dpp_static else None,
    }
    counters = {
        "cleaning": getattr(instance, "cleaningCount", 0.0),
        "chalk": getattr(instance, "chalkCount", 0.0),
        "brewing": getattr(instance, "brewingCount", 0.0),
        "grinding": getattr(instance, "coffeeGrindingCount", 0.0),
        "operatingHRS": getattr(instance, "operatingHRS", 0.0),
    }

    def _cost_eur(step: Any) -> float:
        for field_name in ("costEur", "costEUR", "cost", "priceEUR", "priceEur"):
            value = getattr(step, field_name, None)
            if isinstance(value, (int, float)):
                return float(value)
        return 0.0

    def _type_name(step: Any) -> str:
        label = getattr(step, "type_", None) or getattr(step, "type", None)
        return label if isinstance(label, str) and label else step.__class__.__name__

    def _bucket_from_type(type_name: str) -> Optional[str]:
        label = (type_name or "").lower()
        if "repair" in label:
            return "Repair"
        if "replace" in label:
            return "Replace"
        if "clean" in label:
            return "Cleaning"
        if "remanufactur" in label:
            return "Remanufacturing"
        if "refurb" in label:
            return "Refurbishment"
        return None

    def _is_secondary_like(step: Any) -> bool:
        try:
            return isinstance(step, SecondaryValueStep)
        except Exception:
            name_lower = step.__class__.__name__.lower()
            return any(
                key in name_lower
                for key in ("secondaryvaluestep", "repair", "replace", "clean", "refurb", "remanufactur")
            )

    service_totals = {
        "costEUR": 0.0,
        "Repair": 0,
        "Replace": 0,
        "Cleaning": 0,
        "Remanufacturing": 0,
        "Refurbishment": 0,
    }
    if root_part:
        for step in getattr(root_part, "partProcessTracking", []) or []:
            if not _is_secondary_like(step):
                continue
            bucket_name = _bucket_from_type(_type_name(step))
            if not bucket_name:
                continue
            service_totals["costEUR"] += _cost_eur(step)
            service_totals[bucket_name] += 1

    return {
        "id": instance.id,
        "staticId": dpp_static.id if dpp_static else None,
        "productName": getattr(dpp_static, "name", None) if dpp_static else None,
        "productClass": getattr(dpp_static, "productClass", None) if dpp_static else None,
        "responsibleOperator": responsible,
        "weeeRegistrationNumber": getattr(dpp_static, "weeeRegistrationNumber", None) if dpp_static else None,
        "expectedMtbfHRS": getattr(dpp_static, "expectedMtbfHRS", None) if dpp_static else None,
        "documents": documents_block,
        "counters": counters,
        "materials": {
            "byName": materials_by_name,
            "byNameRecycled": materials_by_name_recycled,
            "overallRecycledPercent": overall_recycled_percent,
            "rareEarthPercent": rare_earth_percent,
        },
        "rareEarthParts": rare_parts_grouped,
        "hazardous": hazardous_list,
        "parts": {"firstLevel": first_level, "totalCount": total_parts_count},
        "linkedDpps": sorted(list(linked_sub_dpps_by_part_id.values()), key=lambda x: (x.get("partName") or "")),
        "service": {"totals": service_totals},
    }


# =============================================================================
# Service summary
# =============================================================================


@router.get("/instance/{instance_id}/service-summary")
async def get_service_summary(instance_id: str, request: Request) -> Dict[str, Any]:
    """
    Service summary for a DPP instance for the frontend
    """
    name_cache = getattr(get_service_summary, "_ps_name_cache", None) or {}
    get_service_summary._ps_name_cache = name_cache
    NAME_TTL_SECONDS = getattr(get_service_summary, "_ps_name_ttl", 600.0)

    def get_name_from_cache(part_static_id: str) -> Optional[str]:
        cached = name_cache.get(part_static_id)
        if not cached:
            return None
        display_name, cached_at = cached
        if monotonic() - cached_at <= NAME_TTL_SECONDS:
            return display_name
        name_cache.pop(part_static_id, None)
        return None

    def put_name_in_cache(part_static_id: str, display_name: str) -> None:
        name_cache[part_static_id] = (display_name, monotonic())

    mtbf_cache = getattr(get_service_summary, "_ps_mtbf_cache", None) or {}
    get_service_summary._ps_mtbf_cache = mtbf_cache
    MTBF_TTL_SECONDS = getattr(get_service_summary, "_ps_mtbf_ttl", 600.0)

    def get_mtbf_from_cache(part_static_id: str) -> Optional[float]:
        cached = mtbf_cache.get(part_static_id)
        if not cached:
            return None
        value, cached_at = cached
        if monotonic() - cached_at <= MTBF_TTL_SECONDS:
            return value
        mtbf_cache.pop(part_static_id, None)
        return None

    def put_mtbf_in_cache(part_static_id: str, mtbf_value: Optional[float]) -> None:
        mtbf_cache[part_static_id] = (mtbf_value, monotonic())

    instance = await DPPInstance.get(instance_id, fetch_links=["dppStaticLink", "partInstanceLink"])
    if not instance:
        raise HTTPException(status_code=404, detail="DPPInstance not found")

    dpp_static: Optional[DPPStatic] = instance.dppStaticLink
    root_part: Optional[PartInstance] = instance.partInstanceLink

    flat_parts: List[PartInstance] = []
    parent_by_part_id: Dict[str, Optional[str]] = {}

    def collect_parts(node: PartInstance, parent_id: Optional[str]) -> None:
        node_id = str(node.id)
        flat_parts.append(node)
        parent_by_part_id[node_id] = parent_id
        for child in getattr(node, "compositeParts", []) or []:
            collect_parts(child, node_id)

    if root_part:
        collect_parts(root_part, None)

    def static_id_from_link(link_or_obj: Any) -> Optional[str]:
        return _extract_id_from_link(link_or_obj) if link_or_obj is not None else None

    static_ids_in_tree: set[str] = set()
    part_to_static_id: Dict[str, Optional[str]] = {}
    for part in flat_parts:
        part_id = str(part.id)
        static_id = static_id_from_link(getattr(part, "partStaticLink", None))
        if static_id:
            static_ids_in_tree.add(static_id)
        part_to_static_id[part_id] = static_id

    detached_parts = list(getattr(root_part, "historyOfDetachedParts", []) or []) if root_part else []
    static_ids_detached: set[str] = set()
    for detached in detached_parts:
        static_id = static_id_from_link(getattr(detached, "partStaticLink", None))
        if static_id:
            static_ids_detached.add(static_id)

    spare_part_ids: List[str] = []
    try:
        for spare in getattr(dpp_static, "has_spare_parts", None) or []:
            static_id = (
                _extract_id_from_link(spare)
                if isinstance(spare, Link)
                else (
                    spare.get("$id") or spare.get("id") or spare.get("_id")
                    if isinstance(spare, dict)
                    else (spare if isinstance(spare, str) else getattr(spare, "id", None))
                )
            )
            if not static_id:
                continue
            if not isinstance(spare, (Link, dict, str)):
                display_name = getattr(spare, "name", None)
                if display_name:
                    put_name_in_cache(str(static_id), display_name)
                try:
                    put_mtbf_in_cache(str(static_id), float(spare.mtbfHRS))
                except Exception:
                    put_mtbf_in_cache(str(static_id), None)
            spare_part_ids.append(str(static_id))
    except Exception:
        pass

    missing_name_ids = [
        sid
        for sid in (static_ids_in_tree | static_ids_detached | set(spare_part_ids))
        if get_name_from_cache(sid) is None
    ]
    if missing_name_ids:
        try:
            static_docs = await PartStatic.find(In(PartStatic.id, missing_name_ids)).to_list()
            for static_doc in static_docs:
                static_id = str(getattr(static_doc, "id", "") or "")
                display_name = getattr(static_doc, "name", None)
                if static_id and display_name:
                    put_name_in_cache(static_id, display_name)
                try:
                    put_mtbf_in_cache(static_id, float(static_doc.mtbfHRS))
                except Exception:
                    put_mtbf_in_cache(static_id, None)
        except Exception:
            pass

    missing_mtbf_ids = [sid for sid in static_ids_in_tree if get_mtbf_from_cache(sid) is None]
    if missing_mtbf_ids:
        try:
            static_docs = await PartStatic.find(In(PartStatic.id, missing_mtbf_ids)).to_list()
            for static_doc in static_docs:
                static_id = str(getattr(static_doc, "id", "") or "")
                try:
                    put_mtbf_in_cache(static_id, float(static_doc.mtbfHRS))
                except Exception:
                    put_mtbf_in_cache(static_id, None)
        except Exception:
            pass

    display_name_by_part_id: Dict[str, str] = {}
    for part in flat_parts:
        part_id = str(part.id)
        static_id = part_to_static_id.get(part_id)
        display_name = get_name_from_cache(static_id) if static_id else None
        display_name_by_part_id[part_id] = display_name or getattr(part, "name", None) or part_id

    breadcrumb_by_part_id: Dict[str, Tuple[str, str]] = {}

    def build_paths(node: PartInstance, crumbs: List[str]) -> None:
        node_id = str(node.id)
        node_name = display_name_by_part_id.get(node_id, node_id)
        current = [*crumbs, node_name]
        breadcrumb_by_part_id[node_id] = (node_name, " \u2192 ".join(current))
        for child in getattr(node, "compositeParts", []) or []:
            build_paths(child, current)

    if root_part:
        build_paths(root_part, [])

    detached_name_by_id: Dict[str, str] = {}
    for detached in detached_parts:
        detached_id = str(getattr(detached, "id", "") or "")
        if not detached_id:
            continue
        static_id = static_id_from_link(getattr(detached, "partStaticLink", None))
        display_name = get_name_from_cache(static_id) if static_id else None
        detached_name_by_id[detached_id] = display_name or getattr(detached, "name", None) or detached_id

    first_level: List[dict] = []
    total_parts_count = 0
    if root_part:
        for child in getattr(root_part, "compositeParts", []) or []:
            child_id = str(child.id)
            first_level.append(
                {
                    "id": child.id,
                    "name": display_name_by_part_id.get(child_id, child_id),
                    "isModular": getattr(child, "isModular", False),
                    "hasFailstate": getattr(child, "hasFailstate", False),
                }
            )
        total_parts_count = len(flat_parts)

    top_has_failstate = bool(getattr(root_part, "hasFailstate", False)) if root_part else False
    first_level_fail_count = sum(1 for child in first_level if child.get("hasFailstate"))
    product_has_fail = top_has_failstate or first_level_fail_count > 0
    product_fail_count = (1 if top_has_failstate else 0) + first_level_fail_count

    failing_parts: List[dict] = []
    if root_part:

        def walk_and_collect_fails(node: PartInstance) -> None:
            node_id = str(node.id)
            if getattr(node, "hasFailstate", False):
                name, path = breadcrumb_by_part_id.get(
                    node_id,
                    (display_name_by_part_id.get(node_id, node_id), display_name_by_part_id.get(node_id, node_id)),
                )
                failing_parts.append({"id": node_id, "name": name, "path": path})
            for child in getattr(node, "compositeParts", []) or []:
                walk_and_collect_fails(child)

        walk_and_collect_fails(root_part)

    spare_parts: List[dict] = [
        {"id": static_id, "name": (get_name_from_cache(static_id) or None)} for static_id in spare_part_ids
    ]

    tools_for_maintenance = list(getattr(dpp_static, "toolsForMaintenance", []) or []) if dpp_static else []
    qualification_for_repair = getattr(dpp_static, "qualificationForRepair", None) if dpp_static else None
    document_links = {
        "repairManual": _doc_minimal(getattr(dpp_static, "repairAndServiceManual", None)) if dpp_static else None,
        "disassembly": _doc_minimal(getattr(dpp_static, "DisassemblyInstructions", None)) if dpp_static else None,
    }

    date_of_declaration = getattr(instance, "dateOfDeclaration", None)
    end_of_guarantee = getattr(instance, "endOfGuarantee", None)
    guarantee_description = getattr(dpp_static, "guaranteeDescription", None) if dpp_static else None
    counters = {
        "operatingHRS": getattr(instance, "operatingHRS", 0.0),
        "cleaning": getattr(instance, "cleaningCount", 0.0),
        "chalk": getattr(instance, "chalkCount", 0.0),
        "brewing": getattr(instance, "brewingCount", 0.0),
        "grinding": getattr(instance, "coffeeGrindingCount", 0.0),
    }
    expected_mtbf_hrs = getattr(dpp_static, "expectedMtbfHRS", None) if dpp_static else None

    operating_hours = float(counters.get("operatingHRS") or 0.0)
    try:
        product_mtbf_hrs = float(expected_mtbf_hrs) if expected_mtbf_hrs is not None else None
    except Exception:
        product_mtbf_hrs = None
    remaining_hours = (
        max(0.0, product_mtbf_hrs - operating_hours) if isinstance(product_mtbf_hrs, (int, float)) else None
    )
    mtbf_exceeded = bool(operating_hours >= product_mtbf_hrs) if isinstance(product_mtbf_hrs, (int, float)) else False

    product_age_days = None
    try:
        declared_at = _coerce_datetime(date_of_declaration)
        if declared_at is not None:
            now_utc = datetime.now(_tz_cls.utc)
            product_age_days = max(0, int((now_utc - declared_at).total_seconds() // 86400))
    except Exception:
        product_age_days = None

    root_service_steps = list(_iter_secondary_steps(root_part)) if root_part else []

    def cost_eur(step: Any) -> float:
        for field_name in ("costEur", "costEUR", "cost", "priceEUR", "priceEur"):
            value = getattr(step, field_name, None)
            if isinstance(value, (int, float)):
                return float(value)
        return 0.0

    def type_label(step: Any) -> str:
        label = getattr(step, "type_", None) or getattr(step, "type", None)
        return label if isinstance(label, str) and label else step.__class__.__name__

    def target_part_ids(step: Any) -> Set[str]:
        targets: Set[str] = set()
        for field_name in ("repairedPartId", "replacedPartId", "cleanedPartId"):
            value = getattr(step, field_name, None)
            if value:
                targets.add(str(value))
        for field_name in ("repairedPartIds", "cleanedPartIds"):
            value_many = getattr(step, field_name, None)
            if value_many and isinstance(value_many, (list, tuple, set)):
                for item in value_many:
                    if item:
                        targets.add(str(item))
        if hasattr(step, "replacedAndNewParts"):
            for pair in getattr(step, "replacedAndNewParts", []) or []:
                if pair and isinstance(pair, (list, tuple)) and pair[0]:
                    targets.add(str(pair[0]))
        return targets

    def bucket_from_type(type_name: str) -> Optional[str]:
        lower = (type_name or "").lower()
        if "repair" in lower:
            return "Repair"
        if "replace" in lower:
            return "Replace"
        if "clean" in lower:
            return "Cleaning"
        if "remanufactur" in lower:
            return "Remanufacturing"
        if "refurb" in lower:
            return "Refurbishment"
        return None

    prepared_steps: List[Tuple[str, float, Set[str]]] = []
    for step in root_service_steps:
        step_type_label = type_label(step)
        bucket = bucket_from_type(step_type_label)
        if not bucket:
            continue
        prepared_steps.append((bucket, cost_eur(step), target_part_ids(step)))

    detached_ids: Set[str] = {
        str(getattr(detached, "id", "")) for detached in detached_parts if getattr(detached, "id", None)
    }
    per_part_stats: Dict[str, dict] = {}
    if root_part:
        for part in flat_parts:
            per_part_stats[str(part.id)] = {
                "costEUR": 0.0,
                "Repair": 0,
                "Replace": 0,
                "Cleaning": 0,
                "Remanufacturing": 0,
                "Refurbishment": 0,
            }

        root_id = str(root_part.id)

        def list_ancestors(part_id: str) -> List[str]:
            lineage: List[str] = []
            current = part_id
            while current is not None:
                lineage.append(current)
                current = parent_by_part_id.get(current)
            return lineage

        for bucket, step_cost, targets in prepared_steps:
            nodes_to_credit: Set[str] = set()
            for target_id in targets:
                if target_id in parent_by_part_id:
                    nodes_to_credit.update(list_ancestors(target_id))
            if targets & detached_ids:
                nodes_to_credit.add(root_id)
            for node_id in nodes_to_credit:
                agg = per_part_stats[node_id]
                agg["costEUR"] += float(step_cost or 0.0)
                agg[bucket] += 1

    def is_secondary_like(step: Any) -> bool:
        try:
            return isinstance(step, SecondaryValueStep)
        except Exception:
            class_name = step.__class__.__name__.lower()
            return any(
                key in class_name
                for key in ("secondaryvaluestep", "repair", "replace", "clean", "refurb", "remanufactur")
            )

    def short_type(step: Any) -> str:
        return type_label(step).replace("ServiceStep", "").replace("Step", "")

    secondary_value_steps: List[dict] = []
    for step in root_service_steps:
        if not is_secondary_like(step):
            continue
        ids_for_step = target_part_ids(step)
        part_names = [
            display_name_by_part_id.get(pid) or detached_name_by_id.get(pid) or pid for pid in ids_for_step or []
        ]
        raw_observed = getattr(step, "observedSymptoms", None)
        if isinstance(raw_observed, str) and raw_observed.strip():
            observed_list = [x.strip() for x in raw_observed.split(",") if x.strip()]
        elif isinstance(raw_observed, (list, tuple)):
            observed_list = [str(x).strip() for x in raw_observed if str(x).strip()]
        else:
            observed_list = []
        secondary_value_steps.append(
            {
                "type": short_type(step),
                "costEUR": getattr(step, "costEur", None)
                or getattr(step, "costEUR", None)
                or getattr(step, "cost", None),
                "beginDate": getattr(step, "beginDate", None),
                "diagnose": getattr(step, "diagnose", None) or getattr(step, "diagnosis", None),
                "observedSymptoms": observed_list,
                "partNames": part_names,
            }
        )

    symptom_to_diagnoses: Dict[str, Counter] = defaultdict(Counter)
    symptom_to_instance_ids: Dict[str, Set[str]] = defaultdict(set)
    diagnosis_cost_samples: Dict[str, List[float]] = defaultdict(list)
    diagnosis_days_samples: Dict[str, List[float]] = defaultdict(list)

    try:
        sibling_instances: List[DPPInstance] = await DPPInstance.find(
            DPPInstance.dppStaticLink.id == (dpp_static.id if dpp_static else None),
            fetch_links=["partInstanceLink"],
        ).to_list()
    except Exception:
        sibling_instances = [instance]

    for other_instance in sibling_instances:
        other_root = getattr(other_instance, "partInstanceLink", None)
        if not other_root:
            continue
        seen_in_this_instance: Set[str] = set()
        for step in getattr(other_root, "partProcessTracking", []) or []:
            if not is_secondary_like(step):
                continue
            diag_text = getattr(step, "diagnose", None) or getattr(step, "diagnosis", None) or ""
            step_cost = cost_eur(step)
            if diag_text:
                diagnosis_cost_samples[diag_text].append(step_cost)
                days_since_decl = _days_between(
                    getattr(step, "beginDate", None), getattr(other_instance, "dateOfDeclaration", None)
                )
                if days_since_decl is not None and days_since_decl >= 0:
                    diagnosis_days_samples[diag_text].append(days_since_decl)

            observed = getattr(step, "observedSymptoms", None)
            if isinstance(observed, str) and observed.strip():
                symptoms = [x.strip() for x in observed.split(",") if x.strip()]
            elif isinstance(observed, (list, tuple)):
                symptoms = [str(x).strip() for x in observed if str(x).strip()]
            else:
                symptoms = []
            for symptom in symptoms:
                symptom_to_diagnoses[symptom][diag_text] += 1
                if symptom not in seen_in_this_instance:
                    symptom_to_instance_ids[symptom].add(other_instance.id)
                    seen_in_this_instance.add(symptom)

    symptom_diagnosis_summary: List[Dict[str, Any]] = []
    for symptom, diag_counter in symptom_to_diagnoses.items():
        total_occurrences = sum(diag_counter.values()) or 1
        top_two = diag_counter.most_common()[:2]
        ranked_diagnoses = []
        for diag, count in top_two:
            probability = count / total_occurrences
            costs = diagnosis_cost_samples.get(diag, [])
            avg_cost = (sum(costs) / len(costs)) if costs else None
            days = diagnosis_days_samples.get(diag, [])
            avg_days = (sum(days) / len(days)) if days else None
            ranked_diagnoses.append(
                {
                    "diagnosis": diag,
                    "probability": probability,
                    "count": count,
                    "avgCostEUR": avg_cost,
                    "avgDaysSinceDeclaration": avg_days,
                }
            )
        symptom_diagnosis_summary.append(
            {
                "symptom": symptom,
                "instanceCount": len(symptom_to_instance_ids.get(symptom, set())),
                "diagnoses": ranked_diagnoses,
            }
        )
    symptom_diagnosis_summary.sort(key=lambda item: item.get("instanceCount", 0), reverse=True)

    responsible = await _resolve_org(getattr(dpp_static, "responsibleOperator", None)) if dpp_static else None
    manufacturer = await _resolve_org(getattr(dpp_static, "productManufacturer", None)) if dpp_static else None
    importer = await _resolve_org(getattr(dpp_static, "importer", None)) if dpp_static else None
    per_part_mtbf: Dict[str, Dict[str, Optional[float]]] = {}
    if flat_parts:
        for part in flat_parts:
            part_id = str(part.id)
            static_id = part_to_static_id.get(part_id)
            mtbf_value = get_mtbf_from_cache(static_id) if static_id else None
            try:
                mtbf_value = float(mtbf_value) if mtbf_value is not None else None
            except Exception:
                mtbf_value = None
            remaining_for_part = (
                max(0.0, mtbf_value - operating_hours) if isinstance(mtbf_value, (int, float)) else None
            )
            exceeded_for_part = bool(operating_hours >= mtbf_value) if isinstance(mtbf_value, (int, float)) else False
            per_part_mtbf[part_id] = {
                "mtbfHRS": mtbf_value,
                "remainingHRS": remaining_for_part,
                "exceeded": exceeded_for_part,
            }

    return {
        "id": instance.id,
        "staticId": dpp_static.id if dpp_static else None,
        "productName": getattr(dpp_static, "name", None) if dpp_static else None,
        "productClass": getattr(dpp_static, "productClass", None) if dpp_static else None,
        "responsibleOperator": responsible,
        "manufacturer": manufacturer,
        "importer": importer,
        "dateOfDeclaration": date_of_declaration,
        "endOfGuarantee": end_of_guarantee,
        "guaranteeDescription": guarantee_description,
        "expectedMtbfHRS": expected_mtbf_hrs,
        "counters": counters,
        "mtbf": {"remainingHRS": remaining_hours, "exceeded": mtbf_exceeded},
        "productAgeDays": product_age_days,
        "spareParts": spare_parts,
        "toolsForMaintenance": tools_for_maintenance,
        "qualificationForRepair": qualification_for_repair,
        "documents": document_links,
        "failState": {"hasAny": product_has_fail, "count": product_fail_count, "totalPartsInTree": total_parts_count},
        "parts": {"firstLevel": first_level, "totalCount": total_parts_count, "topHasFailstate": top_has_failstate},
        "service": {
            "perPart": per_part_stats,
            "perPartMtbf": per_part_mtbf,
        },
        "secondaryValueSteps": secondary_value_steps,
        "symptomDiagnosisSummary": symptom_diagnosis_summary,
        "failingParts": failing_parts,
        "detachedParts": [{"id": part_id, "name": part_name} for part_id, part_name in detached_name_by_id.items()],
    }


# ============================================================================
# Utility summary
# ============================================================================


@router.get("/instance/{instance_id}/utility-summary")
async def get_utility_summary(instance_id: str, request: Request) -> Dict[str, Any]:
    """UtilityView summary across instances for the frontend."""
    instance_obj = await DPPInstance.get(instance_id, fetch_links=["dppStaticLink", "partInstanceLink"])
    if not instance_obj:
        raise HTTPException(status_code=404, detail="DPPInstance not found")

    dpp_static: Optional[DPPStatic] = instance_obj.dppStaticLink
    static_id = getattr(dpp_static, "id", None) if dpp_static else None
    product_name = getattr(dpp_static, "name", None) if dpp_static else None

    def _cost_eur(step: Any) -> float:
        for attr_name in ("costEur", "costEUR", "cost", "priceEUR", "priceEur"):
            value = getattr(step, attr_name, None)
            if isinstance(value, (int, float)):
                return float(value)
        return 0.0

    def _type_name(step: Any) -> str:
        label = getattr(step, "type_", None) or getattr(step, "type", None)
        return label if isinstance(label, str) and label else step.__class__.__name__

    def _is_secondary_like(step: Any) -> bool:
        try:
            return isinstance(step, SecondaryValueStep)
        except Exception:
            lowered = step.__class__.__name__.lower()
            return any(
                k in lowered
                for k in ("secondaryvaluestep", "repair", "replace", "clean", "refurb", "remanufactur", "recycl")
            )

    def _target_ids(step: Any) -> Set[str]:
        part_ids: Set[str] = set()
        for field in ("repairedPartId", "replacedPartId", "cleanedPartId"):
            value = getattr(step, field, None)
            if value:
                part_ids.add(str(value))
        for field in ("repairedPartIds", "cleanedPartIds"):
            collection = getattr(step, field, None)
            if collection and isinstance(collection, (list, tuple, set)):
                for item in collection:
                    if item:
                        part_ids.add(str(item))
        if hasattr(step, "replacedAndNewParts"):
            for pair in getattr(step, "replacedAndNewParts", []) or []:
                if pair and isinstance(pair, (list, tuple)) and pair[0]:
                    part_ids.add(str(pair[0]))
        return part_ids

    async def _part_static_name(part_inst: PartInstance) -> Optional[str]:
        try:
            ps_link = getattr(part_inst, "partStaticLink", None)
            ps = await ps_link.fetch() if isinstance(ps_link, Link) else ps_link
            return getattr(ps, "name", None)
        except Exception:
            return None

    async def _name_map_for_tree(root: Optional[PartInstance]) -> Tuple[Dict[str, str], Dict[str, str]]:
        """Return in-tree and detached part-id→display-name maps."""
        name_map: Dict[str, str] = {}
        detached_name_map: Dict[str, str] = {}
        if not root:
            return name_map, detached_name_map

        async def _walk(node: PartInstance) -> None:
            part_id = str(node.id)
            display_name = await _part_static_name(node) or getattr(node, "name", None) or part_id
            name_map[part_id] = display_name
            for child in getattr(node, "compositeParts", []) or []:
                await _walk(child)

        await _walk(root)

        for detached in getattr(root, "historyOfDetachedParts", []) or []:
            part_id = str(getattr(detached, "id", "") or "")
            if not part_id:
                continue
            display_name = await _part_static_name(detached) or getattr(detached, "name", None) or part_id
            detached_name_map[part_id] = display_name

        return name_map, detached_name_map

    def _days_between(later: Any, earlier: Any) -> Optional[float]:
        try:
            from datetime import datetime, timezone

            def _coerce(val: Any) -> Optional[datetime]:
                if val is None:
                    return None
                if isinstance(val, datetime):
                    return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
                return datetime.fromisoformat(str(val).replace("Z", "+00:00"))

            d_later, d_earlier = _coerce(later), _coerce(earlier)
            if not d_later or not d_earlier:
                return None
            return (d_later - d_earlier).total_seconds() / 86400.0
        except Exception:
            return None

    try:
        related_instances: List[DPPInstance] = (
            await DPPInstance.find(
                DPPInstance.dppStaticLink.id == static_id, fetch_links=["partInstanceLink"]
            ).to_list()
            if static_id
            else [instance_obj]
        )
    except Exception:
        related_instances = [instance_obj]

    instance_count = max(1, len(related_instances))

    operation_totals: Dict[str, int] = defaultdict(int)
    part_counts_overall: Counter = Counter()
    part_counts_by_type: Dict[str, Counter] = defaultdict(Counter)

    symptom_diag_counts: Dict[str, Counter] = defaultdict(Counter)
    symptom_instance_ids: Dict[str, Set[str]] = defaultdict(set)
    diagnosis_costs: Dict[str, List[float]] = defaultdict(list)
    diagnosis_days: Dict[str, List[float]] = defaultdict(list)

    for other_instance in related_instances:
        other_root = getattr(other_instance, "partInstanceLink", None)
        if not other_root:
            continue

        name_map, detached_name_map = await _name_map_for_tree(other_root)
        root_steps = list(getattr(other_root, "partProcessTracking", []) or [])

        for step in root_steps:
            if not _is_secondary_like(step):
                continue

            type_name = _type_name(step)
            operation_totals["SecondaryValueStep"] += 1
            operation_totals[type_name] += 1

            for part_id in _target_ids(step) or []:
                part_name = name_map.get(part_id) or detached_name_map.get(part_id) or part_id
                part_counts_overall[part_name] += 1
                part_counts_by_type[type_name][part_name] += 1

            diagnosis_text = getattr(step, "diagnose", None) or getattr(step, "diagnosis", None) or ""
            if diagnosis_text:
                diagnosis_costs[diagnosis_text].append(_cost_eur(step))
                delta_days = _days_between(
                    getattr(step, "beginDate", None), getattr(other_instance, "dateOfDeclaration", None)
                )
                if delta_days is not None and delta_days >= 0:
                    diagnosis_days[diagnosis_text].append(delta_days)

            observed = getattr(step, "observedSymptoms", None)
            if isinstance(observed, str) and observed.strip():
                symptoms = [x.strip() for x in observed.split(",") if x.strip()]
            elif isinstance(observed, (list, tuple)):
                symptoms = [str(x).strip() for x in observed if str(x).strip()]
            else:
                symptoms = []

            seen_in_instance: Set[str] = set()
            for symptom in symptoms:
                symptom_diag_counts[symptom][diagnosis_text] += 1
                if symptom not in seen_in_instance:
                    symptom_instance_ids[symptom].add(other_instance.id)
                    seen_in_instance.add(symptom)

    symptom_diagnosis_summary: List[Dict[str, Any]] = []
    for symptom, diag_counter in symptom_diag_counts.items():
        total_occurrences = sum(diag_counter.values()) or 1
        top_diagnoses = diag_counter.most_common()[:2]
        diagnoses: List[Dict[str, Any]] = []
        for diagnosis_text, count in top_diagnoses:
            probability = count / total_occurrences
            costs = diagnosis_costs.get(diagnosis_text, [])
            avg_cost = (sum(costs) / len(costs)) if costs else None
            days = diagnosis_days.get(diagnosis_text, [])
            avg_days = (sum(days) / len(days)) if days else None
            diagnoses.append(
                {
                    "diagnosis": diagnosis_text,
                    "probability": probability,
                    "count": count,
                    "avgCostEUR": avg_cost,
                    "avgDaysSinceDeclaration": avg_days,
                }
            )
        symptom_diagnosis_summary.append(
            {"symptom": symptom, "instanceCount": len(symptom_instance_ids.get(symptom, set())), "diagnoses": diagnoses}
        )
    symptom_diagnosis_summary.sort(key=lambda x: x.get("instanceCount", 0), reverse=True)

    average_per_instance = {key: (value / instance_count) for key, value in operation_totals.items()}

    def _top(counter: Counter, limit: int = 10) -> List[Dict[str, Any]]:
        return [{"name": name, "count": count} for name, count in counter.most_common(limit)]

    top_overall = _top(part_counts_overall, 10)
    top_by_operation = {key: _top(val, 10) for key, val in part_counts_by_type.items()}

    return {
        "id": instance_obj.id,
        "staticId": static_id,
        "productName": product_name,
        "backup": {
            "instance": getattr(instance_obj, "backupLink", None),
            "static": getattr(dpp_static, "backupLink", None) if dpp_static else None,
        },
        "jsonld": {
            "instance": str(request.url_for("dpp_instance_jsonld", instance_id=instance_obj.id)),
            "bundle": str(request.url_for("export_dpp_and_instances", dpp_id=static_id)) if static_id else None,
            "downloadInstance": str(request.url_for("download_dpp_instance_jsonld", instance_id=instance_obj.id)),
            "downloadBundle": str(request.url_for("download_dpp_and_instances", dpp_id=static_id))
            if static_id
            else None,
        },
        "instancesCount": instance_count,
        "symptomDiagnosisSummary": symptom_diagnosis_summary,
        "operations": {
            "totals": dict(operation_totals),
            "averagePerInstance": average_per_instance,
            "topPartsOverall": top_overall,
            "topPartsByOperation": top_by_operation,
        },
    }


# =============================================================================
# Process map (nodes/edges + category counts)
# =============================================================================


@router.get(
    "/instance/{instance_id}/process-map",
    response_model=ProcessMapResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
)
async def get_process_map(instance_id: str) -> ProcessMapResponse:
    """Build the process map with places."""

    instance_obj = await DPPInstance.get(instance_id, fetch_links=["partInstanceLink"])
    if not instance_obj:
        raise HTTPException(status_code=404, detail="DPPInstance not found")

    root_ref = instance_obj.partInstanceLink
    if root_ref is None:
        return ProcessMapResponse(
            nodes=[], edges=[], counts={"production": 0, "transport": 0, "secondary": 0, "total": 0}
        )
    place_cache: Dict[str, Tuple[Any, float]] = getattr(get_process_map, "_place_cache", None)
    if place_cache is None:
        place_cache = {}
        get_process_map._place_cache = place_cache
    cache_ttl = getattr(get_process_map, "_place_cache_ttl", 300.0)

    def cache_get(place_id: str) -> Optional[Any]:
        item = place_cache.get(place_id)
        if not item:
            return None
        obj, ts = item
        if monotonic() - ts <= cache_ttl:
            return obj
        place_cache.pop(place_id, None)
        return None

    def cache_put(place_id: str, obj: Any) -> None:
        place_cache[place_id] = (obj, monotonic())

    parts_by_id: Dict[str, PartInstance] = {}
    seen_ids: Set[str] = set()
    sem_parts = asyncio.Semaphore(48)

    async def _fetch_part(ref_or_doc: Any) -> Optional[PartInstance]:
        if isinstance(ref_or_doc, PartInstance):
            return ref_or_doc
        if hasattr(ref_or_doc, "document") and isinstance(ref_or_doc.document, PartInstance):
            return ref_or_doc.document
        if isinstance(ref_or_doc, Link):
            async with sem_parts:
                try:
                    return await ref_or_doc.fetch()
                except Exception:
                    return None
        return None

    root_doc = await _fetch_part(root_ref)
    if root_doc is None or getattr(root_doc, "id", None) is None:
        return ProcessMapResponse(
            nodes=[], edges=[], counts={"production": 0, "transport": 0, "secondary": 0, "total": 0}
        )

    frontier: List[PartInstance] = [root_doc]
    while frontier:
        for part in frontier:
            part_id = getattr(part, "id", None)
            if isinstance(part_id, str) and part_id not in seen_ids:
                seen_ids.add(part_id)
                parts_by_id[part_id] = part

        child_refs: List[Any] = []
        for part in frontier:
            for child in getattr(part, "compositeParts", []) or []:
                if isinstance(child, PartInstance):
                    if getattr(child, "id", None) not in seen_ids:
                        child_refs.append(child)
                elif isinstance(child, Link):
                    child_refs.append(child)
        if not child_refs:
            break

        fetched_children = await asyncio.gather(*(_fetch_part(child) for child in child_refs))
        frontier = [
            doc for doc in fetched_children if isinstance(getattr(doc, "id", None), str) and doc.id not in seen_ids
        ]

    def _category(step: Any) -> str:
        if isinstance(step, TransportStep):
            return "transport"
        if isinstance(step, ProductionStep):
            return "production"
        if isinstance(step, SecondaryValueStep):
            return "secondary"
        return _classify_step(step)

    def _iter_steps(part: PartInstance) -> Iterable[Any]:
        for step in getattr(part, "partProcessTracking", []) or []:
            yield step
        for material in getattr(part, "compositeMaterials", []) or []:
            for step in getattr(material, "materialProcessTracking", []) or []:
                yield step

    EventTuple: TypeAlias = Tuple[str, Any, Optional[Any]]
    events: List[EventTuple] = []

    place_ids: Set[str] = set()
    links_without_ids: Dict[int, Link] = {}
    embedded_places: List[Any] = []

    def _collect_ref(ref: Any) -> None:
        if ref is None:
            return
        if isinstance(ref, Link):
            link_id = getattr(ref, "id", None) or getattr(ref, "ref_id", None)
            if link_id is None:
                maybe = getattr(ref, "ref", None)
                link_id = getattr(maybe, "id", None) if maybe is not None else None
            if link_id is not None:
                place_ids.add(str(link_id))
            else:
                links_without_ids.setdefault(id(ref), ref)
            return
        pid = getattr(ref, "id", None)
        if isinstance(pid, str):
            place_ids.add(pid)
        embedded_places.append(ref)

    for part in parts_by_id.values():
        for step in _iter_steps(part):
            cat = _category(step)
            processed_at = getattr(step, "processedAt", None)
            destination = getattr(step, "destination", None) if cat == "transport" else None
            _collect_ref(processed_at)
            if destination is not None:
                _collect_ref(destination)
            events.append((cat, processed_at, destination))

    for place_obj in embedded_places:
        pid = getattr(place_obj, "id", None)
        if isinstance(pid, str):
            cache_put(pid, place_obj)

    ids_to_query = [pid for pid in place_ids if cache_get(pid) is None]
    if ids_to_query:
        fetched_places = await Place.find(In(Place.id, ids_to_query)).to_list()
        for obj in fetched_places:
            pid = getattr(obj, "id", None)
            if isinstance(pid, str):
                cache_put(pid, obj)

    sem_places = asyncio.Semaphore(64)
    place_by_linkid: Dict[int, Any] = {}

    async def _fetch_link_place(linking: Link) -> None:
        async with sem_places:
            try:
                obj = await linking.fetch()
                if obj is None:
                    return
                place_by_linkid[id(linking)] = obj
                pid = getattr(obj, "id", None)
                if isinstance(pid, str):
                    cache_put(pid, obj)
            except Exception:
                return

    if links_without_ids:
        await asyncio.gather(*(_fetch_link_place(linking) for linking in links_without_ids.values()))

    nodes_map: Dict[str, MapNode] = {}
    edge_buckets: Dict[Tuple[str, str, str], int] = {}
    category_counts = {"production": 0, "transport": 0, "secondary": 0, "total": 0}

    def _resolve_place(ref: Any) -> Optional[Any]:
        if ref is None:
            return None
        if isinstance(ref, Link):
            obj = place_by_linkid.get(id(ref))
            if obj is not None:
                return obj
            link_id = getattr(ref, "id", None) or getattr(ref, "ref_id", None)
            if link_id is None:
                maybe = getattr(ref, "ref", None)
                link_id = getattr(maybe, "id", None) if maybe is not None else None
            return cache_get(str(link_id)) if link_id is not None else None
        pid = getattr(ref, "id", None)
        if isinstance(pid, str):
            obj = cache_get(pid)
            return obj or ref
        return ref

    def _ensure_node(place_obj: Any) -> Optional[str]:
        node_key = _place_key(place_obj)
        if node_key is None:
            return None
        if node_key not in nodes_map:
            lat, lon = _coords_from_place(place_obj)
            if lat is None or lon is None:
                return None
            nodes_map[node_key] = MapNode(
                id=getattr(place_obj, "id", None),
                name=getattr(place_obj, "name", None) or getattr(place_obj, "id", None),
                latitude=float(lat),
                longitude=float(lon),
            )
        return node_key

    def _bump_node(place_obj: Any, category: str) -> None:
        node_key = _ensure_node(place_obj)
        if node_key is None:
            return
        node = nodes_map[node_key]
        node.categoryCounts[category] = node.categoryCounts.get(category, 0) + 1
        node.totalCount += 1

    for cat, processed_ref, destination_ref in events:
        category_counts[cat] += 1
        category_counts["total"] += 1

        src = _resolve_place(processed_ref)
        if src is not None:
            _bump_node(src, cat)
            if cat == "transport":
                dst = _resolve_place(destination_ref)
                if dst is not None:
                    s_key = _ensure_node(src)
                    d_key = _ensure_node(dst)
                    if s_key and d_key:
                        s_id = nodes_map[s_key].id or s_key
                        d_id = nodes_map[d_key].id or d_key
                        bucket_key = (str(s_id), str(d_id), "transport")
                        edge_buckets[bucket_key] = edge_buckets.get(bucket_key, 0) + 1

    edges: List[MapEdge] = [
        MapEdge(sourceId=s, targetId=t, category=c, count=n) for (s, t, c), n in edge_buckets.items()
    ]
    return ProcessMapResponse(nodes=list(nodes_map.values()), edges=edges, counts=category_counts)


# =============================================================================
# Mutations on instance: toggle fail-state and add service steps
# =============================================================================


def _find_part(root: PartInstance, target_id: str) -> Optional[PartInstance]:
    """lookup by id within a part tree."""
    stack: List[PartInstance] = [root]
    while stack:
        current = stack.pop()
        if current.id == target_id:
            return current
        stack.extend(getattr(current, "compositeParts", []) or [])
    return None


def _find_part_with_parent(root: PartInstance, target_id: str) -> Tuple[Optional[PartInstance], Optional[PartInstance]]:
    """lookup and return the parent of the matched node."""
    stack: List[Tuple[PartInstance, Optional[PartInstance]]] = [(root, None)]
    while stack:
        node, parent = stack.pop()
        if node.id == target_id:
            return node, parent
        for child in getattr(node, "compositeParts", []) or []:
            stack.append((child, node))
    return None, None


def _snapshot_part_instance(source: PartInstance) -> PartInstance:
    """Create deep copy of a PartInstance for history."""
    try:
        return (
            source.model_copy(deep=True)
            if hasattr(source, "model_copy")
            else PartInstance.model_validate(source.model_dump(by_alias=True))
        )
    except Exception:
        return PartInstance.model_validate(source.model_dump(by_alias=True))


@router.post(
    "/instance/{instance_id}/part/{part_id}/toggle-failstate",
    response_model=DPPInstance,
    response_model_by_alias=True,
)
async def toggle_part_failstate(instance_id: str, part_id: str) -> DPPInstance:
    """Flip `hasFailstate` on a nested PartInstance."""
    instance = await DPPInstance.get(instance_id, fetch_links=True)
    if not instance:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"DPPInstance {instance_id} not found")

    root: Optional[PartInstance] = instance.partInstanceLink
    if not root:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Root PartInstance not found")

    target = _find_part(root, part_id)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"PartInstance {part_id} not found under this DPPInstance",
        )

    target.hasFailstate = not bool(getattr(target, "hasFailstate", False))
    await root.save()
    return await DPPInstance.get(instance_id, fetch_links=True)


@router.post(
    "/instance/{instance_id}/service/repair/",
    response_model=DPPInstance,
    response_model_by_alias=True,
)
async def add_repair_step_to_instance(instance_id: str, step: RepairServiceStep) -> DPPInstance:
    """Append a RepairServiceStep to the root tracking."""
    instance = await DPPInstance.get(instance_id, fetch_links=True)
    if not instance:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"DPPInstance {instance_id} not found")

    root: PartInstance = instance.partInstanceLink
    if not _find_part(root, step.repairedPartId):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"PartInstance {step.repairedPartId} not found in compositeParts",
        )

    root.partProcessTracking.append(step)
    await root.save()
    return await DPPInstance.get(instance_id, fetch_links=True)


@router.post(
    "/instance/{instance_id}/service/replace/",
    response_model=DPPInstance,
    response_model_by_alias=True,
)
async def add_replace_step_to_instance(instance_id: str, step: ReplaceServiceStep) -> DPPInstance:
    """Append a ReplaceServiceStep, snapshot the old part, swap the new part in."""
    instance = await DPPInstance.get(instance_id, fetch_links=True)
    if not instance:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"DPPInstance {instance_id} not found")

    root: PartInstance = instance.partInstanceLink

    target, parent = _find_part_with_parent(root, step.replacedPartId)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"PartInstance {step.replacedPartId} not found in compositeParts",
        )
    if parent is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Replacing the root part is not supported.")

    root.historyOfDetachedParts.append(_snapshot_part_instance(target))
    replaced_successfully = False
    for child_index, child in enumerate(parent.compositeParts):
        if child.id == target.id:
            parent.compositeParts[child_index] = step.newPart
            replaced_successfully = True
            break
    if not replaced_successfully:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Replacement failed: target was found but not swapped.",
        )

    root.partProcessTracking.append(step)
    await root.save()
    logger.info("Replaced part %s in DPPInstance %s", target.id, instance_id)
    return await DPPInstance.get(instance_id, fetch_links=True)


@router.post(
    "/instance/{instance_id}/service/cleaning/",
    response_model=DPPInstance,
    response_model_by_alias=True,
)
async def add_cleaning_step_to_instance(instance_id: str, step: CleaningServiceStep) -> DPPInstance:
    """Append a CleaningServiceStep on the root part."""
    instance = await DPPInstance.get(instance_id, fetch_links=True)
    if not instance:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"DPPInstance {instance_id} not found")

    root: PartInstance = instance.partInstanceLink
    root.partProcessTracking.append(step)
    await root.save()
    logger.info("Added cleaning step to DPPInstance %s: %s", instance_id, step.cleanedPartId)
    return await DPPInstance.get(instance_id, fetch_links=True)


@router.post(
    "/instance/{instance_id}/service/remanufacturing/",
    response_model=DPPInstance,
    response_model_by_alias=True,
)
async def add_remanufacturing_step_to_instance(instance_id: str, step: RemanufacturingServiceStep) -> DPPInstance:
    """Remanufacturing: validate target ids, snapshot replaced parts, swap new ones, persist step."""
    instance = await DPPInstance.get(instance_id, fetch_links=True)
    if not instance:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"DPPInstance {instance_id} not found")

    root_candidate = instance.partInstanceLink
    if not root_candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Root PartInstance not found")
    root: PartInstance = (
        await root_candidate.fetch() if not isinstance(root_candidate, PartInstance) else root_candidate
    )

    for repaired_id in step.repairedPartIds:
        part, _ = _find_part_with_parent(root, repaired_id)
        if not part:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Repaired part {repaired_id} not found in compositeParts",
            )
    for cleaned_id in step.cleanedPartIds:
        part, _ = _find_part_with_parent(root, cleaned_id)
        if not part:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cleaned part {cleaned_id} not found in compositeParts",
            )

    for replaced_id, new_part_raw in step.replacedAndNewParts:
        target, parent = _find_part_with_parent(root, replaced_id)
        if not target:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Part to replace {replaced_id} not found in compositeParts",
            )
        if parent is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Replacing the root part is not supported."
            )

        if isinstance(new_part_raw, dict):
            try:
                new_part_obj = PartInstance.model_validate(new_part_raw)
            except Exception as exc:
                logger.error("Failed to validate new part in remanufacturing: %s", exc, exc_info=True)
                raise HTTPException(status_code=400, detail="Invalid new part in replacedAndNewParts.") from exc
        elif isinstance(new_part_raw, PartInstance):
            new_part_obj = new_part_raw
        else:
            raise HTTPException(status_code=400, detail="Unsupported type for new part in replacedAndNewParts.")

        root.historyOfDetachedParts.append(_snapshot_part_instance(target))

        replaced_flag = False
        for child_index, child in enumerate(parent.compositeParts):
            if child.id == target.id:
                parent.compositeParts[child_index] = new_part_obj
                replaced_flag = True
                break
        if not replaced_flag:
            logger.error("Replacement target found but not swapped: target id %s in parent %s", target.id, parent.id)
            raise HTTPException(status_code=500, detail=f"Replacement failed for target {replaced_id}.")

        logger.info(
            "Replaced part %s with new %s during remanufacturing in DPPInstance %s",
            replaced_id,
            new_part_obj.id,
            instance_id,
        )

    root.partProcessTracking.append(step)
    await root.save()
    return await DPPInstance.get(instance_id, fetch_links=True)


@router.post(
    "/instance/{instance_id}/service/refurbishment/",
    response_model=DPPInstance,
    response_model_by_alias=True,
)
async def add_refurbishment_step_to_instance(instance_id: str, step: RefurbishmentServiceStep) -> DPPInstance:
    """Refurbishment as remanufacturing."""
    instance = await DPPInstance.get(instance_id, fetch_links=True)
    if not instance:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"DPPInstance {instance_id} not found")

    root_candidate = instance.partInstanceLink
    if not root_candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Root PartInstance not found")
    root: PartInstance = (
        await root_candidate.fetch() if not isinstance(root_candidate, PartInstance) else root_candidate
    )

    for repaired_id in step.repairedPartIds:
        part, _ = _find_part_with_parent(root, repaired_id)
        if not part:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Repaired part {repaired_id} not found in compositeParts",
            )
    for cleaned_id in step.cleanedPartIds:
        part, _ = _find_part_with_parent(root, cleaned_id)
        if not part:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cleaned part {cleaned_id} not found in compositeParts",
            )

    for replaced_id, new_part_raw in step.replacedAndNewParts:
        target, parent = _find_part_with_parent(root, replaced_id)
        if not target:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Part to replace {replaced_id} not found in compositeParts",
            )
        if parent is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Replacing the root part is not supported."
            )

        if isinstance(new_part_raw, dict):
            try:
                new_part_obj = PartInstance.model_validate(new_part_raw)
            except Exception as exc:
                logger.error("Failed to validate new part in refurbishment: %s", exc, exc_info=True)
                raise HTTPException(status_code=400, detail="Invalid new part in replacedAndNewParts.") from exc
        elif isinstance(new_part_raw, PartInstance):
            new_part_obj = new_part_raw
        else:
            raise HTTPException(status_code=400, detail="Unsupported type for new part in replacedAndNewParts.")

        root.historyOfDetachedParts.append(_snapshot_part_instance(target))

        replaced_flag = False
        for child_index, child in enumerate(parent.compositeParts):
            if child.id == target.id:
                parent.compositeParts[child_index] = new_part_obj
                replaced_flag = True
                break
        if not replaced_flag:
            raise HTTPException(status_code=500, detail=f"Replacement failed for target {replaced_id}.")

        logger.info(
            "Replaced part %s with new %s during refurbishment in DPPInstance %s",
            replaced_id,
            new_part_obj.id,
            instance_id,
        )

    root.partProcessTracking.append(step)
    await root.save()
    return await DPPInstance.get(instance_id, fetch_links=True)


@router.post(
    "/instance/{instance_id}/service/recycling/",
    response_model=DPPInstance,
    response_model_by_alias=True,
)
async def add_recycling_step_to_instance(instance_id: str, step: RecyclingStep) -> DPPInstance:
    """Append a RecyclingStep and mark the instance as discontinued."""
    instance = await DPPInstance.get(instance_id, fetch_links=True)
    if not instance:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"DPPInstance {instance_id} not found")

    root: PartInstance = instance.partInstanceLink
    root.partProcessTracking.append(step)
    await root.save()

    instance.discontinued = True
    await instance.save()
    logger.info("Added recycling step to DPPInstance %s: %s", instance_id, step.reason)
    return await DPPInstance.get(instance_id, fetch_links=True)


# =============================================================================
# Statistics
# =============================================================================


@router.get(
    "/{dpp_id}/statistics/diagnosis_summary",
    response_model=DiagnosisSummaryResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
)
async def get_symptom_diagnosis_summary(dpp_id: str) -> DiagnosisSummaryResponse:
    """Count diagnoses per observed symptom."""
    dpp_static = await DPPStatic.get(dpp_id)
    if not dpp_static:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"DPPStatic {dpp_id} not found")

    instances = await DPPInstance.find(
        DPPInstance.dppStaticLink.id == dpp_static.id, fetch_links=["partInstanceLink"]
    ).to_list()

    symptom_to_diagnoses: Dict[str, Counter] = defaultdict(Counter)
    symptom_to_instance_ids: Dict[str, Set[str]] = defaultdict(set)

    for instance_item in instances:
        root: Optional[PartInstance] = instance_item.partInstanceLink
        if not root:
            continue
        steps: List[SecondaryValueStep] = await _gather_secondary_steps_from_part(root)  # type: ignore

        seen_in_instance: Set[str] = set()
        for step in steps:
            diagnosis_text = step.diagnose or ""
            for symptom in getattr(step, "observedSymptoms", []) or []:
                if not symptom:
                    continue
                symptom_to_diagnoses[symptom][diagnosis_text] += 1
                if symptom not in seen_in_instance:
                    symptom_to_instance_ids[symptom].add(instance_item.id)
                    seen_in_instance.add(symptom)

    summary_entries: List[SymptomDiagnosisSummaryEntry] = []
    for symptom, diag_counter in symptom_to_diagnoses.items():
        most_likely = diag_counter.most_common(1)[0][0] if diag_counter else ""
        summary_entries.append(
            SymptomDiagnosisSummaryEntry(
                symptom=symptom,
                most_likely_diagnosis=most_likely,
                instance_count=len(symptom_to_instance_ids.get(symptom, set())),
                diagnosis_counts=dict(diag_counter),
            )
        )

    summary_entries.sort(key=lambda entry: entry.instance_count, reverse=True)
    return DiagnosisSummaryResponse(
        dpp_static_id=dpp_static.id, total_instances=len(instances), summary=summary_entries
    )


@router.get(
    "/{dpp_id}/statistics/secondary-steps-aggregate",
    response_model=SecondaryStepsAggregateResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
)
async def get_secondary_steps_aggregate(dpp_id: str) -> SecondaryStepsAggregateResponse:
    """Aggregate SecondaryValueStep entries."""
    dpp_static = await DPPStatic.get(dpp_id)
    if not dpp_static:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"DPPStatic {dpp_id} not found")

    instances: List[DPPInstance] = await DPPInstance.find(
        DPPInstance.dppStaticLink.id == dpp_static.id, fetch_links=["partInstanceLink"]
    ).to_list()

    step_entries_by_type: Dict[str, List[SecondaryStepInstanceEntry]] = defaultdict(list)
    tracked_types = {
        "RepairServiceStep": RepairServiceStep,
        "ReplaceServiceStep": ReplaceServiceStep,
        "CleaningServiceStep": CleaningServiceStep,
        "RemanufacturingServiceStep": RemanufacturingServiceStep,
        "RefurbishmentServiceStep": RefurbishmentServiceStep,
        "RecyclingStep": RecyclingStep,
    }

    for instance_item in instances:
        cleaning_raw = getattr(instance_item, "cleaningCount", None)
        chalk_raw = getattr(instance_item, "chalkCount", None)
        brewing_raw = getattr(instance_item, "brewingCount", None)
        grinding_raw = getattr(instance_item, "coffeeGrindingCount", None)

        cleaning_count = getattr(cleaning_raw, "value", 0) if cleaning_raw is not None else 0
        chalk_count = getattr(chalk_raw, "value", 0) if chalk_raw is not None else 0
        brewing_count = getattr(brewing_raw, "value", 0) if brewing_raw is not None else 0
        grinding_count = getattr(grinding_raw, "value", 0) if grinding_raw is not None else 0

        location_summary: Optional[PlaceLocationSummary] = None
        current_location = getattr(instance_item, "currentLocation", None)
        if isinstance(current_location, Place):
            location_summary = PlaceLocationSummary(
                name=current_location.name, latitude=current_location.latitude, longitude=current_location.longitude
            )

        root: Optional[PartInstance] = instance_item.partInstanceLink
        if not root:
            continue

        try:
            steps: List[SecondaryValueStep] = await _gather_secondary_steps_from_part(root)
        except Exception:
            steps = [s for s in getattr(root, "partProcessTracking", []) if isinstance(s, SecondaryValueStep)]

        for step in steps:
            step_type_name = getattr(step, "type_", None) or type(step).__name__
            if step_type_name not in tracked_types:
                continue
            entry = SecondaryStepInstanceEntry(
                step=step.model_dump(by_alias=True),
                cleaningCount=cleaning_count,
                chalkCount=chalk_count,
                brewingCount=brewing_count,
                coffeeGrindingCount=grinding_count,
                location=location_summary,
            )
            step_entries_by_type[step_type_name].append(entry)

    overall_counts: Dict[str, int] = {
        step_type: len(step_entries_by_type.get(step_type, [])) for step_type in tracked_types.keys()
    }
    summaries: List[SecondaryStepAggregateEntry] = [
        SecondaryStepAggregateEntry(
            step_type=step_type,
            total_count=overall_counts.get(step_type, 0),
            entries=step_entries_by_type.get(step_type, []),
        )
        for step_type in tracked_types.keys()
    ]

    return SecondaryStepsAggregateResponse(
        dpp_static_id=dpp_static.id,
        total_instances=len(instances),
        overall_counts=overall_counts,
        step_type_summaries=summaries,
    )


@router.get(
    "/instance/{instance_id}/statistics/count-service-modular/",
    response_model=ServiceModularSummary,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
)
async def get_service_modular_summary(instance_id: str) -> ServiceModularSummary:
    """Count Repair/Replace steps and modular parts for a single instance."""
    instance = await DPPInstance.get(instance_id, fetch_links=["partInstanceLink"])
    if not instance:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"DPPInstance {instance_id} not found")
    return await compute_service_and_modular_counts(instance)


@router.get(
    "/{dpp_id}/statistics/count-service-modular/",
    response_model=StaticServiceAggregateSummary,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
)
async def get_dpp_static_service_aggregate(dpp_id: str) -> StaticServiceAggregateSummary:
    """Aggregate Repair/Replace/modular counts across all instances of a DPPStatic."""
    dpp_static = await DPPStatic.get(dpp_id)
    if not dpp_static:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"DPPStatic {dpp_id} not found")

    instances: List[DPPInstance] = await DPPInstance.find(
        DPPInstance.dppStaticLink.id == dpp_static.id, fetch_links=["partInstanceLink"]
    ).to_list()

    per_instance: List[ServiceModularSummary] = []
    total_repairs = total_replaces = total_modulars = 0
    for instance_item in instances:
        summary = await compute_service_and_modular_counts(instance_item)
        per_instance.append(summary)
        total_repairs += summary.repair_count
        total_replaces += summary.replace_count
        total_modulars += summary.modular_part_count

    instance_count = len(instances) or 1
    return StaticServiceAggregateSummary(
        dpp_static_id=dpp_static.id,
        total_instances=len(instances),
        total_repair_count=total_repairs,
        total_replace_count=total_replaces,
        total_modular_part_count=total_modulars,
        average_repair_per_instance=round(total_repairs / instance_count, 2) if len(instances) else 0.0,
        average_replace_per_instance=round(total_replaces / instance_count, 2) if len(instances) else 0.0,
        average_modular_parts_per_instance=round(total_modulars / instance_count, 2) if len(instances) else 0.0,
        per_instance=per_instance,
    )


@router.get(
    "/instance/{instance_id}/statistics/rare_earth_metrics",
    response_model=RareEarthSummary,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
)
async def get_rare_earth_metrics_from_dpp_instance(instance_id: str) -> RareEarthSummary:
    """Compute rare-earth metrics for the root part of an instance."""
    instance = await DPPInstance.get(instance_id, fetch_links=["partInstanceLink"])
    if not instance:
        raise HTTPException(status_code=404, detail="DPPInstance not found")
    root: Optional[PartInstance] = instance.partInstanceLink
    if not root:
        raise HTTPException(status_code=404, detail="Root PartInstance not found")
    return await compute_rare_earth_metrics_rare_only(root)


@router.get(
    "/instance/{instance_id}/statistics/combined_material_summary_by_name",
    response_model=CombinedMaterialSummary,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
)
async def get_combined_summary_by_name_from_dpp_instance(instance_id: str) -> CombinedMaterialSummary:
    """Return combined material summary (grouped by material name) for an instance."""
    instance = await DPPInstance.get(instance_id, fetch_links=["partInstanceLink"])
    if not instance:
        raise HTTPException(status_code=404, detail="DPPInstance not found")
    root: Optional[PartInstance] = instance.partInstanceLink
    if not root:
        raise HTTPException(status_code=404, detail="Root PartInstance not found")
    return await compute_combined_material_summary_by_name(root)


@router.get(
    "/instance/{instance_id}/statistics/ghg-footprint",
    response_model=GHGFootprintAggregated,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
    summary="Aggregated GHG footprint for a DPP instance (Scope 1/2/3)",
)
async def get_ghg_footprint(instance_id: str) -> GHGFootprintAggregated:
    """Aggregate GHG emissions by scope/category for a DPPInstance."""
    instance = await DPPInstance.get(instance_id, fetch_links=["partInstanceLink"])
    if not instance:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"DPPInstance {instance_id} not found")

    try:
        raw = await aggregate_ghg_for_dpp_instance(instance)
    except Exception as exc:
        logger.error("Error aggregating GHG for DPPInstance %s: %s", instance_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to aggregate GHG emissions.") from exc

    aggregated_raw = raw.get("aggregated", {})
    transformed: Dict[str, GHGCategoryBreakdown] = {
        scope_key: GHGCategoryBreakdown(
            total=round(bucket.get("total", 0.0), 6),
            by_category={cat: round(val, 6) for cat, val in bucket.get("by_category", {}).items()},
        )
        for scope_key, bucket in aggregated_raw.items()
    }
    return GHGFootprintAggregated(dpp_instance_id=instance.id, aggregated=transformed)


# =============================================================================
# Images (GridFS)
# =============================================================================


@router.post(
    "/{dpp_id}/images/",
    response_model=List[ImageReference],
    status_code=status.HTTP_201_CREATED,
    summary="Upload images and link to DPPStatic (keeps filenames)",
)
async def upload_images(
    dpp_id: str,
    files: List[UploadFile] = FILES_PARAM,
    fs_bucket: AsyncIOMotorGridFSBucket = FS_DEPENDENCY,
) -> List[ImageReference]:
    """Upload images to GridFS and link them to a DPPStatic."""
    dpp_static = await DPPStatic.get(dpp_id)
    if not dpp_static:
        raise HTTPException(status_code=404, detail=f"DPPStatic {dpp_id} not found")

    uploaded: List[ImageReference] = []
    for upload in files:
        blob = await upload.read()
        file_id = await fs_bucket.upload_from_stream(upload.filename, io.BytesIO(blob))
        ref = ImageReference(file_id=file_id, filename=upload.filename)
        dpp_static.image_file_ids.append(ref)
        uploaded.append(ref)

    await dpp_static.save()
    return uploaded


@router.get(
    "/{dpp_id}/images/",
    response_model=List[ImageReference],
    summary="List all linked images (id + filename)",
)
async def list_images(dpp_id: str, _fs_bucket: AsyncIOMotorGridFSBucket = FS_DEPENDENCY) -> List[ImageReference]:
    """List all GridFS-linked images for a DPPStatic."""
    dpp_static = await DPPStatic.get(dpp_id)
    if not dpp_static:
        raise HTTPException(status_code=404, detail=f"DPPStatic {dpp_id} not found")
    return dpp_static.image_file_ids


@router.get(
    "/{dpp_id}/images-web/",
    response_model=List[ImageMetadata],
    summary="List all images with download URLs for web galleries",
)
async def list_images_web(
    dpp_id: str,
    request: Request,
    _fs_bucket: AsyncIOMotorGridFSBucket = FS_DEPENDENCY,
) -> List[ImageMetadata]:
    """Return file metadata with URLs for use in web galleries."""
    dpp_static = await DPPStatic.get(dpp_id)
    if not dpp_static:
        raise HTTPException(status_code=404, detail=f"DPPStatic {dpp_id} not found")

    images: List[ImageMetadata] = []
    for ref in dpp_static.image_file_ids:
        path = request.url_for("get_image", dpp_id=dpp_id, file_id=str(ref.file_id)).path
        images.append(ImageMetadata(file_id=str(ref.file_id), filename=ref.filename, url=path))
    return images


@router.get("/{dpp_id}/images/{file_id}", name="get_image", summary="Download a single linked image")
async def get_image(
    dpp_id: str,
    file_id: str,
    fs_bucket: AsyncIOMotorGridFSBucket = FS_DEPENDENCY,
):
    """Stream response for a single GridFS-stored image linked to a DPPStatic."""
    dpp_static = await DPPStatic.get(dpp_id)
    if not dpp_static:
        raise HTTPException(status_code=404, detail=f"DPPStatic {dpp_id} not found")

    file_object_id = PydanticObjectId(file_id)
    ref = next((img for img in dpp_static.image_file_ids if img.file_id == file_object_id), None)
    if not ref:
        raise HTTPException(status_code=404, detail="Image not linked to this DPP")

    try:
        grid_out = await fs_bucket.open_download_stream(file_object_id)
    except Exception as exc:
        logger.error("Error opening GridFS stream for file %s: %s", file_id, exc)
        raise HTTPException(status_code=404, detail="File not found in GridFS") from exc

    return StreamingResponse(
        grid_out,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={ref.filename}"},
    )
