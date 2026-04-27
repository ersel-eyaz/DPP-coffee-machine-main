"""
Shared scope schemas for the data quality layer.

The scope objects are configuration-like definitions. They describe which
canonical model fields and structural relations are relevant for harmonization
and anomaly detection, without importing or depending on the original Beanie
document models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


FieldRole = Literal[
    "label_harmonization",
    "unit_harmonization",
    "controlled_vocabulary",
    "analysis_context",
]


@dataclass(frozen=True)
class CanonicalField:
    """
    A canonical field used by the data quality layer.

    Attributes:
        entity_type: Canonical entity/class name from the DPP prototype model.
        field_name: Canonical field name as used in the prototype code.
        role: How this field is used in the data quality layer.
        target_unit: Canonical unit after normalization, if applicable.
        description: Short explanation for documentation and reports.
    """

    entity_type: str
    field_name: str
    role: FieldRole
    target_unit: str | None = None
    description: str = ""

    @property
    def path(self) -> str:
        """Return the canonical field path, e.g. 'DPPInstance.operatingHRS'."""
        return f"{self.entity_type}.{self.field_name}"


@dataclass(frozen=True)
class CanonicalRelation:
    """
    A trusted structural relation that should be preserved.

    Relations are not harmonized by the data quality layer. Entity typing and
    relation structure are assumed to be reliable. These definitions only state
    which relations should be carried into the intermediate representation so
    downstream anomaly detection can use the graph context.
    """

    source_entity_type: str
    relation_name: str
    target_entity_type: str
    is_collection: bool = False
    required: bool = False
    description: str = ""

    @property
    def path(self) -> str:
        """Return the canonical relation path, e.g. 'DPPInstance.partInstanceLink'."""
        return f"{self.source_entity_type}.{self.relation_name}"


@dataclass(frozen=True)
class ScopeDefinition:
    """
    A reusable data quality scope.

    The same scope definition is consumed by both harmonization and anomaly
    detection. Harmonization uses field definitions for label/unit/vocabulary
    normalization and preserves the listed structural relations. Anomaly
    detection uses the active fields plus the preserved graph context.
    """

    name: str
    title: str
    description: str
    entities: tuple[str, ...]
    fields: tuple[CanonicalField, ...] = field(default_factory=tuple)
    relations: tuple[CanonicalRelation, ...] = field(default_factory=tuple)

    def fields_by_role(self, role: FieldRole) -> tuple[CanonicalField, ...]:
        """Return fields matching a given role."""
        return tuple(item for item in self.fields if item.role == role)

    def label_harmonization_fields(self) -> tuple[CanonicalField, ...]:
        """Return fields that should receive explicit label harmonization."""
        return self.fields_by_role("label_harmonization")

    def unit_harmonization_fields(self) -> tuple[CanonicalField, ...]:
        """Return fields that should receive explicit unit harmonization."""
        return self.fields_by_role("unit_harmonization")

    def controlled_vocabulary_fields(self) -> tuple[CanonicalField, ...]:
        """Return fields that should receive controlled-vocabulary normalization."""
        return self.fields_by_role("controlled_vocabulary")

    def relation_paths(self) -> tuple[str, ...]:
        """Return all preserved canonical relation paths."""
        return tuple(relation.path for relation in self.relations)
