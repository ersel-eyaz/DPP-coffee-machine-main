"""
Optional product-specific plausibility profiles.

Generic anomaly rules remain broad and product-family oriented. Profiles add
stricter reference ranges only when the harmonized data contains enough context
to identify a product model. The built-in profile is synthetic and belongs to
the prototype scenario; real deployments should replace or extend it with
validated model, batch, or material reference data.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re


PROFILE_AUTO_FUZZY_THRESHOLD = 0.84
PROFILE_MIN_FUZZY_MARGIN = 0.06


@dataclass(frozen=True)
class ProfileRange:
    """A product-specific expected range for one canonical field."""

    field_path: str
    min_value: float
    max_value: float
    reference_value: float
    unit: str
    description: str = ""

    def expected_range(self) -> dict[str, float | str]:
        """Return a report-friendly range description."""
        return {
            "min": self.min_value,
            "max": self.max_value,
            "reference_value": self.reference_value,
            "unit": self.unit,
        }


@dataclass(frozen=True)
class ProductProfile:
    """A model-specific product profile used for optional anomaly checks."""

    profile_id: str
    label: str
    match_terms: tuple[str, ...]
    source: str
    reference_type: str
    reference_level: str
    ranges: tuple[ProfileRange, ...]


@dataclass(frozen=True)
class ProductProfileMatch:
    """A resolved product profile plus traceable matching metadata."""

    profile: ProductProfile
    method: str
    confidence: float
    matched_term: str


PRODUCT_PROFILES: tuple[ProductProfile, ...] = (
    ProductProfile(
        profile_id="baristacore_2500",
        label="BaristaCore 2500",
        match_terms=(
            "baristacore 2500",
            "barista core 2500",
        ),
        source="Synthetic prototype reference values from seed_dpp_multilevel.py.",
        reference_type="synthetic_seed",
        reference_level="model",
        ranges=(
            ProfileRange(
                field_path="DPPStatic.weightGRM",
                min_value=9000.0,
                max_value=11000.0,
                reference_value=10000.0,
                unit="g",
                description="Synthetic BaristaCore weight with +/-10% tolerance.",
            ),
            ProfileRange(
                field_path="DPPStatic.heightCM",
                min_value=42.75,
                max_value=47.25,
                reference_value=45.0,
                unit="cm",
                description="Synthetic BaristaCore height with +/-5% tolerance.",
            ),
            ProfileRange(
                field_path="DPPStatic.widthCM",
                min_value=33.25,
                max_value=36.75,
                reference_value=35.0,
                unit="cm",
                description="Synthetic BaristaCore width with +/-5% tolerance.",
            ),
            ProfileRange(
                field_path="DPPStatic.depthCM",
                min_value=38.0,
                max_value=42.0,
                reference_value=40.0,
                unit="cm",
                description="Synthetic BaristaCore depth with +/-5% tolerance.",
            ),
        ),
    ),
)


def _normalize_profile_text(value: str) -> str:
    """Normalize product names and profile terms for conservative matching."""
    cleaned = value.lower().replace("-", " ").replace("_", " ")
    cleaned = " ".join(cleaned.split())
    cleaned = re.sub(r"\b([a-z])\s+(\d+)\b", r"\1\2", cleaned)
    cleaned = cleaned.replace(" alu ", " aluminium ")
    return cleaned


def _profile_similarity(product_name: str, term: str) -> float:
    """Return a conservative string similarity score for product/profile names."""
    if not product_name or not term:
        return 0.0

    sequence_score = SequenceMatcher(None, product_name, term).ratio()
    product_tokens = set(product_name.split())
    term_tokens = set(term.split())
    token_score = len(product_tokens & term_tokens) / len(term_tokens) if term_tokens else 0.0
    return (sequence_score + token_score) / 2.0


def resolve_product_profile(product_name: object) -> ProductProfileMatch | None:
    """Return a product profile match with method and confidence metadata."""
    if not isinstance(product_name, str):
        return None

    normalized_name = _normalize_profile_text(product_name)
    if not normalized_name:
        return None

    for profile in PRODUCT_PROFILES:
        for term in profile.match_terms:
            normalized_term = _normalize_profile_text(term)
            if normalized_term in normalized_name:
                return ProductProfileMatch(
                    profile=profile,
                    method="product_name_contains_profile_term",
                    confidence=1.0,
                    matched_term=term,
                )

    fuzzy_matches: list[ProductProfileMatch] = []
    for profile in PRODUCT_PROFILES:
        best_term = ""
        best_score = 0.0
        for term in profile.match_terms:
            score = _profile_similarity(normalized_name, _normalize_profile_text(term))
            if score > best_score:
                best_score = score
                best_term = term

        fuzzy_matches.append(
            ProductProfileMatch(
                profile=profile,
                method="fuzzy_product_name",
                confidence=round(best_score, 3),
                matched_term=best_term,
            )
        )

    fuzzy_matches.sort(key=lambda match: match.confidence, reverse=True)
    top_match = fuzzy_matches[0]
    second_score = fuzzy_matches[1].confidence if len(fuzzy_matches) > 1 else 0.0
    if (
        top_match.confidence >= PROFILE_AUTO_FUZZY_THRESHOLD
        and top_match.confidence - second_score >= PROFILE_MIN_FUZZY_MARGIN
    ):
        return top_match

    return None
