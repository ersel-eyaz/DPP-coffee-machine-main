from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from dpp.harmonization.schemas import (
    DERIVED_FIELD_NAMES,
    PRIMARY_FIELD_NAMES,
    CONTEXT_FIELD_NAMES,
    RelationType,
    ScopedEntityType,
)


class ScopedFieldDefinition(BaseModel):
    """
    Definition of one canonical field inside the harmonization scope.
    """

    model_config = ConfigDict(frozen=True)

    canonical_name: str = Field(..., min_length=1)
    entity_type: ScopedEntityType
    role: str = Field(..., min_length=1)
    required: bool = False
    description: str = Field(..., min_length=1)


class ScopedRelationDefinition(BaseModel):
    """
    Definition of one structural relation supported by the harmonization scope.
    """

    model_config = ConfigDict(frozen=True)

    relation_type: RelationType
    subject_type: ScopedEntityType
    object_type: ScopedEntityType
    required: bool = False
    description: str = Field(..., min_length=1)


IN_SCOPE_ENTITY_TYPES: frozenset[ScopedEntityType] = frozenset(
    {
        ScopedEntityType.PART_INSTANCE,
        ScopedEntityType.PART_STATIC,
        ScopedEntityType.MATERIAL_INSTANCE,
        ScopedEntityType.MATERIAL_STATIC,
        ScopedEntityType.PROCESS_STEP,
        ScopedEntityType.ACTIVITY_DATA,
        ScopedEntityType.EMISSION_FACTOR,
        ScopedEntityType.GHG_EMISSION_RECORD,
        ScopedEntityType.DPP_INSTANCE,
    }
)


PRIMARY_FIELD_DEFINITIONS: tuple[ScopedFieldDefinition, ...] = (
    ScopedFieldDefinition(
        canonical_name="PartStatic.weightGRM",
        entity_type=ScopedEntityType.PART_STATIC,
        role="primary",
        required=False,
        description="Primary harmonization target for part weight in grams.",
    ),
    ScopedFieldDefinition(
        canonical_name="PartStatic.mtbfHRS",
        entity_type=ScopedEntityType.PART_STATIC,
        role="primary",
        required=False,
        description="Primary harmonization target for part MTBF in hours.",
    ),
    ScopedFieldDefinition(
        canonical_name="MaterialInstance.weightGRM",
        entity_type=ScopedEntityType.MATERIAL_INSTANCE,
        role="primary",
        required=False,
        description="Primary harmonization target for material instance weight in grams.",
    ),
    ScopedFieldDefinition(
        canonical_name="MaterialInstance.percentRecycled",
        entity_type=ScopedEntityType.MATERIAL_INSTANCE,
        role="primary",
        required=False,
        description="Primary harmonization target for recycled percentage.",
    ),
    ScopedFieldDefinition(
        canonical_name="MaterialInstance.purityLevel",
        entity_type=ScopedEntityType.MATERIAL_INSTANCE,
        role="primary",
        required=False,
        description="Primary harmonization target for purity level.",
    ),
    ScopedFieldDefinition(
        canonical_name="DPPInstance.operatingHRS",
        entity_type=ScopedEntityType.DPP_INSTANCE,
        role="primary",
        required=False,
        description="Primary harmonization target for operating hours.",
    ),
    ScopedFieldDefinition(
        canonical_name="DPPInstance.cleaningCount",
        entity_type=ScopedEntityType.DPP_INSTANCE,
        role="primary",
        required=False,
        description="Primary harmonization target for cleaning count.",
    ),
    ScopedFieldDefinition(
        canonical_name="DPPInstance.chalkCount",
        entity_type=ScopedEntityType.DPP_INSTANCE,
        role="primary",
        required=False,
        description="Primary harmonization target for chalk/descaling count.",
    ),
    ScopedFieldDefinition(
        canonical_name="DPPInstance.brewingCount",
        entity_type=ScopedEntityType.DPP_INSTANCE,
        role="primary",
        required=False,
        description="Primary harmonization target for brewing count.",
    ),
    ScopedFieldDefinition(
        canonical_name="ActivityData.quantity",
        entity_type=ScopedEntityType.ACTIVITY_DATA,
        role="primary",
        required=False,
        description="Primary harmonization target for activity quantity.",
    ),
    ScopedFieldDefinition(
        canonical_name="EmissionFactor.value",
        entity_type=ScopedEntityType.EMISSION_FACTOR,
        role="primary",
        required=False,
        description="Primary harmonization target for emission factor value.",
    ),
)


CONTEXT_FIELD_DEFINITIONS: tuple[ScopedFieldDefinition, ...] = (
    ScopedFieldDefinition(
        canonical_name="PartInstance.isModular",
        entity_type=ScopedEntityType.PART_INSTANCE,
        role="context",
        required=False,
        description="Supporting field indicating whether a part is modular.",
    ),
    ScopedFieldDefinition(
        canonical_name="PartInstance.hasFailstate",
        entity_type=ScopedEntityType.PART_INSTANCE,
        role="context",
        required=False,
        description="Supporting field indicating whether a part is currently in fail state.",
    ),
    ScopedFieldDefinition(
        canonical_name="MaterialStatic.hazardous",
        entity_type=ScopedEntityType.MATERIAL_STATIC,
        role="context",
        required=False,
        description="Supporting field indicating hazardous material status.",
    ),
    ScopedFieldDefinition(
        canonical_name="MaterialStatic.rareEarth",
        entity_type=ScopedEntityType.MATERIAL_STATIC,
        role="context",
        required=False,
        description="Supporting field indicating rare-earth presence.",
    ),
    ScopedFieldDefinition(
        canonical_name="ProcessStep.beginDate",
        entity_type=ScopedEntityType.PROCESS_STEP,
        role="context",
        required=False,
        description="Supporting field for process-step start time.",
    ),
    ScopedFieldDefinition(
        canonical_name="ProcessStep.endDate",
        entity_type=ScopedEntityType.PROCESS_STEP,
        role="context",
        required=False,
        description="Supporting field for process-step end time.",
    ),
    ScopedFieldDefinition(
        canonical_name="ActivityData.activity_type",
        entity_type=ScopedEntityType.ACTIVITY_DATA,
        role="context",
        required=False,
        description="Supporting field for the activity type.",
    ),
    ScopedFieldDefinition(
        canonical_name="ActivityData.unit",
        entity_type=ScopedEntityType.ACTIVITY_DATA,
        role="context",
        required=False,
        description="Supporting field for the activity unit.",
    ),
    ScopedFieldDefinition(
        canonical_name="EmissionFactor.unit",
        entity_type=ScopedEntityType.EMISSION_FACTOR,
        role="context",
        required=False,
        description="Supporting field for the emission factor unit.",
    ),
    ScopedFieldDefinition(
        canonical_name="GHGEmissionRecord.scope",
        entity_type=ScopedEntityType.GHG_EMISSION_RECORD,
        role="context",
        required=False,
        description="Supporting field for GHG scope.",
    ),
    ScopedFieldDefinition(
        canonical_name="GHGEmissionRecord.scope3_category",
        entity_type=ScopedEntityType.GHG_EMISSION_RECORD,
        role="context",
        required=False,
        description="Supporting field for Scope 3 category.",
    ),
    ScopedFieldDefinition(
        canonical_name="GHGEmissionRecord.calculation_method",
        entity_type=ScopedEntityType.GHG_EMISSION_RECORD,
        role="context",
        required=False,
        description="Supporting field for calculation method.",
    ),
    ScopedFieldDefinition(
        canonical_name="GHGEmissionRecord.provenance",
        entity_type=ScopedEntityType.GHG_EMISSION_RECORD,
        role="context",
        required=False,
        description="Supporting field for provenance.",
    ),
)


DERIVED_FIELD_DEFINITIONS: tuple[ScopedFieldDefinition, ...] = (
    ScopedFieldDefinition(
        canonical_name="GHGEmissionRecord.emissions_kg_co2e",
        entity_type=ScopedEntityType.GHG_EMISSION_RECORD,
        role="derived",
        required=False,
        description="Derived emissions value used mainly for plausibility and anomaly checks.",
    ),
)


RELATION_DEFINITIONS: tuple[ScopedRelationDefinition, ...] = (
    ScopedRelationDefinition(
        relation_type=RelationType.PART_INSTANCE_TO_STATIC,
        subject_type=ScopedEntityType.PART_INSTANCE,
        object_type=ScopedEntityType.PART_STATIC,
        required=False,
        description="Maps PartInstance to its PartStatic definition.",
    ),
    ScopedRelationDefinition(
        relation_type=RelationType.PART_INSTANCE_TO_PART,
        subject_type=ScopedEntityType.PART_INSTANCE,
        object_type=ScopedEntityType.PART_INSTANCE,
        required=False,
        description="Represents nested composite part structure.",
    ),
    ScopedRelationDefinition(
        relation_type=RelationType.PART_INSTANCE_TO_MATERIAL,
        subject_type=ScopedEntityType.PART_INSTANCE,
        object_type=ScopedEntityType.MATERIAL_INSTANCE,
        required=False,
        description="Represents materials contained in a part instance.",
    ),
    ScopedRelationDefinition(
        relation_type=RelationType.MATERIAL_INSTANCE_TO_STATIC,
        subject_type=ScopedEntityType.MATERIAL_INSTANCE,
        object_type=ScopedEntityType.MATERIAL_STATIC,
        required=False,
        description="Maps MaterialInstance to its MaterialStatic definition.",
    ),
    ScopedRelationDefinition(
        relation_type=RelationType.DPP_INSTANCE_TO_PART,
        subject_type=ScopedEntityType.DPP_INSTANCE,
        object_type=ScopedEntityType.PART_INSTANCE,
        required=False,
        description="Maps DPPInstance to its top-level part instance.",
    ),
    ScopedRelationDefinition(
        relation_type=RelationType.PROCESS_STEP_TO_GHG_RECORD,
        subject_type=ScopedEntityType.PROCESS_STEP,
        object_type=ScopedEntityType.GHG_EMISSION_RECORD,
        required=False,
        description="Maps ProcessStep to its GHG emission records.",
    ),
    ScopedRelationDefinition(
        relation_type=RelationType.GHG_RECORD_TO_ACTIVITY,
        subject_type=ScopedEntityType.GHG_EMISSION_RECORD,
        object_type=ScopedEntityType.ACTIVITY_DATA,
        required=False,
        description="Maps GHGEmissionRecord to its ActivityData.",
    ),
    ScopedRelationDefinition(
        relation_type=RelationType.GHG_RECORD_TO_EMISSION_FACTOR,
        subject_type=ScopedEntityType.GHG_EMISSION_RECORD,
        object_type=ScopedEntityType.EMISSION_FACTOR,
        required=False,
        description="Maps GHGEmissionRecord to its EmissionFactor.",
    ),
)


ALL_FIELD_DEFINITIONS: tuple[ScopedFieldDefinition, ...] = (
    PRIMARY_FIELD_DEFINITIONS + CONTEXT_FIELD_DEFINITIONS + DERIVED_FIELD_DEFINITIONS
)

FIELD_DEFINITION_BY_CANONICAL_NAME: dict[str, ScopedFieldDefinition] = {
    definition.canonical_name: definition for definition in ALL_FIELD_DEFINITIONS
}


RELATION_DEFINITION_BY_TYPE: dict[RelationType, ScopedRelationDefinition] = {
    definition.relation_type: definition for definition in RELATION_DEFINITIONS
}


def is_in_scope_entity_type(entity_type: str) -> bool:
    return entity_type in {item.value for item in IN_SCOPE_ENTITY_TYPES}


def is_primary_field(canonical_name: str) -> bool:
    return canonical_name in PRIMARY_FIELD_NAMES


def is_context_field(canonical_name: str) -> bool:
    return canonical_name in CONTEXT_FIELD_NAMES


def is_derived_field(canonical_name: str) -> bool:
    return canonical_name in DERIVED_FIELD_NAMES


def get_field_definition(canonical_name: str) -> ScopedFieldDefinition | None:
    return FIELD_DEFINITION_BY_CANONICAL_NAME.get(canonical_name)


def get_relation_definition(relation_type: RelationType) -> ScopedRelationDefinition | None:
    return RELATION_DEFINITION_BY_TYPE.get(relation_type)