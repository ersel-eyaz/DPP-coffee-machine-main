"""
Rule configuration for the first anomaly/plausibility layer.

The rules are deliberately transparent and conservative. They provide a
baseline architecture that can later be extended with statistical models or
semantic anomaly scoring without changing the reporting contract.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NumericRangeRule:
    """A model-near numeric plausibility range for one canonical field."""

    check_id: str
    field_path: str
    min_value: float | None = None
    max_value: float | None = None
    min_exclusive: bool = False
    severity: str = "warning"
    description: str = ""

    def expected_range(self) -> dict[str, float]:
        """Return a compact expected range dictionary for report output."""
        expected: dict[str, float] = {}
        if self.min_value is not None:
            expected["min_exclusive" if self.min_exclusive else "min"] = self.min_value
        if self.max_value is not None:
            expected["max"] = self.max_value
        return expected


PRODUCT_NUMERIC_RANGE_RULES: tuple[NumericRangeRule, ...] = (
    NumericRangeRule(
        "product_weight_range",
        "DPPStatic.weightGRM",
        1000.0,
        30000.0,
        description="Coffee-machine product mass in grams.",
    ),
    NumericRangeRule(
        "product_height_range",
        "DPPStatic.heightCM",
        10.0,
        100.0,
        description="Coffee-machine product height in centimetres.",
    ),
    NumericRangeRule(
        "product_width_range",
        "DPPStatic.widthCM",
        10.0,
        100.0,
        description="Coffee-machine product width in centimetres.",
    ),
    NumericRangeRule(
        "product_depth_range",
        "DPPStatic.depthCM",
        10.0,
        100.0,
        description="Coffee-machine product depth in centimetres.",
    ),
    NumericRangeRule(
        "part_weight_positive",
        "PartStatic.weightGRM",
        0.0,
        None,
        min_exclusive=True,
        severity="error",
        description="Part mass must be greater than zero.",
    ),
    NumericRangeRule(
        "part_height_positive",
        "PartStatic.heightCM",
        0.0,
        None,
        min_exclusive=True,
        severity="error",
        description="Part height must be greater than zero.",
    ),
    NumericRangeRule(
        "part_width_positive",
        "PartStatic.widthCM",
        0.0,
        None,
        min_exclusive=True,
        severity="error",
        description="Part width must be greater than zero.",
    ),
    NumericRangeRule(
        "part_depth_positive",
        "PartStatic.depthCM",
        0.0,
        None,
        min_exclusive=True,
        severity="error",
        description="Part depth must be greater than zero.",
    ),
    NumericRangeRule(
        "material_weight_positive",
        "MaterialInstance.weightGRM",
        0.0,
        None,
        severity="error",
        description="Material mass must not be negative.",
    ),
    NumericRangeRule(
        "recycled_percent_range",
        "MaterialInstance.percentRecycled",
        0.0,
        100.0,
        severity="error",
        description="Recycled content is a percentage.",
    ),
    NumericRangeRule(
        "purity_ratio_range",
        "MaterialInstance.purityLevel",
        0.0,
        1.0,
        severity="error",
        description="Purity is represented as a ratio.",
    ),
    NumericRangeRule(
        "operating_hours_positive",
        "DPPInstance.operatingHRS",
        0.0,
        None,
        severity="error",
        description="Operating hours must not be negative.",
    ),
    NumericRangeRule(
        "brewing_count_positive",
        "DPPInstance.brewingCount",
        0.0,
        None,
        severity="error",
        description="Brewing count must not be negative.",
    ),
    NumericRangeRule(
        "cleaning_count_positive",
        "DPPInstance.cleaningCount",
        0.0,
        None,
        severity="error",
        description="Cleaning count must not be negative.",
    ),
    NumericRangeRule(
        "chalk_count_positive",
        "DPPInstance.chalkCount",
        0.0,
        None,
        severity="error",
        description="Descaling count must not be negative.",
    ),
    NumericRangeRule(
        "grinding_count_positive",
        "DPPInstance.coffeeGrindingCount",
        0.0,
        None,
        severity="error",
        description="Grinding count must not be negative.",
    ),
)


EMISSION_NUMERIC_RANGE_RULES: tuple[NumericRangeRule, ...] = (
    NumericRangeRule(
        "activity_quantity_positive",
        "ActivityData.quantity",
        0.0,
        None,
        severity="error",
        description="Activity quantity must not be negative.",
    ),
    NumericRangeRule(
        "emission_factor_positive",
        "EmissionFactor.value",
        0.0,
        None,
        severity="error",
        description="Emission factor value must not be negative.",
    ),
    NumericRangeRule(
        "reported_emissions_positive",
        "GHGEmissionRecord.emissions_kg_co2e",
        0.0,
        None,
        severity="error",
        description="Reported emissions must not be negative.",
    ),
)


SERVICE_NUMERIC_RANGE_RULES: tuple[NumericRangeRule, ...] = (
    NumericRangeRule(
        "service_cost_positive",
        "RepairServiceStep.costEur",
        0.0,
        None,
        severity="error",
        description="Service cost must not be negative.",
    ),
    NumericRangeRule(
        "service_cost_positive",
        "ReplaceServiceStep.costEur",
        0.0,
        None,
        severity="error",
        description="Service cost must not be negative.",
    ),
    NumericRangeRule(
        "service_cost_positive",
        "CleaningServiceStep.costEur",
        0.0,
        None,
        severity="error",
        description="Service cost must not be negative.",
    ),
    NumericRangeRule(
        "service_cost_positive",
        "RefurbishmentServiceStep.costEur",
        0.0,
        None,
        severity="error",
        description="Service cost must not be negative.",
    ),
    NumericRangeRule(
        "service_cost_positive",
        "RemanufacturingServiceStep.costEur",
        0.0,
        None,
        severity="error",
        description="Service cost must not be negative.",
    ),
    NumericRangeRule(
        "service_cost_positive",
        "SecondaryValueStep.costEur",
        0.0,
        None,
        severity="error",
        description="Service cost must not be negative.",
    ),
    NumericRangeRule(
        "service_cost_high_review",
        "RepairServiceStep.costEur",
        None,
        300.0,
        severity="info",
        description="High service cost worth review in the prototype context.",
    ),
    NumericRangeRule(
        "service_cost_high_review",
        "ReplaceServiceStep.costEur",
        None,
        300.0,
        severity="info",
        description="High service cost worth review in the prototype context.",
    ),
    NumericRangeRule(
        "service_cost_high_review",
        "CleaningServiceStep.costEur",
        None,
        300.0,
        severity="info",
        description="High service cost worth review in the prototype context.",
    ),
    NumericRangeRule(
        "service_cost_high_review",
        "RefurbishmentServiceStep.costEur",
        None,
        300.0,
        severity="info",
        description="High service cost worth review in the prototype context.",
    ),
    NumericRangeRule(
        "service_cost_high_review",
        "RemanufacturingServiceStep.costEur",
        None,
        300.0,
        severity="info",
        description="High service cost worth review in the prototype context.",
    ),
    NumericRangeRule(
        "service_cost_high_review",
        "SecondaryValueStep.costEur",
        None,
        300.0,
        severity="info",
        description="High service cost worth review in the prototype context.",
    ),
)
