from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from dpp.harmonization.schemas import (
    FieldRole,
    HarmonizationResult,
    HarmonizationStats,
    HarmonizedEntity,
    HarmonizedField,
    HarmonizedRelation,
    IssueSeverity,
)


def build_normalized_result(
    mapped: Any,
    raw_property_count: int = 0,
    raw_relation_count: int = 0,
) -> HarmonizationResult:
    """
    Convert mapped output into a compact normalized HarmonizationResult.

    This version stays intentionally small:
    - normalize only a handful of units/values/enums we actually need now
    - avoid noisy issue generation for expected conversions
    - keep compatibility with mapper outputs accessed via dynamic attributes
    """
    result = HarmonizationResult(
        stats=HarmonizationStats(
            raw_property_count=raw_property_count,
            raw_relation_count=raw_relation_count,
        )
    )

    for entity in _iter_mapped_entities(mapped):
        normalized_entity = HarmonizedEntity(
            entity_id=str(_read(entity, "entity_id")),
            entity_type=_read(entity, "entity_type"),
            source_ids=_as_string_list(_read(entity, "source_ids", [])),
            source_node_types=_as_string_list(_read(entity, "source_node_types", [])),
            source_paths=_as_string_list(_read(entity, "source_paths", [])),
            tags=_as_string_list(_read(entity, "tags", [])),
        )

        raw_fields = _read(entity, "fields", {})
        if isinstance(raw_fields, dict):
            for field_name, field in raw_fields.items():
                normalized_field = _normalize_field(field_name, field)
                normalized_entity.fields[field_name] = normalized_field

        _synchronize_entity_fields(normalized_entity)
        result.entities[normalized_entity.entity_id] = normalized_entity

    for relation in _iter_mapped_relations(mapped):
        result.relations.append(
            HarmonizedRelation(
                relation_type=_read(relation, "relation_type"),
                subject_entity_id=str(_read(relation, "subject_entity_id")),
                object_entity_id=str(_read(relation, "object_entity_id")),
                confidence=float(_read(relation, "confidence", 1.0)),
                provenance_paths=_as_string_list(_read(relation, "provenance_paths", [])),
                notes=_as_string_list(_read(relation, "notes", [])),
            )
        )

    # Keep mapper issues only; do not add noisy info issues for routine normalization.
    for issue in _iter_mapped_issues(mapped):
        result.issues.append(issue)

    result.stats.harmonized_entity_count = len(result.entities)
    result.stats.harmonized_relation_count = len(result.relations)
    result.stats.harmonized_field_count = sum(
        len(entity.fields) for entity in result.entities.values()
    )
    result.stats.issue_count = len(result.issues)
    result.stats.warning_count = sum(
        1 for issue in result.issues if getattr(issue, "severity", None) == IssueSeverity.WARNING
    )
    result.stats.error_count = sum(
        1 for issue in result.issues if getattr(issue, "severity", None) == IssueSeverity.ERROR
    )
    result.success = result.stats.error_count == 0
    return result


def _normalize_field(field_name: str, field: Any) -> HarmonizedField:
    canonical_name = str(_read(field, "canonical_name", field_name))
    original_value = _read(field, "original_value", _read(field, "normalized_value"))
    original_unit = _read(field, "original_unit", _read(field, "normalized_unit"))
    normalized_value = _read(field, "normalized_value", original_value)
    normalized_unit = _read(field, "normalized_unit", original_unit)

    normalized_field = HarmonizedField(
        canonical_name=canonical_name,
        role=_coerce_field_role(_read(field, "role", "context")),
        normalized_value=normalized_value,
        normalized_unit=normalized_unit,
        original_label=_read(field, "original_label"),
        original_value=original_value,
        original_unit=original_unit,
        confidence=float(_read(field, "confidence", 1.0)),
        matched_by=str(_read(field, "matched_by", "unknown")),
        provenance_paths=_as_string_list(_read(field, "provenance_paths", [])),
        supporting_evidence=_as_string_list(_read(field, "supporting_evidence", [])),
        notes=_as_string_list(_read(field, "notes", [])),
    )

    name = normalized_field.canonical_name

    if name in {"DPPInstance.operatingHRS", "PartStatic.mtbfHRS"}:
        normalized_field.normalized_unit = _normalize_hour_unit(normalized_field.normalized_unit)

    elif name in {
        "DPPInstance.cleaningCount",
        "DPPInstance.chalkCount",
        "DPPInstance.brewingCount",
    }:
        normalized_field.normalized_unit = _normalize_count_unit(normalized_field.normalized_unit)

    elif name in {"PartStatic.weightGRM", "MaterialInstance.weightGRM"}:
        normalized_field.normalized_value, normalized_field.normalized_unit = _normalize_weight_to_grams(
            normalized_field.normalized_value,
            normalized_field.normalized_unit,
        )

    elif name in {"MaterialInstance.percentRecycled", "MaterialInstance.purityLevel"}:
        normalized_field.normalized_value, normalized_field.normalized_unit = _normalize_percentage_like(
            normalized_field.normalized_value,
            normalized_field.normalized_unit,
        )

    elif name in {"ProcessStep.beginDate", "ProcessStep.endDate"}:
        normalized_field.normalized_value = _normalize_datetime(normalized_field.normalized_value)

    elif name == "GHGEmissionRecord.scope":
        normalized_field.normalized_value = _normalize_scope(normalized_field.normalized_value)

    elif name == "GHGEmissionRecord.scope3_category":
        normalized_field.normalized_value = _to_snake_case(str(normalized_field.normalized_value)) if isinstance(normalized_field.normalized_value, str) else normalized_field.normalized_value

    elif name == "GHGEmissionRecord.emissions_kg_co2e":
        normalized_field.normalized_unit = _canonicalize_emission_mass_unit(normalized_field.normalized_unit)

    elif name == "ActivityData.quantity":
        normalized_field.normalized_value, normalized_field.normalized_unit = _normalize_distance_quantity(
            normalized_field.normalized_value,
            normalized_field.normalized_unit,
        )

    elif name == "ActivityData.unit":
        normalized_field.normalized_value = _canonicalize_distance_unit_value(normalized_field.normalized_value)

    elif name in {"EmissionFactor.value", "EmissionFactor.unit"}:
        normalized_field.normalized_value, normalized_field.normalized_unit = _normalize_emission_factor_field(
            normalized_field.normalized_value,
            normalized_field.normalized_unit,
        )

    return normalized_field


def _synchronize_entity_fields(entity: HarmonizedEntity) -> None:
    quantity_field = entity.fields.get("ActivityData.quantity")
    unit_field = entity.fields.get("ActivityData.unit")
    if quantity_field and unit_field and quantity_field.normalized_unit:
        unit_field.normalized_value = quantity_field.normalized_unit

    value_field = entity.fields.get("EmissionFactor.value")
    ef_unit_field = entity.fields.get("EmissionFactor.unit")
    if value_field and ef_unit_field and value_field.normalized_unit:
        ef_unit_field.normalized_value = value_field.normalized_unit


# ---------------------------------------------------------------------------
# Specific normalizers
# ---------------------------------------------------------------------------


def _normalize_hour_unit(unit: Any) -> Any:
    normalized = _normalize_string(unit)
    if normalized in {"h", "hr", "hrs", "hour", "hours"}:
        return "h"
    return unit


def _normalize_count_unit(unit: Any) -> Any:
    normalized = _normalize_string(unit)
    if normalized in {"count", "counts", "cycle", "cycles", "time", "times"}:
        return "count"
    return unit


def _normalize_weight_to_grams(value: Any, unit: Any) -> tuple[Any, Any]:
    if not _is_number(value):
        return value, unit

    normalized = _normalize_string(unit)
    if normalized in {"kg", "kilogram", "kilograms"}:
        return float(value) * 1000.0, "g"
    if normalized in {"g", "gram", "grams"}:
        return value, "g"
    return value, unit


def _normalize_percentage_like(value: Any, unit: Any) -> tuple[Any, Any]:
    if not _is_number(value):
        return value, unit

    normalized = _normalize_string(unit)
    if normalized in {"%", "percent", "percentage", "pct"}:
        return value, "%" if normalized != "pct" else "pct"
    if 0.0 <= float(value) <= 1.0:
        return float(value) * 100.0, "pct"
    return value, unit


def _normalize_datetime(value: Any) -> Any:
    if not isinstance(value, str):
        return value

    candidates = [value.strip(), value.strip().replace(" ", "T")]
    for candidate in candidates:
        try:
            if candidate.endswith("Z"):
                dt = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
            else:
                dt = datetime.fromisoformat(candidate)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt.isoformat().replace("+00:00", "Z")
        except ValueError:
            continue
    return value


def _normalize_scope(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    raw = _normalize_string(value)
    mapping = {
        "scope 1": "scope_1",
        "scope_1": "scope_1",
        "scope1": "scope_1",
        "scope 2": "scope_2",
        "scope_2": "scope_2",
        "scope2": "scope_2",
        "scope 3": "scope_3",
        "scope_3": "scope_3",
        "scope3": "scope_3",
    }
    return mapping.get(raw, _to_snake_case(value))


def _canonicalize_emission_mass_unit(unit: Any) -> Any:
    normalized = _normalize_string(unit)
    mapping = {
        "kgco2e": "kg_co2e",
        "kg_co2e": "kg_co2e",
        "kg co2e": "kg_co2e",
    }
    return mapping.get(normalized, unit)


def _normalize_distance_quantity(value: Any, unit: Any) -> tuple[Any, Any]:
    if not _is_number(value):
        return value, unit

    normalized = _normalize_string(unit)
    if normalized in {"m", "meter", "meters", "metre", "metres"}:
        return float(value) / 1000.0, "km"
    if normalized in {"km", "kilometer", "kilometers", "kilometre", "kilometres"}:
        return value, "km"
    return value, unit


def _canonicalize_distance_unit_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    normalized = _normalize_string(value)
    if normalized in {"m", "meter", "meters", "metre", "metres"}:
        return "m"
    if normalized in {"km", "kilometer", "kilometers", "kilometre", "kilometres"}:
        return "km"
    return value


def _normalize_emission_factor_field(value: Any, unit: Any) -> tuple[Any, Any]:
    if isinstance(value, str):
        value = _canonicalize_emission_factor_unit(value)
    if unit is not None:
        unit = _canonicalize_emission_factor_unit(unit)
    return value, unit


def _canonicalize_emission_factor_unit(unit: Any) -> Any:
    normalized = _normalize_string(unit)
    if normalized is None:
        return unit
    compact = normalized.replace(" ", "")
    mapping = {
        "kgco2e/km": "kg_co2e_per_km",
        "kg_co2e/km": "kg_co2e_per_km",
        "kg_co2e_per_km": "kg_co2e_per_km",
        "kgco2e/kwh": "kg_co2e_per_kwh",
        "kg_co2e/kwh": "kg_co2e_per_kwh",
        "kg_co2e_per_kwh": "kg_co2e_per_kwh",
        "kgco2e/kg": "kg_co2e_per_kg",
        "kg_co2e/kg": "kg_co2e_per_kg",
        "kg_co2e_per_kg": "kg_co2e_per_kg",
    }
    return mapping.get(compact, unit)


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def _iter_mapped_entities(mapped: Any) -> list[Any]:
    entities = _read(mapped, "entities", {})
    if isinstance(entities, dict):
        return list(entities.values())
    if isinstance(entities, list):
        return entities
    return []


def _iter_mapped_relations(mapped: Any) -> list[Any]:
    relations = _read(mapped, "relations", [])
    return relations if isinstance(relations, list) else []


def _iter_mapped_issues(mapped: Any) -> list[Any]:
    issues = _read(mapped, "issues", [])
    return issues if isinstance(issues, list) else []


def _read(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _coerce_field_role(value: Any) -> FieldRole:
    if isinstance(value, FieldRole):
        return value
    raw = str(value).strip().lower()
    if raw == "primary":
        return FieldRole.PRIMARY
    if raw == "derived":
        return FieldRole.DERIVED
    return FieldRole.CONTEXT


def _normalize_string(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).strip().lower()


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _to_snake_case(value: str) -> str:
    cleaned = (
        value.strip()
        .replace("-", " ")
        .replace("/", " ")
        .replace("(", " ")
        .replace(")", " ")
        .replace(",", " ")
    )
    parts = [part for part in cleaned.lower().split() if part]
    return "_".join(parts)
