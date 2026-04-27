"""
Unit and value normalization helpers for the harmonization layer.

This module is intentionally small and rule-based. It does not perform field
label mapping. It only normalizes values once a target canonical unit is known.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class NormalizationError(ValueError):
    """Raised when a value or unit cannot be normalized."""


@dataclass(frozen=True)
class NormalizedValue:
    """
    Result of a unit/value normalization step.

    Attributes:
        value: Numeric value after conversion.
        unit: Canonical unit after conversion.
    """

    value: float
    unit: str


def _to_float(value: Any) -> float:
    """Convert supported numeric inputs to float."""
    if isinstance(value, bool):
        raise NormalizationError("Boolean values cannot be normalized as numbers.")

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        stripped = value.strip().replace(",", ".")
        if not stripped:
            raise NormalizationError("Empty string cannot be normalized as a number.")

        try:
            return float(stripped)
        except ValueError as exc:
            raise NormalizationError(f"Cannot parse numeric value: {value!r}") from exc

    raise NormalizationError(f"Unsupported numeric value type: {type(value).__name__}")


def normalize_unit_label(unit: str | None) -> str | None:
    """
    Normalize common unit labels to compact canonical labels.

    The returned labels are internal data-quality labels. They are aligned with
    the target units used in scope definitions, not necessarily with display text.
    """

    if unit is None:
        return None

    normalized = unit.strip().lower()
    normalized = normalized.replace(" ", "")
    normalized = normalized.replace("_", "")
    normalized = normalized.replace("-", "")

    aliases = {
        # mass
        "g": "g",
        "gram": "g",
        "grams": "g",
        "grm": "g",
        "kg": "kg",
        "kilogram": "kg",
        "kilograms": "kg",
        "mg": "mg",
        "milligram": "mg",
        "milligrams": "mg",

        # length
        "mm": "mm",
        "millimeter": "mm",
        "millimeters": "mm",
        "millimetre": "mm",
        "millimetres": "mm",
        "cm": "cm",
        "centimeter": "cm",
        "centimeters": "cm",
        "centimetre": "cm",
        "centimetres": "cm",
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
        "h": "h",
        "hr": "h",
        "hrs": "h",
        "hour": "h",
        "hours": "h",
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
        "unit": "count",
        "units": "count",
        "piece": "count",
        "pieces": "count",

        # emission/activity units
        "kwh": "kWh",
        "ltr": "ltr",
        "liter": "ltr",
        "liters": "ltr",
        "litre": "ltr",
        "litres": "ltr",
        "m3": "m3",
        "t": "t",
        "tonne": "t",
        "tonnes": "t",
        "kgco2e": "kgCO2e",
        "kgco2eq": "kgCO2e",
        "kgco2equivalent": "kgCO2e",
        "kgco2e/kwh": "kgCO2e/kWh",
        "kgco2eperkwh": "kgCO2e/kWh",
        "kgco2equivalentperkilowatthour": "kgCO2e/kWh",
        "kgco2e/kg": "kgCO2e/kg",
        "kgco2eperkg": "kgCO2e/kg",
        "kgco2equivalentperkilogram": "kgCO2e/kg",
        "kgco2e/km": "kgCO2e/km",
        "kgco2eperkm": "kgCO2e/km",
        "kgco2eperkilometer": "kgCO2e/km",
        "kgco2eperkilometre": "kgCO2e/km",
        "kgco2equivalentperkilometer": "kgCO2e/km",
        "kgco2equivalentperkilometre": "kgCO2e/km",
    }

    return aliases.get(normalized, unit.strip())


def normalize_value_to_unit(value: Any, source_unit: str | None, target_unit: str) -> NormalizedValue:
    """
    Normalize a numeric value from source_unit to target_unit.

    Supported target units:
        - g
        - cm
        - km
        - h
        - percent
        - ratio
        - count
        - kWh
        - kg
        - kgCO2e
        - kgCO2e/kWh
        - kgCO2e/kg
        - kgCO2e/km
    """

    numeric = _to_float(value)
    normalized_source = normalize_unit_label(source_unit)
    normalized_target = normalize_unit_label(target_unit)

    if normalized_target is None:
        raise NormalizationError("Target unit must not be None.")

    if normalized_source is None:
        return NormalizedValue(value=numeric, unit=normalized_target)

    if normalized_source == normalized_target:
        return NormalizedValue(value=numeric, unit=normalized_target)

    conversion_factors: dict[tuple[str, str], float] = {
        # mass to gram
        ("kg", "g"): 1000.0,
        ("g", "g"): 1.0,
        ("mg", "g"): 0.001,

        # length to centimeter
        ("mm", "cm"): 0.1,
        ("cm", "cm"): 1.0,
        ("m", "cm"): 100.0,

        # distance to kilometer
        ("m", "km"): 0.001,
        ("km", "km"): 1.0,

        # time to hours
        ("min", "h"): 1.0 / 60.0,
        ("h", "h"): 1.0,

        # ratio / percent
        ("percent", "percent"): 1.0,
        ("ratio", "ratio"): 1.0,
        ("percent", "ratio"): 0.01,
        ("ratio", "percent"): 100.0,

        # counts
        ("count", "count"): 1.0,

        # emission/activity units without scale conversion
        ("kWh", "kWh"): 1.0,
        ("kg", "kg"): 1.0,
        ("kgCO2e", "kgCO2e"): 1.0,
        ("kgCO2e/kWh", "kgCO2e/kWh"): 1.0,
        ("kgCO2e/kg", "kgCO2e/kg"): 1.0,
        ("kgCO2e/km", "kgCO2e/km"): 1.0,
    }

    factor = conversion_factors.get((normalized_source, normalized_target))
    if factor is None:
        raise NormalizationError(
            f"Unsupported unit conversion: {normalized_source!r} -> {normalized_target!r}"
        )

    return NormalizedValue(value=numeric * factor, unit=normalized_target)


def normalize_without_unit(value: Any) -> float:
    """
    Normalize a numeric value without applying a unit conversion.

    This is useful for counters, enum-independent numeric values, and values
    whose unit has already been handled elsewhere.
    """

    return _to_float(value)
