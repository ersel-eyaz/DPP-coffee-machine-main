"""
Emission Scope definition.

This scope focuses on activity data, emission factors, and calculated GHG
emission records. It supports label harmonization for numeric fields, unit
harmonization for activity/factor units, controlled vocabulary normalization,
and cross-entity consistency checks.

GHG scope and Scope 3 category are treated as controlled-vocabulary fields,
not as structural relations, because this follows the original prototype model.
"""

from __future__ import annotations

from dpp.data_quality.scopes.schemas import CanonicalField, CanonicalRelation, ScopeDefinition


EMISSION_SCOPE = ScopeDefinition(
    name="emission",
    title="Emission Calculation Consistency",
    description=(
        "Selected GHG fields used for harmonizing emission-related input and "
        "checking calculation, unit, scope, and category consistency."
    ),
    entities=(
        "ActivityData",
        "EmissionFactor",
        "GHGEmissionRecord",
        "GHGScope",
        "Scope3Category",
        "UnitCode",
        "ActivityType",
    ),
    fields=(
        # Numeric label harmonization targets
        CanonicalField(
            entity_type="ActivityData",
            field_name="quantity",
            role="label_harmonization",
            paired_unit_field="ActivityData.unit",
            description="Activity quantity used as input for emission calculation.",
        ),
        CanonicalField(
            entity_type="EmissionFactor",
            field_name="value",
            role="label_harmonization",
            paired_unit_field="EmissionFactor.unit",
            description="Emission factor numeric value.",
        ),
        CanonicalField(
            entity_type="GHGEmissionRecord",
            field_name="emissions_kg_co2e",
            role="label_harmonization",
            target_unit="kgCO2e",
            description="Calculated or reported emissions in kg CO2 equivalent.",
        ),

        # Unit normalization targets
        CanonicalField(
            entity_type="ActivityData",
            field_name="unit",
            role="unit_harmonization",
            description="Activity unit, e.g. km, kg, or kWh.",
        ),
        CanonicalField(
            entity_type="EmissionFactor",
            field_name="unit",
            role="unit_harmonization",
            description="Emission factor unit, e.g. kgCO2e/km.",
        ),

        # Controlled vocabulary targets
        CanonicalField(
            entity_type="ActivityData",
            field_name="activity_type",
            role="controlled_vocabulary",
            description="Canonical activity type such as distance_traveled.",
        ),
        CanonicalField(
            entity_type="GHGEmissionRecord",
            field_name="scope",
            role="controlled_vocabulary",
            description="GHG Protocol scope such as Scope 1, Scope 2, or Scope 3.",
        ),
        CanonicalField(
            entity_type="GHGEmissionRecord",
            field_name="scope3_category",
            role="controlled_vocabulary",
            description="Scope 3 category when the record belongs to Scope 3.",
        ),

        # Optional metadata/context fields, not active harmonization targets.
        CanonicalField(
            entity_type="GHGEmissionRecord",
            field_name="calculation_method",
            role="analysis_context",
            description="Optional metadata; not an active harmonization target.",
        ),
        CanonicalField(
            entity_type="GHGEmissionRecord",
            field_name="provenance",
            role="analysis_context",
            description="Optional source metadata; not an active harmonization target.",
        ),
    ),
    relations=(
        CanonicalRelation(
            source_entity_type="GHGEmissionRecord",
            relation_name="activity",
            target_entity_type="ActivityData",
            required=True,
            description="Preserves the link to the activity input used in the emission calculation.",
        ),
        CanonicalRelation(
            source_entity_type="GHGEmissionRecord",
            relation_name="emission_factor",
            target_entity_type="EmissionFactor",
            required=True,
            description="Preserves the link to the emission factor used in the emission calculation.",
        ),
    ),
)
