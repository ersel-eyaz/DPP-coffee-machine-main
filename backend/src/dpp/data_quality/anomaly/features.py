"""
Feature extraction for statistical and ML-based anomaly detection.

The feature layer converts harmonized, graph-shaped DPP data into flat numeric
rows. These rows are the input for later statistical baselines and the planned
Isolation Forest component.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from dpp.data_quality.harmonization.result_access import effective_field_value
from dpp.data_quality.harmonization.schemas import HarmonizationResult, HarmonizedEntity


@dataclass(frozen=True)
class FeatureRow:
    """One flat numeric row extracted from a harmonized entity or record."""

    scope_name: str
    feature_set: str
    entity_id: str
    entity_type: str
    features: dict[str, float]
    source_entity_ids: list[str] = field(default_factory=list)
    missing_features: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)


def _as_float(value: Any) -> float | None:
    """Convert scalar or measurement-like values to float when possible."""
    if isinstance(value, dict) and "value" in value:
        value = value.get("value")

    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None

    return None


def _field_value(entity: HarmonizedEntity, field_path: str) -> Any | None:
    """Return the effective harmonized value for one canonical field."""
    field = entity.fields.get(field_path)
    if field is None or field.status in {"error", "ambiguous", "unmapped"}:
        return None
    return effective_field_value(field)


def _numeric_field_value(entity: HarmonizedEntity, field_path: str) -> float | None:
    """Return a numeric harmonized value for one canonical field."""
    return _as_float(_field_value(entity, field_path))


def _relation_targets(entity: HarmonizedEntity, relation_name: str) -> list[str]:
    """Return target ids for one preserved relation name."""
    return [
        relation.target_entity_id
        for relation in entity.relations
        if relation.relation_name == relation_name
    ]


def _single_relation_target(entity: HarmonizedEntity, relation_name: str) -> str | None:
    """Return the first target id for one preserved relation name."""
    targets = _relation_targets(entity, relation_name)
    return targets[0] if targets else None


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    """Return numerator / denominator when the denominator is positive."""
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def _add_feature(
    features: dict[str, float],
    missing: list[str],
    name: str,
    value: float | None,
) -> None:
    """Add a feature value or record that it could not be computed."""
    if value is None:
        missing.append(name)
        return
    features[name] = round(float(value), 6)


def _part_static_weight(result: HarmonizationResult, part_instance: HarmonizedEntity) -> tuple[str | None, float | None]:
    """Return the linked PartStatic id and weight for one PartInstance."""
    part_static_id = _single_relation_target(part_instance, "partStaticLink")
    if part_static_id is None:
        return None, None

    part_static = result.entities.get(part_static_id)
    if part_static is None:
        return part_static_id, None

    return part_static_id, _numeric_field_value(part_static, "PartStatic.weightGRM")


def _active_leaf_part_weight_summary(result: HarmonizationResult, root_part_id: str) -> dict[str, Any]:
    """Summarize active leaf-part weights below a root PartInstance."""
    visited: set[str] = set()
    leaf_part_ids: list[str] = []
    leaf_static_ids: list[str] = []
    leaf_weights: list[float] = []
    detached_part_ids: set[str] = set()
    missing_part_ids: set[str] = set()
    missing_weight_part_ids: list[str] = []

    def walk(part_id: str) -> None:
        if part_id in visited:
            return

        visited.add(part_id)
        part = result.entities.get(part_id)
        if part is None or part.entity_type != "PartInstance":
            missing_part_ids.add(part_id)
            return

        detached_part_ids.update(_relation_targets(part, "historyOfDetachedParts"))
        child_ids = _relation_targets(part, "compositeParts")
        if child_ids:
            for child_id in child_ids:
                walk(child_id)
            return

        leaf_part_ids.append(part_id)
        part_static_id, weight = _part_static_weight(result, part)
        if part_static_id is not None:
            leaf_static_ids.append(part_static_id)
        if weight is None:
            missing_weight_part_ids.append(part_id)
            return
        leaf_weights.append(weight)

    walk(root_part_id)
    return {
        "total_weight": sum(leaf_weights),
        "leaf_part_ids": leaf_part_ids,
        "leaf_static_ids": leaf_static_ids,
        "leaf_weights": leaf_weights,
        "detached_part_ids_excluded": sorted(detached_part_ids),
        "missing_part_ids": sorted(missing_part_ids),
        "missing_weight_part_ids": missing_weight_part_ids,
        "visited_part_ids": sorted(visited),
    }


def _material_weight_ratio_summary(result: HarmonizationResult) -> dict[str, Any]:
    """Return max material-to-part weight ratio across PartInstance entities."""
    ratios: list[float] = []
    part_ids: list[str] = []
    material_ids_by_part: dict[str, list[str]] = {}

    for part in [entity for entity in result.entities.values() if entity.entity_type == "PartInstance"]:
        _, part_weight = _part_static_weight(result, part)
        material_ids = _relation_targets(part, "compositeMaterials")
        if part_weight is None or part_weight <= 0 or not material_ids:
            continue

        material_weights: list[float] = []
        material_ids_with_weight: list[str] = []
        for material_id in material_ids:
            material = result.entities.get(material_id)
            if material is None or material.entity_type != "MaterialInstance":
                continue
            weight = _numeric_field_value(material, "MaterialInstance.weightGRM")
            if weight is None:
                continue
            material_weights.append(weight)
            material_ids_with_weight.append(material_id)

        if not material_weights:
            continue

        ratios.append(sum(material_weights) / part_weight)
        part_ids.append(part.entity_id)
        material_ids_by_part[part.entity_id] = material_ids_with_weight

    return {
        "max_ratio": max(ratios) if ratios else None,
        "part_ids": part_ids,
        "material_ids_by_part": material_ids_by_part,
    }


def _extract_product_feature_rows(result: HarmonizationResult) -> list[FeatureRow]:
    """Extract product usage and graph features from DPPInstance entities."""
    rows: list[FeatureRow] = []
    material_summary = _material_weight_ratio_summary(result)

    for instance in [entity for entity in result.entities.values() if entity.entity_type == "DPPInstance"]:
        features: dict[str, float] = {}
        missing: list[str] = []
        evidence: dict[str, Any] = {}
        source_ids = [instance.entity_id]

        operating = _numeric_field_value(instance, "DPPInstance.operatingHRS")
        brewing = _numeric_field_value(instance, "DPPInstance.brewingCount")
        cleaning = _numeric_field_value(instance, "DPPInstance.cleaningCount")
        chalk = _numeric_field_value(instance, "DPPInstance.chalkCount")
        grinding = _numeric_field_value(instance, "DPPInstance.coffeeGrindingCount")

        for name, value in (
            ("operatingHRS", operating),
            ("brewingCount", brewing),
            ("cleaningCount", cleaning),
            ("chalkCount", chalk),
            ("coffeeGrindingCount", grinding),
            ("cleaning_to_brewing_ratio", _safe_ratio(cleaning, brewing)),
            ("chalk_to_brewing_ratio", _safe_ratio(chalk, brewing)),
            ("grinding_to_brewing_ratio", _safe_ratio(grinding, brewing)),
            ("brews_per_operating_hour", _safe_ratio(brewing, operating)),
            ("max_material_weight_to_part_weight", material_summary["max_ratio"]),
        ):
            _add_feature(features, missing, name, value)

        dpp_static_id = _single_relation_target(instance, "dppStaticLink")
        root_part_id = _single_relation_target(instance, "partInstanceLink")
        product_weight = None
        if dpp_static_id is not None:
            source_ids.append(dpp_static_id)
            dpp_static = result.entities.get(dpp_static_id)
            if dpp_static is not None:
                product_weight = _numeric_field_value(dpp_static, "DPPStatic.weightGRM")

        active_summary: dict[str, Any] | None = None
        active_total = None
        if root_part_id is not None:
            source_ids.append(root_part_id)
            active_summary = _active_leaf_part_weight_summary(result, root_part_id)
            active_total = float(active_summary["total_weight"])

        _add_feature(features, missing, "product_weightGRM", product_weight)
        _add_feature(features, missing, "active_part_weightGRM", active_total)
        _add_feature(
            features,
            missing,
            "active_part_weight_to_product_weight",
            _safe_ratio(active_total, product_weight),
        )

        if active_summary is not None:
            evidence["active_part_tree"] = active_summary
        evidence["material_weight_ratios"] = material_summary

        rows.append(
            FeatureRow(
                scope_name=result.scope_name,
                feature_set="product_usage_graph",
                entity_id=instance.entity_id,
                entity_type=instance.entity_type,
                features=features,
                source_entity_ids=sorted(set(source_ids)),
                missing_features=missing,
                evidence=evidence,
            )
        )

    return rows


def _compatible_emission_factor_unit(activity_unit: str) -> str | None:
    """Return the expected emission-factor unit for an activity unit."""
    return {
        "kWh": "kgCO2e/kWh",
        "kg": "kgCO2e/kg",
        "km": "kgCO2e/km",
    }.get(activity_unit)


def _unit_compatibility_value(activity_unit: Any, factor_unit: Any) -> float | None:
    """Return 1.0 for compatible known units, 0.0 for incompatible known units."""
    if not isinstance(activity_unit, str) or not isinstance(factor_unit, str):
        return None
    expected_factor_unit = _compatible_emission_factor_unit(activity_unit)
    if expected_factor_unit is None:
        return None
    return 1.0 if factor_unit == expected_factor_unit else 0.0


def _extract_emission_feature_rows(result: HarmonizationResult) -> list[FeatureRow]:
    """Extract calculation and intensity features from GHGEmissionRecord entities."""
    rows: list[FeatureRow] = []

    for record in [entity for entity in result.entities.values() if entity.entity_type == "GHGEmissionRecord"]:
        features: dict[str, float] = {}
        missing: list[str] = []
        evidence: dict[str, Any] = {}
        source_ids = [record.entity_id]

        activity_id = _single_relation_target(record, "activity")
        factor_id = _single_relation_target(record, "emission_factor")
        activity = result.entities.get(activity_id) if activity_id is not None else None
        factor = result.entities.get(factor_id) if factor_id is not None else None

        if activity_id is not None:
            source_ids.append(activity_id)
        if factor_id is not None:
            source_ids.append(factor_id)

        quantity = _numeric_field_value(activity, "ActivityData.quantity") if activity is not None else None
        factor_value = _numeric_field_value(factor, "EmissionFactor.value") if factor is not None else None
        reported = _numeric_field_value(record, "GHGEmissionRecord.emissions_kg_co2e")
        expected = quantity * factor_value if quantity is not None and factor_value is not None else None
        absolute_deviation = abs(reported - expected) if reported is not None and expected is not None else None
        relative_deviation = _safe_ratio(absolute_deviation, abs(expected)) if expected is not None else None
        intensity = _safe_ratio(reported, quantity)

        activity_unit = _field_value(activity, "ActivityData.unit") if activity is not None else None
        factor_unit = _field_value(factor, "EmissionFactor.unit") if factor is not None else None

        for name, value in (
            ("quantity", quantity),
            ("factor_value", factor_value),
            ("reported_emissions", reported),
            ("expected_emissions", expected),
            ("absolute_calculation_deviation", absolute_deviation),
            ("relative_calculation_deviation", relative_deviation),
            ("reported_emissions_per_quantity", intensity),
            ("unit_compatible", _unit_compatibility_value(activity_unit, factor_unit)),
        ):
            _add_feature(features, missing, name, value)

        evidence.update(
            {
                "activity_entity_id": activity_id,
                "factor_entity_id": factor_id,
                "activity_unit": activity_unit,
                "factor_unit": factor_unit,
            }
        )

        rows.append(
            FeatureRow(
                scope_name=result.scope_name,
                feature_set="emission_calculation_intensity",
                entity_id=record.entity_id,
                entity_type=record.entity_type,
                features=features,
                source_entity_ids=sorted(set(source_ids)),
                missing_features=missing,
                evidence=evidence,
            )
        )

    return rows


def extract_feature_rows(result: HarmonizationResult) -> list[FeatureRow]:
    """Extract numeric feature rows for the supported ML-ready scopes."""
    if result.scope_name == "product":
        return _extract_product_feature_rows(result)
    if result.scope_name == "emission":
        return _extract_emission_feature_rows(result)
    return []


def build_feature_table(result: HarmonizationResult) -> dict[str, Any]:
    """Build a JSON-serializable feature table payload."""
    rows = extract_feature_rows(result)
    feature_names = sorted({name for row in rows for name in row.features})
    return {
        "scope_name": result.scope_name,
        "rows_total": len(rows),
        "feature_names": feature_names,
        "rows": [asdict(row) for row in rows],
    }
