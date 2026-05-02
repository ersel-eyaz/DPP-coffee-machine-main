"""
Service-text scope definition.

This scope focuses on free-text service fields from SecondaryValueStep and its
specialized service-step subclasses. It is intentionally separated from product
and emission harmonization because symptoms and diagnoses are open text values,
not units, numeric measurements, or closed enum values.
"""

from __future__ import annotations

from dpp.data_quality.scopes.schemas import CanonicalField, ScopeDefinition


_SERVICE_STEP_ENTITIES = (
    "SecondaryValueStep",
    "RepairServiceStep",
    "ReplaceServiceStep",
    "CleaningServiceStep",
    "RefurbishmentServiceStep",
    "RemanufacturingServiceStep",
)


SERVICE_SCOPE = ScopeDefinition(
    name="service",
    title="Service Free-Text Harmonization",
    description=(
        "Selected service-step fields used for harmonizing observed symptoms "
        "and diagnoses into seeded canonical service concepts."
    ),
    entities=_SERVICE_STEP_ENTITIES,
    fields=tuple(
        field
        for entity_type in _SERVICE_STEP_ENTITIES
        for field in (
            CanonicalField(
                entity_type=entity_type,
                field_name="observedSymptoms",
                role="free_text_harmonization",
                description="Original observed symptom texts recorded during service steps.",
            ),
            CanonicalField(
                entity_type=entity_type,
                field_name="diagnose",
                role="free_text_harmonization",
                description="Original diagnosis text recorded during service steps.",
            ),
            CanonicalField(
                entity_type=entity_type,
                field_name="costEur",
                role="analysis_context",
                description="Service-step cost in euros, preserved as contextual information.",
            ),
        )
    ),
    relations=(),
)
