# src/dpp/data_quality/detectors/rules.py
"""
Rule-based anomaly detection.

Implements hard constraints and cross-field consistency checks
that go beyond the model-level validators already in the prototype.
"""
from __future__ import annotations

from ..schemas import (
    AnomalyFlag,
    AnomalySeverity,
    AnalysisResult,
    DetectorType,
    DPPInstancePayload,
    MaterialInstancePayload,
)

RULE = DetectorType.RULE


# ── DPPInstance rules ─────────────────────────────────────────────────────────

# Domain constants (derived from seed data patterns)
# operatingHRS per brewing cycle: realistic range
_MIN_HRS_PER_BREW = 0.01   # ~36 seconds minimum
_MAX_HRS_PER_BREW = 50.0   # 50 hours per brew is implausible

# cleaning frequency: at least every N operating hours
_MAX_HRS_PER_CLEANING = 2000.0

# chalk (descaling) frequency: at least every N operating hours
_MAX_HRS_PER_CHALK = 4000.0

# grinding should match brewing closely
_MAX_GRIND_BREW_RATIO = 1.2   # grinding > 120% of brewing is suspicious
_MIN_GRIND_BREW_RATIO = 0.8   # grinding < 80% of brewing is suspicious


def check_dpp_instance_rules(payload: DPPInstancePayload) -> AnalysisResult:
    """Apply all rule-based checks to a DPPInstance payload."""
    result = AnalysisResult(entity_type="DPPInstance", entity_id=payload.entity_id)

    cleaning = payload.cleaningCount
    chalk = payload.chalkCount
    brewing = payload.brewingCount
    grinding = payload.coffeeGrindingCount
    hrs = payload.operatingHRS

    # R1: purityLevel upper bound — model only checks >= 0
    # (not applicable here, but pattern established in material rules)

    # R2: coffeeGrindingCount should not far exceed brewingCount
    if brewing > 0:
        ratio = grinding / brewing
        if ratio > _MAX_GRIND_BREW_RATIO:
            result.add_flag(AnomalyFlag(
                field="coffeeGrindingCount / brewingCount",
                detector=RULE,
                severity=AnomalySeverity.MEDIUM,
                message=(
                    f"Grinding count ({grinding}) is {ratio:.2f}x brewing count ({brewing}). "
                    f"Expected ratio <= {_MAX_GRIND_BREW_RATIO}."
                ),
                value=ratio,
                expected=f"<= {_MAX_GRIND_BREW_RATIO}",
            ))
        elif ratio < _MIN_GRIND_BREW_RATIO and grinding > 0:
            result.add_flag(AnomalyFlag(
                field="coffeeGrindingCount / brewingCount",
                detector=RULE,
                severity=AnomalySeverity.LOW,
                message=(
                    f"Grinding count ({grinding}) is only {ratio:.2f}x brewing count ({brewing}). "
                    f"Expected ratio >= {_MIN_GRIND_BREW_RATIO}."
                ),
                value=ratio,
                expected=f">= {_MIN_GRIND_BREW_RATIO}",
            ))

    # R3: operatingHRS / brewingCount ratio
    if brewing > 0 and hrs > 0:
        hrs_per_brew = hrs / brewing
        if hrs_per_brew > _MAX_HRS_PER_BREW:
            result.add_flag(AnomalyFlag(
                field="operatingHRS / brewingCount",
                detector=RULE,
                severity=AnomalySeverity.MEDIUM,
                message=(
                    f"Operating hours per brew ({hrs_per_brew:.2f}h) exceeds plausible maximum "
                    f"({_MAX_HRS_PER_BREW}h). Possible counter mismatch."
                ),
                value=hrs_per_brew,
                expected=f"<= {_MAX_HRS_PER_BREW}",
            ))
        elif hrs_per_brew < _MIN_HRS_PER_BREW:
            result.add_flag(AnomalyFlag(
                field="operatingHRS / brewingCount",
                detector=RULE,
                severity=AnomalySeverity.HIGH,
                message=(
                    f"Operating hours per brew ({hrs_per_brew:.4f}h) is implausibly low "
                    f"(< {_MIN_HRS_PER_BREW}h). Possible counter overflow or data error."
                ),
                value=hrs_per_brew,
                expected=f">= {_MIN_HRS_PER_BREW}",
            ))

    # R4: cleaning frequency relative to operating hours
    if cleaning > 0 and hrs > 0:
        hrs_per_clean = hrs / cleaning
        if hrs_per_clean > _MAX_HRS_PER_CLEANING:
            result.add_flag(AnomalyFlag(
                field="operatingHRS / cleaningCount",
                detector=RULE,
                severity=AnomalySeverity.LOW,
                message=(
                    f"Average {hrs_per_clean:.0f}h between cleanings exceeds expected maximum "
                    f"({_MAX_HRS_PER_CLEANING}h)."
                ),
                value=hrs_per_clean,
                expected=f"<= {_MAX_HRS_PER_CLEANING}",
            ))

    # R5: chalk (descaling) frequency relative to operating hours
    if chalk > 0 and hrs > 0:
        hrs_per_chalk = hrs / chalk
        if hrs_per_chalk > _MAX_HRS_PER_CHALK:
            result.add_flag(AnomalyFlag(
                field="operatingHRS / chalkCount",
                detector=RULE,
                severity=AnomalySeverity.LOW,
                message=(
                    f"Average {hrs_per_chalk:.0f}h between descaling cycles exceeds expected maximum "
                    f"({_MAX_HRS_PER_CHALK}h)."
                ),
                value=hrs_per_chalk,
                expected=f"<= {_MAX_HRS_PER_CHALK}",
            ))

    # R6: chalk count should not exceed cleaning count
    if chalk > cleaning and cleaning > 0:
        result.add_flag(AnomalyFlag(
            field="chalkCount / cleaningCount",
            detector=RULE,
            severity=AnomalySeverity.MEDIUM,
            message=(
                f"Descaling count ({chalk}) exceeds cleaning count ({cleaning}). "
                "Descaling is typically a subset of cleaning operations."
            ),
            value=chalk,
            expected=f"<= cleaningCount ({cleaning})",
        ))

    return result


# ── MaterialInstance rules ────────────────────────────────────────────────────

# purityLevel is stored as a ratio (0.0 – 1.0) in the seed data,
# but the model only validates >= 0. Values > 1.0 are schema gaps.
_MAX_PURITY_LEVEL = 1.0

# Practical minimum weight for a tracked material batch
_MIN_WEIGHT_GRM = 0.1

# percentRecycled and purityLevel together: very high recycled + very high purity
# is physically unusual for most materials
_HIGH_RECYCLED_THRESHOLD = 80.0
_HIGH_PURITY_THRESHOLD = 0.99


def check_material_instance_rules(payload: MaterialInstancePayload) -> AnalysisResult:
    """Apply all rule-based checks to a MaterialInstance payload."""
    result = AnalysisResult(entity_type="MaterialInstance", entity_id=payload.entity_id)

    weight = payload.weightGRM
    recycled = payload.percentRecycled
    purity = payload.purityLevel

    # R1: purityLevel upper bound (schema gap — model only checks >= 0)
    if purity > _MAX_PURITY_LEVEL:
        result.add_flag(AnomalyFlag(
            field="purityLevel",
            detector=RULE,
            severity=AnomalySeverity.HIGH,
            message=(
                f"purityLevel ({purity}) exceeds 1.0. "
                "In this data model, purity is stored as a ratio (0.0–1.0), not a percentage."
            ),
            value=purity,
            expected="0.0 – 1.0",
        ))

    # R2: weight sanity check
    if weight < _MIN_WEIGHT_GRM:
        result.add_flag(AnomalyFlag(
            field="weightGRM",
            detector=RULE,
            severity=AnomalySeverity.MEDIUM,
            message=f"weightGRM ({weight}g) is below practical minimum ({_MIN_WEIGHT_GRM}g).",
            value=weight,
            expected=f">= {_MIN_WEIGHT_GRM}",
        ))

    # R3: very high recycled + very high purity combination
    if recycled >= _HIGH_RECYCLED_THRESHOLD and purity >= _HIGH_PURITY_THRESHOLD:
        result.add_flag(AnomalyFlag(
            field="percentRecycled + purityLevel",
            detector=RULE,
            severity=AnomalySeverity.LOW,
            message=(
                f"High recycled content ({recycled}%) combined with very high purity "
                f"({purity}) is unusual for most materials. "
                "Verify that both values are correctly measured."
            ),
            value={"percentRecycled": recycled, "purityLevel": purity},
            expected=f"Unlikely combination: recycled >= {_HIGH_RECYCLED_THRESHOLD}% AND purity >= {_HIGH_PURITY_THRESHOLD}",
        ))

    return result
