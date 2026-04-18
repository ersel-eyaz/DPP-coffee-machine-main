# src/dpp/models/dppstatistics.py
"""
Aggregations and response models for DPP statistics.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Tuple

from beanie import Link
from pydantic import BaseModel, Field

from .dpp import DPPInstance
from .ghg import GHGScope
from .part import PartInstance
from .processstep import (
    RepairServiceStep,
    ReplaceServiceStep,
    SecondaryValueStep,
    TransportStep,
)

# ---------------------------------------------------------------------------
# Diagnosis summary models
# ---------------------------------------------------------------------------


class SymptomDiagnosisSummaryEntry(BaseModel):
    """Single symptom line for the diagnosis summary."""

    symptom: str
    most_likely_diagnosis: str
    instance_count: int
    diagnosis_counts: Dict[str, int]


class DiagnosisSummaryResponse(BaseModel):
    """Aggregate diagnosis summary for a DPP static ID."""

    dpp_static_id: str
    total_instances: int
    summary: List[SymptomDiagnosisSummaryEntry]


# ---------------------------------------------------------------------------
# Process map models
# ---------------------------------------------------------------------------

PROCESS_CATEGORIES: Tuple[str, str, str] = ("production", "transport", "secondary")


class MapNode(BaseModel):
    """Node in a process map; represents a place/location."""

    id: Optional[str] = None
    name: Optional[str] = None
    latitude: float
    longitude: float
    categoryCounts: Dict[str, int] = Field(default_factory=lambda: {k: 0 for k in PROCESS_CATEGORIES})
    totalCount: int = 0


class MapEdge(BaseModel):
    """Directed edge in a process map; represents a step from source to target."""

    sourceId: Optional[str] = None
    targetId: Optional[str] = None
    category: str
    count: int = 1


class ProcessMapResponse(BaseModel):
    """Complete process map including nodes, edges, and category totals."""

    nodes: List[MapNode]
    edges: List[MapEdge]
    counts: Dict[str, int]


# ---------------------------------------------------------------------------
# Secondary value step helpers and response models
# ---------------------------------------------------------------------------


async def _gather_secondary_steps_from_part(part_obj: Any) -> List[SecondaryValueStep]:
    """
    Recursively collect SecondaryValueStep entries from a part tree.
    """
    steps: List[SecondaryValueStep] = []

    for step in getattr(part_obj, "partProcessTracking", []) or []:
        if isinstance(step, SecondaryValueStep):
            steps.append(step)
    for child in getattr(part_obj, "compositeParts", []) or []:
        child_part = await child.fetch() if isinstance(child, Link) else child
        if child_part:
            steps.extend(await _gather_secondary_steps_from_part(child_part))

    return steps


class ServiceModularSummary(BaseModel):
    """Counters for service steps and modular parts."""

    dpp_instance_id: str
    repair_count: int
    replace_count: int
    modular_part_count: int


class StaticServiceAggregateSummary(BaseModel):
    """Aggregate counters across all instances linked to a DPP static."""

    dpp_static_id: str
    total_instances: int
    total_repair_count: int
    total_replace_count: int
    total_modular_part_count: int
    average_repair_per_instance: float
    average_replace_per_instance: float
    average_modular_parts_per_instance: float
    per_instance: List[ServiceModularSummary]


class PlaceLocationSummary(BaseModel):
    """Representation of a place with coordinates."""

    name: str
    latitude: float
    longitude: float


class SecondaryStepInstanceEntry(BaseModel):
    """
    A single secondary step instance with selected counters and optional location.
    """

    step: dict
    cleaningCount: int
    chalkCount: int
    brewingCount: int
    coffeeGrindingCount: int
    location: Optional[PlaceLocationSummary]


class SecondaryStepAggregateEntry(BaseModel):
    """Aggregate of secondary steps grouped by step type."""

    step_type: str
    total_count: int
    entries: List[SecondaryStepInstanceEntry]


class SecondaryStepsAggregateResponse(BaseModel):
    """Top-level response for secondary steps aggregation."""

    dpp_static_id: str
    total_instances: int
    overall_counts: Dict[str, int]
    step_type_summaries: List[SecondaryStepAggregateEntry]


# ---------------------------------------------------------------------------
# Tree traversal helpers
# ---------------------------------------------------------------------------


async def _gather_all_parts(root: PartInstance | Link[PartInstance]) -> List[PartInstance]:
    """
    Flatten a composite PartInstance tree into a list.
    """
    collected: List[PartInstance] = []
    await _gather_all_parts_recursive(root, collected)
    return collected


async def _gather_all_parts_recursive(part_obj: Any, collected: List[PartInstance]) -> None:
    """
    Traversal for collecting all PartInstance nodes.
    """
    node = await part_obj.fetch() if isinstance(part_obj, Link) else part_obj
    if not isinstance(node, PartInstance):
        return
    collected.append(node)
    for child_part in getattr(node, "compositeParts", []) or []:
        await _gather_all_parts_recursive(child_part, collected)


# ---------------------------------------------------------------------------
# Public aggregators
# ---------------------------------------------------------------------------


async def compute_service_and_modular_counts(dpp_instance: DPPInstance) -> ServiceModularSummary:
    """
    Compute service and modular-part counts for a DPPInstance.
    """
    root_part: Any = dpp_instance.partInstanceLink
    repair_count = replace_count = modular_part_count = 0

    if not root_part:
        return ServiceModularSummary(
            dpp_instance_id=dpp_instance.id,
            repair_count=0,
            replace_count=0,
            modular_part_count=0,
        )

    all_parts = await _gather_all_parts(root_part)
    for part in all_parts:
        if getattr(part, "isModular", False):
            modular_part_count += 1
        for step in getattr(part, "partProcessTracking", []) or []:
            if isinstance(step, RepairServiceStep):
                repair_count += 1
            elif isinstance(step, ReplaceServiceStep):
                replace_count += 1

    return ServiceModularSummary(
        dpp_instance_id=dpp_instance.id,
        repair_count=repair_count,
        replace_count=replace_count,
        modular_part_count=modular_part_count,
    )


async def aggregate_ghg_for_dpp_instance(dpp_instance: DPPInstance) -> Dict[str, Any]:
    """
    Aggregate all GHGEmissionRecords for the given DPPInstance by traversing the
    linked part tree and its embedded materials.
    """
    aggregates: Dict[str, Dict[str, Any]] = {}
    seen_record_keys: set[str] = set()
    visited_part_ids: set[str] = set()

    root_part: Any = getattr(dpp_instance, "partInstanceLink", None)
    if root_part:
        root_part = await root_part.fetch() if isinstance(root_part, Link) else root_part
        await _recurse_part_for_ghg(root_part, aggregates, seen_record_keys, visited_part_ids)

    for scope_name in (GHGScope.SCOPE_1.value, GHGScope.SCOPE_2.value, GHGScope.SCOPE_3.value):
        aggregates.setdefault(scope_name, {"total": 0.0, "by_category": {}})

    for bucket in aggregates.values():
        bucket.setdefault("by_category", {})

    return {"dpp_id": dpp_instance.id, "aggregated": aggregates}


async def compute_transport_distances(root: PartInstance | Link[PartInstance]) -> Dict[str, float]:
    """
    Sum distanceKM from TransportStep across the full tree.
    """
    accumulators: Dict[str, float] = {"parts_km": 0.0, "materials_km": 0.0}
    if root is not None:
        await _walk_transport(root, accumulators)

    total_km = accumulators["parts_km"] + accumulators["materials_km"]
    return {
        "totalKM": round(total_km, 3),
        "partsKM": round(accumulators["parts_km"], 3),
        "materialsKM": round(accumulators["materials_km"], 3),
    }


# ---------------------------------------------------------------------------
# GHG helpers
# ---------------------------------------------------------------------------


def _enum_value(value: Any) -> str:
    """Return Enum.value if `value` is an Enum, else str(value)."""
    return value.value if isinstance(value, Enum) else str(value)


def _record_key(record: Any, step: Any) -> str:
    """
    Build a stable key for a GHG record to prevent double-counting when
    the same record is reachable via multiple paths.
    """
    record_id = getattr(record, "id", None)
    if record_id:
        return f"rec:{record_id}"

    scope_key = _enum_value(getattr(record, "scope", ""))
    category = getattr(record, "scope3_category", None)
    category_key = _enum_value(category) if category else "Uncategorized"
    quantity = getattr(getattr(record, "activity", None), "quantity", None)
    ef_value = getattr(getattr(record, "emission_factor", None), "value", None)
    emission_val = getattr(record, "emissions_kg_co2e", None)
    method = getattr(record, "calculation_method", None)
    step_tag = getattr(step, "id", None) or id(step)
    return f"{scope_key}|{category_key}|{quantity}|{ef_value}|{emission_val}|{method}|{step_tag}"


async def _collect_emissions_from_steps(
    steps: Optional[Iterable[Any]],
    aggregates: Dict[str, Dict[str, Any]],
    seen_record_keys: set[str],
) -> None:
    """Accumulate emissions in `aggregates` from a sequence of steps."""
    if not steps:
        return

    for step in steps or []:
        for record in getattr(step, "ghgEmissionRecords", []) or []:
            if getattr(record, "excluded_from_aggregation", False):
                continue

            key = _record_key(record, step)
            if key in seen_record_keys:
                continue
            seen_record_keys.add(key)

            scope_key = _enum_value(getattr(record, "scope", ""))
            bucket = aggregates.setdefault(scope_key, {"total": 0.0, "by_category": {}})

            value = float(getattr(record, "emissions_kg_co2e", 0.0) or 0.0)
            bucket["total"] += value

            if scope_key == GHGScope.SCOPE_3.value:
                category = getattr(record, "scope3_category", None)
                category_key = _enum_value(category) if category else "Uncategorized"
            else:
                category_key = "direct"

            bucket["by_category"][category_key] = bucket["by_category"].get(category_key, 0.0) + value


async def _recurse_part_for_ghg(
    part_obj: Any,
    aggregates: Dict[str, Dict[str, Any]],
    seen_record_keys: set[str],
    visited_part_ids: set[str],
) -> None:
    """Traversal for GHG aggregation across a part tree and its materials."""
    node = await part_obj.fetch() if isinstance(part_obj, Link) else part_obj
    if not isinstance(node, PartInstance):
        return
    if node.id in visited_part_ids:
        return
    visited_part_ids.add(node.id)

    await _collect_emissions_from_steps(getattr(node, "partProcessTracking", []), aggregates, seen_record_keys)

    for material in getattr(node, "compositeMaterials", []) or []:
        await _collect_emissions_from_steps(
            getattr(material, "materialProcessTracking", []), aggregates, seen_record_keys
        )

    for subpart in getattr(node, "compositeParts", []) or []:
        await _recurse_part_for_ghg(subpart, aggregates, seen_record_keys, visited_part_ids)


# ---------------------------------------------------------------------------
# Misc helpers (kept for compatibility with other endpoints)
# ---------------------------------------------------------------------------


def _count_failstates_recursive(part_instance: PartInstance) -> int:
    """
    Count parts with `hasFailstate == True` across a subtree.
    """
    if part_instance is None:
        return 0
    total = 1 if bool(getattr(part_instance, "hasFailstate", False)) else 0
    for child_part in getattr(part_instance, "compositeParts", []) or []:
        total += _count_failstates_recursive(child_part)
    return total


def _place_key(place_obj: Any) -> Optional[str]:
    """Derive key for a place."""
    if place_obj is None:
        return None
    pid = getattr(place_obj, "id", None) or getattr(place_obj, "name", None)
    return str(pid) if pid else None


def _coords_from_place(place_obj: Any) -> Tuple[Optional[float], Optional[float]]:
    """
    Extract (lat, lon) from a place or its nested `geo` attribute.
    """
    if place_obj is None:
        return None, None
    lat = getattr(place_obj, "latitude", None)
    lon = getattr(place_obj, "longitude", None)
    if lat is None or lon is None:
        geo = getattr(place_obj, "geo", None)
        if geo is not None:
            lat = getattr(geo, "latitude", None)
            lon = getattr(geo, "longitude", None)
    try:
        return (float(lat) if lat is not None else None, float(lon) if lon is not None else None)
    except Exception:
        return None, None


def _classify_step(step_obj: Any) -> str:
    """
    Classify a step into one of PROCESS_CATEGORIES based on its type/name.
    """
    type_name = (
        getattr(step_obj, "type_", None) or getattr(step_obj, "type", None) or step_obj.__class__.__name__
    ).lower()
    if "transport" in type_name:
        return "transport"
    if "production" in type_name or "manufactur" in type_name or "assembly" in type_name:
        return "production"
    return "secondary"


# ---------------------------------------------------------------------------
# Transport helpers
# ---------------------------------------------------------------------------


def _distance_value(item: Any, attr_name: str = "distanceKM") -> float:
    """Extract float distance."""
    try:
        distance = getattr(item, attr_name, 0.0)
        distance = getattr(distance, "value", distance)
        return float(distance or 0.0)
    except Exception:
        return 0.0


async def _walk_transport(part_obj: Any, accumulators: Dict[str, float]) -> None:
    """
    Accumulates TransportStep distances for parts and materials.
    """
    node = await part_obj.fetch() if isinstance(part_obj, Link) else part_obj
    if not isinstance(node, PartInstance):
        return

    for step in getattr(node, "partProcessTracking", []) or []:
        if isinstance(step, TransportStep):
            accumulators["parts_km"] += _distance_value(step)

    for material in getattr(node, "compositeMaterials", []) or []:
        for step in getattr(material, "materialProcessTracking", []) or []:
            if isinstance(step, TransportStep):
                accumulators["materials_km"] += _distance_value(step)

    for child_part in getattr(node, "compositeParts", []) or []:
        await _walk_transport(child_part, accumulators)


__all__ = [
    "SymptomDiagnosisSummaryEntry",
    "DiagnosisSummaryResponse",
    "MapNode",
    "MapEdge",
    "ProcessMapResponse",
    "ServiceModularSummary",
    "StaticServiceAggregateSummary",
    "PlaceLocationSummary",
    "SecondaryStepInstanceEntry",
    "SecondaryStepAggregateEntry",
    "SecondaryStepsAggregateResponse",
    "compute_service_and_modular_counts",
    "aggregate_ghg_for_dpp_instance",
    "compute_transport_distances",
    "_gather_secondary_steps_from_part",
    "_gather_all_parts",
    "_count_failstates_recursive",
    "_place_key",
    "_coords_from_place",
    "_classify_step",
]
