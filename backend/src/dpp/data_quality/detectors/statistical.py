# src/dpp/data_quality/detectors/statistical.py
"""
Statistical anomaly detection.

Uses z-score and IQR methods to detect univariate outliers
within a batch of entity payloads.
"""
from __future__ import annotations

from typing import List, Sequence, Tuple

import numpy as np

from ..schemas import (
    AnomalyFlag,
    AnomalySeverity,
    AnalysisResult,
    DetectorType,
    DPPInstancePayload,
    MaterialInstancePayload,
)

STAT = DetectorType.STATISTICAL

# Thresholds
_ZSCORE_THRESHOLD = 3.0      # |z| > 3 → high severity
_ZSCORE_WARN = 2.5           # |z| > 2.5 → medium severity
_IQR_MULTIPLIER = 1.5        # standard Tukey fence


def _zscore_flags(
    values: np.ndarray,
    field: str,
    payloads: Sequence,
    results: List[AnalysisResult],
) -> None:
    """Add z-score flags to the corresponding AnalysisResult entries."""
    if len(values) < 3:
        return  # not enough data for meaningful statistics

    mean = float(np.mean(values))
    std = float(np.std(values))

    if std == 0:
        return  # no variance — nothing to detect

    zscores = (values - mean) / std

    for i, z in enumerate(zscores):
        abs_z = abs(float(z))
        if abs_z > _ZSCORE_THRESHOLD:
            severity = AnomalySeverity.HIGH
        elif abs_z > _ZSCORE_WARN:
            severity = AnomalySeverity.MEDIUM
        else:
            continue

        results[i].add_flag(AnomalyFlag(
            field=field,
            detector=STAT,
            severity=severity,
            message=(
                f"z-score of {z:.2f} for '{field}' (value={values[i]:.4g}, "
                f"mean={mean:.4g}, std={std:.4g}). "
                f"Threshold: |z| > {_ZSCORE_WARN}."
            ),
            value=float(values[i]),
            expected=f"mean ± {_ZSCORE_WARN}σ  [{mean - _ZSCORE_WARN*std:.4g}, {mean + _ZSCORE_WARN*std:.4g}]",
        ))


def _iqr_flags(
    values: np.ndarray,
    field: str,
    results: List[AnalysisResult],
) -> None:
    """Add IQR-based flags (Tukey fences) to results."""
    if len(values) < 4:
        return

    q1, q3 = float(np.percentile(values, 25)), float(np.percentile(values, 75))
    iqr = q3 - q1

    if iqr == 0:
        return

    lower = q1 - _IQR_MULTIPLIER * iqr
    upper = q3 + _IQR_MULTIPLIER * iqr

    for i, v in enumerate(values):
        fv = float(v)
        if fv < lower or fv > upper:
            results[i].add_flag(AnomalyFlag(
                field=field,
                detector=STAT,
                severity=AnomalySeverity.MEDIUM,
                message=(
                    f"IQR outlier for '{field}': value={fv:.4g} "
                    f"outside Tukey fences [{lower:.4g}, {upper:.4g}]."
                ),
                value=fv,
                expected=f"[{lower:.4g}, {upper:.4g}]",
            ))


# ── DPPInstance statistical analysis ─────────────────────────────────────────

_DPP_FIELDS: List[Tuple[str, str]] = [
    ("cleaningCount",        "cleaningCount"),
    ("chalkCount",           "chalkCount"),
    ("brewingCount",         "brewingCount"),
    ("coffeeGrindingCount",  "coffeeGrindingCount"),
    ("operatingHRS",         "operatingHRS"),
]

# Derived ratios for cross-field statistical analysis
def _dpp_ratios(payload: DPPInstancePayload) -> dict:
    """Compute cross-field ratios for a DPPInstance."""
    ratios: dict = {}
    if payload.brewingCount > 0:
        ratios["grind_brew_ratio"] = payload.coffeeGrindingCount / payload.brewingCount
        ratios["hrs_per_brew"] = payload.operatingHRS / payload.brewingCount
    if payload.cleaningCount > 0:
        ratios["hrs_per_cleaning"] = payload.operatingHRS / payload.cleaningCount
    if payload.chalkCount > 0:
        ratios["hrs_per_chalk"] = payload.operatingHRS / payload.chalkCount
    return ratios


def analyze_dpp_instances_statistical(
    payloads: List[DPPInstancePayload],
) -> List[AnalysisResult]:
    """Run statistical analysis on a batch of DPPInstance payloads."""
    results = [
        AnalysisResult(entity_type="DPPInstance", entity_id=p.entity_id)
        for p in payloads
    ]

    if len(payloads) < 3:
        # Statistical methods need at least 3 points
        return results

    # Univariate checks on raw fields
    for attr, label in _DPP_FIELDS:
        values = np.array([getattr(p, attr) for p in payloads], dtype=float)
        _zscore_flags(values, label, payloads, results)
        _iqr_flags(values, label, results)

    # Derived ratio checks — only compute where denominator > 0
    ratio_keys = ["grind_brew_ratio", "hrs_per_brew", "hrs_per_cleaning", "hrs_per_chalk"]
    for key in ratio_keys:
        ratio_values = []
        valid_indices = []
        for i, p in enumerate(payloads):
            r = _dpp_ratios(p)
            if key in r:
                ratio_values.append(r[key])
                valid_indices.append(i)

        if len(ratio_values) < 3:
            continue

        arr = np.array(ratio_values, dtype=float)
        # Build proxy results list aligned to valid_indices
        proxy_results = [results[i] for i in valid_indices]
        _zscore_flags(arr, key, payloads, proxy_results)
        _iqr_flags(arr, key, proxy_results)

    return results


# ── MaterialInstance statistical analysis ────────────────────────────────────

_MAT_FIELDS: List[Tuple[str, str]] = [
    ("weightGRM",       "weightGRM"),
    ("percentRecycled", "percentRecycled"),
    ("purityLevel",     "purityLevel"),
]


def analyze_material_instances_statistical(
    payloads: List[MaterialInstancePayload],
) -> List[AnalysisResult]:
    """Run statistical analysis on a batch of MaterialInstance payloads."""
    results = [
        AnalysisResult(entity_type="MaterialInstance", entity_id=p.entity_id)
        for p in payloads
    ]

    if len(payloads) < 3:
        return results

    for attr, label in _MAT_FIELDS:
        values = np.array([getattr(p, attr) for p in payloads], dtype=float)
        _zscore_flags(values, label, payloads, results)
        _iqr_flags(values, label, results)

    return results
