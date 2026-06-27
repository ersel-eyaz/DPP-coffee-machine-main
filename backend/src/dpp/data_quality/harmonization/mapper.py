"""
Rule-based field-label mapper for the harmonization layer.

The mapper resolves dirty input labels to canonical field paths within a selected
entity context. It does not normalize values or units; that is handled by
normalizers.py and services.py.

Entity types are assumed to be reliable at this stage. Field-label
harmonization is therefore restricted to the declared entity type whenever an
entity type is available.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from dpp.data_quality.scopes import SUPPORTED_SCOPES
from dpp.data_quality.scopes.schemas import CanonicalField, ScopeDefinition


class MappingError(ValueError):
    """Raised when a field label cannot be mapped safely."""


AUTO_FUZZY_THRESHOLD = 0.92
AMBIGUOUS_FUZZY_THRESHOLD = 0.80


@dataclass(frozen=True)
class FieldMappingCandidate:
    """
    A possible mapping from a dirty input label to a canonical field.

    Attributes:
        original_label: Field label from the dirty input.
        canonical_path: Canonical target path, e.g. 'DPPStatic.weightGRM'.
        entity_type: Canonical entity type for the mapped field.
        field_name: Canonical field name for the mapped field.
        confidence: Rule-based confidence score.
    """

    original_label: str
    canonical_path: str
    entity_type: str
    field_name: str
    confidence: float = 1.0


def _normalize_label(label: str) -> str:
    """
    Normalize a field label for rule-based lookup.

    This intentionally keeps the logic simple and deterministic:
    - lower-case
    - remove common separators
    - remove namespace prefixes such as 'dpp:'
    """

    cleaned = label.strip()

    if ":" in cleaned:
        cleaned = cleaned.split(":", maxsplit=1)[1]

    for prefix in ("@",):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]

    return (
        cleaned.lower()
        .replace("_", "")
        .replace("-", "")
        .replace(" ", "")
        .replace(".", "")
    )


# ---------------------------------------------------------------------------
# Entity-aware field-label aliases
# ---------------------------------------------------------------------------

_ENTITY_LABEL_MAPPINGS: dict[tuple[str, str], dict[str, str]] = {
    # Product scope: product-level static fields.
    ("product", "DPPStatic"): {
        "name": "DPPStatic.name",
        "productname": "DPPStatic.name",
        "dppname": "DPPStatic.name",
        "category": "DPPStatic.productClass",
        "productclass": "DPPStatic.productClass",
        "producttype": "DPPStatic.productClass",
        "class": "DPPStatic.productClass",
        "weight": "DPPStatic.weightGRM",
        "height": "DPPStatic.heightCM",
        "width": "DPPStatic.widthCM",
        "depth": "DPPStatic.depthCM",
        "productweight": "DPPStatic.weightGRM",
        "productmass": "DPPStatic.weightGRM",
        "totalproductweight": "DPPStatic.weightGRM",
        "totalweight": "DPPStatic.weightGRM",
        "deviceweight": "DPPStatic.weightGRM",
        "applianceweight": "DPPStatic.weightGRM",
        "productheight": "DPPStatic.heightCM",
        "deviceheight": "DPPStatic.heightCM",
        "applianceheight": "DPPStatic.heightCM",
        "productwidth": "DPPStatic.widthCM",
        "devicewidth": "DPPStatic.widthCM",
        "appliancewidth": "DPPStatic.widthCM",
        "productdepth": "DPPStatic.depthCM",
        "devicedepth": "DPPStatic.depthCM",
        "appliancedepth": "DPPStatic.depthCM",
    },
    # Product scope: part-level static fields.
    ("product", "PartStatic"): {
        "weight": "PartStatic.weightGRM",
        "height": "PartStatic.heightCM",
        "width": "PartStatic.widthCM",
        "depth": "PartStatic.depthCM",
        "partweight": "PartStatic.weightGRM",
        "partmass": "PartStatic.weightGRM",
        "componentweight": "PartStatic.weightGRM",
        "componentmass": "PartStatic.weightGRM",
        "partheight": "PartStatic.heightCM",
        "componentheight": "PartStatic.heightCM",
        "partwidth": "PartStatic.widthCM",
        "componentwidth": "PartStatic.widthCM",
        "partdepth": "PartStatic.depthCM",
        "componentdepth": "PartStatic.depthCM",
    },
    # Product scope: part-instance flags.
    ("product", "PartInstance"): {
        "ismodular": "PartInstance.isModular",
        "modular": "PartInstance.isModular",
        "modularpart": "PartInstance.isModular",
        "hasfailstate": "PartInstance.hasFailstate",
        "failstate": "PartInstance.hasFailstate",
        "failurestate": "PartInstance.hasFailstate",
        "hasfailurestate": "PartInstance.hasFailstate",
    },
    # Product scope: material instance fields.
    ("product", "MaterialInstance"): {
        "weight": "MaterialInstance.weightGRM",
        "materialweight": "MaterialInstance.weightGRM",
        "materialmass": "MaterialInstance.weightGRM",
        "rawmaterialweight": "MaterialInstance.weightGRM",
        "rawmaterialmass": "MaterialInstance.weightGRM",
        "recycledcontent": "MaterialInstance.percentRecycled",
        "recycledshare": "MaterialInstance.percentRecycled",
        "percentrecycled": "MaterialInstance.percentRecycled",
        "recyclingpercentage": "MaterialInstance.percentRecycled",
        "recycledpercentage": "MaterialInstance.percentRecycled",
        "purity": "MaterialInstance.purityLevel",
        "materialpurity": "MaterialInstance.purityLevel",
        "puritylevel": "MaterialInstance.purityLevel",
    },
    # Product scope: product-instance usage counters.
    ("product", "DPPInstance"): {
        "runtime": "DPPInstance.operatingHRS",
        "operatinghours": "DPPInstance.operatingHRS",
        "usagehours": "DPPInstance.operatingHRS",
        "operatinghrs": "DPPInstance.operatingHRS",
        "operationhours": "DPPInstance.operatingHRS",
        "brewcycles": "DPPInstance.brewingCount",
        "brewingcycles": "DPPInstance.brewingCount",
        "cupsmade": "DPPInstance.brewingCount",
        "brewingcount": "DPPInstance.brewingCount",
        "coffeeproduced": "DPPInstance.brewingCount",
        "cleaningcycles": "DPPInstance.cleaningCount",
        "cleaningcount": "DPPInstance.cleaningCount",
        "cleanings": "DPPInstance.cleaningCount",
        "descalingcycles": "DPPInstance.chalkCount",
        "descalingcount": "DPPInstance.chalkCount",
        "chalkcount": "DPPInstance.chalkCount",
        "decalcificationcycles": "DPPInstance.chalkCount",
        "grindercycles": "DPPInstance.coffeeGrindingCount",
        "grindingcycles": "DPPInstance.coffeeGrindingCount",
        "grindingcount": "DPPInstance.coffeeGrindingCount",
        "coffeegrindingcount": "DPPInstance.coffeeGrindingCount",
    },
    # Service scope: free-text fields shared by secondary value steps.
    ("service", "SecondaryValueStep"): {
        "observedsymptoms": "SecondaryValueStep.observedSymptoms",
        "symptoms": "SecondaryValueStep.observedSymptoms",
        "reportedissues": "SecondaryValueStep.observedSymptoms",
        "diagnose": "SecondaryValueStep.diagnose",
        "diagnosis": "SecondaryValueStep.diagnose",
        "servicediagnosis": "SecondaryValueStep.diagnose",
    },
    ("service", "RepairServiceStep"): {
        "observedsymptoms": "RepairServiceStep.observedSymptoms",
        "symptoms": "RepairServiceStep.observedSymptoms",
        "reportedissues": "RepairServiceStep.observedSymptoms",
        "diagnose": "RepairServiceStep.diagnose",
        "diagnosis": "RepairServiceStep.diagnose",
        "servicediagnosis": "RepairServiceStep.diagnose",
    },
    ("service", "ReplaceServiceStep"): {
        "observedsymptoms": "ReplaceServiceStep.observedSymptoms",
        "symptoms": "ReplaceServiceStep.observedSymptoms",
        "reportedissues": "ReplaceServiceStep.observedSymptoms",
        "diagnose": "ReplaceServiceStep.diagnose",
        "diagnosis": "ReplaceServiceStep.diagnose",
        "servicediagnosis": "ReplaceServiceStep.diagnose",
    },
    ("service", "CleaningServiceStep"): {
        "observedsymptoms": "CleaningServiceStep.observedSymptoms",
        "symptoms": "CleaningServiceStep.observedSymptoms",
        "reportedissues": "CleaningServiceStep.observedSymptoms",
        "diagnose": "CleaningServiceStep.diagnose",
        "diagnosis": "CleaningServiceStep.diagnose",
        "servicediagnosis": "CleaningServiceStep.diagnose",
    },
    ("service", "RefurbishmentServiceStep"): {
        "observedsymptoms": "RefurbishmentServiceStep.observedSymptoms",
        "symptoms": "RefurbishmentServiceStep.observedSymptoms",
        "reportedissues": "RefurbishmentServiceStep.observedSymptoms",
        "diagnose": "RefurbishmentServiceStep.diagnose",
        "diagnosis": "RefurbishmentServiceStep.diagnose",
        "servicediagnosis": "RefurbishmentServiceStep.diagnose",
    },
    ("service", "RemanufacturingServiceStep"): {
        "observedsymptoms": "RemanufacturingServiceStep.observedSymptoms",
        "symptoms": "RemanufacturingServiceStep.observedSymptoms",
        "reportedissues": "RemanufacturingServiceStep.observedSymptoms",
        "diagnose": "RemanufacturingServiceStep.diagnose",
        "diagnosis": "RemanufacturingServiceStep.diagnose",
        "servicediagnosis": "RemanufacturingServiceStep.diagnose",
    },

    # Emission scope: activity data fields.
    ("emission", "ActivityData"): {
        "activitytype": "ActivityData.activity_type",
        "typeofactivity": "ActivityData.activity_type",
        "measuredamount": "ActivityData.quantity",
        "activityquantity": "ActivityData.quantity",
        "quantity": "ActivityData.quantity",
        "amount": "ActivityData.quantity",
        "consumptionamount": "ActivityData.quantity",
        "unit": "ActivityData.unit",
        "activityunit": "ActivityData.unit",
        "activitydataunit": "ActivityData.unit",
        "quantityunit": "ActivityData.unit",
        "measuredamountunit": "ActivityData.unit",
        "hasunit": "ActivityData.unit",
    },
    # Emission scope: emission factor fields.
    ("emission", "EmissionFactor"): {
        "co2factor": "EmissionFactor.value",
        "carbonfactor": "EmissionFactor.value",
        "emissionfactor": "EmissionFactor.value",
        "factorvalue": "EmissionFactor.value",
        "unit": "EmissionFactor.unit",
        "factorunit": "EmissionFactor.unit",
        "emissionfactorunit": "EmissionFactor.unit",
        "co2factorunit": "EmissionFactor.unit",
        "carbonfactorunit": "EmissionFactor.unit",
        "hasunit": "EmissionFactor.unit",
    },
    # Emission scope: GHG emission record fields.
    ("emission", "GHGEmissionRecord"): {
        "totalcarbon": "GHGEmissionRecord.emissions_kg_co2e",
        "totalemissions": "GHGEmissionRecord.emissions_kg_co2e",
        "emissions": "GHGEmissionRecord.emissions_kg_co2e",
        "emissionskgco2e": "GHGEmissionRecord.emissions_kg_co2e",
        "carbonfootprint": "GHGEmissionRecord.emissions_kg_co2e",
        "scope": "GHGEmissionRecord.scope",
        "ghgscope": "GHGEmissionRecord.scope",
        "emissionscope": "GHGEmissionRecord.scope",
        "scope3category": "GHGEmissionRecord.scope3_category",
        "calculationmethod": "GHGEmissionRecord.calculation_method",
        "method": "GHGEmissionRecord.calculation_method",
        "provenance": "GHGEmissionRecord.provenance",
        "source": "GHGEmissionRecord.provenance",
        "dataprovenance": "GHGEmissionRecord.provenance",
    },
}


def _canonical_fields_by_path(scope: ScopeDefinition) -> dict[str, CanonicalField]:
    """Return scope fields keyed by canonical path."""
    return {field.path: field for field in scope.fields}


def _build_candidate(label: str, canonical_path: str, canonical_fields: dict[str, CanonicalField], confidence: float) -> FieldMappingCandidate:
    """Build a mapping candidate and fail loudly if the target path is invalid."""

    canonical_field = canonical_fields.get(canonical_path)

    if canonical_field is None:
        raise MappingError(f"Mapping for label {label!r} points to unregistered field {canonical_path!r}.")

    return FieldMappingCandidate(
        original_label=label,
        canonical_path=canonical_field.path,
        entity_type=canonical_field.entity_type,
        field_name=canonical_field.field_name,
        confidence=confidence,
    )


def _similarity(left: str, right: str) -> float:
    """Return a normalized similarity score between two normalized labels."""

    if not left or not right:
        return 0.0

    return SequenceMatcher(None, left, right).ratio()


def _fields_for_entity(
    canonical_fields: dict[str, CanonicalField],
    entity_type: str | None,
) -> list[tuple[str, CanonicalField]]:
    """Return canonical fields that are safe to consider for the current entity context."""

    if entity_type is not None:
        return [
            (path, field)
            for path, field in canonical_fields.items()
            if field.entity_type == entity_type
        ]

    # Without reliable entity context, do not broaden fuzzy search. Exact canonical
    # matches below may still be accepted only if they are unique across the scope.
    return list(canonical_fields.items())


def _find_exact_canonical_field_match(
    normalized_label: str,
    canonical_fields: dict[str, CanonicalField],
    entity_type: str | None,
) -> str | None:
    """
    Resolve labels that already match canonical field names or full paths.

    The resolver is ambiguity-safe:
    - If entity_type is known, only fields of that entity are considered.
    - If entity_type is unknown, a match is accepted only when unique in the scope.
    """

    matches: set[str] = set()

    for canonical_path, canonical_field in _fields_for_entity(canonical_fields, entity_type):
        variants = {
            _normalize_label(canonical_field.field_name),
            _normalize_label(canonical_field.path),
        }

        if normalized_label in variants:
            matches.add(canonical_path)

    if len(matches) == 1:
        return next(iter(matches))

    return None


def _candidate_alias_mappings(scope_name: str, entity_type: str | None) -> dict[str, str]:
    """Return entity-specific aliases for the current trusted entity context."""

    if entity_type is None:
        return {}

    return dict(_ENTITY_LABEL_MAPPINGS.get((scope_name, entity_type), {}))


def map_field_label(label: str, scope_name: str, entity_type: str | None = None) -> FieldMappingCandidate | None:
    """
    Map a dirty field label to a canonical field path using exact aliases only.

    Entity types are assumed to be reliable. If entity_type is available, exact
    alias and canonical-name matching are restricted to that entity. This avoids
    broad scope-level mappings for generic labels such as 'unit', 'value', or
    'description'.

    Args:
        label: Original input label.
        scope_name: Selected data-quality scope.
        entity_type: Optional parsed entity type.

    Returns:
        None if the label is unknown for the selected entity context.
    """

    scope = SUPPORTED_SCOPES.get(scope_name)
    if scope is None:
        raise MappingError(f"Unsupported scope: {scope_name!r}")

    normalized_label = _normalize_label(label)
    canonical_fields = _canonical_fields_by_path(scope)

    entity_mapping = _candidate_alias_mappings(scope_name, entity_type)
    canonical_path = entity_mapping.get(normalized_label)

    if canonical_path is None:
        canonical_path = _find_exact_canonical_field_match(
            normalized_label=normalized_label,
            canonical_fields=canonical_fields,
            entity_type=entity_type,
        )

    if canonical_path is None:
        return None

    return _build_candidate(
        label=label,
        canonical_path=canonical_path,
        canonical_fields=canonical_fields,
        confidence=1.0,
    )


def find_field_label_candidates(
    label: str,
    scope_name: str,
    entity_type: str | None = None,
    min_confidence: float = AMBIGUOUS_FUZZY_THRESHOLD,
) -> list[FieldMappingCandidate]:
    """
    Find conservative fuzzy fallback candidates for a dirty field label.

    This function is intended to be called only after map_field_label() returned
    None. It keeps the search entity-aware: when an entity type is known, only
    canonical fields and aliases belonging to that entity are considered. This
    avoids broad cross-entity matches such as mapping a generic "weight" label to
    a material, part, or product field without enough context.
    """

    scope = SUPPORTED_SCOPES.get(scope_name)
    if scope is None:
        raise MappingError(f"Unsupported scope: {scope_name!r}")

    normalized_label = _normalize_label(label)
    canonical_fields = _canonical_fields_by_path(scope)
    candidate_scores: dict[str, float] = {}

    for alias, canonical_path in _candidate_alias_mappings(scope_name, entity_type).items():
        canonical_field = canonical_fields.get(canonical_path)
        if canonical_field is None:
            continue

        if entity_type is not None and canonical_field.entity_type != entity_type:
            continue

        score = _similarity(normalized_label, alias)
        if score >= min_confidence:
            candidate_scores[canonical_path] = max(candidate_scores.get(canonical_path, 0.0), score)

    # Fuzzy comparison against canonical field names is restricted to known entity
    # context. Without entity context, exact canonical matching above may be used,
    # but fuzzy matching would be too broad for generic names.
    if entity_type is not None:
        for canonical_path, canonical_field in _fields_for_entity(canonical_fields, entity_type):
            canonical_label_variants = (
                _normalize_label(canonical_field.field_name),
                _normalize_label(canonical_field.path),
            )

            for canonical_label in canonical_label_variants:
                score = _similarity(normalized_label, canonical_label)
                if score >= min_confidence:
                    candidate_scores[canonical_path] = max(candidate_scores.get(canonical_path, 0.0), score)

    candidates = [
        _build_candidate(
            label=label,
            canonical_path=canonical_path,
            canonical_fields=canonical_fields,
            confidence=score,
        )
        for canonical_path, score in candidate_scores.items()
    ]

    return sorted(candidates, key=lambda item: item.confidence, reverse=True)


def get_label_mappings(scope_name: str) -> dict[str, str]:
    """
    Return the raw entity-aware mapping table for a scope.

    The returned dict is flattened with keys of the form 'EntityType:alias' so
    callers can inspect mappings without losing entity context.
    """

    if scope_name not in SUPPORTED_SCOPES:
        raise MappingError(f"Unsupported scope: {scope_name!r}")

    flattened: dict[str, str] = {}
    for (mapping_scope, entity_type), aliases in _ENTITY_LABEL_MAPPINGS.items():
        if mapping_scope != scope_name:
            continue
        for alias, canonical_path in aliases.items():
            flattened[f"{entity_type}:{alias}"] = canonical_path

    return flattened
