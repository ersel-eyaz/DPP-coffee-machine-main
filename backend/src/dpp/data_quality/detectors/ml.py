# src/dpp/data_quality/detectors/ml.py
"""
ML-based anomaly detection using Isolation Forest.

Isolation Forest is an unsupervised method that isolates anomalies
by randomly partitioning features. Anomalies require fewer splits
to isolate, resulting in shorter average path lengths.

Reference: Liu, F.T., Ting, K.M., Zhou, Z.H. (2008).
Isolation Forest. ICDM 2008.
"""
from __future__ import annotations

from typing import List, Optional

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from ..schemas import (
    AnomalyFlag,
    AnomalySeverity,
    AnalysisResult,
    DetectorType,
    DPPInstancePayload,
    MaterialInstancePayload,
)

ML = DetectorType.ML

# Isolation Forest hyperparameters
_CONTAMINATION = 0.1    # expected proportion of anomalies
_N_ESTIMATORS = 100
_RANDOM_STATE = 42


def _severity_from_score(score: float) -> AnomalySeverity:
    """
    Map Isolation Forest anomaly score to severity.
    Scores are negative; more negative = more anomalous.
    score < -0.1  → HIGH
    score < 0.0   → MEDIUM
    """
    if score < -0.1:
        return AnomalySeverity.HIGH
    return AnomalySeverity.MEDIUM


def _build_dpp_feature_matrix(payloads: List[DPPInstancePayload]) -> np.ndarray:
    """
    Build feature matrix for DPPInstance.
    Includes raw counters + derived cross-field ratios.
    NaN values from zero denominators are replaced with 0.
    """
    rows = []
    for p in payloads:
        grind_brew = p.coffeeGrindingCount / p.brewingCount if p.brewingCount > 0 else 0.0
        hrs_brew   = p.operatingHRS / p.brewingCount if p.brewingCount > 0 else 0.0
        hrs_clean  = p.operatingHRS / p.cleaningCount if p.cleaningCount > 0 else 0.0
        hrs_chalk  = p.operatingHRS / p.chalkCount if p.chalkCount > 0 else 0.0

        rows.append([
            p.cleaningCount,
            p.chalkCount,
            p.brewingCount,
            p.coffeeGrindingCount,
            p.operatingHRS,
            grind_brew,
            hrs_brew,
            hrs_clean,
            hrs_chalk,
        ])
    return np.array(rows, dtype=float)


def _build_material_feature_matrix(payloads: List[MaterialInstancePayload]) -> np.ndarray:
    """Build feature matrix for MaterialInstance."""
    rows = []
    for p in payloads:
        rows.append([
            p.weightGRM,
            p.percentRecycled,
            p.purityLevel,
        ])
    return np.array(rows, dtype=float)


def _run_isolation_forest(
    X: np.ndarray,
    contamination: float = _CONTAMINATION,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Fit and predict with Isolation Forest.
    Returns (predictions, scores):
      predictions: 1 = normal, -1 = anomaly
      scores: raw decision function scores (more negative = more anomalous)
    """
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    clf = IsolationForest(
        n_estimators=_N_ESTIMATORS,
        contamination=contamination,
        random_state=_RANDOM_STATE,
    )
    predictions = clf.fit_predict(X_scaled)
    scores = clf.decision_function(X_scaled)
    return predictions, scores


# ── DPPInstance ML analysis ───────────────────────────────────────────────────

_DPP_FEATURE_NAMES = [
    "cleaningCount",
    "chalkCount",
    "brewingCount",
    "coffeeGrindingCount",
    "operatingHRS",
    "grind_brew_ratio",
    "hrs_per_brew",
    "hrs_per_cleaning",
    "hrs_per_chalk",
]


def analyze_dpp_instances_ml(
    payloads: List[DPPInstancePayload],
    contamination: float = _CONTAMINATION,
) -> List[AnalysisResult]:
    """Run Isolation Forest on a batch of DPPInstance payloads."""
    results = [
        AnalysisResult(entity_type="DPPInstance", entity_id=p.entity_id)
        for p in payloads
    ]

    if len(payloads) < 5:
        # Isolation Forest needs enough samples to be meaningful
        return results

    X = _build_dpp_feature_matrix(payloads)
    predictions, scores = _run_isolation_forest(X, contamination)

    for i, (pred, score) in enumerate(zip(predictions, scores)):
        if pred == -1:
            severity = _severity_from_score(float(score))
            results[i].add_flag(AnomalyFlag(
                field="[cleaningCount, chalkCount, brewingCount, coffeeGrindingCount, operatingHRS, ratios]",
                detector=ML,
                severity=severity,
                message=(
                    f"Isolation Forest flagged this instance as anomalous "
                    f"(decision score={score:.4f}). "
                    "The combination of counter values and derived ratios is unusual "
                    "relative to the rest of the batch."
                ),
                value={"anomaly_score": float(score)},
                expected="decision_score >= 0 (normal region)",
            ))

    return results


# ── MaterialInstance ML analysis ──────────────────────────────────────────────

_MAT_FEATURE_NAMES = ["weightGRM", "percentRecycled", "purityLevel"]


def analyze_material_instances_ml(
    payloads: List[MaterialInstancePayload],
    contamination: float = _CONTAMINATION,
) -> List[AnalysisResult]:
    """Run Isolation Forest on a batch of MaterialInstance payloads."""
    results = [
        AnalysisResult(entity_type="MaterialInstance", entity_id=p.entity_id)
        for p in payloads
    ]

    if len(payloads) < 5:
        return results

    X = _build_material_feature_matrix(payloads)
    predictions, scores = _run_isolation_forest(X, contamination)

    for i, (pred, score) in enumerate(zip(predictions, scores)):
        if pred == -1:
            severity = _severity_from_score(float(score))
            results[i].add_flag(AnomalyFlag(
                field="[weightGRM, percentRecycled, purityLevel]",
                detector=ML,
                severity=severity,
                message=(
                    f"Isolation Forest flagged this material instance as anomalous "
                    f"(decision score={score:.4f}). "
                    "The combination of weight, recycled content, and purity is unusual "
                    "relative to the rest of the batch."
                ),
                value={"anomaly_score": float(score)},
                expected="decision_score >= 0 (normal region)",
            ))

    return results
