"""
Rule-based field-label mapper for the harmonization layer.

The mapper resolves dirty input labels to canonical field paths within a selected
data-quality scope. It does not normalize values or units; that is handled by
normalizers.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from dpp.data_quality.scopes import SUPPORTED_SCOPES
from dpp.data_quality.scopes.schemas import CanonicalField, ScopeDefinition


class MappingError(ValueError):
    """Raised when a field label cannot be mapped safely."""


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
# Product Scope mappings
# ---------------------------------------------------------------------------

_PRODUCT_LABEL_MAPPINGS: dict[str, str] = {
    # DPPStatic.weightGRM
    "productweight": "DPPStatic.weightGRM",
    "productmass": "DPPStatic.weightGRM",
    "totalproductweight": "DPPStatic.weightGRM",
    "totalweight": "DPPStatic.weightGRM",
    "deviceweight": "DPPStatic.weightGRM",
    "applianceweight": "DPPStatic.weightGRM",

    # DPPStatic.heightCM
    "productheight": "DPPStatic.heightCM",
    "deviceheight": "DPPStatic.heightCM",
    "applianceheight": "DPPStatic.heightCM",

    # DPPStatic.widthCM
    "productwidth": "DPPStatic.widthCM",
    "devicewidth": "DPPStatic.widthCM",
    "appliancewidth": "DPPStatic.widthCM",

    # DPPStatic.depthCM
    "productdepth": "DPPStatic.depthCM",
    "devicedepth": "DPPStatic.depthCM",
    "appliancedepth": "DPPStatic.depthCM",

    # PartStatic.weightGRM
    "partweight": "PartStatic.weightGRM",
    "partmass": "PartStatic.weightGRM",
    "componentweight": "PartStatic.weightGRM",
    "componentmass": "PartStatic.weightGRM",

    # PartStatic.heightCM
    "partheight": "PartStatic.heightCM",
    "componentheight": "PartStatic.heightCM",

    # PartStatic.widthCM
    "partwidth": "PartStatic.widthCM",
    "componentwidth": "PartStatic.widthCM",

    # PartStatic.depthCM
    "partdepth": "PartStatic.depthCM",
    "componentdepth": "PartStatic.depthCM",

    # MaterialInstance.weightGRM
    "materialweight": "MaterialInstance.weightGRM",
    "materialmass": "MaterialInstance.weightGRM",
    "rawmaterialweight": "MaterialInstance.weightGRM",
    "rawmaterialmass": "MaterialInstance.weightGRM",

    # MaterialInstance.percentRecycled
    "recycledcontent": "MaterialInstance.percentRecycled",
    "recycledshare": "MaterialInstance.percentRecycled",
    "percentrecycled": "MaterialInstance.percentRecycled",
    "recyclingpercentage": "MaterialInstance.percentRecycled",
    "recycledpercentage": "MaterialInstance.percentRecycled",

    # MaterialInstance.purityLevel
    "purity": "MaterialInstance.purityLevel",
    "materialpurity": "MaterialInstance.purityLevel",
    "puritylevel": "MaterialInstance.purityLevel",

    # DPPInstance.operatingHRS
    "runtime": "DPPInstance.operatingHRS",
    "operatinghours": "DPPInstance.operatingHRS",
    "usagehours": "DPPInstance.operatingHRS",
    "operatinghrs": "DPPInstance.operatingHRS",
    "operationhours": "DPPInstance.operatingHRS",

    # DPPInstance.brewingCount
    "brewcycles": "DPPInstance.brewingCount",
    "brewingcycles": "DPPInstance.brewingCount",
    "cupsmade": "DPPInstance.brewingCount",
    "brewingcount": "DPPInstance.brewingCount",
    "coffeeproduced": "DPPInstance.brewingCount",

    # DPPInstance.cleaningCount
    "cleaningcycles": "DPPInstance.cleaningCount",
    "cleaningcount": "DPPInstance.cleaningCount",
    "cleanings": "DPPInstance.cleaningCount",

    # DPPInstance.chalkCount
    "descalingcycles": "DPPInstance.chalkCount",
    "descalingcount": "DPPInstance.chalkCount",
    "chalkcount": "DPPInstance.chalkCount",
    "decalcificationcycles": "DPPInstance.chalkCount",

    # DPPInstance.coffeeGrindingCount
    "grindercycles": "DPPInstance.coffeeGrindingCount",
    "grindingcycles": "DPPInstance.coffeeGrindingCount",
    "grindingcount": "DPPInstance.coffeeGrindingCount",
    "coffeegrindingcount": "DPPInstance.coffeeGrindingCount",
}


# ---------------------------------------------------------------------------
# Emission Scope mappings
# ---------------------------------------------------------------------------

_EMISSION_LABEL_MAPPINGS: dict[str, str] = {
    # ActivityData.quantity
    "measuredamount": "ActivityData.quantity",
    "activityquantity": "ActivityData.quantity",
    "quantity": "ActivityData.quantity",
    "amount": "ActivityData.quantity",
    "consumptionamount": "ActivityData.quantity",

    # EmissionFactor.value
    "co2factor": "EmissionFactor.value",
    "carbonfactor": "EmissionFactor.value",
    "emissionfactor": "EmissionFactor.value",
    "factorvalue": "EmissionFactor.value",

    # GHGEmissionRecord.emissions_kg_co2e
    "totalcarbon": "GHGEmissionRecord.emissions_kg_co2e",
    "totalemissions": "GHGEmissionRecord.emissions_kg_co2e",
    "emissions": "GHGEmissionRecord.emissions_kg_co2e",
    "emissionskgco2e": "GHGEmissionRecord.emissions_kg_co2e",
    "carbonfootprint": "GHGEmissionRecord.emissions_kg_co2e",
}


_SCOPE_MAPPINGS: dict[str, dict[str, str]] = {
    "product": _PRODUCT_LABEL_MAPPINGS,
    "emission": _EMISSION_LABEL_MAPPINGS,
}


def _canonical_fields_by_path(scope: ScopeDefinition) -> dict[str, CanonicalField]:
    """Return scope fields keyed by canonical path."""
    return {field.path: field for field in scope.fields}


def map_field_label(label: str, scope_name: str) -> FieldMappingCandidate | None:
    """
    Map a dirty field label to a canonical field path.

    Returns None if the label is unknown for the selected scope.
    """

    scope = SUPPORTED_SCOPES.get(scope_name)
    if scope is None:
        raise MappingError(f"Unsupported scope: {scope_name!r}")

    normalized_label = _normalize_label(label)
    scope_mapping = _SCOPE_MAPPINGS.get(scope_name, {})
    canonical_path = scope_mapping.get(normalized_label)

    if canonical_path is None:
        return None

    canonical_fields = _canonical_fields_by_path(scope)
    canonical_field = canonical_fields.get(canonical_path)

    if canonical_field is None:
        raise MappingError(
            f"Mapping for label {label!r} points to field {canonical_path!r}, "
            f"but this field is not registered in scope {scope_name!r}."
        )

    return FieldMappingCandidate(
        original_label=label,
        canonical_path=canonical_field.path,
        entity_type=canonical_field.entity_type,
        field_name=canonical_field.field_name,
        confidence=1.0,
    )


def get_label_mappings(scope_name: str) -> dict[str, str]:
    """
    Return the raw mapping table for a scope.

    The returned dict is a copy so callers cannot mutate module-level mappings.
    """

    if scope_name not in SUPPORTED_SCOPES:
        raise MappingError(f"Unsupported scope: {scope_name!r}")

    return dict(_SCOPE_MAPPINGS.get(scope_name, {}))
