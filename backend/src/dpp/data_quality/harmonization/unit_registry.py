"""
Field-aware unit registry for the data-quality harmonization layer.

The legacy prototype has two different unit patterns:

1. Field-bound measurement units, encoded in field names such as weightGRM,
   heightCM, and operatingHRS.
2. Explicit emission UnitCode values, stored in ActivityData.unit and
   EmissionFactor.unit.

This registry keeps those vocabularies close to the unit conversion metadata so
the normalizer and JSON-LD output builder do not each maintain their own unit
tables.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FieldUnitBinding:
    """Unit contract for one measurable canonical field."""

    field_path: str
    target_unit: str
    accepted_source_units: frozenset[str]
    jsonld_quantity_name: str | None = None
    property_value_term: str | None = None
    property_value_name: str | None = None


# Alias keys are normalized by normalizers._normalize_unit_key before lookup.
UNIT_ALIASES: dict[str, str] = {
    # mass
    "g": "GRM",
    "gram": "GRM",
    "grams": "GRM",
    "grm": "GRM",
    "kg": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "mg": "mg",
    "milligram": "mg",
    "milligrams": "mg",

    # length and distance
    "mm": "mm",
    "millimeter": "mm",
    "millimeters": "mm",
    "millimetre": "mm",
    "millimetres": "mm",
    "cm": "CM",
    "centimeter": "CM",
    "centimeters": "CM",
    "centimetre": "CM",
    "centimetres": "CM",
    "m": "m",
    "meter": "m",
    "meters": "m",
    "metre": "m",
    "metres": "m",
    "km": "km",
    "kilometer": "km",
    "kilometers": "km",
    "kilometre": "km",
    "kilometres": "km",

    # time
    "h": "HRS",
    "hr": "HRS",
    "hrs": "HRS",
    "hour": "HRS",
    "hours": "HRS",
    "min": "min",
    "mins": "min",
    "minute": "min",
    "minutes": "min",

    # percentages and ratios
    "%": "percent",
    "percent": "percent",
    "percentage": "percent",
    "ratio": "ratio",
    "fraction": "ratio",

    # count-like values
    "count": "count",
    "counts": "count",
    "cycle": "count",
    "cycles": "count",
    "unit": "unit",
    "units": "unit",
    "piece": "unit",
    "pieces": "unit",

    # emission/activity units
    "kwh": "kWh",
    "kwhr": "kWh",
    "kilowatthour": "kWh",
    "kilowatthours": "kWh",
    "ltr": "ltr",
    "l": "ltr",
    "liter": "ltr",
    "liters": "ltr",
    "litre": "ltr",
    "litres": "ltr",
    "m3": "m3",
    "cubicmeter": "m3",
    "cubicmeters": "m3",
    "cubicmetre": "m3",
    "cubicmetres": "m3",
    "tonne": "t",
    "tonnes": "t",
    "metricton": "t",
    "metrictons": "t",
    "kgco2e": "kgCO2e",
    "kgco2eq": "kgCO2e",
    "kgco2equivalent": "kgCO2e",
    "kgco2e/kwh": "kgCO2e/kWh",
    "kgco2eq/kwh": "kgCO2e/kWh",
    "kgco2eperkwh": "kgCO2e/kWh",
    "kgco2eqperkwh": "kgCO2e/kWh",
    "kgco2equivalentperkilowatthour": "kgCO2e/kWh",
    "kgco2e/kg": "kgCO2e/kg",
    "kgco2eq/kg": "kgCO2e/kg",
    "kgco2eperkg": "kgCO2e/kg",
    "kgco2eqperkg": "kgCO2e/kg",
    "kgco2equivalentperkilogram": "kgCO2e/kg",
    "kgco2e/km": "kgCO2e/km",
    "kgco2eq/km": "kgCO2e/km",
    "kgco2eperkm": "kgCO2e/km",
    "kgco2eqperkm": "kgCO2e/km",
    "kgco2eperkilometer": "kgCO2e/km",
    "kgco2eperkilometre": "kgCO2e/km",
    "kgco2equivalentperkilometer": "kgCO2e/km",
    "kgco2equivalentperkilometre": "kgCO2e/km",
}


CANONICAL_OUTPUT_UNITS = frozenset(
    {
        "GRM",
        "CM",
        "km",
        "HRS",
        "percent",
        "ratio",
        "count",
        "kWh",
        "kg",
        "kgCO2e",
        "kgCO2e/kWh",
        "kgCO2e/kg",
        "kgCO2e/km",
        "ltr",
        "m3",
        "t",
        "unit",
    }
)


AMBIGUOUS_UNIT_KEYS = frozenset({"unit", "units", "u", "t"})


SOURCE_UNITS_BY_TARGET = {
    "GRM": frozenset({"mg", "GRM", "kg"}),
    "CM": frozenset({"mm", "CM", "m"}),
    "km": frozenset({"m", "km"}),
    "HRS": frozenset({"min", "HRS"}),
    "percent": frozenset({"percent", "ratio"}),
    "ratio": frozenset({"percent", "ratio"}),
    "count": frozenset({"count"}),
    "unit": frozenset({"unit"}),
    "kWh": frozenset({"kWh"}),
    "kg": frozenset({"kg"}),
    "kgCO2e": frozenset({"kgCO2e"}),
    "kgCO2e/kWh": frozenset({"kgCO2e/kWh"}),
    "kgCO2e/kg": frozenset({"kgCO2e/kg"}),
    "kgCO2e/km": frozenset({"kgCO2e/km"}),
    "ltr": frozenset({"ltr"}),
    "m3": frozenset({"m3"}),
    "t": frozenset({"t"}),
}


CONVERSION_FACTORS = {
    # mass to legacy grams
    ("kg", "GRM"): 1000.0,
    ("GRM", "GRM"): 1.0,
    ("mg", "GRM"): 0.001,

    # length to legacy centimeters
    ("mm", "CM"): 0.1,
    ("CM", "CM"): 1.0,
    ("m", "CM"): 100.0,

    # distance to kilometers
    ("m", "km"): 0.001,
    ("km", "km"): 1.0,

    # time to legacy hours
    ("min", "HRS"): 1.0 / 60.0,
    ("HRS", "HRS"): 1.0,

    # ratio / percent
    ("percent", "percent"): 1.0,
    ("ratio", "ratio"): 1.0,
    ("percent", "ratio"): 0.01,
    ("ratio", "percent"): 100.0,

    # counts and pieces
    ("count", "count"): 1.0,
    ("unit", "unit"): 1.0,

    # emission/activity units without scale conversion
    ("kWh", "kWh"): 1.0,
    ("kg", "kg"): 1.0,
    ("kgCO2e", "kgCO2e"): 1.0,
    ("kgCO2e/kWh", "kgCO2e/kWh"): 1.0,
    ("kgCO2e/kg", "kgCO2e/kg"): 1.0,
    ("kgCO2e/km", "kgCO2e/km"): 1.0,
}


FIELD_UNIT_BINDINGS: dict[str, FieldUnitBinding] = {
    "DPPStatic.weightGRM": FieldUnitBinding(
        field_path="DPPStatic.weightGRM",
        target_unit="GRM",
        accepted_source_units=SOURCE_UNITS_BY_TARGET["GRM"],
        jsonld_quantity_name="weight",
    ),
    "DPPStatic.heightCM": FieldUnitBinding(
        field_path="DPPStatic.heightCM",
        target_unit="CM",
        accepted_source_units=SOURCE_UNITS_BY_TARGET["CM"],
        jsonld_quantity_name="height",
    ),
    "DPPStatic.widthCM": FieldUnitBinding(
        field_path="DPPStatic.widthCM",
        target_unit="CM",
        accepted_source_units=SOURCE_UNITS_BY_TARGET["CM"],
        jsonld_quantity_name="width",
    ),
    "DPPStatic.depthCM": FieldUnitBinding(
        field_path="DPPStatic.depthCM",
        target_unit="CM",
        accepted_source_units=SOURCE_UNITS_BY_TARGET["CM"],
        jsonld_quantity_name="depth",
    ),
    "PartStatic.weightGRM": FieldUnitBinding(
        field_path="PartStatic.weightGRM",
        target_unit="GRM",
        accepted_source_units=SOURCE_UNITS_BY_TARGET["GRM"],
        jsonld_quantity_name="weight",
    ),
    "PartStatic.heightCM": FieldUnitBinding(
        field_path="PartStatic.heightCM",
        target_unit="CM",
        accepted_source_units=SOURCE_UNITS_BY_TARGET["CM"],
        jsonld_quantity_name="height",
    ),
    "PartStatic.widthCM": FieldUnitBinding(
        field_path="PartStatic.widthCM",
        target_unit="CM",
        accepted_source_units=SOURCE_UNITS_BY_TARGET["CM"],
        jsonld_quantity_name="width",
    ),
    "PartStatic.depthCM": FieldUnitBinding(
        field_path="PartStatic.depthCM",
        target_unit="CM",
        accepted_source_units=SOURCE_UNITS_BY_TARGET["CM"],
        jsonld_quantity_name="depth",
    ),
    "MaterialInstance.weightGRM": FieldUnitBinding(
        field_path="MaterialInstance.weightGRM",
        target_unit="GRM",
        accepted_source_units=SOURCE_UNITS_BY_TARGET["GRM"],
        jsonld_quantity_name="weight",
    ),
    "DPPInstance.operatingHRS": FieldUnitBinding(
        field_path="DPPInstance.operatingHRS",
        target_unit="HRS",
        accepted_source_units=SOURCE_UNITS_BY_TARGET["HRS"],
        property_value_term="schema:additionalProperty",
        property_value_name="operatingHRS",
    ),
}


EXPLICIT_UNIT_VALUES_BY_FIELD = {
    "ActivityData.unit": frozenset({"m", "km", "kg", "kWh", "ltr", "m3", "t", "unit"}),
    "EmissionFactor.unit": frozenset({"kgCO2e/kWh", "kgCO2e/kg", "kgCO2e/km"}),
}


def unit_binding_for_field(field_path: str) -> FieldUnitBinding | None:
    """Return the field-bound unit contract for one canonical field."""
    return FIELD_UNIT_BINDINGS.get(field_path)


def source_units_for_target(target_unit: str) -> frozenset[str]:
    """Return source units that can be converted safely into a target unit."""
    return SOURCE_UNITS_BY_TARGET.get(target_unit, frozenset({target_unit}))


def explicit_unit_values_for_field(field_path: str) -> frozenset[str] | None:
    """Return allowed legacy UnitCode values for an explicit unit field."""
    return EXPLICIT_UNIT_VALUES_BY_FIELD.get(field_path)
