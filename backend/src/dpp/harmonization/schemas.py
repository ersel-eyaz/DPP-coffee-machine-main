from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Scope-level enums
# ---------------------------------------------------------------------------


class ScopedEntityType(str, Enum):
    DPP_INSTANCE = "DPPInstance"
    PART_INSTANCE = "PartInstance"
    PART_STATIC = "PartStatic"
    MATERIAL_INSTANCE = "MaterialInstance"
    MATERIAL_STATIC = "MaterialStatic"
    PROCESS_STEP = "ProcessStep"
    ACTIVITY_DATA = "ActivityData"
    EMISSION_FACTOR = "EmissionFactor"
    GHG_EMISSION_RECORD = "GHGEmissionRecord"


class FieldRole(str, Enum):
    PRIMARY = "primary"
    CONTEXT = "context"
    DERIVED = "derived"


class RelationType(str, Enum):
    PART_INSTANCE_TO_STATIC = "part_instance_to_static"
    PART_INSTANCE_TO_PART = "part_instance_to_part"
    PART_INSTANCE_TO_MATERIAL = "part_instance_to_material"
    MATERIAL_INSTANCE_TO_STATIC = "material_instance_to_static"
    DPP_INSTANCE_TO_PART = "dpp_instance_to_part"
    PROCESS_STEP_TO_GHG_RECORD = "process_step_to_ghg_record"
    GHG_RECORD_TO_ACTIVITY = "ghg_record_to_activity"
    GHG_RECORD_TO_EMISSION_FACTOR = "ghg_record_to_emission_factor"


class IssueSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class IssueType(str, Enum):
    UNMAPPED_FIELD = "unmapped_field"
    OUT_OF_SCOPE_FIELD = "out_of_scope_field"
    OUT_OF_SCOPE_ENTITY = "out_of_scope_entity"
    UNIT_NORMALIZATION_WARNING = "unit_normalization_warning"
    VALUE_NORMALIZATION_WARNING = "value_normalization_warning"
    ENUM_NORMALIZATION_WARNING = "enum_normalization_warning"
    RELATION_WARNING = "relation_warning"
    STRUCTURE_WARNING = "structure_warning"
    DUPLICATE_CANDIDATE = "duplicate_candidate"
    LOW_CONFIDENCE_MAPPING = "low_confidence_mapping"
    MISSING_REQUIRED_CONTEXT = "missing_required_context"
    DERIVATION_WARNING = "derivation_warning"


# ---------------------------------------------------------------------------
# Raw extracted layer
# ---------------------------------------------------------------------------


class RawPropertyObservation(BaseModel):
    """
    Raw field-level observation extracted from heterogeneous input.

    This is not yet canonical. It preserves the original signal
    that later mapping and normalization steps can interpret.
    """

    model_config = ConfigDict(extra="forbid")

    source_path: str = Field(..., min_length=1)
    source_entity_id: str | None = None
    source_entity_type: str | None = None

    raw_label: str = Field(..., min_length=1)
    raw_value: Any = None
    raw_unit: str | None = None

    neighbor_labels: list[str] = Field(default_factory=list)
    source_node_types: list[str] = Field(default_factory=list)

    @field_validator("raw_label")
    @classmethod
    def _strip_raw_label(cls, value: str) -> str:
        return value.strip()

    @field_validator("raw_unit")
    @classmethod
    def _strip_raw_unit(cls, value: str | None) -> str | None:
        return value.strip() if value else value

    @field_validator("neighbor_labels")
    @classmethod
    def _normalize_neighbor_labels(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            stripped = value.strip()
            if stripped:
                normalized.append(stripped)
        return normalized

    @field_validator("source_node_types")
    @classmethod
    def _normalize_source_node_types(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            stripped = value.strip()
            if stripped:
                normalized.append(stripped)
        return normalized


class RawRelationObservation(BaseModel):
    """
    Raw graph edge extracted from the input before semantic harmonization.
    """

    model_config = ConfigDict(extra="forbid")

    source_path: str = Field(..., min_length=1)

    subject_id: str = Field(..., min_length=1)
    subject_type: str | None = None

    predicate_label: str = Field(..., min_length=1)

    object_id: str | None = None
    object_type: str | None = None
    object_inline: bool = False

    @field_validator("predicate_label")
    @classmethod
    def _strip_predicate_label(cls, value: str) -> str:
        return value.strip()


# ---------------------------------------------------------------------------
# Canonical field layer
# ---------------------------------------------------------------------------


class HarmonizedField(BaseModel):
    """
    Canonical field-level result after mapping and normalization.

    `canonical_name` should match the scoped target field naming
    used by the harmonization layer, not necessarily the final DB field.
    """

    model_config = ConfigDict(extra="forbid")

    canonical_name: str = Field(..., min_length=1)
    role: FieldRole

    normalized_value: Any = None
    normalized_unit: str | None = None

    original_label: str | None = None
    original_value: Any = None
    original_unit: str | None = None

    confidence: float = Field(..., ge=0.0, le=1.0)
    matched_by: str = Field(..., min_length=1)
    provenance_paths: list[str] = Field(default_factory=list)

    supporting_evidence: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @field_validator("canonical_name", "matched_by")
    @classmethod
    def _strip_required_strings(cls, value: str) -> str:
        return value.strip()

    @field_validator("normalized_unit", "original_label", "original_unit")
    @classmethod
    def _strip_optional_strings(cls, value: str | None) -> str | None:
        return value.strip() if value else value

    @field_validator("provenance_paths", "supporting_evidence", "notes")
    @classmethod
    def _normalize_string_lists(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            stripped = value.strip()
            if stripped:
                normalized.append(stripped)
        return normalized


class HarmonizedRelation(BaseModel):
    """
    Canonical structural relation between two harmonized entities.
    """

    model_config = ConfigDict(extra="forbid")

    relation_type: RelationType
    subject_entity_id: str = Field(..., min_length=1)
    object_entity_id: str = Field(..., min_length=1)

    confidence: float = Field(..., ge=0.0, le=1.0)
    provenance_paths: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @field_validator("subject_entity_id", "object_entity_id")
    @classmethod
    def _strip_ids(cls, value: str) -> str:
        return value.strip()

    @field_validator("provenance_paths", "notes")
    @classmethod
    def _normalize_lists(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            stripped = value.strip()
            if stripped:
                normalized.append(stripped)
        return normalized


# ---------------------------------------------------------------------------
# Canonical entity layer
# ---------------------------------------------------------------------------


class HarmonizedEntity(BaseModel):
    """
    Scope-limited canonical entity.

    `fields` contains only the harmonized fields that were actually found
    or derived for this entity. Missing fields simply stay absent.
    """

    model_config = ConfigDict(extra="forbid")

    entity_id: str = Field(..., min_length=1)
    entity_type: ScopedEntityType

    source_ids: list[str] = Field(default_factory=list)
    source_node_types: list[str] = Field(default_factory=list)
    source_paths: list[str] = Field(default_factory=list)

    fields: dict[str, HarmonizedField] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)

    @field_validator("entity_id")
    @classmethod
    def _strip_entity_id(cls, value: str) -> str:
        return value.strip()

    @field_validator("source_ids", "source_node_types", "source_paths", "tags")
    @classmethod
    def _normalize_string_lists(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            stripped = value.strip()
            if stripped:
                normalized.append(stripped)
        return normalized


# ---------------------------------------------------------------------------
# Issue / report layer
# ---------------------------------------------------------------------------


class HarmonizationIssue(BaseModel):
    """
    Non-fatal or fatal issue produced during harmonization.
    """

    model_config = ConfigDict(extra="forbid")

    severity: IssueSeverity
    issue_type: IssueType
    message: str = Field(..., min_length=1)

    entity_id: str | None = None
    entity_type: ScopedEntityType | None = None
    field_name: str | None = None

    source_path: str | None = None
    raw_label: str | None = None

    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("message")
    @classmethod
    def _strip_message(cls, value: str) -> str:
        return value.strip()

    @field_validator("entity_id", "field_name", "source_path", "raw_label")
    @classmethod
    def _strip_optional_strings(cls, value: str | None) -> str | None:
        return value.strip() if value else value


class HarmonizationStats(BaseModel):
    """
    Lightweight counters for quick debugging and CLI inspection.
    """

    model_config = ConfigDict(extra="forbid")

    raw_property_count: int = Field(default=0, ge=0)
    raw_relation_count: int = Field(default=0, ge=0)

    harmonized_entity_count: int = Field(default=0, ge=0)
    harmonized_field_count: int = Field(default=0, ge=0)
    harmonized_relation_count: int = Field(default=0, ge=0)

    issue_count: int = Field(default=0, ge=0)
    warning_count: int = Field(default=0, ge=0)
    error_count: int = Field(default=0, ge=0)


# ---------------------------------------------------------------------------
# Top-level payload
# ---------------------------------------------------------------------------


class HarmonizationResult(BaseModel):
    """
    Top-level intermediate output of the harmonization layer.

    This is the main object that later stages can consume:
    - projection to current Beanie models
    - anomaly detection
    - CLI debugging
    - API responses for dry-run harmonization
    """

    model_config = ConfigDict(extra="forbid")

    entities: dict[str, HarmonizedEntity] = Field(default_factory=dict)
    relations: list[HarmonizedRelation] = Field(default_factory=list)
    issues: list[HarmonizationIssue] = Field(default_factory=list)
    stats: HarmonizationStats = Field(default_factory=HarmonizationStats)

    source_format: Literal["jsonld"] = "jsonld"
    scope_name: str = "dpp_harmonization_scope_v1"
    success: bool = True


# ---------------------------------------------------------------------------
# Optional convenience constants
# ---------------------------------------------------------------------------

PRIMARY_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "PartStatic.weightGRM",
        "PartStatic.mtbfHRS",
        "MaterialInstance.weightGRM",
        "MaterialInstance.percentRecycled",
        "MaterialInstance.purityLevel",
        "DPPInstance.operatingHRS",
        "DPPInstance.cleaningCount",
        "DPPInstance.chalkCount",
        "DPPInstance.brewingCount",
        "ActivityData.quantity",
        "EmissionFactor.value",
    }
)

CONTEXT_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "PartInstance.isModular",
        "PartInstance.hasFailstate",
        "MaterialStatic.hazardous",
        "MaterialStatic.rareEarth",
        "ProcessStep.beginDate",
        "ProcessStep.endDate",
        "ActivityData.activity_type",
        "ActivityData.unit",
        "EmissionFactor.unit",
        "GHGEmissionRecord.scope",
        "GHGEmissionRecord.scope3_category",
        "GHGEmissionRecord.calculation_method",
        "GHGEmissionRecord.provenance",
    }
)

DERIVED_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "GHGEmissionRecord.emissions_kg_co2e",
    }
)