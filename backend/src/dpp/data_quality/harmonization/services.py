"""
High-level harmonization service.

This module combines the parser, rule-based field mapper, unit/value
normalizers, and harmonization result schemas into one small workflow.
"""

from __future__ import annotations

from typing import Any

from dpp.data_quality.harmonization.mapper import map_field_label
from dpp.data_quality.harmonization.normalizers import (
    NormalizationError,
    normalize_unit_label,
    normalize_value_to_unit,
    normalize_without_unit,
)
from dpp.data_quality.harmonization.parser import ParsedEntity, parse_jsonld_document
from dpp.data_quality.harmonization.schemas import (
    HarmonizationIssue,
    HarmonizationResult,
    HarmonizedEntity,
    HarmonizedField,
    PreservedRelation,
    RawField,
)
from dpp.data_quality.scopes import SUPPORTED_SCOPES
from dpp.data_quality.scopes.schemas import CanonicalField, ScopeDefinition


class HarmonizationServiceError(ValueError):
    """Raised when the harmonization service cannot run safely."""


def _fields_by_path(scope: ScopeDefinition) -> dict[str, CanonicalField]:
    """Return scope fields keyed by canonical path."""
    return {field.path: field for field in scope.fields}


def _relation_names_for_entity(scope: ScopeDefinition, entity_type: str) -> set[str]:
    """Return preserved relation names for a given source entity type."""
    return {
        relation.relation_name
        for relation in scope.relations
        if relation.source_entity_type == entity_type
    }


def _target_type_for_relation(scope: ScopeDefinition, entity_type: str, relation_name: str) -> str | None:
    """Return the configured target entity type for a preserved relation."""
    for relation in scope.relations:
        if relation.source_entity_type == entity_type and relation.relation_name == relation_name:
            return relation.target_entity_type

    return None


def _build_preserved_relations(parsed_entity: ParsedEntity, scope: ScopeDefinition) -> list[PreservedRelation]:
    """
    Preserve trusted structural relations that are registered for the selected scope.

    Relation labels are not harmonized. Only relations whose names are already
    part of the selected scope are carried forward.
    """

    allowed_relation_names = _relation_names_for_entity(scope, parsed_entity.entity_type)
    preserved: list[PreservedRelation] = []

    for relation in parsed_entity.relations:
        if relation.label not in allowed_relation_names:
            continue

        preserved.append(
            PreservedRelation(
                source_entity_id=parsed_entity.entity_id,
                relation_name=relation.label,
                target_entity_id=relation.target_id,
                target_entity_type=_target_type_for_relation(
                    scope=scope,
                    entity_type=parsed_entity.entity_type,
                    relation_name=relation.label,
                ),
            )
        )

    return preserved


def _extract_value_and_unit(raw_value: Any) -> tuple[Any, str | None]:
    """
    Extract a value and optional nested unit metadata from an input value.

    Supported nested format:
        {"value": 85000, "unit": "m"}
    """

    if isinstance(raw_value, dict):
        return raw_value.get("value"), raw_value.get("unit")

    return raw_value, None


def _target_unit_for_activity_quantity(source_unit: str | None) -> str | None:
    """
    Infer the canonical target unit for ActivityData.quantity from its source unit.

    ActivityData.quantity is context-dependent in the original model, so it does
    not have one globally fixed target unit. The unit enum determines the target.
    """

    normalized_source = normalize_unit_label(source_unit)

    if normalized_source in {"m", "km"}:
        return "km"

    if normalized_source in {"kg", "kWh", "ltr", "m3", "t", "count"}:
        return normalized_source

    return None


def _normalize_unit_field(value: Any) -> str:
    """Normalize an explicit unit field value."""
    scalar_value, _ = _extract_value_and_unit(value)
    if not isinstance(scalar_value, str):
        raise NormalizationError(f"Unit field must contain a string value, got {type(scalar_value).__name__}")

    normalized = normalize_unit_label(scalar_value)
    if normalized is None:
        raise NormalizationError("Unit field cannot be None.")

    return normalized


def _collect_explicit_units(parsed_entity: ParsedEntity, scope_name: str) -> dict[str, str]:
    """
    Collect explicit unit fields from an entity before value normalization.

    This makes quantity/value normalization independent from field order.
    """

    explicit_units: dict[str, str] = {}

    for parsed_field in parsed_entity.fields:
        mapping = map_field_label(parsed_field.label, scope_name, entity_type=parsed_entity.entity_type)
        if mapping is None:
            continue

        if mapping.canonical_path not in {"ActivityData.unit", "EmissionFactor.unit"}:
            continue

        try:
            explicit_units[mapping.canonical_path] = _normalize_unit_field(parsed_field.value)
        except NormalizationError:
            continue

    return explicit_units


def _normalize_mapped_value(
    value: Any,
    source_unit: str | None,
    canonical_field: CanonicalField,
) -> tuple[Any, str | None]:
    """
    Normalize a mapped value according to the canonical field.

    Product-scope fields usually have fixed target units. Emission-scope quantity
    and factor values are context-dependent and use their source/explicit unit.
    """

    if canonical_field.role == "unit_harmonization":
        normalized_unit = _normalize_unit_field(value)
        return normalized_unit, None

    if canonical_field.path == "ActivityData.quantity":
        target_unit = _target_unit_for_activity_quantity(source_unit)
        if target_unit is None:
            return normalize_without_unit(value), None

        normalized = normalize_value_to_unit(
            value=value,
            source_unit=source_unit,
            target_unit=target_unit,
        )
        return normalized.value, normalized.unit

    if canonical_field.path == "EmissionFactor.value":
        normalized_unit = normalize_unit_label(source_unit)
        return normalize_without_unit(value), normalized_unit

    if canonical_field.target_unit:
        normalized = normalize_value_to_unit(
            value=value,
            source_unit=source_unit,
            target_unit=canonical_field.target_unit,
        )
        return normalized.value, normalized.unit

    return normalize_without_unit(value), None


def _align_explicit_unit_fields(fields: dict[str, HarmonizedField]) -> None:
    """
    Align explicit unit fields with the final unit used by their numeric value.

    Example:
        ActivityData.quantity: 85000 m -> 85 km
        ActivityData.unit should therefore become "km", not "m".
    """

    unit_pairs = (
        ("ActivityData.quantity", "ActivityData.unit"),
        ("EmissionFactor.value", "EmissionFactor.unit"),
    )

    for value_path, unit_path in unit_pairs:
        value_field = fields.get(value_path)
        unit_field = fields.get(unit_path)

        if value_field is None or unit_field is None:
            continue

        if value_field.normalized_unit is None:
            continue

        fields[unit_path] = HarmonizedField(
            canonical_path=unit_field.canonical_path,
            original_label=unit_field.original_label,
            original_value=unit_field.original_value,
            normalized_value=value_field.normalized_unit,
            original_unit=unit_field.original_unit,
            normalized_unit=unit_field.normalized_unit,
            status=unit_field.status,
            confidence=unit_field.confidence,
        )


def harmonize_document(document: dict[str, Any], scope_name: str) -> HarmonizationResult:
    """
    Harmonize a JSON-LD-like input document for a selected scope.

    Entity types and structural relations are assumed to be reliable. Field label
    mapping is accepted only when the mapped canonical entity type matches the
    actual parsed entity type. Otherwise, the field is treated as unmapped and a
    warning is recorded.
    """

    scope = SUPPORTED_SCOPES.get(scope_name)
    if scope is None:
        raise HarmonizationServiceError(f"Unsupported scope: {scope_name!r}")

    parsed_document = parse_jsonld_document(document)
    canonical_fields = _fields_by_path(scope)

    harmonized_entities: dict[str, HarmonizedEntity] = {}
    global_issues: list[HarmonizationIssue] = []

    for parsed_entity in parsed_document.entities:
        fields: dict[str, HarmonizedField] = {}
        unmapped_fields: list[RawField] = []
        issues: list[HarmonizationIssue] = []
        preserved_relations = _build_preserved_relations(parsed_entity, scope)
        explicit_units = _collect_explicit_units(parsed_entity, scope_name)

        if parsed_entity.entity_type not in scope.entities:
            issues.append(
                HarmonizationIssue(
                    severity="warning",
                    message=f"Entity type {parsed_entity.entity_type!r} is not part of scope {scope_name!r}.",
                    entity_id=parsed_entity.entity_id,
                    entity_type=parsed_entity.entity_type,
                )
            )

        for parsed_field in parsed_entity.fields:
            mapping = map_field_label(parsed_field.label, scope_name, entity_type=parsed_entity.entity_type)

            if mapping is None:
                unmapped_fields.append(
                    RawField(
                        label=parsed_field.label,
                        value=parsed_field.value,
                    )
                )
                continue

            if mapping.entity_type != parsed_entity.entity_type:
                unmapped_fields.append(
                    RawField(
                        label=parsed_field.label,
                        value=parsed_field.value,
                    )
                )
                issues.append(
                    HarmonizationIssue(
                        severity="warning",
                        message=(
                            f"Field label {parsed_field.label!r} maps to {mapping.canonical_path!r}, "
                            f"but it appeared on entity type {parsed_entity.entity_type!r}."
                        ),
                        entity_id=parsed_entity.entity_id,
                        entity_type=parsed_entity.entity_type,
                        field_label=parsed_field.label,
                    )
                )
                continue

            canonical_field = canonical_fields[mapping.canonical_path]
            original_value = parsed_field.value
            value_for_normalization, original_unit = _extract_value_and_unit(parsed_field.value)

            if original_unit is None:
                if mapping.canonical_path == "ActivityData.quantity":
                    original_unit = explicit_units.get("ActivityData.unit")
                elif mapping.canonical_path == "EmissionFactor.value":
                    original_unit = explicit_units.get("EmissionFactor.unit")

            try:
                normalized_value, normalized_unit = _normalize_mapped_value(
                    value=value_for_normalization,
                    source_unit=original_unit,
                    canonical_field=canonical_field,
                )
                status = "normalized" if normalized_unit is not None or canonical_field.role == "unit_harmonization" else "mapped"
            except NormalizationError as exc:
                normalized_value = None
                normalized_unit = None
                status = "error"
                issues.append(
                    HarmonizationIssue(
                        severity="error",
                        message=str(exc),
                        entity_id=parsed_entity.entity_id,
                        entity_type=parsed_entity.entity_type,
                        field_label=parsed_field.label,
                    )
                )

            fields[mapping.canonical_path] = HarmonizedField(
                canonical_path=mapping.canonical_path,
                original_label=parsed_field.label,
                original_value=original_value,
                normalized_value=normalized_value,
                original_unit=original_unit,
                normalized_unit=normalized_unit,
                status=status,
                confidence=mapping.confidence,
            )

        _align_explicit_unit_fields(fields)

        harmonized_entities[parsed_entity.entity_id] = HarmonizedEntity(
            entity_id=parsed_entity.entity_id,
            entity_type=parsed_entity.entity_type,
            fields=fields,
            relations=preserved_relations,
            unmapped_fields=unmapped_fields,
            issues=issues,
        )

    return HarmonizationResult(
        scope_name=scope_name,
        entities=harmonized_entities,
        issues=global_issues,
    )
