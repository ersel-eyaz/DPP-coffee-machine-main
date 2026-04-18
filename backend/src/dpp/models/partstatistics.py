# src/dpp/models/partstatistics.py
"""
Material and part-tree aggregations.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

from beanie import Link
from pydantic import BaseModel, Field

from .material import MaterialStatic

if TYPE_CHECKING:
    from .part import PartInstance


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _resolve_link(maybe_link: Any) -> Any:
    """
    Resolve a Beanie Link (has `.fetch()`) or passthrough an already-resolved instance.
    """
    if hasattr(maybe_link, "fetch"):
        return await maybe_link.fetch()
    return maybe_link


def _value(obj: Any) -> Any:
    """
    Return `obj.value` if present, else `obj`. Useful for legacy Quantity-like objects.
    """
    return getattr(obj, "value", obj)


def _is_part_instance(obj: Any) -> bool:
    """
    Heuristic check for a PartInstance-like object, tolerant to missing discriminator.
    """
    if getattr(obj, "type_", None) == "PartInstance":
        return True
    return hasattr(obj, "compositeMaterials") and hasattr(obj, "compositeParts")


def _normalize_weight_to_kg(weight_field: Any) -> float:
    """
    Normalize mixed unit inputs to kilograms.
    """
    try:
        value = weight_field.value
    except AttributeError:
        value = weight_field

    unit = getattr(weight_field, "unitCode", "")
    if not unit:  # plain numbers are grams
        return float(value) / 1000.0

    unit = str(unit).upper()
    if unit in ("GRM", "G"):
        return float(value) / 1000.0
    if unit in ("KGM", "KG"):
        return float(value)
    if unit == "MG":
        return float(value) / 1_000_000.0

    # Fallback: treat as grams
    return float(value) / 1000.0


def _weight_g(weight_field: Any) -> float:
    """Return grams for object-or-float weight fields."""
    return _normalize_weight_to_kg(weight_field) * 1000.0


def _qnum(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v)
        return x if x == x else default  # NaN guard
    except Exception:
        return default


# ---------- purity collection helper ----------
async def _collect_purity_maps(part: "PartInstance") -> Tuple[Dict[str, float], Dict[str, float]]:
    """
    Traverse the part tree and collect
    """
    purity_weighted_sum: Dict[str, float] = {}
    purity_mass_sum: Dict[str, float] = {}

    async def _walk(node: Any) -> None:
        p = await node.fetch() if isinstance(node, Link) else node
        if not _is_part_instance(p):
            return

        for m in getattr(p, "compositeMaterials", []) or []:
            link_or_obj = getattr(m, "materialStaticLink", None)
            ms = await (link_or_obj.fetch() if isinstance(link_or_obj, Link) else link_or_obj)
            name = getattr(ms, "name", None) or "Unknown"

            grams = _weight_g(getattr(m, "weightGRM", 0.0))
            raw = getattr(m, "purityLevel", None)
            try:
                purity = float(raw) if raw is not None else None
                if purity is not None and purity > 1.5:  # treat 0..100 inputs
                    purity /= 100.0
                if purity is not None:
                    purity = max(0.0, min(1.0, purity))
            except Exception:
                purity = None

            if purity is not None and grams > 0:
                purity_weighted_sum[name] = purity_weighted_sum.get(name, 0.0) + (purity * grams)
                purity_mass_sum[name] = purity_mass_sum.get(name, 0.0) + grams

        for c in getattr(p, "compositeParts", []) or []:
            await _walk(c)

    await _walk(part)
    return purity_weighted_sum, purity_mass_sum


# ---------------------------------------------------------------------------
# DTOs (response models)
# ---------------------------------------------------------------------------


class RareEarthMaterialDetail(BaseModel):
    material_name: str
    weight_g: float
    share_pct: float
    is_rare_earth: bool = True


class RareEarthSummary(BaseModel):
    total_weight_g: float  # total weight of all materials (g)
    rare_earth_weight_g: float  # rare-earth-only weight (g)
    rare_earth_share_pct: float  # rare-earth share of total (%)
    materials: List[RareEarthMaterialDetail]  # rare-earth entries only


class MaterialShare(BaseModel):
    material_id: str = Field(..., description="MaterialStatic.id")
    material_name: str = Field(..., description="Material name")
    weight_g: float = Field(..., description="Aggregated weight (g)")
    share_pct: float = Field(..., description="Share of total weight (%)")
    recycling_share_pct: float = Field(..., description="Weighted recycling share (%)")


# ---------- DTOs ----------


class MaterialCombinedDetail(BaseModel):
    material_name: str
    weight_g: float
    share_pct: float
    recycled_share_pct: float
    is_rare_earth: bool
    is_hazardous: bool
    purity_percent: Optional[float] = Field(
        default=None, description="Mass-weighted mean purity as a fraction in [0,1]."
    )


class CombinedMaterialSummary(BaseModel):
    total_weight_g: float
    total_recycled_weight_g: float
    total_recycled_share_pct: float
    total_rare_earth_weight_g: float
    rare_earth_share_pct: float
    total_hazardous_weight_g: float
    hazardous_share_pct: float
    materials: List[MaterialCombinedDetail]


class HazardousMaterialLocationBrief(BaseModel):
    part_instance_id: str
    part_static_name: str
    weight_g: float
    share_pct: float  # share relative to the root PartInstance total (%)


class HazardousMaterialAggregatedDetail(BaseModel):
    material_name: str
    total_weight_g: float
    share_pct: float  # share relative to the root PartInstance total (%)
    warnings: List[str]
    locations: List[HazardousMaterialLocationBrief]


class HazardousMaterialsAggregatedList(BaseModel):
    materials: List[HazardousMaterialAggregatedDetail]


# ---------------------------------------------------------------------------
# Rare-earth aggregation
# ---------------------------------------------------------------------------
async def compute_rare_earth_metrics_rare_only(part: "PartInstance") -> RareEarthSummary:
    """
    Aggregate rare-earth material usage for a part tree
    """
    seen_parts: Set[str] = set()
    seen_material_instances: Set[str] = set()
    material_acc: Dict[str, Dict[str, Any]] = {}

    await _collect_rare_earth_part_tree(part, seen_parts, seen_material_instances, material_acc)

    total_weight = sum(float(info["weight_g"]) for info in material_acc.values())
    rare_earth_weight = sum(float(info["weight_g"]) for info in material_acc.values() if info["is_rare"])

    details: List[RareEarthMaterialDetail] = []
    for name, info in material_acc.items():
        if not info["is_rare"]:
            continue
        weight_grams = float(info["weight_g"])
        share_pct = (weight_grams / total_weight * 100.0) if total_weight > 0 else 0.0
        details.append(
            RareEarthMaterialDetail(
                material_name=name,
                weight_g=round(weight_grams, 4),
                share_pct=round(share_pct, 2),
            )
        )

    return RareEarthSummary(
        total_weight_g=round(total_weight, 4),
        rare_earth_weight_g=round(rare_earth_weight, 4),
        rare_earth_share_pct=round((rare_earth_weight / total_weight * 100.0) if total_weight > 0 else 0.0, 2),
        materials=sorted(details, key=lambda x: x.weight_g, reverse=True),
    )


async def _collect_rare_earth_part_tree(
    current: "PartInstance",
    seen_parts: Set[str],
    seen_material_instances: Set[str],
    material_acc: Dict[str, Dict[str, Any]],
) -> None:
    """DFS walk: collect rare-earth material weights keyed by material name."""
    if current.id in seen_parts:
        return
    seen_parts.add(current.id)

    for material_instance in getattr(current, "compositeMaterials", []) or []:
        if material_instance.id in seen_material_instances:
            continue
        seen_material_instances.add(material_instance.id)

        weight_grams = _weight_g(material_instance.weightGRM)
        static: MaterialStatic = await _resolve_link(material_instance.materialStaticLink)
        name = getattr(static, "name", "Unknown")
        is_rare = bool(getattr(static, "rareEarth", False))

        entry = material_acc.setdefault(name, {"weight_g": 0.0, "is_rare": False})
        entry["is_rare"] = entry["is_rare"] or is_rare
        entry["weight_g"] = float(entry["weight_g"]) + float(weight_grams)

    for child in getattr(current, "compositeParts", []) or []:
        child_part = await _resolve_link(child)
        if _is_part_instance(child_part):
            await _collect_rare_earth_part_tree(child_part, seen_parts, seen_material_instances, material_acc)


# ---------------------------------------------------------------------------
# Material shares (by MaterialStatic id)
# ---------------------------------------------------------------------------


async def compute_material_shares(part: "PartInstance") -> List[MaterialShare]:
    """
    Summarize material weights and recycling share for a part tree, keyed by MaterialStatic.id.
    """
    weights: Dict[str, float] = {}
    recycled_mass: Dict[str, float] = {}
    names: Dict[str, str] = {}
    seen_parts: Set[str] = set()

    await _collect_material_share_tree(part, weights, recycled_mass, names, seen_parts)

    total_all = sum(weights.values()) or 1.0
    result: List[MaterialShare] = []

    for material_id, weight in weights.items():
        recycled_weight = recycled_mass.get(material_id, 0.0)
        share_pct = (weight / total_all) * 100.0
        recycling_share_pct = (recycled_weight / weight * 100.0) if weight > 0 else 0.0
        result.append(
            MaterialShare(
                material_id=material_id,
                material_name=names.get(material_id, "Unknown"),
                weight_g=round(weight, 2),
                share_pct=round(share_pct, 2),
                recycling_share_pct=round(recycling_share_pct, 2),
            )
        )

    return result


async def _collect_material_share_tree(
    current: "PartInstance",
    weights: Dict[str, float],
    recycled_mass: Dict[str, float],
    names: Dict[str, str],
    seen_parts: Set[str],
) -> None:
    """DFS walk: collect total and recycled weights per MaterialStatic.id."""
    if current.id in seen_parts:
        return
    seen_parts.add(current.id)

    for material_instance in getattr(current, "compositeMaterials", []) or []:
        static: MaterialStatic = await _resolve_link(material_instance.materialStaticLink)
        material_id = static.id
        names[material_id] = getattr(static, "name", "Unknown")

        weight = _weight_g(material_instance.weightGRM)
        weights[material_id] = weights.get(material_id, 0.0) + float(weight)

        pct_recycled = float(_value(material_instance.percentRecycled)) / 100.0
        recycled_mass[material_id] = recycled_mass.get(material_id, 0.0) + (float(weight) * pct_recycled)

    for child in getattr(current, "compositeParts", []) or []:
        child_part = await _resolve_link(child)
        if _is_part_instance(child_part):
            await _collect_material_share_tree(child_part, weights, recycled_mass, names, seen_parts)


# ---------------------------------------------------------------------------
# Combined material summary (grouped by material name)
# ---------------------------------------------------------------------------


async def compute_combined_material_summary_by_name(part: "PartInstance") -> CombinedMaterialSummary:
    """
    Return aggregated material statistics keyed by material name.
    Includes totals for recycled, rare-earth, hazardous, and mass-weighted purity (0..1).
    """
    # Existing shares (weight, recycling, flags)
    raw_shares = await compute_material_shares(part)

    # Collect purity mass-weighted maps in parallel
    purity_weighted_sum, purity_mass_sum = await _collect_purity_maps(part)

    aggregates: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "total_weight": 0.0,
            "total_recycled_weight": 0.0,
            "has_rare": False,
            "has_hazard": False,
        }
    )

    total_rare_earth_weight = 0.0
    total_hazardous_weight = 0.0

    for share in raw_shares:
        name = share.material_name
        weight = float(share.weight_g)
        recycled_weight = weight * (float(share.recycling_share_pct) / 100.0)

        try:
            static = await MaterialStatic.get(share.material_id)
        except Exception:
            static = None

        is_rare = bool(getattr(static, "rareEarth", False)) if static else False
        is_hazard = bool(getattr(static, "hazardous", False)) if static else False

        entry = aggregates[name]
        entry["total_weight"] = float(entry["total_weight"]) + weight
        entry["total_recycled_weight"] = float(entry["total_recycled_weight"]) + recycled_weight
        entry["has_rare"] = bool(entry["has_rare"] or is_rare)
        entry["has_hazard"] = bool(entry["has_hazard"] or is_hazard)

        if is_rare:
            total_rare_earth_weight += weight
        if is_hazard:
            total_hazardous_weight += weight

    total_weight = sum(float(info["total_weight"]) for info in aggregates.values())
    total_recycled_weight = sum(float(info["total_recycled_weight"]) for info in aggregates.values())

    materials_details: List[MaterialCombinedDetail] = []
    for name, info in aggregates.items():
        weight_total = float(info["total_weight"])
        recycled_weight_total = float(info["total_recycled_weight"])
        share_pct = (weight_total / total_weight * 100.0) if total_weight > 0 else 0.0
        recycled_share_pct = (recycled_weight_total / weight_total * 100.0) if weight_total > 0 else 0.0

        # purity as 0..1 fraction (or None if no data)
        if purity_mass_sum.get(name, 0.0) > 0:
            purity_percent = float(purity_weighted_sum.get(name, 0.0) / purity_mass_sum[name])
        else:
            purity_percent = None

        materials_details.append(
            MaterialCombinedDetail(
                material_name=name,
                weight_g=round(weight_total, 4),
                share_pct=round(share_pct, 2),
                recycled_share_pct=round(recycled_share_pct, 2),
                is_rare_earth=bool(info["has_rare"]),
                is_hazardous=bool(info["has_hazard"]),
                purity_percent=purity_percent,
            )
        )

    total_recycled_share_pct = (total_recycled_weight / total_weight * 100.0) if total_weight > 0 else 0.0
    rare_earth_share_pct = (total_rare_earth_weight / total_weight * 100.0) if total_weight > 0 else 0.0
    hazardous_share_pct = (total_hazardous_weight / total_weight * 100.0) if total_weight > 0 else 0.0

    return CombinedMaterialSummary(
        total_weight_g=round(total_weight, 4),
        total_recycled_weight_g=round(total_recycled_weight, 4),
        total_recycled_share_pct=round(total_recycled_share_pct, 2),
        total_rare_earth_weight_g=round(total_rare_earth_weight, 4),
        rare_earth_share_pct=round(rare_earth_share_pct, 2),
        total_hazardous_weight_g=round(total_hazardous_weight, 4),
        hazardous_share_pct=round(hazardous_share_pct, 2),
        materials=sorted(materials_details, key=lambda m: m.weight_g, reverse=True),
    )


# ---------------------------------------------------------------------------
# Hazardous material aggregation (with locations)
# ---------------------------------------------------------------------------


async def compute_hazardous_materials_aggregated(part: "PartInstance") -> HazardousMaterialsAggregatedList:
    """
    Collect hazardous material amounts grouped by material and part location.
    """
    raw_shares = await compute_material_shares(part)
    total_weight = sum(ms.weight_g for ms in raw_shares) or 1.0

    seen_parts: Set[str] = set()
    aggregates: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "total_weight": 0.0,
            "warnings": set(),
            "locations": defaultdict(lambda: {"weight_g": 0.0, "part_static_name": ""}),
        }
    )

    await _collect_hazardous_materials_tree(part, aggregates, seen_parts)

    materials: List[HazardousMaterialAggregatedDetail] = []
    for material_name, info in aggregates.items():
        total_weight_material = float(info["total_weight"])
        share_pct = (total_weight_material / total_weight * 100.0) if total_weight > 0 else 0.0
        locations_list: List[HazardousMaterialLocationBrief] = []
        for part_id, loc_info in info["locations"].items():
            weight_val = float(loc_info["weight_g"])
            location_share = (weight_val / total_weight * 100.0) if total_weight > 0 else 0.0
            locations_list.append(
                HazardousMaterialLocationBrief(
                    part_instance_id=str(part_id),
                    part_static_name=str(loc_info["part_static_name"]),
                    weight_g=round(weight_val, 4),
                    share_pct=round(location_share, 2),
                )
            )

        locations_list.sort(key=lambda loc: loc.weight_g, reverse=True)

        materials.append(
            HazardousMaterialAggregatedDetail(
                material_name=material_name,
                total_weight_g=round(total_weight_material, 4),
                share_pct=round(share_pct, 2),
                warnings=sorted(info["warnings"]),
                locations=locations_list,
            )
        )

    materials.sort(key=lambda m: m.total_weight_g, reverse=True)
    return HazardousMaterialsAggregatedList(materials=materials)


async def _collect_hazardous_materials_tree(
    current: "PartInstance",
    aggregates: Dict[str, Dict[str, Any]],
    seen_parts: Set[str],
) -> None:
    """DFS walk: collect hazardous material weights and their locations."""
    if current.id in seen_parts:
        return
    seen_parts.add(current.id)

    static_part = await _resolve_link(getattr(current, "partStaticLink", None))
    part_static_name = getattr(static_part, "name", "Unknown")

    for material_instance in getattr(current, "compositeMaterials", []) or []:
        static_mat: MaterialStatic = await _resolve_link(material_instance.materialStaticLink)
        if not static_mat or not getattr(static_mat, "hazardous", False):
            continue

        name = getattr(static_mat, "name", "Unknown")
        weight_grams = _weight_g(material_instance.weightGRM)
        warnings = getattr(static_mat, "warnings", []) or []

        entry = aggregates[name]
        entry["total_weight"] = float(entry["total_weight"]) + float(weight_grams)
        entry["warnings"].update(warnings)

        location_entry = entry["locations"][current.id]
        location_entry["weight_g"] = float(location_entry["weight_g"]) + float(weight_grams)
        location_entry["part_static_name"] = part_static_name

    for child in getattr(current, "compositeParts", []) or []:
        child_part = await _resolve_link(child)
        if _is_part_instance(child_part):
            await _collect_hazardous_materials_tree(child_part, aggregates, seen_parts)


__all__ = [
    "RareEarthMaterialDetail",
    "RareEarthSummary",
    "MaterialShare",
    "MaterialCombinedDetail",
    "CombinedMaterialSummary",
    "HazardousMaterialLocationBrief",
    "HazardousMaterialAggregatedDetail",
    "HazardousMaterialsAggregatedList",
    "compute_rare_earth_metrics_rare_only",
    "compute_material_shares",
    "compute_combined_material_summary_by_name",
    "compute_hazardous_materials_aggregated",
]
