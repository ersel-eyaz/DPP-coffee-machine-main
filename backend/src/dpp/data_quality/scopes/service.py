"""
Service-text scope definition.

This scope focuses on free-text service fields from SecondaryValueStep and its
specialized service-step subclasses. It is intentionally separated from product
and emission harmonization because symptoms and diagnoses are open text values,
not units, numeric measurements, or closed enum values.
"""

from __future__ import annotations

from dpp.data_quality.scopes.schemas import CanonicalField, CanonicalRelation, ScopeDefinition

_SERVICE_STEP_ENTITIES = (
    "SecondaryValueStep",
    "RepairServiceStep",
    "ReplaceServiceStep",
    "CleaningServiceStep",
    "RefurbishmentServiceStep",
    "RemanufacturingServiceStep",
)
_SERVICE_CONTEXT_ENTITIES = ("PartStatic", "PartInstance")


_SERVICE_ACTION_CONTEXT_FIELDS: dict[str, tuple[str, ...]] = {
    "RepairServiceStep": ("repairedPartId",),
    "ReplaceServiceStep": ("replacedPartId",),
    "CleaningServiceStep": ("cleanedPartId",),
    "RefurbishmentServiceStep": ("repairedPartIds", "cleanedPartIds"),
    "RemanufacturingServiceStep": ("repairedPartIds", "cleanedPartIds"),
}


def _service_action_context_fields(entity_type: str) -> tuple[CanonicalField, ...]:
    """Return typed service-action context fields for specialized service steps."""
    return tuple(
        CanonicalField(
            entity_type=entity_type,
            field_name=field_name,
            role="analysis_context",
            description=(
                "Service action target or replacement context preserved for "
                "part-aware review and anomaly assessment."
            ),
        )
        for field_name in _SERVICE_ACTION_CONTEXT_FIELDS.get(entity_type, ())
    )


SERVICE_SCOPE = ScopeDefinition(
    name="service",
    title="Service Free-Text Harmonization",
    description=(
        "Selected service-step fields used for harmonizing observed symptoms "
        "and diagnoses into OpenRepairData-derived canonical service concepts."
    ),
    entities=(*_SERVICE_STEP_ENTITIES, *_SERVICE_CONTEXT_ENTITIES),
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
            *_service_action_context_fields(entity_type),
        )
    ),
    relations=(
        CanonicalRelation(
            source_entity_type="PartInstance",
            relation_name="partStaticLink",
            target_entity_type="PartStatic",
            description=(
                "Static part definition retained as context for replacement-instance "
                "compatibility checks."
            ),
        ),
        CanonicalRelation(
            source_entity_type="ReplaceServiceStep",
            relation_name="newPart",
            target_entity_type="PartInstance",
            representation="embedded",
            required=True,
            description="Replacement part instance introduced by a replace service step.",
        ),
        CanonicalRelation(
            source_entity_type="RefurbishmentServiceStep",
            relation_name="replacedAndNewParts",
            target_entity_type="PartInstance",
            representation="paired_embedded",
            is_collection=True,
            required=False,
            description="Pairs each replaced part id with its embedded replacement part instance.",
        ),
        CanonicalRelation(
            source_entity_type="RemanufacturingServiceStep",
            relation_name="replacedAndNewParts",
            target_entity_type="PartInstance",
            representation="paired_embedded",
            is_collection=True,
            required=False,
            description="Pairs each replaced part id with its embedded replacement part instance.",
        ),
    ),
)
