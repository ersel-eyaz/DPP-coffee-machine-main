"""
High-level harmonization service.

This module combines the parser, rule-based field mapper, unit/value
normalizers, and harmonization result schemas into one small workflow.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from dpp.data_quality.harmonization.free_text import (
    clean_text_normalization_value,
    normalize_text_values,
)
from dpp.data_quality.harmonization.mapper import (
    AUTO_FUZZY_THRESHOLD,
    find_field_label_candidates,
    map_field_label,
)
from dpp.data_quality.harmonization.normalizers import (
    NormalizationError,
    find_unit_label_candidates,
    normalize_enum_value,
    normalize_unit_label,
    normalize_value_to_unit,
    normalize_without_unit,
    resolve_enum_value,
    resolve_unit_label,
)
from dpp.data_quality.harmonization.parser import ParsedEntity, ParsedRelation, parse_jsonld_document
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


_RELATION_INPUT_ALIASES: dict[tuple[str, str], str] = {
    ("DPPInstance", "isVariantOf"): "dppStaticLink",
    ("DPPInstance", "hasPart"): "partInstanceLink",
    ("PartInstance", "isVariantOf"): "partStaticLink",
    ("MaterialInstance", "isVariantOf"): "materialStaticLink",
    ("GHGEmissionRecord", "emissionFactor"): "emission_factor",
}


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


def _canonical_relation_name(entity_type: str, relation_label: str) -> str:
    """Translate a JSON-LD structural term to its model-side property name."""
    return _RELATION_INPUT_ALIASES.get(
        (entity_type, relation_label),
        relation_label,
    )


def _relation_definition(scope: ScopeDefinition, entity_type: str, relation_name: str) -> Any | None:
    """Return the selected-scope structural definition for one property."""
    for relation in scope.relations:
        if relation.source_entity_type == entity_type and relation.relation_name == relation_name:
            return relation
    return None


def _build_preserved_relations(
    parsed_entity: ParsedEntity,
    scope: ScopeDefinition,
    additional_relations: list[ParsedRelation] | None = None,
) -> list[PreservedRelation]:
    """
    Preserve trusted reference relations registered for the selected scope.

    Embedded structural properties are attached to their parent separately and
    therefore are not represented here as id-based references.
    """

    allowed_relation_names = _relation_names_for_entity(scope, parsed_entity.entity_type)
    preserved: list[PreservedRelation] = []

    for relation in [*parsed_entity.relations, *(additional_relations or [])]:
        canonical_relation_name = _canonical_relation_name(parsed_entity.entity_type, relation.label)
        relation_definition = _relation_definition(scope, parsed_entity.entity_type, canonical_relation_name)
        if canonical_relation_name not in allowed_relation_names or relation_definition is None:
            continue
        if relation_definition.representation != "link":
            continue

        preserved.append(
            PreservedRelation(
                source_entity_id=parsed_entity.entity_id,
                relation_name=canonical_relation_name,
                target_entity_id=relation.target_id,
                target_entity_type=_target_type_for_relation(
                    scope=scope,
                    entity_type=parsed_entity.entity_type,
                    relation_name=canonical_relation_name,
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
    """Normalize an explicit unit field value with exact or conservative fuzzy matching."""
    scalar_value, _ = _extract_value_and_unit(value)
    if not isinstance(scalar_value, str):
        raise NormalizationError(f"Unit field must contain a string value, got {type(scalar_value).__name__}")

    candidate = resolve_unit_label(scalar_value)
    if candidate is None:
        candidates = find_unit_label_candidates(scalar_value)
        if candidates:
            candidate_text = ", ".join(
                f"{candidate.canonical_unit} ({candidate.confidence:.2f})"
                for candidate in candidates[:3]
            )
            raise NormalizationError(
                f"Unit label {scalar_value!r} is ambiguous. Possible candidates: {candidate_text}."
            )

        raise NormalizationError(f"Unsupported unit label: {scalar_value!r}")

    return candidate.canonical_unit

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



def _get_unit_candidate_for_trace(
    original_value: Any,
    original_unit: str | None,
    canonical_field: CanonicalField,
) -> tuple[str | None, Any | None]:
    """Return the unit label and candidate used for unit traceability."""

    if canonical_field.role == "unit_harmonization":
        scalar_value, _ = _extract_value_and_unit(original_value)
        unit_label = scalar_value if isinstance(scalar_value, str) else None
    else:
        unit_label = original_unit

    if unit_label is None:
        return None, None

    return unit_label, resolve_unit_label(unit_label)


def _normalize_controlled_vocabulary_field(canonical_path: str, value: Any) -> str:
    """Normalize a controlled-vocabulary field by canonical match, alias, or conservative fuzzy fallback."""
    scalar_value, _ = _extract_value_and_unit(value)
    return normalize_enum_value(canonical_path, scalar_value)


def _free_text_kind_for_path(canonical_path: str) -> str:
    """Return the concept registry kind for a free-text source field."""
    if canonical_path.endswith(".observedSymptoms"):
        return "symptom"

    if canonical_path.endswith(".diagnose"):
        return "diagnosis"

    raise NormalizationError(f"Unsupported free-text harmonization field: {canonical_path!r}")


def _free_text_summary(results: list[Any]) -> tuple[float | None, str | None, str]:
    """Return value confidence, method, and field status for normalized free-text results."""
    normalized = [result for result in results if result.status == "normalized" and result.confidence is not None]
    if normalized:
        confidence = sum(float(result.confidence) for result in normalized) / len(normalized)
        methods = sorted({str(result.method) for result in normalized if result.method is not None})
        method = methods[0] if len(methods) == 1 else "mixed"
        return confidence, method, "normalized"

    if any(result.status == "error" for result in results):
        return None, None, "error"

    if any(result.status == "ambiguous" for result in results):
        return None, None, "ambiguous"

    return None, None, "unmapped"


def _free_text_issues(
    *,
    results: list[Any],
    entity_id: str,
    entity_type: str,
    field_label: str,
) -> list[HarmonizationIssue]:
    """Build traceability issues for free-text concept normalization."""
    issues: list[HarmonizationIssue] = []

    for result in results:
        if result.status == "normalized":
            if result.method in {"alias", "fuzzy", "semantic", "mixed"}:
                issues.append(
                    HarmonizationIssue(
                        severity="info",
                        message=(
                            f"Free-text value {result.original_text!r} was resolved by "
                            f"{result.method} match to {result.normalized_concept!r} "
                            f"with confidence {result.confidence:.2f}."
                        ),
                        entity_id=entity_id,
                        entity_type=entity_type,
                        field_label=field_label,
                    )
                )
            continue

        if result.status == "ambiguous":
            candidate_text = ", ".join(
                f"{candidate.concept_id} ({candidate.confidence:.2f}, {candidate.match_type})"
                for candidate in result.candidates[:3]
            )
            issues.append(
                HarmonizationIssue(
                    severity="warning",
                    message=(
                        f"Free-text value {result.original_text!r} is ambiguous. "
                        f"Possible concepts: {candidate_text}."
                    ),
                    entity_id=entity_id,
                    entity_type=entity_type,
                    field_label=field_label,
                )
            )
            continue

        if result.status == "unresolved":
            issues.append(
                HarmonizationIssue(
                    severity="warning",
                    message=f"Free-text value {result.original_text!r} could not be mapped to a seeded concept.",
                    entity_id=entity_id,
                    entity_type=entity_type,
                    field_label=field_label,
                )
            )
            continue

        if result.status == "error":
            issues.append(
                HarmonizationIssue(
                    severity="error",
                    message=f"Free-text value {result.original_text!r} is not a valid string value.",
                    entity_id=entity_id,
                    entity_type=entity_type,
                    field_label=field_label,
                )
            )

    return issues



def _free_text_report_entry(result: Any) -> dict[str, Any]:
    """Return a compact report entry for one free-text value."""
    entry: dict[str, Any] = {
        "original_value": result.original_text,
        "status": result.status,
    }

    if result.normalized_concept is not None:
        entry["normalized_value"] = result.normalized_concept

    if result.confidence is not None:
        entry["confidence"] = result.confidence

    if result.method is not None:
        entry["method"] = result.method

    if result.candidates:
        entry["candidates"] = [
            {
                "concept_id": candidate.concept_id,
                "confidence": candidate.confidence,
                "method": candidate.match_type,
            }
            for candidate in result.candidates[:3]
        ]

    return entry


def _free_text_report_value(field_name: str, original_value: Any, results: list[Any]) -> Any:
    """Return compact free-text harmonization details for an entity report."""
    if isinstance(original_value, list):
        return [_free_text_report_entry(result) for result in results]

    if len(results) == 1:
        return _free_text_report_entry(results[0])

    return [_free_text_report_entry(result) for result in results]

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

    if canonical_field.role == "controlled_vocabulary":
        return _normalize_controlled_vocabulary_field(canonical_field.path, value), None

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

        fields[unit_path] = replace(
            unit_field,
            normalized_value=value_field.normalized_unit,
            value_confidence=value_field.value_confidence,
            value_method=value_field.value_method,
        )



def _suppress_explicit_unit_metadata(
    fields: dict[str, HarmonizedField],
    canonical_fields: dict[str, CanonicalField],
) -> None:
    """
    Remove unit trace metadata from numeric fields whose unit is a separate field.

    Example:
        ActivityData.quantity uses ActivityData.unit as an explicit model field.
        The quantity report should show only the numeric value normalization,
        while ActivityData.unit carries the unit harmonization trace.

    Product/material fields such as MaterialInstance.weightGRM do not define a
    paired unit field, so their conversion metadata remains visible in the report.
    """

    for canonical_path, canonical_field in canonical_fields.items():
        if canonical_field.paired_unit_field is None:
            continue

        field = fields.get(canonical_path)
        if field is None:
            continue

        fields[canonical_path] = replace(
            field,
            original_unit=None,
            normalized_unit=None,
        )


def _resolve_field_mapping(label: str, scope_name: str, entity_type: str) -> tuple[Any, list[HarmonizationIssue]]:
    """Resolve a field label with exact mapping first and conservative fuzzy fallback second."""

    mapping = map_field_label(label, scope_name, entity_type=entity_type)
    if mapping is not None:
        return mapping, []

    candidates = find_field_label_candidates(
        label=label,
        scope_name=scope_name,
        entity_type=entity_type,
    )

    if candidates:
        top_candidate = candidates[0]
        second_score = candidates[1].confidence if len(candidates) > 1 else 0.0
        confidence_gap = top_candidate.confidence - second_score

        if top_candidate.confidence >= AUTO_FUZZY_THRESHOLD and confidence_gap >= 0.05:
            return top_candidate, [
                HarmonizationIssue(
                    severity="info",
                    message=(
                        f"Field label {label!r} was mapped by fuzzy fallback to "
                        f"{top_candidate.canonical_path!r} with confidence {top_candidate.confidence:.2f}."
                    ),
                    entity_type=entity_type,
                    field_label=label,
                )
            ]

        candidate_text = ", ".join(
            f"{candidate.canonical_path} ({candidate.confidence:.2f})"
            for candidate in candidates[:3]
        )
        return None, [
            HarmonizationIssue(
                severity="warning",
                message=(
                    f"Field label {label!r} could not be mapped exactly. "
                    f"Possible candidates: {candidate_text}."
                ),
                entity_type=entity_type,
                field_label=label,
            )
        ]

    return None, []


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
    parsed_entities: dict[str, ParsedEntity] = {}
    root_entity_ids: list[str] = []
    embedded_children: dict[tuple[str, str], list[str]] = {}
    inline_link_relations: dict[str, list[ParsedRelation]] = {}

    def collect_parsed_entity(parsed_entity: ParsedEntity, *, as_root: bool) -> None:
        """Collect a parsed tree while retaining embedded ownership information."""
        parsed_entities[parsed_entity.entity_id] = parsed_entity
        if as_root and parsed_entity.entity_id not in root_entity_ids:
            root_entity_ids.append(parsed_entity.entity_id)

        for embedded in parsed_entity.embedded_entities:
            relation_name = _canonical_relation_name(parsed_entity.entity_type, embedded.label)
            definition = _relation_definition(scope, parsed_entity.entity_type, relation_name)
            if definition is None:
                collect_parsed_entity(embedded.entity, as_root=True)
                continue

            if definition.representation == "embedded":
                embedded_children.setdefault((parsed_entity.entity_id, relation_name), []).append(
                    embedded.entity.entity_id
                )
                collect_parsed_entity(embedded.entity, as_root=False)
                continue

            inline_link_relations.setdefault(parsed_entity.entity_id, []).append(
                ParsedRelation(label=relation_name, target_id=embedded.entity.entity_id)
            )
            collect_parsed_entity(embedded.entity, as_root=True)

    for parsed_entity in parsed_document.entities:
        collect_parsed_entity(parsed_entity, as_root=True)

    for parsed_entity in parsed_entities.values():
        fields: dict[str, HarmonizedField] = {}
        unmapped_fields: list[RawField] = []
        text_harmonization: dict[str, Any] = {}
        issues: list[HarmonizationIssue] = []
        preserved_relations = _build_preserved_relations(
            parsed_entity,
            scope,
            additional_relations=inline_link_relations.get(parsed_entity.entity_id),
        )
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
            mapping, mapping_issues = _resolve_field_mapping(
                label=parsed_field.label,
                scope_name=scope_name,
                entity_type=parsed_entity.entity_type,
            )

            for mapping_issue in mapping_issues:
                issues.append(
                    HarmonizationIssue(
                        severity=mapping_issue.severity,
                        message=mapping_issue.message,
                        entity_id=parsed_entity.entity_id,
                        entity_type=mapping_issue.entity_type,
                        field_label=mapping_issue.field_label,
                    )
                )

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

            field_method = "fuzzy" if mapping.confidence < 1.0 else "exact_or_alias"

            canonical_field = canonical_fields[mapping.canonical_path]
            original_value = parsed_field.value
            value_for_normalization, original_unit = _extract_value_and_unit(parsed_field.value)

            if original_unit is None:
                if mapping.canonical_path == "ActivityData.quantity":
                    original_unit = explicit_units.get("ActivityData.unit")
                elif mapping.canonical_path == "EmissionFactor.value":
                    original_unit = explicit_units.get("EmissionFactor.unit")

            value_confidence: float | None = None
            value_method: str | None = None

            if canonical_field.role == "free_text_harmonization":
                text_kind = _free_text_kind_for_path(canonical_field.path)
                text_results = normalize_text_values(text_kind, value_for_normalization)
                as_list = isinstance(value_for_normalization, list)
                normalized_value = clean_text_normalization_value(text_results, as_list=as_list)
                value_confidence, value_method, text_status = _free_text_summary(text_results)

                # Clean data should contain the harmonized value directly in the
                # original canonical field. If a free-text value cannot be mapped
                # safely, clean_text_normalization_value preserves the original
                # text instead of returning null. The detailed unresolved/ambiguous
                # state remains visible in text_harmonization and issues.
                field_status = "normalized" if text_status == "normalized" else "mapped"

                fields[mapping.canonical_path] = HarmonizedField(
                    canonical_path=mapping.canonical_path,
                    original_label=parsed_field.label,
                    original_value=original_value,
                    normalized_value=normalized_value,
                    status=field_status,
                    confidence=mapping.confidence,
                    field_confidence=mapping.confidence,
                    value_confidence=value_confidence,
                    field_method=field_method,
                    value_method=value_method,
                )

                report_field_name = mapping.canonical_path.rsplit(".", maxsplit=1)[1]
                text_harmonization[report_field_name] = _free_text_report_value(
                    field_name=report_field_name,
                    original_value=value_for_normalization,
                    results=text_results,
                )

                issues.extend(
                    _free_text_issues(
                        results=text_results,
                        entity_id=parsed_entity.entity_id,
                        entity_type=parsed_entity.entity_type,
                        field_label=parsed_field.label,
                    )
                )
                continue

            if canonical_field.role == "analysis_context":
                # Context fields such as SecondaryValueStep.costEur are not value-harmonized.
                # They are typed fields in the prototype model and are only preserved for
                # later reporting/analytics. The harmonization layer recognizes the field
                # label and passes the value through unchanged.
                fields[mapping.canonical_path] = HarmonizedField(
                    canonical_path=mapping.canonical_path,
                    original_label=parsed_field.label,
                    original_value=original_value,
                    normalized_value=original_value,
                    status="mapped",
                    confidence=mapping.confidence,
                    field_confidence=mapping.confidence,
                    field_method=field_method,
                )
                continue

            try:
                normalized_value, normalized_unit = _normalize_mapped_value(
                    value=value_for_normalization,
                    source_unit=original_unit,
                    canonical_field=canonical_field,
                )
                status = (
                    "normalized"
                    if normalized_unit is not None
                    or canonical_field.role in {"unit_harmonization", "controlled_vocabulary"}
                    else "mapped"
                )

                enum_candidate = None
                if canonical_field.role == "controlled_vocabulary":
                    scalar_value, _ = _extract_value_and_unit(original_value)
                    enum_candidate = resolve_enum_value(canonical_field.path, scalar_value)
                    if enum_candidate is not None:
                        value_confidence = enum_candidate.confidence
                        value_method = enum_candidate.match_type

                if enum_candidate is not None and enum_candidate.match_type == "alias":
                    issues.append(
                        HarmonizationIssue(
                            severity="info",
                            message=(
                                f"Controlled-vocabulary value {enum_candidate.original_value!r} was resolved "
                                f"by alias to {enum_candidate.canonical_value!r}."
                            ),
                            entity_id=parsed_entity.entity_id,
                            entity_type=parsed_entity.entity_type,
                            field_label=parsed_field.label,
                        )
                    )

                if enum_candidate is not None and enum_candidate.match_type == "fuzzy":
                    issues.append(
                        HarmonizationIssue(
                            severity="info",
                            message=(
                                f"Controlled-vocabulary value {enum_candidate.original_value!r} was resolved "
                                f"by fuzzy fallback to {enum_candidate.canonical_value!r} "
                                f"with confidence {enum_candidate.confidence:.2f}."
                            ),
                            entity_id=parsed_entity.entity_id,
                            entity_type=parsed_entity.entity_type,
                            field_label=parsed_field.label,
                        )
                    )

                if enum_candidate is not None and enum_candidate.match_type == "semantic":
                    issues.append(
                        HarmonizationIssue(
                            severity="info",
                            message=(
                                f"Controlled-vocabulary value {enum_candidate.original_value!r} was resolved "
                                f"by semantic embedding match to {enum_candidate.canonical_value!r} "
                                f"with confidence {enum_candidate.confidence:.2f}."
                            ),
                            entity_id=parsed_entity.entity_id,
                            entity_type=parsed_entity.entity_type,
                            field_label=parsed_field.label,
                        )
                    )

                unit_label, unit_candidate = _get_unit_candidate_for_trace(
                    original_value=original_value,
                    original_unit=original_unit,
                    canonical_field=canonical_field,
                )
                if canonical_field.role == "unit_harmonization" and unit_candidate is not None:
                    value_confidence = unit_candidate.confidence
                    value_method = unit_candidate.match_type
                elif normalized_unit is not None:
                    value_confidence = unit_candidate.confidence if unit_candidate is not None else 1.0
                    if normalized_value != value_for_normalization:
                        value_method = "unit_conversion"
                    elif original_unit != normalized_unit:
                        value_method = "unit_normalization"
                    else:
                        value_method = "unit_validation"

                if unit_candidate is not None and unit_candidate.match_type == "fuzzy":
                    issues.append(
                        HarmonizationIssue(
                            severity="info",
                            message=(
                                f"Unit label {unit_label!r} was resolved by fuzzy fallback to "
                                f"{unit_candidate.canonical_unit!r} with confidence {unit_candidate.confidence:.2f}."
                            ),
                            entity_id=parsed_entity.entity_id,
                            entity_type=parsed_entity.entity_type,
                            field_label=parsed_field.label,
                        )
                    )
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
                field_confidence=mapping.confidence,
                value_confidence=value_confidence,
                field_method=field_method,
                value_method=value_method,
            )

        _align_explicit_unit_fields(fields)
        _suppress_explicit_unit_metadata(fields, canonical_fields)

        harmonized_entities[parsed_entity.entity_id] = HarmonizedEntity(
            entity_id=parsed_entity.entity_id,
            entity_type=parsed_entity.entity_type,
            has_explicit_id=parsed_entity.has_explicit_id,
            fields=fields,
            relations=preserved_relations,
            unmapped_fields=unmapped_fields,
            text_harmonization=text_harmonization,
            issues=issues,
        )

    def build_nested_entity(entity_id: str) -> HarmonizedEntity:
        entity = harmonized_entities[entity_id]
        nested: dict[str, list[HarmonizedEntity]] = {}
        for (parent_id, relation_name), child_ids in embedded_children.items():
            if parent_id == entity_id:
                nested[relation_name] = [build_nested_entity(child_id) for child_id in child_ids]
        return replace(entity, embedded_entities=nested)

    return HarmonizationResult(
        scope_name=scope_name,
        entities={entity_id: build_nested_entity(entity_id) for entity_id in root_entity_ids},
        issues=global_issues,
    )
