"""
Output builders for harmonization results.

The harmonization service keeps a detailed intermediate representation for
traceability. This module derives two user-facing outputs from it:

1. Clean JSON-LD data: canonical entity fields with legacy-shaped embedded
   children and preserved true references.
2. Harmonization report: mapping/normalization metadata, confidence values,
   unmapped fields, and issues.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from dpp.data_quality.harmonization.free_text import (
    AMBIGUOUS_TEXT_FUZZY_THRESHOLD,
    AMBIGUOUS_TEXT_SEMANTIC_THRESHOLD,
    AUTO_TEXT_FUZZY_THRESHOLD,
    AUTO_TEXT_SEMANTIC_THRESHOLD,
    MIN_TEXT_SEMANTIC_MARGIN,
)
from dpp.data_quality.harmonization.mapper import (
    AMBIGUOUS_FUZZY_THRESHOLD as AMBIGUOUS_FIELD_FUZZY_THRESHOLD,
    AUTO_FUZZY_THRESHOLD as AUTO_FIELD_FUZZY_THRESHOLD,
)
from dpp.data_quality.harmonization.normalizers import (
    AMBIGUOUS_ENUM_FUZZY_THRESHOLD,
    AMBIGUOUS_ENUM_SEMANTIC_THRESHOLD,
    AMBIGUOUS_UNIT_FUZZY_THRESHOLD,
    AUTO_ENUM_FUZZY_THRESHOLD,
    AUTO_ENUM_SEMANTIC_THRESHOLD,
    AUTO_UNIT_FUZZY_THRESHOLD,
    MIN_ENUM_SEMANTIC_MARGIN,
)
from dpp.data_quality.harmonization.result_access import effective_field_value
from dpp.data_quality.harmonization.schemas import HarmonizationResult, HarmonizedEntity
from dpp.data_quality.harmonization.unit_registry import unit_binding_for_field
from dpp.data_quality.scopes import SUPPORTED_SCOPES


DEFAULT_JSONLD_CONTEXT = {
    "schema": "https://schema.org/",
    "dpp": "https://example.org/dpp#",
    "name": "schema:name",
    "value": "schema:value",
    "unitCode": "schema:unitCode",
    "additionalProperty": "schema:additionalProperty",
    "isVariantOf": "schema:isVariantOf",
    "priceSpecification": "schema:priceSpecification",
}

_ENTITY_JSONLD_TYPES: dict[str, list[str]] = {
    "DPPStatic": ["dpp:DPPStatic", "schema:ProductModel"],
    "DPPInstance": ["dpp:DPPInstance", "schema:Product"],
    "PartStatic": ["dpp:PartStatic", "schema:ProductModel"],
    "PartInstance": ["dpp:PartInstance", "schema:Product"],
    "MaterialStatic": ["dpp:MaterialStatic", "schema:ProductModel"],
    "MaterialInstance": ["dpp:MaterialInstance", "schema:Product"],
    "ActivityData": ["dpp:ActivityData"],
    "EmissionFactor": ["dpp:EmissionFactor"],
    "GHGEmissionRecord": ["dpp:GHGEmissionRecord"],
    "SecondaryValueStep": ["dpp:SecondaryValueStep"],
    "RepairServiceStep": ["dpp:RepairServiceStep", "schema:RepairAction"],
    "ReplaceServiceStep": ["dpp:ReplaceServiceStep", "schema:UpdateAction"],
    "CleaningServiceStep": ["dpp:CleaningServiceStep", "schema:CleanAction"],
    "RefurbishmentServiceStep": ["dpp:RefurbishmentServiceStep", "schema:UpdateAction"],
    "RemanufacturingServiceStep": ["dpp:RemanufacturingServiceStep", "schema:UpdateAction"],
}

_FIELD_JSONLD_TERMS: dict[str, str] = {
    # Product fields with direct legacy JSON-LD counterparts.
    "DPPStatic.name": "schema:name",
    "DPPStatic.productClass": "schema:category",
    "DPPStatic.weightGRM": "schema:weight",
    "DPPStatic.heightCM": "schema:height",
    "DPPStatic.widthCM": "schema:width",
    "DPPStatic.depthCM": "schema:depth",
    "PartStatic.weightGRM": "schema:weight",
    "PartStatic.heightCM": "schema:height",
    "PartStatic.widthCM": "schema:width",
    "PartStatic.depthCM": "schema:depth",
    "MaterialInstance.weightGRM": "schema:weight",
    "MaterialInstance.percentRecycled": "additionalProperty[percentRecycled]",
    "DPPInstance.operatingHRS": "schema:additionalProperty[operatingHRS]",
    "DPPInstance.brewingCount": "schema:additionalProperty[brewingCount]",
    "DPPInstance.cleaningCount": "schema:additionalProperty[cleaningCount]",
    "DPPInstance.chalkCount": "schema:additionalProperty[chalkCount]",
    "DPPInstance.coffeeGrindingCount": "schema:additionalProperty[coffeeGrindingCount]",
    # Emission fields use the vocabulary terms already used by the legacy exporter.
    "ActivityData.activity_type": "dpp:activityType",
    "ActivityData.quantity": "dpp:quantity",
    "ActivityData.unit": "dpp:unit",
    "EmissionFactor.value": "dpp:value",
    "EmissionFactor.unit": "dpp:unit",
    "GHGEmissionRecord.scope": "dpp:scope",
    "GHGEmissionRecord.scope3_category": "dpp:scope3Category",
    "GHGEmissionRecord.emissions_kg_co2e": "dpp:emissionsKgCO2e",
    "GHGEmissionRecord.calculation_method": "dpp:calculationMethod",
    "GHGEmissionRecord.provenance": "dpp:provenance",
    # Service fields with direct legacy JSON-LD counterparts.
    "SecondaryValueStep.diagnose": "dpp:diagnose",
    "SecondaryValueStep.observedSymptoms": "dpp:observedSymptoms",
    "RepairServiceStep.diagnose": "dpp:diagnose",
    "RepairServiceStep.observedSymptoms": "dpp:observedSymptoms",
    "ReplaceServiceStep.diagnose": "dpp:diagnose",
    "ReplaceServiceStep.observedSymptoms": "dpp:observedSymptoms",
    "CleaningServiceStep.diagnose": "dpp:diagnose",
    "CleaningServiceStep.observedSymptoms": "dpp:observedSymptoms",
    "RefurbishmentServiceStep.diagnose": "dpp:diagnose",
    "RefurbishmentServiceStep.observedSymptoms": "dpp:observedSymptoms",
    "RemanufacturingServiceStep.diagnose": "dpp:diagnose",
    "RemanufacturingServiceStep.observedSymptoms": "dpp:observedSymptoms",
    "SecondaryValueStep.costEur": "priceSpecification[schema:price]",
    "RepairServiceStep.costEur": "priceSpecification[schema:price]",
    "RepairServiceStep.repairedPartId": "dpp:repairedPartId",
    "ReplaceServiceStep.costEur": "priceSpecification[schema:price]",
    "ReplaceServiceStep.replacedPartId": "dpp:replacedPartId",
    "CleaningServiceStep.costEur": "priceSpecification[schema:price]",
    "CleaningServiceStep.cleanedPartId": "dpp:cleanedPartId",
    "RefurbishmentServiceStep.costEur": "priceSpecification[schema:price]",
    "RefurbishmentServiceStep.repairedPartIds": "dpp:repairedPartIds",
    "RefurbishmentServiceStep.cleanedPartIds": "dpp:cleanedPartIds",
    "RemanufacturingServiceStep.costEur": "priceSpecification[schema:price]",
    "RemanufacturingServiceStep.repairedPartIds": "dpp:repairedPartIds",
    "RemanufacturingServiceStep.cleanedPartIds": "dpp:cleanedPartIds",
}

_RELATION_JSONLD_TERMS: dict[tuple[str, str], str] = {
    ("DPPInstance", "dppStaticLink"): "isVariantOf",
    ("DPPInstance", "partInstanceLink"): "schema:hasPart",
    ("PartInstance", "partStaticLink"): "isVariantOf",
    ("PartInstance", "compositeParts"): "dpp:compositeParts",
    ("PartInstance", "historyOfDetachedParts"): "dpp:historyOfDetachedParts",
    ("PartInstance", "compositeMaterials"): "dpp:compositeMaterials",
    ("MaterialInstance", "materialStaticLink"): "isVariantOf",
    ("GHGEmissionRecord", "activity"): "dpp:activity",
    ("GHGEmissionRecord", "emission_factor"): "dpp:emissionFactor",
    ("ReplaceServiceStep", "newPart"): "dpp:newPart",
    ("RefurbishmentServiceStep", "replacedAndNewParts"): "dpp:replacedAndNewParts",
    ("RemanufacturingServiceStep", "replacedAndNewParts"): "dpp:replacedAndNewParts",
}

_PROPERTY_VALUE_JSONLD_FIELDS: dict[str, tuple[str, str]] = {
    "MaterialInstance.percentRecycled": ("additionalProperty", "percentRecycled"),
    "DPPInstance.cleaningCount": ("schema:additionalProperty", "cleaningCount"),
    "DPPInstance.chalkCount": ("schema:additionalProperty", "chalkCount"),
    "DPPInstance.brewingCount": ("schema:additionalProperty", "brewingCount"),
    "DPPInstance.coffeeGrindingCount": ("schema:additionalProperty", "coffeeGrindingCount"),
}

_PRICE_SPECIFICATION_JSONLD_FIELDS = {
    "SecondaryValueStep.costEur",
    "RepairServiceStep.costEur",
    "ReplaceServiceStep.costEur",
    "CleaningServiceStep.costEur",
    "RefurbishmentServiceStep.costEur",
    "RemanufacturingServiceStep.costEur",
}


FIELD_LABEL_THRESHOLDS = {
    "automatic_fuzzy_threshold": AUTO_FIELD_FUZZY_THRESHOLD,
    "candidate_reporting_threshold": AMBIGUOUS_FIELD_FUZZY_THRESHOLD,
    "minimum_margin": 0.05,
}

UNIT_VALUE_THRESHOLDS = {
    "automatic_fuzzy_threshold": AUTO_UNIT_FUZZY_THRESHOLD,
    "candidate_reporting_threshold": AMBIGUOUS_UNIT_FUZZY_THRESHOLD,
    "minimum_margin": 0.05,
}

ENUM_VALUE_THRESHOLDS = {
    "automatic_fuzzy_threshold": AUTO_ENUM_FUZZY_THRESHOLD,
    "candidate_fuzzy_reporting_threshold": AMBIGUOUS_ENUM_FUZZY_THRESHOLD,
    "automatic_semantic_threshold": AUTO_ENUM_SEMANTIC_THRESHOLD,
    "candidate_semantic_reporting_threshold": AMBIGUOUS_ENUM_SEMANTIC_THRESHOLD,
    "minimum_fuzzy_margin": 0.05,
    "minimum_semantic_margin": MIN_ENUM_SEMANTIC_MARGIN,
}

TEXT_VALUE_THRESHOLDS = {
    "automatic_fuzzy_threshold": AUTO_TEXT_FUZZY_THRESHOLD,
    "candidate_fuzzy_reporting_threshold": AMBIGUOUS_TEXT_FUZZY_THRESHOLD,
    "automatic_semantic_threshold": AUTO_TEXT_SEMANTIC_THRESHOLD,
    "candidate_semantic_reporting_threshold": AMBIGUOUS_TEXT_SEMANTIC_THRESHOLD,
    "minimum_fuzzy_margin": 0.05,
    "minimum_semantic_margin": MIN_TEXT_SEMANTIC_MARGIN,
}


def _context_from_document(document: dict[str, Any]) -> Any:
    """Return an output context that preserves input terms and defines canonical prefixes."""
    context = document.get("@context")
    if isinstance(context, dict):
        return {**context, **DEFAULT_JSONLD_CONTEXT}

    if context is None:
        return dict(DEFAULT_JSONLD_CONTEXT)

    if isinstance(context, list):
        return [*context, DEFAULT_JSONLD_CONTEXT]

    return [context, DEFAULT_JSONLD_CONTEXT]


def _field_name_from_path(canonical_path: str) -> str:
    """Return the field name from a canonical path such as 'ActivityData.quantity'."""
    return canonical_path.split(".", maxsplit=1)[1]


def _jsonld_type(entity_type: str) -> str | list[str]:
    """Return semantic output type(s), retaining the data-quality entity identity."""
    mapped_types = _ENTITY_JSONLD_TYPES.get(entity_type)
    if mapped_types is None:
        return f"dpp:{entity_type}"

    return mapped_types[0] if len(mapped_types) == 1 else mapped_types


def _jsonld_field_term(canonical_path: str) -> str:
    """Return the external JSON-LD property for an internal canonical field."""
    return _FIELD_JSONLD_TERMS.get(canonical_path, f"dpp:{_field_name_from_path(canonical_path)}")


def _jsonld_field_value(canonical_path: str, harmonized_field: Any) -> Any:
    """Serialize measurement values like the legacy JSON-LD exporter where applicable."""
    value = effective_field_value(harmonized_field)
    unit_binding = unit_binding_for_field(canonical_path)
    if unit_binding is None or unit_binding.jsonld_quantity_name is None:
        return value

    return {
        "@type": "schema:QuantitativeValue",
        "name": unit_binding.jsonld_quantity_name,
        "value": value,
        "unitCode": unit_binding.target_unit,
    }


def _add_legacy_structured_field(
    node: dict[str, Any],
    canonical_path: str,
    harmonized_field: Any,
) -> bool:
    """Serialize legacy exporter containers instead of inventing direct DPP properties."""
    unit_binding = unit_binding_for_field(canonical_path)
    if unit_binding is not None and unit_binding.property_value_term is not None:
        entry: dict[str, Any] = {
            "@type": "schema:PropertyValue",
            "name": unit_binding.property_value_name or _field_name_from_path(canonical_path),
            "value": effective_field_value(harmonized_field),
            "unitCode": unit_binding.target_unit,
        }
        node.setdefault(unit_binding.property_value_term, []).append(entry)
        return True

    property_value = _PROPERTY_VALUE_JSONLD_FIELDS.get(canonical_path)
    if property_value is not None:
        output_term, name = property_value
        entry: dict[str, Any] = {
            "@type": "schema:PropertyValue",
            "name": name,
            "value": effective_field_value(harmonized_field),
        }
        node.setdefault(output_term, []).append(entry)
        return True

    if canonical_path in _PRICE_SPECIFICATION_JSONLD_FIELDS:
        node["priceSpecification"] = {
            "@type": "schema:PriceSpecification",
            "schema:price": float(effective_field_value(harmonized_field)),
            "schema:priceCurrency": "EUR",
        }
        return True

    return False


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


def _field_role(scope_name: str, canonical_path: str) -> str | None:
    """Return the configured scope role for one canonical field path."""
    scope = SUPPORTED_SCOPES.get(scope_name)
    if scope is None:
        return None

    for field in scope.fields:
        if field.path == canonical_path:
            return field.role

    return None


def _value_thresholds_for_field(scope_name: str, canonical_path: str) -> dict[str, Any] | None:
    """Return value-level decision thresholds relevant for one canonical field."""
    role = _field_role(scope_name, canonical_path)
    if role == "controlled_vocabulary":
        return dict(ENUM_VALUE_THRESHOLDS)

    if role == "unit_harmonization" or unit_binding_for_field(canonical_path) is not None:
        return dict(UNIT_VALUE_THRESHOLDS)

    if role == "free_text_harmonization":
        return dict(TEXT_VALUE_THRESHOLDS)

    return None


def _with_decision_thresholds(scope_name: str, canonical_path: str, field_dict: dict[str, Any]) -> dict[str, Any]:
    """Attach structured threshold metadata used by the harmonization decision."""
    enriched = dict(field_dict)

    enriched["field_thresholds"] = dict(FIELD_LABEL_THRESHOLDS)

    value_thresholds = _value_thresholds_for_field(scope_name, canonical_path)
    if value_thresholds is not None:
        enriched["value_thresholds"] = value_thresholds

    return enriched


def _with_text_thresholds(value: Any) -> Any:
    """Attach free-text decision thresholds to service text-harmonization entries."""
    if isinstance(value, dict):
        if "status" in value and "original_value" in value:
            return {**value, "thresholds": dict(TEXT_VALUE_THRESHOLDS)}

        return {key: _with_text_thresholds(item) for key, item in value.items()}

    if isinstance(value, list):
        return [_with_text_thresholds(item) for item in value]

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




def _is_normalized_free_text_path(canonical_path: str) -> bool:
    """Return True for companion fields generated by free-text harmonization."""
    return canonical_path.endswith(".normalizedDiagnose") or canonical_path.endswith(".normalizedObservedSymptoms")


def _is_free_text_source_path(canonical_path: str) -> bool:
    """Return True for original service-text source fields."""
    return canonical_path.endswith(".diagnose") or canonical_path.endswith(".observedSymptoms")


def _format_service_field_for_report(canonical_path: str, field_dict: dict[str, Any]) -> dict[str, Any]:
    """Return a compact report entry for service-scope fields.

    Service fields are already typed by the prototype model. For fields such as
    costEur, the harmonization layer only recognizes the canonical field and
    preserves the value. Therefore label-confidence metadata would be noisy here.
    Detailed concept matching remains available in the separate text_harmonization
    section for diagnose and observedSymptoms.
    """
    compact: dict[str, Any] = {
        "canonical_path": field_dict.get("canonical_path"),
        "original_value": field_dict.get("original_value"),
        "status": field_dict.get("status"),
    }

    original_label = field_dict.get("original_label")
    canonical_field_name = canonical_path.rsplit(".", maxsplit=1)[1]
    if original_label is not None and original_label != canonical_field_name:
        compact["input_label"] = original_label

    normalized_value = field_dict.get("normalized_value")
    original_value = field_dict.get("original_value")
    if (
        normalized_value is not None
        and normalized_value != original_value
        and not _is_free_text_source_path(canonical_path)
    ):
        compact["normalized_value"] = normalized_value

    return compact


def _with_jsonld_term(canonical_path: str, field_dict: dict[str, Any]) -> dict[str, Any]:
    """Expose the external clean-output term alongside the internal canonical path."""
    return {
        **field_dict,
        "jsonld_term": _jsonld_field_term(canonical_path),
    }


def _add_preserved_references(node: dict[str, Any], entity: HarmonizedEntity) -> None:
    """
    Add trusted graph references as normal JSON-LD properties.

    True references are not emitted as a separate top-level 'relations'
    category. They become ordinary JSON-LD reference fields on the source
    entity; embedded owned children are serialized separately below the parent.
    """
    grouped_references: dict[str, list[dict[str, str]]] = {}

    for relation in entity.relations:
        grouped_references.setdefault(relation.relation_name, []).append(
            {"@id": relation.target_entity_id}
        )

    for relation_name, references in grouped_references.items():
        output_term = _RELATION_JSONLD_TERMS.get(
            (entity.entity_type, relation_name),
            f"dpp:{relation_name}",
        )
        if len(references) == 1:
            node[output_term] = references[0]
        else:
            node[output_term] = references


def _build_clean_node(entity: HarmonizedEntity, *, embedded: bool = False) -> dict[str, Any]:
    """Serialize one harmonized entity, recursively including owned children."""
    node: dict[str, Any] = {"@type": _jsonld_type(entity.entity_type)}
    if not embedded or entity.has_explicit_id:
        node["@id"] = entity.entity_id

    for canonical_path, harmonized_field in entity.fields.items():
        if harmonized_field.status in {"error", "ambiguous", "unmapped"}:
            continue
        if _add_legacy_structured_field(node, canonical_path, harmonized_field):
            continue
        node[_jsonld_field_term(canonical_path)] = _jsonld_field_value(canonical_path, harmonized_field)

    _add_preserved_references(node, entity)
    for relation_name, children in entity.embedded_entities.items():
        output_term = _RELATION_JSONLD_TERMS.get(
            (entity.entity_type, relation_name),
            f"dpp:{relation_name}",
        )
        serialized = [_build_clean_node(child, embedded=True) for child in children]
        if relation_name in {"activity", "emission_factor", "newPart"} and len(serialized) == 1:
            node[output_term] = serialized[0]
        else:
            node[output_term] = serialized

    for relation_name, pairs in entity.paired_embedded_entities.items():
        output_term = _RELATION_JSONLD_TERMS.get(
            (entity.entity_type, relation_name),
            f"dpp:{relation_name}",
        )
        node[output_term] = [
            [existing_id, _build_clean_node(child, embedded=True)]
            for existing_id, child in pairs
        ]

    return node


def build_clean_jsonld(result: HarmonizationResult, document: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Build clean canonical JSON-LD from a harmonization result.

    The output intentionally excludes original labels, original values,
    confidence scores, status flags, warnings, and issues. It is meant to be the
    normalized data payload for downstream processing.
    """
    graph = [_build_clean_node(entity) for entity in result.entities.values()]

    return {
        "@context": _context_from_document(document or {}),
        "@graph": graph,
    }



def _iter_text_harmonization_entries(value: Any) -> list[dict[str, Any]]:
    """Return flat free-text harmonization entries from an entity report section."""
    entries: list[dict[str, Any]] = []

    if isinstance(value, dict):
        if "status" in value and "original_value" in value:
            entries.append(value)
        else:
            for item in value.values():
                entries.extend(_iter_text_harmonization_entries(item))
        return entries

    if isinstance(value, list):
        for item in value:
            entries.extend(_iter_text_harmonization_entries(item))

    return entries


def _build_report_summary(result: HarmonizationResult, report_entities: dict[str, Any]) -> dict[str, Any]:
    """Build compact counts for global and entity-level report content.

    The detailed issue lists stay in their original locations. This summary only
    makes it visible at report level that entity-level infos/warnings/errors exist,
    even when there are no global pipeline issues.
    """
    entity_issues = [
        issue
        for entity in result.iter_entities()
        for issue in entity.issues
    ]
    all_issues = [*result.issues, *entity_issues]

    field_status_counts: dict[str, int] = {}
    for entity in result.iter_entities():
        for field in entity.fields.values():
            field_status_counts[field.status] = field_status_counts.get(field.status, 0) + 1

    text_status_counts: dict[str, int] = {}
    for entity_dict in report_entities.values():
        for entry in _iter_text_harmonization_entries(entity_dict.get("text_harmonization", {})):
            status = entry.get("status")
            if isinstance(status, str):
                text_status_counts[status] = text_status_counts.get(status, 0) + 1

    severity_counts = {
        "info": sum(1 for issue in all_issues if issue.severity == "info"),
        "warning": sum(1 for issue in all_issues if issue.severity == "warning"),
        "error": sum(1 for issue in all_issues if issue.severity == "error"),
    }

    return {
        "entities_total": sum(1 for _ in result.iter_entities()),
        "fields_total": sum(len(entity.fields) for entity in result.iter_entities()),
        "unmapped_fields_total": sum(len(entity.unmapped_fields) for entity in result.iter_entities()),
        "field_status_counts": field_status_counts,
        "text_harmonization_status_counts": text_status_counts,
        "issues_total": len(all_issues),
        "global_issues_total": len(result.issues),
        "entity_issues_total": len(entity_issues),
        "issue_severity_counts": severity_counts,
        "has_errors": result.has_errors(),
    }

def build_harmonization_report(result: HarmonizationResult) -> dict[str, Any]:
    """
    Build a traceability report from a harmonization result.

    Trusted structural references are intentionally omitted from the report,
    because they are not harmonized by this layer. They appear as normal JSON-LD
    reference properties in the clean data output.
    """
    report_entities: dict[str, Any] = {}

    for entity in result.iter_entities():
        entity_id = entity.entity_id
        entity_dict = asdict(entity)
        entity_dict.pop("relations", None)
        entity_dict.pop("embedded_entities", None)
        entity_dict.pop("paired_embedded_entities", None)
        entity_dict.pop("has_explicit_id", None)

        if result.scope_name == "service":
            entity_dict["fields"] = {
                canonical_path: _with_jsonld_term(
                    canonical_path,
                    _with_decision_thresholds(
                        result.scope_name,
                        canonical_path,
                        _format_service_field_for_report(canonical_path, field_dict),
                    ),
                )
                for canonical_path, field_dict in entity_dict.get("fields", {}).items()
                if not _is_normalized_free_text_path(canonical_path)
            }
        else:
            entity_dict["fields"] = {
                canonical_path: _with_jsonld_term(
                    canonical_path,
                    _with_decision_thresholds(
                        result.scope_name,
                        canonical_path,
                        _format_measurement_field_for_report(field_dict),
                    ),
                )
                for canonical_path, field_dict in entity_dict.get("fields", {}).items()
            }

        if not entity_dict.get("text_harmonization"):
            entity_dict.pop("text_harmonization", None)
        else:
            entity_dict["text_harmonization"] = _with_text_thresholds(entity_dict["text_harmonization"])

        report_entities[entity_id] = _drop_none_values(entity_dict)

    return {
        "scope_name": result.scope_name,
        "summary": _build_report_summary(result, report_entities),
        "entities": report_entities,
        "global_issues": [_drop_none_values(asdict(issue)) for issue in result.issues],
    }


def build_full_output(result: HarmonizationResult, document: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the combined data/report wrapper used by the CLI default output."""
    return {
        "data": build_clean_jsonld(result, document=document),
        "report": build_harmonization_report(result),
        "has_errors": result.has_errors(),
    }
