# src/dpp/models/ghg.py
"""
GHG (Greenhouse Gas) emissions domain models.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Scopes & categories
# ---------------------------------------------------------------------------


class GHGScope(str, Enum):
    """GHG Protocol scopes."""

    SCOPE_1 = "Scope 1"
    SCOPE_2 = "Scope 2"
    SCOPE_3 = "Scope 3"


class Scope3Category(str, Enum):
    """Standard Scope 3 categories."""

    PURCHASED_GOODS_AND_SERVICES = "Purchased goods and services"
    CAPITAL_GOODS = "Capital goods"
    FUEL_AND_ENERGY_RELATED_ACTIVITIES = "Fuel- and energy-related activities not included in Scope 1 or 2"
    UPSTREAM_TRANSPORTATION_AND_DISTRIBUTION = "Upstream transportation and distribution"
    WASTE_GENERATED_IN_OPERATIONS = "Waste generated in operations"
    BUSINESS_TRAVEL = "Business travel"
    EMPLOYEE_COMMUTING = "Employee commuting"
    UPSTREAM_LEASED_ASSETS = "Upstream leased assets"
    DOWNSTREAM_TRANSPORTATION_AND_DISTRIBUTION = "Downstream transportation and distribution"
    PROCESSING_OF_SOLD_PRODUCTS = "Processing of sold products"
    USE_OF_SOLD_PRODUCTS = "Use of sold products"
    END_OF_LIFE_TREATMENT = "End-of-life treatment of sold products"
    DOWNSTREAM_LEASED_ASSETS = "Downstream leased assets"
    FRANCHISES = "Franchises"
    INVESTMENTS = "Investments"


# ---------------------------------------------------------------------------
# Activity types & units
# ---------------------------------------------------------------------------


class ActivityType(str, Enum):
    """Prototype-level activity types that typically drive emissions."""

    ELECTRICITY_CONSUMPTION = "electricity_consumption"
    DISTANCE_TRAVELED = "distance_traveled"
    MATERIAL_PURCHASE = "material_purchase"
    WATER_USAGE = "water_usage"
    HEAT_USAGE = "heat_usage"
    WASTE_TREATMENT = "waste_treatment"
    FUEL_CONSUMPTION = "fuel_consumption"


class UnitCode(str, Enum):
    """Unit set for activities and emission factors."""

    KWH = "kWh"
    KM = "km"
    KG = "kg"
    LTR = "ltr"
    M3 = "m3"
    TONNE = "t"
    PIECE = "unit"
    KG_CO2E_PER_KWH = "kgCO2e/kWh"
    KG_CO2E_PER_KG = "kgCO2e/kg"
    KG_CO2E_PER_KM = "kgCO2e/km"


_UNIT_COMPATIBILITY: Dict[UnitCode, UnitCode] = {
    UnitCode.KWH: UnitCode.KG_CO2E_PER_KWH,
    UnitCode.KG: UnitCode.KG_CO2E_PER_KG,
    UnitCode.KM: UnitCode.KG_CO2E_PER_KM,
}


def units_compatible(activity_unit: UnitCode, factor_unit: UnitCode) -> bool:
    """
    Return True if the pair (activity_unit, factor_unit) is expected match.
    """
    expected = _UNIT_COMPATIBILITY.get(activity_unit)
    return True if expected is None else expected == factor_unit


# ---------------------------------------------------------------------------
# Aggregation containers
# ---------------------------------------------------------------------------


class GHGCategoryBreakdown(BaseModel):
    """Per-scope aggregate: total + per-category breakdown."""

    total: float
    by_category: Dict[str, float]


class GHGFootprintAggregated(BaseModel):
    """
    Envelope for aggregated footprints.
    """

    dpp_instance_id: str
    aggregated: Dict[str, GHGCategoryBreakdown]


# ---------------------------------------------------------------------------
# Core data models
# ---------------------------------------------------------------------------


class EmissionFactor(BaseModel):
    """
    Emission factor such as 'kgCO2e/kWh' or 'kgCO2e/km'.
    """

    description: str
    value: float
    unit: UnitCode
    technology: Optional[str] = None

    @field_validator("value")
    @classmethod
    def _non_negative_factor(cls, val: float) -> float:
        if val < 0:
            raise ValueError("Emission factor must be non-negative")
        return val


class ActivityData(BaseModel):
    """
    Activity that causes emissions (e.g., 500 kWh consumed, 100 km traveled).
    """

    activity_type: ActivityType
    quantity: float
    unit: UnitCode

    @field_validator("quantity")
    @classmethod
    def _non_negative_quantity(cls, val: float) -> float:
        if val < 0:
            raise ValueError("Activity quantity must be non-negative")
        return val


class GHGEmissionRecord(BaseModel):
    """
    A calculated emission record.
    """

    scope: GHGScope
    scope3_category: Optional[Scope3Category] = None
    activity: ActivityData
    emission_factor: EmissionFactor
    emissions_kg_co2e: float
    calculation_method: str
    provenance: Optional[str] = None
    excluded_from_aggregation: bool = Field(
        default=False,
        description="Use to avoid double counting when recursive aggregation happens.",
    )

    @field_validator("emissions_kg_co2e")
    @classmethod
    def _non_negative_emissions(cls, val: float) -> float:
        if val < 0:
            raise ValueError("Emissions must be non-negative (kg CO2e)")
        return val

    @classmethod
    def from_activity(
        cls,
        *,
        scope: GHGScope,
        activity: ActivityData,
        emission_factor: EmissionFactor,
        scope3_category: Optional[Scope3Category] = None,
        provenance: Optional[str] = None,
        enforce_units: bool = False,
    ) -> "GHGEmissionRecord":
        """
        Create a record by multiplying `activity.quantity * emission_factor.value`.
        """
        if enforce_units and not units_compatible(activity.unit, emission_factor.unit):
            raise ValueError(f"Incompatible units: activity={activity.unit}, factor={emission_factor.unit}")
        emissions = float(activity.quantity) * float(emission_factor.value)
        return cls(
            scope=scope,
            scope3_category=scope3_category,
            activity=activity,
            emission_factor=emission_factor,
            emissions_kg_co2e=emissions,
            calculation_method="activity.quantity * emission_factor.value",
            provenance=provenance,
        )


__all__ = [
    "GHGScope",
    "Scope3Category",
    "ActivityType",
    "UnitCode",
    "EmissionFactor",
    "ActivityData",
    "GHGEmissionRecord",
    "GHGCategoryBreakdown",
    "GHGFootprintAggregated",
    "units_compatible",
]
