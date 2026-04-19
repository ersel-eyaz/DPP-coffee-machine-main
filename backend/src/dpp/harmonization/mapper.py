from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Iterable

from dpp.harmonization.schemas import (
    FieldRole,
    HarmonizationIssue,
    HarmonizationResult,
    HarmonizationStats,
    HarmonizedEntity,
    HarmonizedField,
    HarmonizedRelation,
    IssueSeverity,
    IssueType,
    RawPropertyObservation,
    RawRelationObservation,
    RelationType,
    ScopedEntityType,
)
from dpp.harmonization.scope import (
    get_field_definition,
    get_relation_definition,
    is_context_field,
    is_derived_field,
    is_in_scope_entity_type,
    is_primary_field,
)


# ---------------------------------------------------------------------------
# Internal mapping structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FieldMappingRule:
    """One candidate rule for mapping a raw property to a canonical field."""

    entity_type: ScopedEntityType
    canonical_name: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class RelationMappingRule:
    """One candidate rule for mapping a raw relation to a canonical relation."""

    relation_type: RelationType
    subject_type: ScopedEntityType
    object_type: ScopedEntityType
    aliases: tuple[str, ...]


@dataclass(slots=True)
class MappingOutput:
    """Intermediate mapper output before dedicated normalization/service stages."""

    entities: dict[str, HarmonizedEntity] = field(default_factory=dict)
    relations: list[HarmonizedRelation] = field(default_factory=list)
    issues: list[HarmonizationIssue] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Field mapping configuration
# ---------------------------------------------------------------------------


FIELD_RULES: tuple[FieldMappingRule, ...] = (
    FieldMappingRule(
        entity_type=ScopedEntityType.PART_STATIC,
        canonical_name="PartStatic.weightGRM",
        aliases=("weightgrm", "weight", "massgrm", "partweight", "weightg"),
    ),
    FieldMappingRule(
        entity_type=ScopedEntityType.PART_STATIC,
        canonical_name="PartStatic.mtbfHRS",
        aliases=("mtbfhrs", "mtbf", "meantimebetweenfailures", "mtbfhours"),
    ),
    FieldMappingRule(
        entity_type=ScopedEntityType.MATERIAL_INSTANCE,
        canonical_name="MaterialInstance.weightGRM",
        aliases=("weightgrm", "weight", "massgrm", "materialweight", "weightg"),
    ),
    FieldMappingRule(
        entity_type=ScopedEntityType.MATERIAL_INSTANCE,
        canonical_name="MaterialInstance.percentRecycled",
        aliases=(
            "percentrecycled",
            "recycledcontent",
            "recycledshare",
            "recycledpercentage",
            "recycledpercent",
        ),
    ),
    FieldMappingRule(
        entity_type=ScopedEntityType.MATERIAL_INSTANCE,
        canonical_name="MaterialInstance.purityLevel",
        aliases=("puritylevel", "purity", "puritypercent", "materialpurity"),
    ),
    FieldMappingRule(
        entity_type=ScopedEntityType.DPP_INSTANCE,
        canonical_name="DPPInstance.operatingHRS",
        aliases=("operatinghrs", "operatinghours", "operatinghourscount", "usagehours"),
    ),
    FieldMappingRule(
        entity_type=ScopedEntityType.DPP_INSTANCE,
        canonical_name="DPPInstance.cleaningCount",
        aliases=("cleaningcount", "cleaningcycles", "cleanings", "cleaningcounter"),
    ),
    FieldMappingRule(
        entity_type=ScopedEntityType.DPP_INSTANCE,
        canonical_name="DPPInstance.chalkCount",
        aliases=("chalkcount", "chalkcounter", "descalingcount", "descalingcounter"),
    ),
    FieldMappingRule(
        entity_type=ScopedEntityType.DPP_INSTANCE,
        canonical_name="DPPInstance.brewingCount",
        aliases=("brewingcount", "brewcount", "brewcounter", "brewingcycles"),
    ),
    FieldMappingRule(
        entity_type=ScopedEntityType.ACTIVITY_DATA,
        canonical_name="ActivityData.quantity",
        aliases=("quantity", "amount", "activityquantity", "measuredquantity"),
    ),
    FieldMappingRule(
        entity_type=ScopedEntityType.EMISSION_FACTOR,
        canonical_name="EmissionFactor.value",
        aliases=("value", "factorvalue", "emissionfactor", "emissionfactorvalue"),
    ),
    FieldMappingRule(
        entity_type=ScopedEntityType.PART_INSTANCE,
        canonical_name="PartInstance.isModular",
        aliases=("ismodular", "modular", "ismodularityenabled"),
    ),
    FieldMappingRule(
        entity_type=ScopedEntityType.PART_INSTANCE,
        canonical_name="PartInstance.hasFailstate",
        aliases=("hasfailstate", "failstate", "hasfailurestate", "failurestate"),
    ),
    FieldMappingRule(
        entity_type=ScopedEntityType.MATERIAL_STATIC,
        canonical_name="MaterialStatic.hazardous",
        aliases=("hazardous", "ishazardous", "hazardousmaterial"),
    ),
    FieldMappingRule(
        entity_type=ScopedEntityType.MATERIAL_STATIC,
        canonical_name="MaterialStatic.rareEarth",
        aliases=("rareearth", "containsrareearth", "hasearthmaterials"),
    ),
    FieldMappingRule(
        entity_type=ScopedEntityType.PROCESS_STEP,
        canonical_name="ProcessStep.beginDate",
        aliases=("begindate", "startdate", "starttime", "begin"),
    ),
    FieldMappingRule(
        entity_type=ScopedEntityType.PROCESS_STEP,
        canonical_name="ProcessStep.endDate",
        aliases=("enddate", "endtime", "finishdate", "end"),
    ),
    FieldMappingRule(
        entity_type=ScopedEntityType.ACTIVITY_DATA,
        canonical_name="ActivityData.activity_type",
        aliases=("activitytype", "activity", "type", "activitykind"),
    ),
    FieldMappingRule(
        entity_type=ScopedEntityType.ACTIVITY_DATA,
        canonical_name="ActivityData.unit",
        aliases=("unit", "activityunit", "rawunit"),
    ),
    FieldMappingRule(
        entity_type=ScopedEntityType.EMISSION_FACTOR,
        canonical_name="EmissionFactor.unit",
        aliases=("unit", "factorunit", "emissionfactorunit", "rawunit"),
    ),
    FieldMappingRule(
        entity_type=ScopedEntityType.GHG_EMISSION_RECORD,
        canonical_name="GHGEmissionRecord.scope",
        aliases=("scope", "ghgscope"),
    ),
    FieldMappingRule(
        entity_type=ScopedEntityType.GHG_EMISSION_RECORD,
        canonical_name="GHGEmissionRecord.scope3_category",
        aliases=("scope3category", "scope3categoryname", "scopecategory", "category"),
    ),
    FieldMappingRule(
        entity_type=ScopedEntityType.GHG_EMISSION_RECORD,
        canonical_name="GHGEmissionRecord.calculation_method",
        aliases=("calculationmethod", "method", "formula", "calculation"),
    ),
    FieldMappingRule(
        entity_type=ScopedEntityType.GHG_EMISSION_RECORD,
        canonical_name="GHGEmissionRecord.provenance",
        aliases=("provenance", "source", "datasource", "recordsource"),
    ),
    FieldMappingRule(
        entity_type=ScopedEntityType.GHG_EMISSION_RECORD,
        canonical_name="GHGEmissionRecord.emissions_kg_co2e",
        aliases=("emissionskgco2e", "emissions", "co2e", "ghgemissions"),
    ),
)


RELATION_RULES: tuple[RelationMappingRule, ...] = (
    RelationMappingRule(
        relation_type=RelationType.PART_INSTANCE_TO_STATIC,
        subject_type=ScopedEntityType.PART_INSTANCE,
        object_type=ScopedEntityType.PART_STATIC,
        aliases=("partstaticlink", "describedby", "partstatic", "hasstatic"),
    ),
    RelationMappingRule(
        relation_type=RelationType.PART_INSTANCE_TO_PART,
        subject_type=ScopedEntityType.PART_INSTANCE,
        object_type=ScopedEntityType.PART_INSTANCE,
        aliases=("compositeparts", "contains", "composes", "hastopart", "haspart"),
    ),
    RelationMappingRule(
        relation_type=RelationType.PART_INSTANCE_TO_MATERIAL,
        subject_type=ScopedEntityType.PART_INSTANCE,
        object_type=ScopedEntityType.MATERIAL_INSTANCE,
        aliases=("compositematerials", "hasmaterial", "containsmaterial", "materials"),
    ),
    RelationMappingRule(
        relation_type=RelationType.MATERIAL_INSTANCE_TO_STATIC,
        subject_type=ScopedEntityType.MATERIAL_INSTANCE,
        object_type=ScopedEntityType.MATERIAL_STATIC,
        aliases=("materialstaticlink", "describedby", "materialstatic", "hasstatic"),
    ),
    RelationMappingRule(
        relation_type=RelationType.DPP_INSTANCE_TO_PART,
        subject_type=ScopedEntityType.DPP_INSTANCE,
        object_type=ScopedEntityType.PART_INSTANCE,
        aliases=("partinstancelink", "hastoppart", "hastoppartinstance", "toppart"),
    ),
    RelationMappingRule(
        relation_type=RelationType.DPP_INSTANCE_TO_STATIC,
        subject_type=ScopedEntityType.DPP_INSTANCE,
        object_type=ScopedEntityType.DPP_STATIC,
        aliases=("dppstaticlink", "hasdppstatic", "dppstatic"),
    ),
    RelationMappingRule(
        relation_type=RelationType.PROCESS_STEP_TO_GHG_RECORD,
        subject_type=ScopedEntityType.PROCESS_STEP,
        object_type=ScopedEntityType.GHG_EMISSION_RECORD,
        aliases=("ghgemissionrecords", "logs", "records", "emissionsrecords"),
    ),
    RelationMappingRule(
        relation_type=RelationType.PROCESS_STEP_TO_PLACE,
        subject_type=ScopedEntityType.PROCESS_STEP,
        object_type=ScopedEntityType.PLACE,
        aliases=("processedat",),
    ),
    RelationMappingRule(
        relation_type=RelationType.GHG_RECORD_TO_ACTIVITY,
        subject_type=ScopedEntityType.GHG_EMISSION_RECORD,
        object_type=ScopedEntityType.ACTIVITY_DATA,
        aliases=("activity", "describesactivity", "activitydata"),
    ),
    RelationMappingRule(
        relation_type=RelationType.GHG_RECORD_TO_EMISSION_FACTOR,
        subject_type=ScopedEntityType.GHG_EMISSION_RECORD,
        object_type=ScopedEntityType.EMISSION_FACTOR,
        aliases=("emissionfactor", "emission_factor", "hasfactor", "factor"),
    ),
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def map_observations(
    raw_properties: Iterable[RawPropertyObservation],
    raw_relations: Iterable[RawRelationObservation],
) -> MappingOutput:
    """
    Map raw parser output to canonical fields, entities, and relations.

    This function performs only semantic label/predicate mapping and entity seeding.
    It does not normalize units, values, or enums beyond passing through originals.
    """
    output = MappingOutput()

    raw_properties = list(raw_properties)
    raw_relations = list(raw_relations)

    for item in raw_properties:
        field_result = map_raw_property(item)
        output.issues.extend(field_result.issues)
        if field_result.field is None or field_result.entity_type is None or field_result.entity_id is None:
            continue

        entity = _get_or_create_entity(
            entities=output.entities,
            entity_id=field_result.entity_id,
            entity_type=field_result.entity_type,
            source_entity_id=item.source_entity_id,
            source_entity_type=item.source_entity_type,
            source_path=item.source_path,
            source_node_types=item.source_node_types,
        )

        _merge_field_into_entity(entity=entity, field=field_result.field)

    for item in raw_relations:
        relation_result = map_raw_relation(item)
        output.issues.extend(relation_result.issues)
        if relation_result.relation is None:
            continue

        output.relations.append(relation_result.relation)

        relation_definition = get_relation_definition(relation_result.relation.relation_type)
        if relation_definition is None:
            continue

        _get_or_create_entity(
            entities=output.entities,
            entity_id=relation_result.relation.subject_entity_id,
            entity_type=relation_definition.subject_type,
            source_entity_id=item.subject_id,
            source_entity_type=item.subject_type,
            source_path=item.source_path,
            source_node_types=[],
        )
        _get_or_create_entity(
            entities=output.entities,
            entity_id=relation_result.relation.object_entity_id,
            entity_type=relation_definition.object_type,
            source_entity_id=item.object_id,
            source_entity_type=item.object_type,
            source_path=item.source_path,
            source_node_types=[],
        )

    return output


def build_result_from_mapped_output(mapped: MappingOutput) -> HarmonizationResult:
    """
    Convenience helper for local debugging.

    The dedicated service layer can later decide whether to use this directly.
    """
    warning_count = sum(1 for issue in mapped.issues if issue.severity == IssueSeverity.WARNING)
    error_count = sum(1 for issue in mapped.issues if issue.severity == IssueSeverity.ERROR)

    stats = HarmonizationStats(
        harmonized_entity_count=len(mapped.entities),
        harmonized_field_count=sum(len(entity.fields) for entity in mapped.entities.values()),
        harmonized_relation_count=len(mapped.relations),
        issue_count=len(mapped.issues),
        warning_count=warning_count,
        error_count=error_count,
    )

    return HarmonizationResult(
        entities=mapped.entities,
        relations=mapped.relations,
        issues=mapped.issues,
        stats=stats,
        success=error_count == 0,
    )


# ---------------------------------------------------------------------------
# Raw property mapping
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class FieldMappingResult:
    field: HarmonizedField | None
    entity_id: str | None
    entity_type: ScopedEntityType | None
    issues: list[HarmonizationIssue]


@dataclass(slots=True)
class RelationMappingResult:
    relation: HarmonizedRelation | None
    issues: list[HarmonizationIssue]


def map_raw_property(observation: RawPropertyObservation) -> FieldMappingResult:
    """Map one raw property observation to one canonical field if possible."""
    issues: list[HarmonizationIssue] = []

    entity_type = _infer_scoped_entity_type(
        preferred=observation.source_entity_type,
        fallbacks=observation.source_node_types,
    )

    if observation.source_entity_id is None:
        issues.append(
            HarmonizationIssue(
                severity=IssueSeverity.WARNING,
                issue_type=IssueType.STRUCTURE_WARNING,
                message="Property observation has no source entity ID and cannot be mapped.",
                source_path=observation.source_path,
                raw_label=observation.raw_label,
            )
        )
        return FieldMappingResult(field=None, entity_id=None, entity_type=entity_type, issues=issues)

    if entity_type is None:
        issues.append(
            HarmonizationIssue(
                severity=IssueSeverity.INFO,
                issue_type=IssueType.OUT_OF_SCOPE_ENTITY,
                message="Property source entity type is missing or outside current scope.",
                entity_id=observation.source_entity_id,
                source_path=observation.source_path,
                raw_label=observation.raw_label,
                details={
                    "source_entity_type": observation.source_entity_type,
                    "source_node_types": observation.source_node_types,
                },
            )
        )
        return FieldMappingResult(field=None, entity_id=observation.source_entity_id, entity_type=None, issues=issues)

    rule, confidence, matched_by = _match_field_rule(
        entity_type=entity_type,
        raw_label=observation.raw_label,
    )

    if rule is None:
        issues.append(
            HarmonizationIssue(
                severity=IssueSeverity.INFO,
                issue_type=IssueType.UNMAPPED_FIELD,
                message="No canonical field mapping found for raw property.",
                entity_id=observation.source_entity_id,
                entity_type=entity_type,
                source_path=observation.source_path,
                raw_label=observation.raw_label,
                details={
                    "raw_unit": observation.raw_unit,
                    "neighbor_labels": observation.neighbor_labels,
                },
            )
        )
        return FieldMappingResult(
            field=None,
            entity_id=observation.source_entity_id,
            entity_type=entity_type,
            issues=issues,
        )

    role = _role_for_canonical_name(rule.canonical_name)
    field = HarmonizedField(
        canonical_name=rule.canonical_name,
        role=role,
        normalized_value=observation.raw_value,
        normalized_unit=observation.raw_unit,
        original_label=observation.raw_label,
        original_value=observation.raw_value,
        original_unit=observation.raw_unit,
        confidence=confidence,
        matched_by=matched_by,
        provenance_paths=[observation.source_path],
        supporting_evidence=[f"entity_type={entity_type.value}", f"raw_label={observation.raw_label}"],
    )

    if confidence < 0.9:
        issues.append(
            HarmonizationIssue(
                severity=IssueSeverity.WARNING,
                issue_type=IssueType.LOW_CONFIDENCE_MAPPING,
                message="Field was mapped using a low-confidence alias match.",
                entity_id=observation.source_entity_id,
                entity_type=entity_type,
                field_name=rule.canonical_name,
                source_path=observation.source_path,
                raw_label=observation.raw_label,
                details={"confidence": confidence, "matched_by": matched_by},
            )
        )

    return FieldMappingResult(
        field=field,
        entity_id=observation.source_entity_id,
        entity_type=entity_type,
        issues=issues,
    )


# ---------------------------------------------------------------------------
# Raw relation mapping
# ---------------------------------------------------------------------------


def map_raw_relation(observation: RawRelationObservation) -> RelationMappingResult:
    """Map one raw graph relation observation to one canonical relation if possible."""
    issues: list[HarmonizationIssue] = []

    if observation.object_id is None:
        issues.append(
            HarmonizationIssue(
                severity=IssueSeverity.WARNING,
                issue_type=IssueType.STRUCTURE_WARNING,
                message="Relation observation has no object ID and cannot be mapped.",
                source_path=observation.source_path,
                raw_label=observation.predicate_label,
            )
        )
        return RelationMappingResult(relation=None, issues=issues)

    subject_type = _infer_scoped_entity_type(preferred=observation.subject_type, fallbacks=[])
    object_type = _infer_scoped_entity_type(preferred=observation.object_type, fallbacks=[])

    rule, confidence, matched_by = _match_relation_rule(
        subject_type=subject_type,
        object_type=object_type,
        predicate_label=observation.predicate_label,
    )

    if rule is None:
        issues.append(
            HarmonizationIssue(
                severity=IssueSeverity.INFO,
                issue_type=IssueType.RELATION_WARNING,
                message="No canonical relation mapping found for raw relation.",
                source_path=observation.source_path,
                raw_label=observation.predicate_label,
                details={
                    "subject_type": observation.subject_type,
                    "object_type": observation.object_type,
                    "object_inline": observation.object_inline,
                },
            )
        )
        return RelationMappingResult(relation=None, issues=issues)

    relation = HarmonizedRelation(
        relation_type=rule.relation_type,
        subject_entity_id=observation.subject_id,
        object_entity_id=observation.object_id,
        confidence=confidence,
        provenance_paths=[observation.source_path],
        notes=[matched_by],
    )

    if confidence < 0.9:
        issues.append(
            HarmonizationIssue(
                severity=IssueSeverity.WARNING,
                issue_type=IssueType.LOW_CONFIDENCE_MAPPING,
                message="Relation was mapped using a low-confidence alias match.",
                source_path=observation.source_path,
                raw_label=observation.predicate_label,
                details={"confidence": confidence, "matched_by": matched_by},
            )
        )

    return RelationMappingResult(relation=relation, issues=issues)


# ---------------------------------------------------------------------------
# Matching helpers
# ---------------------------------------------------------------------------


def _match_field_rule(
    entity_type: ScopedEntityType,
    raw_label: str,
) -> tuple[FieldMappingRule | None, float, str]:
    normalized_label = _normalize_label(raw_label)
    candidates = [rule for rule in FIELD_RULES if rule.entity_type == entity_type]

    for rule in candidates:
        if normalized_label in rule.aliases:
            confidence = 0.99 if normalized_label == rule.aliases[0] else 0.96
            return rule, confidence, "entity_type+alias_exact"

    best_rule: FieldMappingRule | None = None
    best_score = 0.0
    for rule in candidates:
        for alias in rule.aliases:
            score = SequenceMatcher(None, normalized_label, alias).ratio()
            if score > best_score:
                best_score = score
                best_rule = rule

    if best_rule is not None and best_score >= 0.84:
        return best_rule, round(best_score, 3), "entity_type+alias_fuzzy"

    return None, 0.0, "unmapped"



def _match_relation_rule(
    subject_type: ScopedEntityType | None,
    object_type: ScopedEntityType | None,
    predicate_label: str,
) -> tuple[RelationMappingRule | None, float, str]:
    normalized_label = _normalize_label(predicate_label)

    candidates = [
        rule
        for rule in RELATION_RULES
        if (subject_type is None or rule.subject_type == subject_type)
        and (object_type is None or rule.object_type == object_type)
    ]
    if not candidates:
        candidates = list(RELATION_RULES)

    for rule in candidates:
        if normalized_label in rule.aliases:
            confidence = 0.99 if normalized_label == rule.aliases[0] else 0.96
            matched_by = "typed_relation_alias_exact"
            if subject_type is None or object_type is None:
                matched_by = "partially_typed_relation_alias_exact"
                confidence -= 0.05
            return rule, confidence, matched_by

    best_rule: RelationMappingRule | None = None
    best_score = 0.0
    for rule in candidates:
        for alias in rule.aliases:
            score = SequenceMatcher(None, normalized_label, alias).ratio()
            if score > best_score:
                best_score = score
                best_rule = rule

    if best_rule is not None and best_score >= 0.84:
        if subject_type is None or object_type is None:
            best_score -= 0.05
        return best_rule, round(best_score, 3), "relation_alias_fuzzy"

    return None, 0.0, "unmapped"


# ---------------------------------------------------------------------------
# Entity helpers
# ---------------------------------------------------------------------------


def _get_or_create_entity(
    entities: dict[str, HarmonizedEntity],
    entity_id: str,
    entity_type: ScopedEntityType,
    source_entity_id: str | None,
    source_entity_type: str | None,
    source_path: str,
    source_node_types: list[str],
) -> HarmonizedEntity:
    entity = entities.get(entity_id)
    if entity is None:
        entity = HarmonizedEntity(
            entity_id=entity_id,
            entity_type=entity_type,
            source_ids=[source_entity_id] if source_entity_id else [],
            source_node_types=[source_entity_type] if source_entity_type else [],
            source_paths=[source_path],
        )
        entities[entity_id] = entity
    else:
        if source_entity_id and source_entity_id not in entity.source_ids:
            entity.source_ids.append(source_entity_id)
        if source_entity_type and source_entity_type not in entity.source_node_types:
            entity.source_node_types.append(source_entity_type)
        for node_type in source_node_types:
            if node_type not in entity.source_node_types:
                entity.source_node_types.append(node_type)
        if source_path not in entity.source_paths:
            entity.source_paths.append(source_path)

    return entity



def _merge_field_into_entity(entity: HarmonizedEntity, field: HarmonizedField) -> None:
    existing = entity.fields.get(field.canonical_name)
    if existing is None:
        entity.fields[field.canonical_name] = field
        return

    if field.confidence > existing.confidence:
        entity.fields[field.canonical_name] = field
        return

    for path in field.provenance_paths:
        if path not in existing.provenance_paths:
            existing.provenance_paths.append(path)
    for evidence in field.supporting_evidence:
        if evidence not in existing.supporting_evidence:
            existing.supporting_evidence.append(evidence)
    for note in field.notes:
        if note not in existing.notes:
            existing.notes.append(note)


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def _infer_scoped_entity_type(
    preferred: str | None,
    fallbacks: Iterable[str],
) -> ScopedEntityType | None:
    candidates = [preferred] if preferred else []
    candidates.extend(fallbacks)

    for candidate in candidates:
        if not candidate:
            continue
        stripped = _strip_prefix(candidate)
        if not is_in_scope_entity_type(stripped):
            continue
        return ScopedEntityType(stripped)

    return None



def _role_for_canonical_name(canonical_name: str) -> FieldRole:
    definition = get_field_definition(canonical_name)
    if definition is not None:
        return FieldRole(definition.role)

    if is_primary_field(canonical_name):
        return FieldRole.PRIMARY
    if is_context_field(canonical_name):
        return FieldRole.CONTEXT
    if is_derived_field(canonical_name):
        return FieldRole.DERIVED

    raise ValueError(f"Unknown canonical field role for: {canonical_name}")



def _normalize_label(value: str) -> str:
    return "".join(char.lower() for char in _strip_prefix(value) if char.isalnum())



def _strip_prefix(value: str) -> str:
    if ":" in value:
        return value.split(":", 1)[1]
    return value
