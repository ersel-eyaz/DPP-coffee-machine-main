"""
Result schemas for the harmonization layer.

These schemas describe the output of parsing, label mapping, unit normalization,
and controlled-vocabulary normalization. They are intentionally independent from
the original Beanie document models.

Entity types are expected to remain recognisable. Registered structural
relations are preserved for downstream anomaly detection, while unregistered
relation-shaped inputs are reported without semantic reconstruction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

HarmonizationStatus = Literal[
    "mapped",
    "normalized",
    "unmapped",
    "ambiguous",
    "error",
]

HarmonizationIssueSeverity = Literal[
    "info",
    "warning",
    "error",
]


@dataclass(frozen=True)
class RawField:
    """
    A field as it appeared in the dirty input.

    Attributes:
        label: Original input label, e.g. 'productWeight'.
        value: Original input value.
        unit: Optional original unit, e.g. 'kg'.
    """

    label: str
    value: Any
    unit: str | None = None


@dataclass(frozen=True)
class HarmonizedField:
    """
    A field after label and/or unit harmonization.

    Attributes:
        canonical_path: Canonical target path, e.g. 'DPPStatic.weightGRM'.
        original_label: Original input label.
        original_value: Original input value.
        normalized_value: Value after normalization, if normalization was applied.
        original_unit: Unit as found in the input, if available.
        normalized_unit: Canonical unit after normalization, if applicable.
        status: Harmonization status.
        confidence: Backward-compatible field mapping confidence. This is kept for
            older callers and should be read as field_confidence.
        field_confidence: Confidence score for the field-label mapping.
        value_confidence: Confidence score for value or unit normalization, if
            such normalization was applied.
        field_method: Method used for field-label mapping, e.g.
            'exact_or_alias' or 'fuzzy'.
        value_method: Method used for value/unit normalization, e.g.
            'canonical', 'alias', 'fuzzy', 'unit_conversion', or 'parsed'.
    """

    canonical_path: str
    original_label: str
    original_value: Any
    normalized_value: Any | None = None
    original_unit: str | None = None
    normalized_unit: str | None = None
    status: HarmonizationStatus = "mapped"
    confidence: float = 1.0
    field_confidence: float | None = None
    value_confidence: float | None = None
    field_method: str | None = None
    value_method: str | None = None


@dataclass(frozen=True)
class PreservedRelation:
    """
    A trusted structural relation preserved from the input.

    Relations are not harmonized in this layer. They are carried forward to
    preserve graph structure and support downstream anomaly detection.
    """

    source_entity_id: str
    relation_name: str
    target_entity_id: str
    target_entity_type: str | None = None


@dataclass(frozen=True)
class HarmonizationIssue:
    """
    A non-fatal issue found during harmonization.

    Examples:
        - Unknown field label.
        - Ambiguous mapping candidate.
        - Unsupported unit.
        - Value could not be converted.
    """

    severity: HarmonizationIssueSeverity
    message: str
    entity_id: str | None = None
    entity_type: str | None = None
    field_label: str | None = None


@dataclass(frozen=True)
class HarmonizedEntity:
    """
    Harmonized representation of one input entity.

    Attributes:
        entity_id: Input entity identifier, usually from '@id'.
        entity_type: Canonical entity type, usually derived from '@type'.
        fields: Harmonized fields keyed by canonical path.
        relations: Trusted reference relations preserved from the input.
        embedded_entities: Owned child entities keyed by structural property,
            such as ``activity`` or ``compositeParts``.
        paired_embedded_entities: Structural replacement pairs keyed by property,
            each retaining an existing-part id and an embedded replacement entity.
        unmapped_fields: Raw fields that could not be mapped.
        text_harmonization: Free-text concept normalization details, separated
            from structural field-label mapping.
        issues: Entity-level harmonization issues.
    """

    entity_id: str
    entity_type: str
    has_explicit_id: bool = True
    fields: dict[str, HarmonizedField] = field(default_factory=dict)
    relations: list[PreservedRelation] = field(default_factory=list)
    embedded_entities: dict[str, list["HarmonizedEntity"]] = field(default_factory=dict)
    paired_embedded_entities: dict[str, list[tuple[str, "HarmonizedEntity"]]] = field(default_factory=dict)
    unmapped_fields: list[RawField] = field(default_factory=list)
    text_harmonization: dict[str, Any] = field(default_factory=dict)
    issues: list[HarmonizationIssue] = field(default_factory=list)


@dataclass(frozen=True)
class HarmonizationResult:
    """
    Complete harmonization result for one input document.

    Attributes:
        scope_name: Scope used for harmonization, e.g. 'product' or 'emission'.
        entities: Harmonized entities keyed by entity id.
        issues: Global harmonization issues.
    """

    scope_name: str
    entities: dict[str, HarmonizedEntity] = field(default_factory=dict)
    issues: list[HarmonizationIssue] = field(default_factory=list)

    def iter_entities(self):
        """Yield root and embedded entities in document order."""
        def walk(entity: HarmonizedEntity):
            yield entity
            for children in entity.embedded_entities.values():
                for child in children:
                    yield from walk(child)
            for pairs in entity.paired_embedded_entities.values():
                for _, child in pairs:
                    yield from walk(child)

        for entity in self.entities.values():
            yield from walk(entity)

    def find_entity(self, entity_id: str) -> HarmonizedEntity | None:
        """Return a root or embedded entity by identifier."""
        for entity in self.iter_entities():
            if entity.entity_id == entity_id:
                return entity
        return None

    def has_errors(self) -> bool:
        """Return True if any global or entity-level issue has severity 'error'."""
        if any(issue.severity == "error" for issue in self.issues):
            return True

        return any(
            issue.severity == "error"
            for entity in self.iter_entities()
            for issue in entity.issues
        )
