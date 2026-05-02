"""
Unit and value normalization helpers for the harmonization layer.

The module is intentionally conservative and rule-based. It supports exact unit
aliases first and a small fuzzy fallback for obvious spelling variants. It also
supports exact controlled-vocabulary alias normalization and a small fuzzy
fallback for obvious controlled-vocabulary spelling variants. It does not use
embeddings or semantic matching.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any


class NormalizationError(ValueError):
    """Raised when a value or unit cannot be normalized."""


AUTO_UNIT_FUZZY_THRESHOLD = 0.92
AMBIGUOUS_UNIT_FUZZY_THRESHOLD = 0.80

AUTO_ENUM_FUZZY_THRESHOLD = 0.95
AMBIGUOUS_ENUM_FUZZY_THRESHOLD = 0.85


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


@dataclass(frozen=True)
class EnumNormalizationCandidate:
    """A possible mapping from an input enum label to a canonical enum value."""

    original_value: str
    canonical_value: str
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


_CONTROLLED_VOCABULARY_ALIASES: dict[str, dict[str, str]] = {
    "ActivityData.activity_type": {
        # Canonical serialized enum values from the model.
        "electricity_consumption": "electricity_consumption",
        "distance_traveled": "distance_traveled",
        "material_purchase": "material_purchase",
        "water_usage": "water_usage",
        "heat_usage": "heat_usage",
        "waste_treatment": "waste_treatment",
        "fuel_consumption": "fuel_consumption",

        # Python enum member names are accepted as input aliases, but are not emitted.
        "ELECTRICITY_CONSUMPTION": "electricity_consumption",
        "DISTANCE_TRAVELED": "distance_traveled",
        "MATERIAL_PURCHASE": "material_purchase",
        "WATER_USAGE": "water_usage",
        "HEAT_USAGE": "heat_usage",
        "WASTE_TREATMENT": "waste_treatment",
        "FUEL_CONSUMPTION": "fuel_consumption",

        # Human-readable aliases.
        "electricity consumption": "electricity_consumption",
        "electricity use": "electricity_consumption",
        "power consumption": "electricity_consumption",
        "energy consumption": "electricity_consumption",
        "distance traveled": "distance_traveled",
        "distance travelled": "distance_traveled",
        "transport distance": "distance_traveled",
        "material purchase": "material_purchase",
        "purchased material": "material_purchase",
        "material purchased": "material_purchase",
        "water usage": "water_usage",
        "water consumption": "water_usage",
        "heat usage": "heat_usage",
        "heat consumption": "heat_usage",
        "waste treatment": "waste_treatment",
        "waste processing": "waste_treatment",
        "fuel consumption": "fuel_consumption",
        "fuel use": "fuel_consumption",
    },
    "GHGEmissionRecord.scope": {
        # Canonical serialized enum values from the model.
        "scope_1": "scope_1",
        "scope_2": "scope_2",
        "scope_3": "scope_3",

        # Python enum member names are accepted as input aliases, but are not emitted.
        "SCOPE_1": "scope_1",
        "SCOPE_2": "scope_2",
        "SCOPE_3": "scope_3",

        # Human-readable aliases.
        "scope 1": "scope_1",
        "scope i": "scope_1",
        "scope one": "scope_1",
        "direct emissions": "scope_1",
        "scope 2": "scope_2",
        "scope ii": "scope_2",
        "scope two": "scope_2",
        "purchased energy": "scope_2",
        "indirect energy emissions": "scope_2",
        "scope 3": "scope_3",
        "scope iii": "scope_3",
        "scope three": "scope_3",
        "value chain emissions": "scope_3",
        "other indirect emissions": "scope_3",
    },
    "GHGEmissionRecord.scope3_category": {
        # Canonical serialized enum values from the model.
        "purchased_goods_and_services": "purchased_goods_and_services",
        "capital_goods": "capital_goods",
        "fuel_and_energy_related_activities": "fuel_and_energy_related_activities",
        "upstream_transportation_and_distribution": "upstream_transportation_and_distribution",
        "waste_generated_in_operations": "waste_generated_in_operations",
        "business_travel": "business_travel",
        "employee_commuting": "employee_commuting",
        "upstream_leased_assets": "upstream_leased_assets",
        "downstream_transportation_and_distribution": "downstream_transportation_and_distribution",
        "processing_of_sold_products": "processing_of_sold_products",
        "use_of_sold_products": "use_of_sold_products",
        "end_of_life_treatment": "end_of_life_treatment",
        "downstream_leased_assets": "downstream_leased_assets",
        "franchises": "franchises",
        "investments": "investments",

        # Python enum member names are accepted as input aliases, but are not emitted.
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

        # Human-readable aliases.
        "purchased goods and services": "purchased_goods_and_services",
        "purchased goods": "purchased_goods_and_services",
        "purchased materials": "purchased_goods_and_services",
        "capital goods": "capital_goods",
        "fuel and energy related activities": "fuel_and_energy_related_activities",
        "fuel and energy activities": "fuel_and_energy_related_activities",
        "upstream transportation and distribution": "upstream_transportation_and_distribution",
        "upstream transport and distribution": "upstream_transportation_and_distribution",
        "upstream logistics": "upstream_transportation_and_distribution",
        "waste generated in operations": "waste_generated_in_operations",
        "operational waste": "waste_generated_in_operations",
        "business travel": "business_travel",
        "employee commuting": "employee_commuting",
        "upstream leased assets": "upstream_leased_assets",
        "downstream transportation and distribution": "downstream_transportation_and_distribution",
        "downstream transport and distribution": "downstream_transportation_and_distribution",
        "downstream logistics": "downstream_transportation_and_distribution",
        "processing of sold products": "processing_of_sold_products",
        "use of sold products": "use_of_sold_products",
        "product use phase": "use_of_sold_products",
        "end of life treatment": "end_of_life_treatment",
        "end-of-life treatment": "end_of_life_treatment",
        "eol treatment": "end_of_life_treatment",
        "downstream leased assets": "downstream_leased_assets",
        "franchises": "franchises",
        "investments": "investments",
    },
}

def _normalize_enum_key(value: str) -> str:
    """Normalize a controlled-vocabulary value for canonical and alias lookup."""
    normalized = value.strip().lower().replace("_", " ").replace("-", " ")
    return " ".join(normalized.split())


def _enum_lookup_table(canonical_path: str) -> dict[str, tuple[str, str]]:
    """Return normalized enum aliases mapped to canonical value and match type."""
    lookup: dict[str, tuple[str, str]] = {}
    for alias, canonical_value in _CONTROLLED_VOCABULARY_ALIASES.get(canonical_path, {}).items():
        match_type = "canonical" if alias == canonical_value else "alias"
        lookup[_normalize_enum_key(alias)] = (canonical_value, match_type)
        lookup[_normalize_enum_key(canonical_value)] = (canonical_value, "canonical")
    return lookup


def _similarity(left: str, right: str) -> float:
    """Return a normalized similarity score between two normalized labels."""
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def find_enum_value_candidates(
    canonical_path: str,
    value: Any,
    min_confidence: float = AMBIGUOUS_ENUM_FUZZY_THRESHOLD,
) -> list[EnumNormalizationCandidate]:
    """
    Find exact or fuzzy candidates for a controlled-vocabulary value.

    The fuzzy fallback is intentionally conservative and is meant for obvious
    spelling variants of canonical enum values or known aliases. Paraphrases
    should be handled by a later semantic matching layer instead.
    """

    if not isinstance(value, str):
        return []

    key = _normalize_enum_key(value)
    if not key:
        return []

    lookup = _enum_lookup_table(canonical_path)
    exact = lookup.get(key)
    if exact is not None:
        canonical_value, match_type = exact
        return [
            EnumNormalizationCandidate(
                original_value=value,
                canonical_value=canonical_value,
                confidence=1.0,
                match_type=match_type,
            )
        ]

    candidates_by_value: dict[str, EnumNormalizationCandidate] = {}
    for alias_key, (canonical_value, _) in lookup.items():
        score = _similarity(key, alias_key)
        if score < min_confidence:
            continue

        current = candidates_by_value.get(canonical_value)
        if current is None or score > current.confidence:
            candidates_by_value[canonical_value] = EnumNormalizationCandidate(
                original_value=value,
                canonical_value=canonical_value,
                confidence=score,
                match_type="fuzzy",
            )

    return sorted(candidates_by_value.values(), key=lambda item: item.confidence, reverse=True)


def resolve_enum_value(
    canonical_path: str,
    value: Any,
    auto_threshold: float = AUTO_ENUM_FUZZY_THRESHOLD,
) -> EnumNormalizationCandidate | None:
    """Resolve a controlled-vocabulary value by canonical match, alias, or conservative fuzzy fallback."""
    candidates = find_enum_value_candidates(canonical_path, value)
    if not candidates:
        return None

    top = candidates[0]
    if top.match_type in {"canonical", "alias"}:
        return top

    second_score = candidates[1].confidence if len(candidates) > 1 else 0.0
    if top.confidence >= auto_threshold and (top.confidence - second_score) >= 0.05:
        return top

    return None


def normalize_enum_value(canonical_path: str, value: Any) -> str:
    """Normalize a controlled-vocabulary value or raise a NormalizationError."""
    if not isinstance(value, str):
        raise NormalizationError(
            f"Controlled-vocabulary field {canonical_path!r} must contain a string value, "
            f"got {type(value).__name__}."
        )

    candidate = resolve_enum_value(canonical_path, value)
    if candidate is not None:
        return candidate.canonical_value

    candidates = find_enum_value_candidates(canonical_path, value)
    if candidates:
        candidate_text = ", ".join(
            f"{candidate.canonical_value} ({candidate.confidence:.2f})"
            for candidate in candidates[:3]
        )
        raise NormalizationError(
            f"Controlled-vocabulary value {value!r} for field {canonical_path!r} is ambiguous. "
            f"Possible candidates: {candidate_text}."
        )

    raise NormalizationError(
        f"Unsupported controlled-vocabulary value {value!r} for field {canonical_path!r}."
    )


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
