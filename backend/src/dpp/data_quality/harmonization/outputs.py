"""
Output builders for harmonization results.

The harmonization service keeps a detailed intermediate representation for
traceability. This module derives two user-facing outputs from it:

1. Clean JSON-LD data: only canonical entity fields and trusted references.
2. Harmonization report: mapping/normalization metadata, confidence values,
   unmapped fields, and issues.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from dpp.data_quality.harmonization.schemas import HarmonizationResult, HarmonizedEntity


def _context_from_document(document: dict[str, Any]) -> Any:
    """Return the input JSON-LD context, or a minimal fallback context."""
    return document.get("@context", {"dpp": "https://example.org/dpp#"})


def _field_name_from_path(canonical_path: str) -> str:
    """Return the field name from a canonical path such as 'ActivityData.quantity'."""
    return canonical_path.split(".", maxsplit=1)[1]


def _clean_value(field_dict: dict[str, Any]) -> Any:
    """Return the value that should appear in clean canonical data."""
    normalized_value = field_dict.get("normalized_value")
    if normalized_value is not None:
        return normalized_value

    return field_dict.get("original_value")


def _drop_none_values(value: Any) -> Any:
    """Recursively remove keys whose value is None from report dictionaries."""
    if isinstance(value, dict):
        return {
            key: _drop_none_values(item)
            for key, item in value.items()
            if item is not None
        }

    if isinstance(value, list):
        return [_drop_none_values(item) for item in value]

    return value


def _as_measurement_value(raw_value: Any, unit: str | None) -> dict[str, Any] | None:
    """Return a consistent value/unit object for report output."""
    if unit is None:
        return None

    if isinstance(raw_value, dict) and "value" in raw_value:
        value = raw_value.get("value")
    else:
        value = raw_value

    return {"value": value, "unit": unit}


def _format_measurement_field_for_report(field_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Represent measurement normalization symmetrically in reports.

    Internally, HarmonizedField stores units as separate trace metadata
    (original_unit / normalized_unit). In the user-facing report, value and unit
    belong together. Therefore a field such as productWeight is rendered as:

        original_value:   {value: 2.5, unit: kg}
        normalized_value: {value: 2500.0, unit: g}

    Fields without unit metadata, including explicit unit fields such as
    ActivityData.unit, are left untouched.
    """
    original_unit = field_dict.get("original_unit")
    normalized_unit = field_dict.get("normalized_unit")

    if original_unit is None and normalized_unit is None:
        return field_dict

    formatted = dict(field_dict)

    original_measurement = _as_measurement_value(
        raw_value=formatted.get("original_value"),
        unit=original_unit,
    )
    if original_measurement is not None:
        formatted["original_value"] = original_measurement

    if formatted.get("normalized_value") is not None and normalized_unit is not None:
        formatted["normalized_value"] = {
            "value": formatted["normalized_value"],
            "unit": normalized_unit,
        }

    formatted.pop("original_unit", None)
    formatted.pop("normalized_unit", None)
    return formatted


def _add_preserved_references(node: dict[str, Any], entity: HarmonizedEntity) -> None:
    """
    Add trusted graph references as normal JSON-LD properties.

    Relations are not emitted as a separate top-level 'relations' category in
    clean output. They become ordinary reference fields on the source entity.
    """
    grouped_references: dict[str, list[dict[str, str]]] = {}

    for relation in entity.relations:
        grouped_references.setdefault(relation.relation_name, []).append(
            {"@id": relation.target_entity_id}
        )

    for relation_name, references in grouped_references.items():
        if len(references) == 1:
            node[relation_name] = references[0]
        else:
            node[relation_name] = references


def build_clean_jsonld(result: HarmonizationResult, document: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Build clean canonical JSON-LD from a harmonization result.

    The output intentionally excludes original labels, original values,
    confidence scores, status flags, warnings, and issues. It is meant to be the
    normalized data payload for downstream processing.
    """
    graph: list[dict[str, Any]] = []

    for entity in result.entities.values():
        node: dict[str, Any] = {
            "@id": entity.entity_id,
            "@type": entity.entity_type,
        }

        for canonical_path, harmonized_field in entity.fields.items():
            if harmonized_field.status == "error":
                continue

            field_name = _field_name_from_path(canonical_path)
            node[field_name] = _clean_value(asdict(harmonized_field))

        _add_preserved_references(node, entity)
        graph.append(node)

    return {
        "@context": _context_from_document(document or {}),
        "@graph": graph,
    }


def build_harmonization_report(result: HarmonizationResult) -> dict[str, Any]:
    """
    Build a traceability report from a harmonization result.

    Trusted structural references are intentionally omitted from the report,
    because they are not harmonized by this layer. They appear as normal JSON-LD
    reference properties in the clean data output.
    """
    report_entities: dict[str, Any] = {}

    for entity_id, entity in result.entities.items():
        entity_dict = asdict(entity)
        entity_dict.pop("relations", None)

        entity_dict["fields"] = {
            canonical_path: _format_measurement_field_for_report(field_dict)
            for canonical_path, field_dict in entity_dict.get("fields", {}).items()
        }

        report_entities[entity_id] = _drop_none_values(entity_dict)

    return {
        "scope_name": result.scope_name,
        "entities": report_entities,
        "issues": [_drop_none_values(asdict(issue)) for issue in result.issues],
    }


def build_full_output(result: HarmonizationResult, document: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the combined data/report wrapper used by the CLI default output."""
    return {
        "data": build_clean_jsonld(result, document=document),
        "report": build_harmonization_report(result),
        "has_errors": result.has_errors(),
    }
