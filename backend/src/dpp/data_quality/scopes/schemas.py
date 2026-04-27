"""
Shared scope schemas for the data quality layer.

The scope objects are configuration-like definitions. They describe which
canonical model fields are relevant for harmonization and anomaly detection,
without importing or depending on the original Beanie document models.
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
        role: How this field is used in the first iteration.
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
class ScopeDefinition:
    """
    A reusable data quality scope.

    The same scope definition is consumed by both harmonization and anomaly
    detection. Harmonization uses the label/unit/vocabulary targets, while
    anomaly detection uses the active fields plus selected context fields.
    """

    name: str
    title: str
    description: str
    entities: tuple[str, ...]
    fields: tuple[CanonicalField, ...] = field(default_factory=tuple)

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
