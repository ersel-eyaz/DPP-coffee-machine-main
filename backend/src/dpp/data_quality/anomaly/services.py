"""
Plausibility and anomaly analysis over harmonized DPP data.

This module starts with transparent rule-based indicators. It is structured so
later thesis work can add statistical baselines or embedding-based semantic
indicators while preserving deterministic report output.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from dpp.data_quality.anomaly.profiles import ProductProfileMatch, resolve_product_profile
from dpp.data_quality.anomaly.rules import (
    EMISSION_NUMERIC_RANGE_RULES,
    PRODUCT_NUMERIC_RANGE_RULES,
    SERVICE_NUMERIC_RANGE_RULES,
    NumericRangeRule,
)
from dpp.data_quality.anomaly.schemas import AnomalyFinding, AnomalyResult
from dpp.data_quality.harmonization.result_access import effective_field_value
from dpp.data_quality.harmonization.schemas import HarmonizationResult, HarmonizedEntity
from dpp.data_quality.harmonization.service_concepts import TEXT_CONCEPTS_BY_KIND
from dpp.data_quality.scopes import SUPPORTED_SCOPES
from dpp.data_quality.scopes.schemas import CanonicalRelation


class AnomalyServiceError(ValueError):
    """Raised when anomaly analysis cannot run safely."""


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
    """Return a clean field value from one entity."""
    field = entity.fields.get(field_path)
    if field is None or field.status in {"error", "ambiguous", "unmapped"}:
        return None
    return effective_field_value(field)


def _numeric_field_value(entity: HarmonizedEntity, field_path: str) -> float | None:
    """Return a numeric clean field value from one entity."""
    value = _field_value(entity, field_path)
    return _as_float(value)


def _is_out_of_range(value: float, rule: NumericRangeRule) -> bool:
    """Return True when a numeric value violates a range rule."""
    if rule.min_value is not None and value < rule.min_value:
        return True
    if rule.max_value is not None and value > rule.max_value:
        return True
    return False


def _apply_numeric_range_rules(
    result: HarmonizationResult,
    rules: tuple[NumericRangeRule, ...],
) -> list[AnomalyFinding]:
    """Apply configured numeric range rules to harmonized fields."""
    findings: list[AnomalyFinding] = []

    for entity in result.entities.values():
        for rule in rules:
            if not rule.field_path.startswith(f"{entity.entity_type}."):
                continue

            value = _numeric_field_value(entity, rule.field_path)
            if value is None or not _is_out_of_range(value, rule):
                continue

            findings.append(
                AnomalyFinding(
                    check_id=rule.check_id,
                    category="range",
                    severity=rule.severity,  # type: ignore[arg-type]
                    message=f"{rule.field_path} value {value:g} is outside the expected plausibility range.",
                    entity_id=entity.entity_id,
                    entity_type=entity.entity_type,
                    field_path=rule.field_path,
                    observed_value=value,
                    expected=rule.expected_range(),
                    evidence={"description": rule.description},
                    review_action="verify_source_value_or_unit",
                )
            )

    return findings


def _relation_targets(entity: HarmonizedEntity, relation_name: str) -> list[str]:
    """Return preserved relation target ids by relation name."""
    return [
        relation.target_entity_id
        for relation in entity.relations
        if relation.relation_name == relation_name
    ]


def _apply_required_relation_checks(result: HarmonizationResult) -> list[AnomalyFinding]:
    """Check required model-near links and dangling preserved references."""
    scope = SUPPORTED_SCOPES[result.scope_name]
    findings: list[AnomalyFinding] = []
    relations_by_source: dict[str, list[CanonicalRelation]] = {}
    for relation in scope.relations:
        relations_by_source.setdefault(relation.source_entity_type, []).append(relation)

    for entity in result.entities.values():
        configured_relations = relations_by_source.get(entity.entity_type, [])

        for relation in entity.relations:
            if relation.target_entity_id not in result.entities:
                findings.append(
                    AnomalyFinding(
                        check_id="dangling_relation_target",
                        category="relationship",
                        severity="warning",
                        message=(
                            f"{entity.entity_type}.{relation.relation_name} points to missing entity "
                            f"{relation.target_entity_id!r}."
                        ),
                        entity_id=entity.entity_id,
                        entity_type=entity.entity_type,
                        relation_path=f"{entity.entity_type}.{relation.relation_name}",
                        observed_value=relation.target_entity_id,
                        expected={"target_entity_type": relation.target_entity_type},
                        review_action="verify_reference_target",
                    )
                )

        for relation in configured_relations:
            if not relation.required:
                continue

            targets = _relation_targets(entity, relation.relation_name)
            if targets:
                continue

            findings.append(
                AnomalyFinding(
                    check_id="missing_required_relation",
                    category="relationship",
                    severity="warning",
                    message=f"Required relation {relation.path} is missing.",
                    entity_id=entity.entity_id,
                    entity_type=entity.entity_type,
                    relation_path=relation.path,
                    expected={"target_entity_type": relation.target_entity_type},
                    evidence={"description": relation.description},
                    review_action="verify_model_link",
                )
            )

    return findings


def _first_entity_by_type(result: HarmonizationResult, entity_type: str) -> HarmonizedEntity | None:
    """Return the first harmonized entity of a given type."""
    for entity in result.entities.values():
        if entity.entity_type == entity_type:
            return entity
    return None


def _single_relation_target(entity: HarmonizedEntity, relation_name: str) -> str | None:
    """Return the first preserved relation target id for a relation."""
    targets = _relation_targets(entity, relation_name)
    return targets[0] if targets else None


def _part_static_weight(result: HarmonizationResult, part_instance: HarmonizedEntity) -> tuple[str | None, float | None]:
    """Return the linked PartStatic id and weight for one PartInstance."""
    part_static_id = _single_relation_target(part_instance, "partStaticLink")
    if part_static_id is None:
        return None, None

    part_static = result.entities.get(part_static_id)
    if part_static is None:
        return part_static_id, None

    return part_static_id, _numeric_field_value(part_static, "PartStatic.weightGRM")


def _active_part_tree_weight_summary(
    result: HarmonizationResult,
    root_part_id: str,
) -> dict[str, Any]:
    """
    Summarize active leaf-part weights below a root PartInstance.

    Only `compositeParts` are treated as the current active structure.
    `historyOfDetachedParts` is preserved as history and reported as excluded
    evidence, but it is not traversed into the current product total.
    """
    visited: set[str] = set()
    cycle_part_ids: set[str] = set()
    missing_part_ids: set[str] = set()
    detached_part_ids: set[str] = set()
    leaf_part_ids: list[str] = []
    leaf_static_ids: list[str] = []
    leaf_weights: list[float] = []
    missing_weight_part_ids: list[str] = []

    def walk(part_id: str) -> None:
        if part_id in visited:
            cycle_part_ids.add(part_id)
            return

        visited.add(part_id)
        entity = result.entities.get(part_id)
        if entity is None or entity.entity_type != "PartInstance":
            missing_part_ids.add(part_id)
            return

        detached_part_ids.update(_relation_targets(entity, "historyOfDetachedParts"))
        child_ids = _relation_targets(entity, "compositeParts")
        if child_ids:
            for child_id in child_ids:
                walk(child_id)
            return

        leaf_part_ids.append(part_id)
        part_static_id, weight = _part_static_weight(result, entity)
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
        "visited_part_ids": sorted(visited),
        "detached_part_ids_excluded": sorted(detached_part_ids),
        "missing_part_ids": sorted(missing_part_ids),
        "cycle_part_ids": sorted(cycle_part_ids),
        "missing_weight_part_ids": missing_weight_part_ids,
    }


def _apply_active_part_tree_weight_checks(result: HarmonizationResult) -> list[AnomalyFinding]:
    """Compare active leaf-part tree weight with the linked product weight."""
    findings: list[AnomalyFinding] = []

    for dpp_instance in [entity for entity in result.entities.values() if entity.entity_type == "DPPInstance"]:
        dpp_static_id = _single_relation_target(dpp_instance, "dppStaticLink")
        root_part_id = _single_relation_target(dpp_instance, "partInstanceLink")
        if dpp_static_id is None or root_part_id is None:
            continue

        dpp_static = result.entities.get(dpp_static_id)
        if dpp_static is None:
            continue

        product_weight = _numeric_field_value(dpp_static, "DPPStatic.weightGRM")
        if product_weight is None:
            continue

        summary = _active_part_tree_weight_summary(result, root_part_id)
        active_total = float(summary["total_weight"])
        if active_total <= 0 or active_total <= product_weight * 1.05:
            continue

        findings.append(
            AnomalyFinding(
                check_id="active_part_tree_weight_exceeds_product_weight",
                category="consistency",
                severity="warning",
                message="Active leaf-part tree weight is greater than the linked product weight.",
                entity_id=dpp_instance.entity_id,
                entity_type=dpp_instance.entity_type,
                relation_path="DPPInstance.partInstanceLink",
                observed_value=active_total,
                expected={"max_approx": product_weight, "tolerance_factor": 1.05},
                evidence={
                    "product_entity_id": dpp_static.entity_id,
                    "root_part_instance_id": root_part_id,
                    "aggregation_scope": "active_leaf_part_instances_reachable_via_compositeParts",
                    "leaf_part_ids": summary["leaf_part_ids"],
                    "leaf_static_ids": summary["leaf_static_ids"],
                    "leaf_weightsGRM": summary["leaf_weights"],
                    "detached_part_ids_excluded": summary["detached_part_ids_excluded"],
                    "missing_part_ids": summary["missing_part_ids"],
                    "cycle_part_ids": summary["cycle_part_ids"],
                    "missing_weight_part_ids": summary["missing_weight_part_ids"],
                },
                review_action="verify_active_part_tree_or_product_weight",
            )
        )

    return findings


def _ratio_finding(
    *,
    check_id: str,
    message: str,
    entity: HarmonizedEntity,
    field_path: str,
    observed_value: float,
    expected: Any,
    evidence: dict[str, Any] | None = None,
    severity: str = "warning",
    review_action: str = "verify_usage_counter_ratio",
) -> AnomalyFinding:
    """Build a usage-ratio consistency finding."""
    return AnomalyFinding(
        check_id=check_id,
        category="consistency",
        severity=severity,  # type: ignore[arg-type]
        message=message,
        entity_id=entity.entity_id,
        entity_type=entity.entity_type,
        field_path=field_path,
        observed_value=observed_value,
        expected=expected,
        evidence=evidence or {},
        review_action=review_action,
    )


def _apply_product_usage_ratio_checks(result: HarmonizationResult) -> list[AnomalyFinding]:
    """Apply broad plausibility ratios for product usage counters."""
    findings: list[AnomalyFinding] = []

    for dpp_instance in [entity for entity in result.entities.values() if entity.entity_type == "DPPInstance"]:
        operating = _numeric_field_value(dpp_instance, "DPPInstance.operatingHRS")
        brewing = _numeric_field_value(dpp_instance, "DPPInstance.brewingCount")
        cleaning = _numeric_field_value(dpp_instance, "DPPInstance.cleaningCount")
        chalk = _numeric_field_value(dpp_instance, "DPPInstance.chalkCount")

        if operating is not None and brewing is not None:
            if operating <= 0 < brewing:
                findings.append(
                    _ratio_finding(
                        check_id="brewing_count_without_operating_hours",
                        message="DPPInstance.brewingCount is positive while operating hours are zero.",
                        entity=dpp_instance,
                        field_path="DPPInstance.brewingCount",
                        observed_value=brewing,
                        expected={"operatingHRS": "> 0"},
                        review_action="verify_operating_hours_or_brewing_counter",
                    )
                )
            elif operating > 0:
                brews_per_hour = brewing / operating
                if brews_per_hour > 20.0:
                    findings.append(
                        _ratio_finding(
                            check_id="brewing_per_operating_hour_high",
                            message="Brewing count per operating hour is unusually high.",
                            entity=dpp_instance,
                            field_path="DPPInstance.brewingCount",
                            observed_value=round(brews_per_hour, 3),
                            expected={"max_brews_per_operating_hour": 20.0},
                            evidence={"brewingCount": brewing, "operatingHRS": operating},
                            severity="info",
                            review_action="verify_usage_counter_semantics",
                        )
                    )

        if brewing is None or brewing <= 0:
            continue

        for field_path, counter, max_ratio in (
            ("DPPInstance.cleaningCount", cleaning, 0.2),
            ("DPPInstance.chalkCount", chalk, 0.2),
        ):
            if counter is None:
                continue
            ratio = counter / brewing
            if ratio <= max_ratio:
                continue
            findings.append(
                _ratio_finding(
                    check_id="maintenance_to_brewing_ratio_high",
                    message=f"{field_path} is unusually high relative to DPPInstance.brewingCount.",
                    entity=dpp_instance,
                    field_path=field_path,
                    observed_value=round(ratio, 3),
                    expected={"max_ratio_to_brewingCount": max_ratio},
                    evidence={"counter_value": counter, "brewingCount": brewing},
                    severity="info",
                    review_action="verify_maintenance_schedule_or_counter_semantics",
                )
            )

    return findings


def _apply_product_consistency_checks(result: HarmonizationResult) -> list[AnomalyFinding]:
    """Apply cross-field and cross-entity checks for product-scope data."""
    findings: list[AnomalyFinding] = []

    dpp_static = _first_entity_by_type(result, "DPPStatic")
    if dpp_static is not None:
        product_weight = _numeric_field_value(dpp_static, "DPPStatic.weightGRM")
        if product_weight is not None:
            for part_static in [entity for entity in result.entities.values() if entity.entity_type == "PartStatic"]:
                part_weight = _numeric_field_value(part_static, "PartStatic.weightGRM")
                if part_weight is None or part_weight <= product_weight * 1.05:
                    continue
                findings.append(
                    AnomalyFinding(
                        check_id="part_weight_exceeds_product_weight",
                        category="consistency",
                        severity="warning",
                        message="PartStatic.weightGRM is greater than the linked product weight.",
                        entity_id=part_static.entity_id,
                        entity_type=part_static.entity_type,
                        field_path="PartStatic.weightGRM",
                        observed_value=part_weight,
                        expected={"max_approx": product_weight},
                        evidence={"product_entity_id": dpp_static.entity_id, "product_weightGRM": product_weight},
                        review_action="verify_component_weight_or_product_weight",
                    )
                )

    for dpp_instance in [entity for entity in result.entities.values() if entity.entity_type == "DPPInstance"]:
        brewing = _numeric_field_value(dpp_instance, "DPPInstance.brewingCount")
        cleaning = _numeric_field_value(dpp_instance, "DPPInstance.cleaningCount")
        chalk = _numeric_field_value(dpp_instance, "DPPInstance.chalkCount")
        grinding = _numeric_field_value(dpp_instance, "DPPInstance.coffeeGrindingCount")

        for field_path, counter in (
            ("DPPInstance.cleaningCount", cleaning),
            ("DPPInstance.chalkCount", chalk),
        ):
            if brewing is None or counter is None or counter <= brewing:
                continue
            findings.append(
                AnomalyFinding(
                    check_id="maintenance_counter_exceeds_brewing_count",
                    category="consistency",
                    severity="warning",
                    message=f"{field_path} is greater than DPPInstance.brewingCount.",
                    entity_id=dpp_instance.entity_id,
                    entity_type=dpp_instance.entity_type,
                    field_path=field_path,
                    observed_value=counter,
                    expected={"max": brewing},
                    review_action="verify_usage_counters",
                )
            )

        if brewing is not None and grinding is not None and max(brewing, grinding) >= 50:
            deviation = abs(grinding - brewing) / max(brewing, 1.0)
            if deviation > 0.25:
                findings.append(
                    AnomalyFinding(
                        check_id="grinding_brewing_counter_deviation",
                        category="consistency",
                        severity="info",
                        message="Grinding and brewing counters deviate strongly.",
                        entity_id=dpp_instance.entity_id,
                        entity_type=dpp_instance.entity_type,
                        field_path="DPPInstance.coffeeGrindingCount",
                        observed_value=grinding,
                        expected={"close_to_brewingCount": brewing, "max_relative_deviation": 0.25},
                        confidence=0.8,
                        evidence={"relative_deviation": round(deviation, 3)},
                        review_action="inspect_counter_semantics",
                    )
                )

    return findings


def _profile_value_outside_range(value: float, profile_range_min: float, profile_range_max: float) -> bool:
    """Return True when a value falls outside a product-specific profile range."""
    return value < profile_range_min or value > profile_range_max


def _apply_product_profile_checks(result: HarmonizationResult) -> list[AnomalyFinding]:
    """Apply stricter product-specific ranges when a known product profile matches."""
    findings: list[AnomalyFinding] = []

    for entity in [item for item in result.entities.values() if item.entity_type == "DPPStatic"]:
        profile_match = resolve_product_profile(_field_value(entity, "DPPStatic.name"))
        if profile_match is None:
            continue

        findings.extend(_apply_single_product_profile(entity, profile_match))

    return findings


def _apply_single_product_profile(entity: HarmonizedEntity, profile_match: ProductProfileMatch) -> list[AnomalyFinding]:
    """Apply one product profile to one DPPStatic entity."""
    findings: list[AnomalyFinding] = []
    profile = profile_match.profile

    for profile_range in profile.ranges:
        value = _numeric_field_value(entity, profile_range.field_path)
        if value is None:
            continue

        if not _profile_value_outside_range(value, profile_range.min_value, profile_range.max_value):
            continue

        relative_deviation = abs(value - profile_range.reference_value) / profile_range.reference_value

        findings.append(
            AnomalyFinding(
                check_id="product_profile_range_mismatch",
                category="range",
                severity="warning",
                message=f"{profile_range.field_path} is outside the matched product profile range.",
                entity_id=entity.entity_id,
                entity_type=entity.entity_type,
                field_path=profile_range.field_path,
                observed_value=value,
                expected=profile_range.expected_range(),
                evidence={
                    "profile_id": profile.profile_id,
                    "profile_label": profile.label,
                    "profile_match_method": profile_match.method,
                    "profile_match_confidence": profile_match.confidence,
                    "profile_matched_term": profile_match.matched_term,
                    "profile_source": profile.source,
                    "profile_reference_type": profile.reference_type,
                    "profile_reference_level": profile.reference_level,
                    "relative_deviation": round(relative_deviation, 3),
                    "description": profile_range.description,
                },
                review_action="verify_product_model_or_specification_value",
            )
        )

    return findings


def _apply_emission_calculation_checks(result: HarmonizationResult) -> list[AnomalyFinding]:
    """Check whether reported emissions are plausible against activity and factor values."""
    findings: list[AnomalyFinding] = []

    for record in [entity for entity in result.entities.values() if entity.entity_type == "GHGEmissionRecord"]:
        activity_targets = _relation_targets(record, "activity")
        factor_targets = _relation_targets(record, "emission_factor")
        if not activity_targets or not factor_targets:
            continue

        activity = result.entities.get(activity_targets[0])
        factor = result.entities.get(factor_targets[0])
        if activity is None or factor is None:
            continue

        quantity = _numeric_field_value(activity, "ActivityData.quantity")
        factor_value = _numeric_field_value(factor, "EmissionFactor.value")
        reported = _numeric_field_value(record, "GHGEmissionRecord.emissions_kg_co2e")
        if quantity is None or factor_value is None or reported is None:
            continue

        expected = quantity * factor_value
        tolerance = max(abs(expected) * 0.05, 0.01)
        difference = abs(reported - expected)
        if difference <= tolerance:
            continue

        findings.append(
            AnomalyFinding(
                check_id="emission_record_calculation_mismatch",
                category="calculation",
                severity="warning",
                message="Reported GHG emissions differ from activity quantity multiplied by emission factor.",
                entity_id=record.entity_id,
                entity_type=record.entity_type,
                field_path="GHGEmissionRecord.emissions_kg_co2e",
                observed_value=reported,
                expected={"quantity_x_factor": round(expected, 6), "tolerance": round(tolerance, 6)},
                confidence=0.95,
                evidence={
                    "activity_entity_id": activity.entity_id,
                    "factor_entity_id": factor.entity_id,
                    "quantity": quantity,
                    "factor_value": factor_value,
                    "absolute_difference": round(difference, 6),
                },
                review_action="verify_calculation_or_factor_unit",
            )
        )

    return findings


def _apply_emission_scope_category_checks(result: HarmonizationResult) -> list[AnomalyFinding]:
    """Check categorical consistency between GHG scope and Scope 3 category."""
    findings: list[AnomalyFinding] = []

    for record in [entity for entity in result.entities.values() if entity.entity_type == "GHGEmissionRecord"]:
        scope_value = _field_value(record, "GHGEmissionRecord.scope")
        scope3_category = _field_value(record, "GHGEmissionRecord.scope3_category")

        if scope_value == "scope_3" and scope3_category is None:
            findings.append(
                AnomalyFinding(
                    check_id="scope3_category_missing",
                    category="consistency",
                    severity="warning",
                    message="GHGEmissionRecord.scope is Scope 3 but no Scope 3 category is present.",
                    entity_id=record.entity_id,
                    entity_type=record.entity_type,
                    field_path="GHGEmissionRecord.scope3_category",
                    observed_value=None,
                    expected="scope3_category for Scope 3 records",
                    confidence=0.9,
                    evidence={"scope": scope_value},
                    review_action="add_or_verify_scope3_category",
                )
            )
            continue

        if isinstance(scope_value, str) and scope_value != "scope_3" and scope3_category is not None:
            findings.append(
                AnomalyFinding(
                    check_id="scope3_category_without_scope3",
                    category="consistency",
                    severity="warning",
                    message="GHGEmissionRecord has a Scope 3 category although its scope is not Scope 3.",
                    entity_id=record.entity_id,
                    entity_type=record.entity_type,
                    field_path="GHGEmissionRecord.scope3_category",
                    observed_value=scope3_category,
                    expected={"scope": "scope_3"},
                    confidence=0.9,
                    evidence={"scope": scope_value},
                    review_action="verify_ghg_scope_or_remove_scope3_category",
                )
            )

    return findings


def _concept_applicability_lookup() -> dict[str, tuple[str, ...]]:
    """Return applicable service types keyed by service concept id."""
    lookup: dict[str, tuple[str, ...]] = {}
    for concepts in TEXT_CONCEPTS_BY_KIND.values():
        for concept in concepts:
            lookup[concept.concept_id] = concept.applicable_service_types
    return lookup


def _iter_text_report_entries(value: Any) -> list[dict[str, Any]]:
    """Flatten text_harmonization report entries from one field."""
    if isinstance(value, dict):
        if "status" in value and "original_value" in value:
            return [value]
        entries: list[dict[str, Any]] = []
        for item in value.values():
            entries.extend(_iter_text_report_entries(item))
        return entries

    if isinstance(value, list):
        entries = []
        for item in value:
            entries.extend(_iter_text_report_entries(item))
        return entries

    return []


def _apply_service_semantic_checks(result: HarmonizationResult) -> list[AnomalyFinding]:
    """Check unresolved service text and concept/service-type plausibility."""
    findings: list[AnomalyFinding] = []
    applicable_by_concept = _concept_applicability_lookup()

    for entity in result.entities.values():
        if not entity.text_harmonization:
            continue

        for field_name, report_value in entity.text_harmonization.items():
            for entry in _iter_text_report_entries(report_value):
                status = entry.get("status")
                concept_id = entry.get("normalized_value")
                original_value = entry.get("original_value")

                if status in {"ambiguous", "unresolved"}:
                    findings.append(
                        AnomalyFinding(
                            check_id="service_text_requires_review",
                            category="review",
                            severity="warning",
                            message=f"Service text in {field_name} could not be normalized unambiguously.",
                            entity_id=entity.entity_id,
                            entity_type=entity.entity_type,
                            field_path=f"{entity.entity_type}.{field_name}",
                            observed_value=original_value,
                            expected="expert-confirmed service concept",
                            confidence=0.7,
                            evidence={"text_status": status, "candidates": entry.get("candidates", [])},
                            review_action="confirm_or_correct_service_concept",
                        )
                    )
                    continue

                if not isinstance(concept_id, str):
                    continue

                applicable_types = applicable_by_concept.get(concept_id, ())
                if applicable_types and entity.entity_type not in applicable_types:
                    findings.append(
                        AnomalyFinding(
                            check_id="service_concept_type_mismatch",
                            category="semantic",
                            severity="info",
                            message=f"Service concept {concept_id!r} is unusual for {entity.entity_type}.",
                            entity_id=entity.entity_id,
                            entity_type=entity.entity_type,
                            field_path=f"{entity.entity_type}.{field_name}",
                            observed_value=concept_id,
                            expected={"applicable_service_types": applicable_types},
                            confidence=0.75,
                            evidence={"original_value": original_value},
                            review_action="verify_service_step_type_or_concept",
                        )
                    )

    return findings


def analyze_harmonization_result(result: HarmonizationResult) -> AnomalyResult:
    """
    Build plausibility/anomaly indicators from a harmonization result.

    The function assumes harmonization has already handled labels, units, enums,
    and service-text concept mapping. Findings therefore refer to canonical
    field paths and preserved relation paths.
    """
    if result.scope_name not in SUPPORTED_SCOPES:
        raise AnomalyServiceError(f"Unsupported scope: {result.scope_name!r}")

    findings: list[AnomalyFinding] = []
    findings.extend(_apply_required_relation_checks(result))

    if result.scope_name == "product":
        findings.extend(_apply_numeric_range_rules(result, PRODUCT_NUMERIC_RANGE_RULES))
        findings.extend(_apply_product_profile_checks(result))
        findings.extend(_apply_active_part_tree_weight_checks(result))
        findings.extend(_apply_product_consistency_checks(result))
        findings.extend(_apply_product_usage_ratio_checks(result))
    elif result.scope_name == "emission":
        findings.extend(_apply_numeric_range_rules(result, EMISSION_NUMERIC_RANGE_RULES))
        findings.extend(_apply_emission_calculation_checks(result))
        findings.extend(_apply_emission_scope_category_checks(result))
    elif result.scope_name == "service":
        findings.extend(_apply_numeric_range_rules(result, SERVICE_NUMERIC_RANGE_RULES))
        findings.extend(_apply_service_semantic_checks(result))

    return AnomalyResult(
        scope_name=result.scope_name,
        findings=findings,
    )


def finding_as_dict(finding: AnomalyFinding) -> dict[str, Any]:
    """Return a finding dictionary without empty optional values."""
    return {
        key: value
        for key, value in asdict(finding).items()
        if value is not None and value != {} and value != []
    }
