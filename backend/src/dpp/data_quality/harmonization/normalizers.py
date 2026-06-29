"""
Unit, numeric value, and controlled-vocabulary normalization helpers.

Unit metadata lives in harmonization.unit_registry. This module applies that
registry conservatively: exact unit aliases first, then a small fuzzy fallback
for obvious spelling variants, with field-specific source-unit restrictions
enforced by the service layer. Field-bound product units normalize to the
legacy-aligned target codes such as GRM, CM, and HRS; source-only units such as
mg, mm, m, and min are accepted only when a mapped field allows conversion.

Controlled-vocabulary definitions live in scopes.controlled_vocabularies:
canonical serialized values, Python enum member aliases, and semantic profile
texts are scope metadata rather than normalization logic. Human-readable dirty
input aliases live in harmonization.enum_value_aliases and are generated from
the documented LLM notebook workflow.

This module combines those sources at runtime. It accepts canonical values
directly, applies generated and model-code aliases, then uses a conservative
fuzzy fallback and an optional embedding-based semantic fallback for unresolved
values. The semantic fallback is lazy and optional: sentence-transformers is
imported only when a semantic lookup is actually needed. Exact, alias, fuzzy,
and unit behavior therefore remain available without ML dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
from math import sqrt
from typing import Any

from dpp.data_quality.harmonization.enum_value_aliases import GENERATED_ENUM_VALUE_ALIASES
from dpp.data_quality.scopes.controlled_vocabularies import (
    CONTROLLED_VOCABULARY_PYTHON_MEMBER_ALIASES,
    CONTROLLED_VOCABULARY_SEMANTIC_PROFILES,
    CONTROLLED_VOCABULARY_VALUES,
)
from dpp.data_quality.harmonization.unit_registry import (
    AMBIGUOUS_UNIT_KEYS,
    CANONICAL_OUTPUT_UNITS,
    CONVERSION_FACTORS,
    UNIT_ALIASES,
    source_units_for_target,
)


class NormalizationError(ValueError):
    """Raised when a value or unit cannot be normalized."""


AUTO_UNIT_FUZZY_THRESHOLD = 0.92
AMBIGUOUS_UNIT_FUZZY_THRESHOLD = 0.80

AUTO_ENUM_FUZZY_THRESHOLD = 0.95
AMBIGUOUS_ENUM_FUZZY_THRESHOLD = 0.85

AUTO_ENUM_SEMANTIC_THRESHOLD = 0.55
AMBIGUOUS_ENUM_SEMANTIC_THRESHOLD = 0.42
MIN_ENUM_SEMANTIC_MARGIN = 0.04
DEFAULT_ENUM_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


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


def _controlled_vocabulary_lookup_entries(canonical_path: str) -> dict[str, tuple[str, str]]:
    """Return raw lookup entries for one controlled-vocabulary field.

    Canonical serialized values are accepted as canonical input. Python enum
    member names and generated dirty-input variants are accepted as aliases.
    """
    entries: dict[str, tuple[str, str]] = {}

    for canonical_value in CONTROLLED_VOCABULARY_VALUES.get(canonical_path, ()):
        entries[canonical_value] = (canonical_value, "canonical")

    for alias, canonical_value in CONTROLLED_VOCABULARY_PYTHON_MEMBER_ALIASES.get(canonical_path, {}).items():
        entries[alias] = (canonical_value, "alias")

    for alias, canonical_value in GENERATED_ENUM_VALUE_ALIASES.get(canonical_path, {}).items():
        entries[alias] = (canonical_value, "alias")

    return entries


def _normalize_enum_key(value: str) -> str:
    """Normalize a controlled-vocabulary value for canonical and alias lookup."""
    normalized = value.strip().lower().replace("_", " ").replace("-", " ")
    return " ".join(normalized.split())


def _enum_lookup_table(canonical_path: str) -> dict[str, tuple[str, str]]:
    """Return normalized enum aliases mapped to canonical value and match type."""
    lookup: dict[str, tuple[str, str]] = {}
    for alias, (canonical_value, match_type) in _controlled_vocabulary_lookup_entries(canonical_path).items():
        lookup[_normalize_enum_key(alias)] = (canonical_value, match_type)
        lookup[_normalize_enum_key(canonical_value)] = (canonical_value, "canonical")
    return lookup


def canonical_enum_values_for_path(canonical_path: str) -> tuple[str, ...]:
    """Return the canonical values configured for one controlled-vocabulary field."""
    return tuple(CONTROLLED_VOCABULARY_VALUES.get(canonical_path, ()))


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


@lru_cache(maxsize=1)
def _embedding_model() -> Any:
    """Load the optional sentence-transformers model lazily."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise NormalizationError(
            "Semantic controlled-vocabulary matching requires the optional "
            "'sentence-transformers' package. Install it or keep the value as a "
            "canonical/alias/fuzzy-resolvable enum value."
        ) from exc

    try:
        return SentenceTransformer(DEFAULT_ENUM_EMBEDDING_MODEL)
    except Exception as exc:
        raise NormalizationError(
            "Could not load the sentence-transformers model "
            f"{DEFAULT_ENUM_EMBEDDING_MODEL!r}. Check the local model cache or internet access."
        ) from exc


def _as_vector(embedding: Any) -> list[float]:
    """Convert model output to a plain Python vector."""
    if hasattr(embedding, "tolist"):
        values = embedding.tolist()
    else:
        values = embedding

    return [float(item) for item in values]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    """Return cosine similarity for two embedding vectors."""
    dot_product = sum(a * b for a, b in zip(left, right))
    left_norm = sqrt(sum(a * a for a in left))
    right_norm = sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0

    return dot_product / (left_norm * right_norm)


@lru_cache(maxsize=64)
def _semantic_profile_embeddings(canonical_path: str) -> tuple[tuple[str, str, tuple[float, ...]], ...]:
    """Return cached embeddings for the semantic profiles of one controlled field."""
    profiles = CONTROLLED_VOCABULARY_SEMANTIC_PROFILES.get(canonical_path, {})
    if not profiles:
        return ()

    model = _embedding_model()
    profile_items = list(profiles.values())
    texts = [profile.description for profile in profile_items]
    embeddings = model.encode(texts, normalize_embeddings=True)

    result: list[tuple[str, str, tuple[float, ...]]] = []
    for profile, embedding in zip(profile_items, embeddings):
        result.append((profile.canonical_value, profile.description, tuple(_as_vector(embedding))))

    return tuple(result)


def find_enum_semantic_candidates(
    canonical_path: str,
    value: Any,
    min_confidence: float = AMBIGUOUS_ENUM_SEMANTIC_THRESHOLD,
) -> list[EnumNormalizationCandidate]:
    """Find semantic candidates for an unresolved controlled-vocabulary value."""
    if not isinstance(value, str):
        return []

    text = " ".join(value.strip().split())
    if not text:
        return []

    profile_embeddings = _semantic_profile_embeddings(canonical_path)
    if not profile_embeddings:
        return []

    model = _embedding_model()
    query_vector = _as_vector(model.encode(text, normalize_embeddings=True))

    candidates: list[EnumNormalizationCandidate] = []
    for canonical_value, _description, profile_vector_tuple in profile_embeddings:
        score = _cosine_similarity(query_vector, list(profile_vector_tuple))
        if score < min_confidence:
            continue

        candidates.append(
            EnumNormalizationCandidate(
                original_value=value,
                canonical_value=canonical_value,
                confidence=score,
                match_type="semantic",
            )
        )

    return sorted(candidates, key=lambda item: item.confidence, reverse=True)


def resolve_enum_value(
    canonical_path: str,
    value: Any,
    auto_threshold: float = AUTO_ENUM_FUZZY_THRESHOLD,
    semantic_threshold: float = AUTO_ENUM_SEMANTIC_THRESHOLD,
    enable_semantic: bool = True,
) -> EnumNormalizationCandidate | None:
    """Resolve a controlled-vocabulary value by canonical, alias, fuzzy, or semantic matching."""
    candidates = find_enum_value_candidates(canonical_path, value)
    if candidates:
        top = candidates[0]
        if top.match_type in {"canonical", "alias"}:
            return top

        second_score = candidates[1].confidence if len(candidates) > 1 else 0.0
        if top.confidence >= auto_threshold and (top.confidence - second_score) >= 0.05:
            return top

    if not enable_semantic:
        return None

    semantic_candidates = find_enum_semantic_candidates(canonical_path, value)
    if not semantic_candidates:
        return None

    top_semantic = semantic_candidates[0]
    second_semantic_score = semantic_candidates[1].confidence if len(semantic_candidates) > 1 else 0.0
    if (
        top_semantic.confidence >= semantic_threshold
        and (top_semantic.confidence - second_semantic_score) >= MIN_ENUM_SEMANTIC_MARGIN
    ):
        return top_semantic

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
    if not candidates:
        candidates = find_enum_semantic_candidates(canonical_path, value)

    if candidates:
        candidate_text = ", ".join(
            f"{candidate.canonical_value} ({candidate.confidence:.2f}, {candidate.match_type})"
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
    return set(CANONICAL_OUTPUT_UNITS)


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
    has_field_context = allowed_units is not None

    exact = UNIT_ALIASES.get(key)
    if exact is not None and exact in allowed and (has_field_context or key not in AMBIGUOUS_UNIT_KEYS):
        return [
            UnitNormalizationCandidate(
                original_unit=unit,
                canonical_unit=exact,
                confidence=1.0,
                match_type="exact",
            )
        ]

    candidates_by_unit: dict[str, UnitNormalizationCandidate] = {}
    for alias, canonical_unit in UNIT_ALIASES.items():
        if canonical_unit not in allowed:
            continue
        if alias in AMBIGUOUS_UNIT_KEYS and not has_field_context:
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


def allowed_source_units_for_target(target_unit: str) -> set[str]:
    """Return unit families that can be converted safely into a target unit."""
    return set(source_units_for_target(target_unit))


def normalize_value_to_unit(value: Any, source_unit: str | None, target_unit: str) -> NormalizedValue:
    """
    Normalize a numeric value from source_unit to target_unit.

    Supported target units include legacy field units such as GRM, CM, and HRS,
    plus emission/activity units such as km, kWh, kg, kgCO2e, kgCO2e/kWh,
    kgCO2e/kg, and kgCO2e/km.
    """

    numeric = _to_float(value)
    normalized_target_candidate = resolve_unit_label(target_unit, allowed_units={target_unit})

    if normalized_target_candidate is None:
        raise NormalizationError(f"Unsupported target unit: {target_unit!r}")

    normalized_target = normalized_target_candidate.canonical_unit

    if source_unit is None:
        return NormalizedValue(value=numeric, unit=normalized_target)

    source_candidate = resolve_unit_label(
        source_unit,
        allowed_units=allowed_source_units_for_target(normalized_target),
    )
    if source_candidate is None:
        allowed_units = ", ".join(sorted(allowed_source_units_for_target(normalized_target)))
        raise NormalizationError(
            f"Unsupported or ambiguous source unit {source_unit!r} for target unit "
            f"{normalized_target!r}. Expected one of: {allowed_units}."
        )

    normalized_source = source_candidate.canonical_unit

    if normalized_source == normalized_target:
        return NormalizedValue(value=numeric, unit=normalized_target)

    factor = CONVERSION_FACTORS.get((normalized_source, normalized_target))
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
