"""
Unit and value normalization helpers for the harmonization layer.

The module is intentionally conservative and rule-based. It supports exact unit
aliases first and a small fuzzy fallback for obvious spelling variants. It does
not use embeddings or semantic matching.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any


class NormalizationError(ValueError):
    """Raised when a value or unit cannot be normalized."""


AUTO_UNIT_FUZZY_THRESHOLD = 0.92
AMBIGUOUS_UNIT_FUZZY_THRESHOLD = 0.80


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


@dataclass(frozen=True)
class UnitNormalizationCandidate:
    """
    A possible mapping from an input unit label to a canonical unit.

    Attributes:
        original_unit: Unit label from the dirty input.
        canonical_unit: Canonical unit used internally by the data-quality layer.
        confidence: Rule-based confidence score.
        match_type: Either 'exact' or 'fuzzy'.
    """

    original_unit: str
    canonical_unit: str
    confidence: float
    match_type: str


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


def _normalize_unit_key(unit: str) -> str:
    """Normalize a unit label for alias lookup and fuzzy comparison."""
    normalized = unit.strip().lower()
    normalized = normalized.replace(" ", "")
    normalized = normalized.replace("_", "")
    normalized = normalized.replace("-", "")
    normalized = normalized.replace("·", "")
    normalized = normalized.replace("*", "")
    normalized = normalized.replace("²", "2")
    normalized = normalized.replace("³", "3")
    return normalized


_UNIT_ALIASES: dict[str, str] = {
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

    # length and distance
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
    "piece": "count",
    "pieces": "count",

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

# These short labels are too generic to auto-resolve without additional context.
_AMBIGUOUS_UNIT_KEYS = {
    "unit",
    "units",
    "u",
    "t",
}


def _similarity(left: str, right: str) -> float:
    """Return a normalized similarity score between two normalized unit labels."""
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _known_canonical_units() -> set[str]:
    """Return all canonical units known by the normalizer."""
    return set(_UNIT_ALIASES.values())


def find_unit_label_candidates(
    unit: str | None,
    allowed_units: set[str] | None = None,
    min_confidence: float = AMBIGUOUS_UNIT_FUZZY_THRESHOLD,
) -> list[UnitNormalizationCandidate]:
    """
    Find exact or fuzzy candidates for a dirty unit label.

    The function is meant as a controlled fallback for typos such as 'kilogrm'
    or 'centimter'. It does not use embeddings and does not auto-resolve generic
    labels such as 'unit'.
    """

    if unit is None:
        return []

    key = _normalize_unit_key(unit)
    if not key:
        return []

    allowed = allowed_units or _known_canonical_units()

    exact = _UNIT_ALIASES.get(key)
    if exact is not None and exact in allowed and key not in _AMBIGUOUS_UNIT_KEYS:
        return [
            UnitNormalizationCandidate(
                original_unit=unit,
                canonical_unit=exact,
                confidence=1.0,
                match_type="exact",
            )
        ]

    candidates_by_unit: dict[str, UnitNormalizationCandidate] = {}
    for alias, canonical_unit in _UNIT_ALIASES.items():
        if canonical_unit not in allowed:
            continue
        if alias in _AMBIGUOUS_UNIT_KEYS:
            continue

        score = _similarity(key, alias)
        if score < min_confidence:
            continue

        current = candidates_by_unit.get(canonical_unit)
        if current is None or score > current.confidence:
            candidates_by_unit[canonical_unit] = UnitNormalizationCandidate(
                original_unit=unit,
                canonical_unit=canonical_unit,
                confidence=score,
                match_type="fuzzy",
            )

    return sorted(candidates_by_unit.values(), key=lambda item: item.confidence, reverse=True)


def resolve_unit_label(
    unit: str | None,
    allowed_units: set[str] | None = None,
    auto_threshold: float = AUTO_UNIT_FUZZY_THRESHOLD,
) -> UnitNormalizationCandidate | None:
    """
    Resolve a unit label by exact alias first and conservative fuzzy fallback second.
    """

    candidates = find_unit_label_candidates(unit, allowed_units=allowed_units)
    if not candidates:
        return None

    top = candidates[0]
    if top.match_type == "exact":
        return top

    second_score = candidates[1].confidence if len(candidates) > 1 else 0.0
    if top.confidence >= auto_threshold and (top.confidence - second_score) >= 0.05:
        return top

    return None


def normalize_unit_label(unit: str | None) -> str | None:
    """
    Normalize common unit labels to compact canonical labels.

    Unknown or ambiguous unit labels are returned unchanged to preserve the
    original information. Strict conversion functions will still reject unsupported
    conversions later.
    """

    if unit is None:
        return None

    candidate = resolve_unit_label(unit)
    if candidate is None:
        return unit.strip()

    return candidate.canonical_unit


def _allowed_sources_for_target(target_unit: str) -> set[str]:
    """Return unit families that can be converted safely into a target unit."""
    return {
        "g": {"mg", "g", "kg"},
        "cm": {"mm", "cm", "m"},
        "km": {"m", "km"},
        "h": {"min", "h"},
        "percent": {"percent", "ratio"},
        "ratio": {"percent", "ratio"},
        "count": {"count"},
        "kWh": {"kWh"},
        "kg": {"kg"},
        "kgCO2e": {"kgCO2e"},
        "kgCO2e/kWh": {"kgCO2e/kWh"},
        "kgCO2e/kg": {"kgCO2e/kg"},
        "kgCO2e/km": {"kgCO2e/km"},
        "ltr": {"ltr"},
        "m3": {"m3"},
        "t": {"t"},
    }.get(target_unit, {target_unit})


def normalize_value_to_unit(value: Any, source_unit: str | None, target_unit: str) -> NormalizedValue:
    """
    Normalize a numeric value from source_unit to target_unit.

    Supported target units include g, cm, km, h, percent, ratio, count, kWh, kg,
    kgCO2e, kgCO2e/kWh, kgCO2e/kg, and kgCO2e/km.
    """

    numeric = _to_float(value)
    normalized_target_candidate = resolve_unit_label(target_unit)

    if normalized_target_candidate is None:
        raise NormalizationError(f"Unsupported target unit: {target_unit!r}")

    normalized_target = normalized_target_candidate.canonical_unit

    if source_unit is None:
        return NormalizedValue(value=numeric, unit=normalized_target)

    source_candidate = resolve_unit_label(
        source_unit,
        allowed_units=_allowed_sources_for_target(normalized_target),
    )
    if source_candidate is None:
        raise NormalizationError(
            f"Unsupported or ambiguous source unit {source_unit!r} for target unit {normalized_target!r}"
        )

    normalized_source = source_candidate.canonical_unit

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
