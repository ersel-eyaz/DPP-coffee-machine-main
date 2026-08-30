"""
Controlled-vocabulary definitions for data-quality scopes.

This module keeps the scoped enum vocabulary data separate from normalization
algorithms. Canonical values are the serialized values accepted by the model;
Python member aliases support model-code style inputs; semantic profiles provide
compact embedding support text for optional semantic fallback.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EnumSemanticProfile:
    """Embedding support text for one canonical controlled-vocabulary value."""

    canonical_value: str
    description: str


CONTROLLED_VOCABULARY_VALUES: dict[str, tuple[str, ...]] = {
    "ActivityData.activity_type": (
        "electricity_consumption",
        "distance_traveled",
        "material_purchase",
        "water_usage",
        "heat_usage",
        "waste_treatment",
        "fuel_consumption",
    ),
    "GHGEmissionRecord.scope": (
        "scope_1",
        "scope_2",
        "scope_3",
    ),
    "GHGEmissionRecord.scope3_category": (
        "purchased_goods_and_services",
        "capital_goods",
        "fuel_and_energy_related_activities",
        "upstream_transportation_and_distribution",
        "waste_generated_in_operations",
        "business_travel",
        "employee_commuting",
        "upstream_leased_assets",
        "downstream_transportation_and_distribution",
        "processing_of_sold_products",
        "use_of_sold_products",
        "end_of_life_treatment",
        "downstream_leased_assets",
        "franchises",
        "investments",
    ),
}


CONTROLLED_VOCABULARY_PYTHON_MEMBER_TO_CANONICAL_VALUE: dict[str, dict[str, str]] = {
    "ActivityData.activity_type": {
        "ELECTRICITY_CONSUMPTION": "electricity_consumption",
        "DISTANCE_TRAVELED": "distance_traveled",
        "MATERIAL_PURCHASE": "material_purchase",
        "WATER_USAGE": "water_usage",
        "HEAT_USAGE": "heat_usage",
        "WASTE_TREATMENT": "waste_treatment",
        "FUEL_CONSUMPTION": "fuel_consumption",
    },
    "GHGEmissionRecord.scope": {
        "SCOPE_1": "scope_1",
        "SCOPE_2": "scope_2",
        "SCOPE_3": "scope_3",
    },
    "GHGEmissionRecord.scope3_category": {
        "PURCHASED_GOODS_AND_SERVICES": "purchased_goods_and_services",
        "CAPITAL_GOODS": "capital_goods",
        "FUEL_AND_ENERGY_RELATED_ACTIVITIES": "fuel_and_energy_related_activities",
        "UPSTREAM_TRANSPORTATION_AND_DISTRIBUTION": "upstream_transportation_and_distribution",
        "WASTE_GENERATED_IN_OPERATIONS": "waste_generated_in_operations",
        "BUSINESS_TRAVEL": "business_travel",
        "EMPLOYEE_COMMUTING": "employee_commuting",
        "UPSTREAM_LEASED_ASSETS": "upstream_leased_assets",
        "DOWNSTREAM_TRANSPORTATION_AND_DISTRIBUTION": "downstream_transportation_and_distribution",
        "PROCESSING_OF_SOLD_PRODUCTS": "processing_of_sold_products",
        "USE_OF_SOLD_PRODUCTS": "use_of_sold_products",
        "END_OF_LIFE_TREATMENT": "end_of_life_treatment",
        "DOWNSTREAM_LEASED_ASSETS": "downstream_leased_assets",
        "FRANCHISES": "franchises",
        "INVESTMENTS": "investments",
    },
}


# Scope 3 category descriptions are derived from GHG Protocol Corporate Value
# Chain (Scope 3) Accounting and Reporting Standard, chapter 5, especially
# table 5.4 ("Description and boundaries of scope 3 categories"). The text is
# intentionally compact because it is used as embedding input, not as a full
# documentation source.
CONTROLLED_VOCABULARY_SEMANTIC_PROFILES: dict[str, dict[str, EnumSemanticProfile]] = {
    "ActivityData.activity_type": {
        "electricity_consumption": EnumSemanticProfile(
            canonical_value="electricity_consumption",
            description="electricity consumption; kilowatt-hours of electricity consumed; electrical energy use as activity data",
        ),
        "distance_traveled": EnumSemanticProfile(
            canonical_value="distance_traveled",
            description="distance traveled; kilometers of transport distance; movement by road rail sea or air as activity data",
        ),
        "material_purchase": EnumSemanticProfile(
            canonical_value="material_purchase",
            description="material purchase; kilograms of material consumed or acquired; purchased material amount as activity data",
        ),
        "water_usage": EnumSemanticProfile(
            canonical_value="water_usage",
            description="water usage; water consumption; cubic meters or liters of water used as activity data",
        ),
        "heat_usage": EnumSemanticProfile(
            canonical_value="heat_usage",
            description="heat usage; purchased or consumed heat energy; heating or thermal energy use as activity data",
        ),
        "waste_treatment": EnumSemanticProfile(
            canonical_value="waste_treatment",
            description="waste treatment; kilograms of waste generated; disposal treatment recycling incineration or wastewater treatment as activity data",
        ),
        "fuel_consumption": EnumSemanticProfile(
            canonical_value="fuel_consumption",
            description="fuel consumption; liters or kilograms of fuel consumed; fuel use by vehicles machines or processes as activity data",
        ),
    },
    "GHGEmissionRecord.scope": {
        "scope_1": EnumSemanticProfile(
            canonical_value="scope_1",
            description="direct greenhouse gas emissions from operations owned or controlled by the reporting company such as company facilities and vehicles",
        ),
        "scope_2": EnumSemanticProfile(
            canonical_value="scope_2",
            description="indirect greenhouse gas emissions from purchased or acquired electricity steam heating or cooling consumed by the reporting company",
        ),
        "scope_3": EnumSemanticProfile(
            canonical_value="scope_3",
            description="all other indirect greenhouse gas emissions in the reporting company's upstream and downstream value chain",
        ),
    },
    "GHGEmissionRecord.scope3_category": {
        "purchased_goods_and_services": EnumSemanticProfile(
            canonical_value="purchased_goods_and_services",
            description="purchased goods and services; extraction production and transportation of goods and services purchased or acquired in the reporting year; upstream cradle-to-gate emissions",
        ),
        "capital_goods": EnumSemanticProfile(
            canonical_value="capital_goods",
            description="capital goods; extraction production and transportation of capital goods purchased or acquired in the reporting year; equipment machinery buildings facilities and vehicles",
        ),
        "fuel_and_energy_related_activities": EnumSemanticProfile(
            canonical_value="fuel_and_energy_related_activities",
            description="fuel and energy related activities not included in scope 1 or scope 2; upstream emissions of purchased fuels and purchased electricity; transmission and distribution losses",
        ),
        "upstream_transportation_and_distribution": EnumSemanticProfile(
            canonical_value="upstream_transportation_and_distribution",
            description="upstream transportation and distribution; transportation and distribution of purchased products between tier 1 suppliers and own operations; purchased inbound outbound and internal third-party logistics",
        ),
        "waste_generated_in_operations": EnumSemanticProfile(
            canonical_value="waste_generated_in_operations",
            description="waste generated in operations; third-party disposal and treatment of waste from owned or controlled operations; solid waste wastewater landfill recycling incineration composting",
        ),
        "business_travel": EnumSemanticProfile(
            canonical_value="business_travel",
            description="business travel; transportation of employees for business-related activities in third-party vehicles such as aircraft trains buses rental cars or passenger cars",
        ),
        "employee_commuting": EnumSemanticProfile(
            canonical_value="employee_commuting",
            description="employee commuting; transportation of employees between homes and worksites; automobile bus rail air travel and optional teleworking",
        ),
        "upstream_leased_assets": EnumSemanticProfile(
            canonical_value="upstream_leased_assets",
            description="upstream leased assets; operation of assets leased by the reporting company as lessee not included in scope 1 or scope 2",
        ),
        "downstream_transportation_and_distribution": EnumSemanticProfile(
            canonical_value="downstream_transportation_and_distribution",
            description="downstream transportation and distribution; transportation distribution retail and storage of sold products between the reporting company's operations and the end consumer when not paid for by the reporting company",
        ),
        "processing_of_sold_products": EnumSemanticProfile(
            canonical_value="processing_of_sold_products",
            description="processing of sold products; processing of sold intermediate products by downstream companies after sale before use by the end consumer",
        ),
        "use_of_sold_products": EnumSemanticProfile(
            canonical_value="use_of_sold_products",
            description="use of sold products; end use of goods and services sold in the reporting year; direct use-phase emissions over expected lifetime from products consuming energy fuels feedstocks or emitting greenhouse gases",
        ),
        "end_of_life_treatment": EnumSemanticProfile(
            canonical_value="end_of_life_treatment",
            description="end-of-life treatment of sold products; waste disposal and treatment of sold products at the end of their life such as landfill incineration recycling or wastewater treatment",
        ),
        "downstream_leased_assets": EnumSemanticProfile(
            canonical_value="downstream_leased_assets",
            description="downstream leased assets; operation of assets owned by the reporting company as lessor and leased to other entities not included in scope 1 or scope 2",
        ),
        "franchises": EnumSemanticProfile(
            canonical_value="franchises",
            description="franchises; operation of franchises in the reporting year not included in scope 1 or scope 2; emissions of franchisees reported by franchisor",
        ),
        "investments": EnumSemanticProfile(
            canonical_value="investments",
            description="investments; operation of investments including equity debt investments and project finance in the reporting year not included in scope 1 or scope 2",
        ),
    },
}
