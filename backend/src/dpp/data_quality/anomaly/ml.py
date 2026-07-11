"""
Statistical and ML-based anomaly scoring over harmonized feature rows.

The implementation provides simple statistical baselines and a scikit-learn
Isolation Forest layer. The thesis contribution is the model-near DPP feature
pipeline and report integration, not a custom reimplementation of the ML
algorithm.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import mean, pstdev
from typing import Any

import sklearn
from sklearn.ensemble import IsolationForest

from dpp.data_quality.anomaly.features import FeatureRow
from dpp.data_quality.anomaly.schemas import AnomalyFinding


_MIN_REFERENCE_ROWS = 8


@dataclass(frozen=True)
class IsolationForestConfig:
    """Runtime configuration for the local Isolation Forest layer."""

    enabled: bool = True
    n_estimators: int = 100
    contamination: float = 0.15
    max_samples: float | int | None = None
    random_state: int = 42


@dataclass(frozen=True)
class MLAnomalyOptions:
    """Optional ML runtime options and externally provided reference rows."""

    isolation_forest: IsolationForestConfig = field(default_factory=IsolationForestConfig)
    reference_rows: list[FeatureRow] | None = None
    reference_description: str | None = None


@dataclass(frozen=True)
class MLAnomalyAnalysis:
    """Findings plus report metadata for the ML/statistical anomaly layer."""

    findings: list[AnomalyFinding]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class _ReferenceProfile:
    """Synthetic reference population for one feature set."""

    scope_name: str
    feature_set: str
    rows: list[FeatureRow]
    description: str
    profile_id: str = "synthetic_plausible_batch"
    source: str = "built_in_default"


def _reference_row(scope_name: str, feature_set: str, row_id: str, features: dict[str, float]) -> FeatureRow:
    """Create one reference feature row."""
    return FeatureRow(
        scope_name=scope_name,
        feature_set=feature_set,
        entity_id=row_id,
        entity_type="ReferenceProfile",
        features=features,
        evidence={"reference_profile": "synthetic_plausible_batch"},
    )


def _product_reference_profile() -> _ReferenceProfile:
    """Return a small plausible synthetic product usage population."""
    rows: list[FeatureRow] = []
    samples = [
        (160, 380, 24, 12, 370, 8400, 4200, 0.62),
        (210, 520, 31, 18, 510, 8600, 4550, 0.68),
        (260, 650, 42, 24, 640, 8750, 4800, 0.71),
        (320, 780, 48, 28, 760, 8900, 5100, 0.75),
        (390, 950, 63, 36, 930, 9100, 5350, 0.79),
        (450, 1120, 72, 44, 1105, 9300, 5700, 0.82),
        (520, 1280, 82, 51, 1260, 9450, 5900, 0.86),
        (610, 1500, 94, 61, 1485, 9600, 6150, 0.88),
        (690, 1710, 108, 70, 1690, 9800, 6400, 0.91),
        (760, 1880, 116, 76, 1860, 9950, 6650, 0.94),
        (850, 2090, 132, 88, 2075, 10100, 6900, 0.96),
        (930, 2260, 145, 95, 2240, 10300, 7100, 0.98),
    ]
    for index, (operating, brewing, cleaning, chalk, grinding, product_weight, part_weight, material_ratio) in enumerate(
        samples,
        start=1,
    ):
        rows.append(
            _reference_row(
                "product",
                "product_usage_graph",
                f"product-reference-{index:03d}",
                {
                    "operatingHRS": float(operating),
                    "brewingCount": float(brewing),
                    "cleaningCount": float(cleaning),
                    "chalkCount": float(chalk),
                    "coffeeGrindingCount": float(grinding),
                    "cleaning_to_brewing_ratio": round(cleaning / brewing, 6),
                    "chalk_to_brewing_ratio": round(chalk / brewing, 6),
                    "grinding_to_brewing_ratio": round(grinding / brewing, 6),
                    "brews_per_operating_hour": round(brewing / operating, 6),
                    "max_material_weight_to_part_weight": material_ratio,
                    "product_weightGRM": float(product_weight),
                    "active_part_weightGRM": float(part_weight),
                    "active_part_weight_to_product_weight": round(part_weight / product_weight, 6),
                },
            )
        )
    return _ReferenceProfile(
        scope_name="product",
        feature_set="product_usage_graph",
        rows=rows,
        description="Synthetic plausible coffee-machine usage and part-weight reference batch.",
    )


def _emission_reference_profile() -> _ReferenceProfile:
    """Return a small plausible synthetic emission calculation population."""
    rows: list[FeatureRow] = []
    samples = [
        (8, 0.18),
        (12, 0.22),
        (18, 0.28),
        (24, 0.31),
        (35, 0.37),
        (48, 0.43),
        (60, 0.51),
        (75, 0.58),
        (90, 0.66),
        (115, 0.74),
        (140, 0.82),
        (170, 0.93),
    ]
    for index, (quantity, factor_value) in enumerate(samples, start=1):
        expected = quantity * factor_value
        rows.append(
            _reference_row(
                "emission",
                "emission_calculation_intensity",
                f"emission-reference-{index:03d}",
                {
                    "quantity": float(quantity),
                    "factor_value": float(factor_value),
                    "reported_emissions": round(expected, 6),
                    "expected_emissions": round(expected, 6),
                    "absolute_calculation_deviation": 0.0,
                    "relative_calculation_deviation": 0.0,
                    "reported_emissions_per_quantity": float(factor_value),
                    "unit_compatible": 1.0,
                },
            )
        )
    return _ReferenceProfile(
        scope_name="emission",
        feature_set="emission_calculation_intensity",
        rows=rows,
        description="Synthetic plausible emission calculation and intensity reference batch.",
    )


def _reference_profiles() -> dict[tuple[str, str], _ReferenceProfile]:
    """Return built-in synthetic reference profiles keyed by scope and feature set."""
    profiles = [_product_reference_profile(), _emission_reference_profile()]
    return {(profile.scope_name, profile.feature_set): profile for profile in profiles}


def _external_reference_profiles(options: MLAnomalyOptions | None) -> dict[tuple[str, str], _ReferenceProfile]:
    """Return uploaded reference profiles keyed by scope and feature set."""
    if not options or not options.reference_rows:
        return {}

    grouped: dict[tuple[str, str], list[FeatureRow]] = {}
    for row in options.reference_rows:
        grouped.setdefault((row.scope_name, row.feature_set), []).append(row)

    description = options.reference_description or "User-provided reference feature rows."
    return {
        key: _ReferenceProfile(
            scope_name=key[0],
            feature_set=key[1],
            rows=rows,
            description=description,
            profile_id="uploaded_reference_batch",
            source="user_uploaded",
        )
        for key, rows in grouped.items()
    }


def _common_feature_names(target: FeatureRow, reference_rows: list[FeatureRow]) -> list[str]:
    """Return numeric feature names available in the target and all reference rows."""
    names = set(target.features)
    for row in reference_rows:
        names.intersection_update(row.features)
    return sorted(names)


def _quantile(values: list[float], q: float) -> float:
    """Return a simple interpolated quantile."""
    if not values:
        raise ValueError("Cannot compute quantile for an empty list")
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _z_score_findings(target: FeatureRow, reference_rows: list[FeatureRow], feature_names: list[str]) -> list[dict[str, Any]]:
    """Return per-feature z-score deviations above the configured threshold."""
    deviations: list[dict[str, Any]] = []
    for feature_name in feature_names:
        values = [row.features[feature_name] for row in reference_rows]
        std = pstdev(values)
        if std == 0:
            continue
        feature_mean = mean(values)
        z_score = (target.features[feature_name] - feature_mean) / std
        if abs(z_score) >= 3.0:
            deviations.append(
                {
                    "feature_name": feature_name,
                    "observed_value": target.features[feature_name],
                    "reference_mean": round(feature_mean, 6),
                    "reference_std": round(std, 6),
                    "z_score": round(z_score, 6),
                }
            )
    return sorted(deviations, key=lambda item: abs(item["z_score"]), reverse=True)


def _iqr_findings(target: FeatureRow, reference_rows: list[FeatureRow], feature_names: list[str]) -> list[dict[str, Any]]:
    """Return per-feature Tukey IQR fence deviations."""
    deviations: list[dict[str, Any]] = []
    for feature_name in feature_names:
        values = [row.features[feature_name] for row in reference_rows]
        q1 = _quantile(values, 0.25)
        q3 = _quantile(values, 0.75)
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        observed = target.features[feature_name]
        if lower <= observed <= upper:
            continue
        deviations.append(
            {
                "feature_name": feature_name,
                "observed_value": observed,
                "lower_fence": round(lower, 6),
                "upper_fence": round(upper, 6),
                "q1": round(q1, 6),
                "q3": round(q3, 6),
            }
        )
    return deviations


def _top_feature_deviations(
    target: FeatureRow,
    reference_rows: list[FeatureRow],
    feature_names: list[str],
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Return the largest univariate deviations for explaining a row-level ML score."""
    deviations: list[dict[str, Any]] = []
    for feature_name in feature_names:
        values = [row.features[feature_name] for row in reference_rows]
        feature_mean = mean(values)
        std = pstdev(values)
        observed = target.features[feature_name]
        if std > 0:
            deviation_score = abs((observed - feature_mean) / std)
            explanation = {
                "reference_mean": round(feature_mean, 6),
                "reference_std": round(std, 6),
                "z_like_deviation": round(deviation_score, 6),
            }
        else:
            q1 = _quantile(values, 0.25)
            q3 = _quantile(values, 0.75)
            spread = max(abs(q3 - q1), 1.0)
            deviation_score = abs(observed - feature_mean) / spread
            explanation = {
                "reference_mean": round(feature_mean, 6),
                "reference_iqr": round(q3 - q1, 6),
                "relative_deviation": round(deviation_score, 6),
            }
        deviations.append(
            {
                "feature_name": feature_name,
                "observed_value": observed,
                "deviation_score": round(deviation_score, 6),
                **explanation,
            }
        )
    return sorted(deviations, key=lambda item: item["deviation_score"], reverse=True)[:limit]


def _format_top_deviations(deviations: list[dict[str, Any]], limit: int = 3) -> str:
    """Return compact human-readable feature deviation text for finding messages."""
    if not deviations:
        return ""
    parts = [
        f"{item['feature_name']}={item['observed_value']}"
        for item in deviations[:limit]
    ]
    return " Top deviating features: " + ", ".join(parts) + "."


def _effective_max_samples(config: IsolationForestConfig, reference_count: int) -> int | float:
    """Return a scikit-learn-compatible max_samples value."""
    if config.max_samples is None:
        return min(16, reference_count)

    if isinstance(config.max_samples, float) and config.max_samples <= 1.0:
        return config.max_samples

    return max(1, min(int(config.max_samples), reference_count))


def _isolation_forest_scores(
    reference_rows: list[FeatureRow],
    target_rows: list[FeatureRow],
    feature_names: list[str],
    config: IsolationForestConfig,
) -> tuple[dict[str, float], dict[str, float], dict[str, int], dict[str, Any]]:
    """Train a scikit-learn Isolation Forest and score target rows."""
    sample_size = _effective_max_samples(config, len(reference_rows))
    reference_matrix = [[row.features[name] for name in feature_names] for row in reference_rows]
    target_matrix = {
        row.entity_id: [row.features[name] for name in feature_names]
        for row in target_rows
    }

    model = IsolationForest(
        n_estimators=config.n_estimators,
        max_samples=sample_size,
        contamination=config.contamination,
        random_state=config.random_state,
    )
    model.fit(reference_matrix)

    reference_scores = [-float(score) for score in model.score_samples(reference_matrix)]
    anomaly_scores = {
        entity_id: round(-float(model.score_samples([row])[0]), 6)
        for entity_id, row in target_matrix.items()
    }
    decision_scores = {
        entity_id: round(float(model.decision_function([row])[0]), 6)
        for entity_id, row in target_matrix.items()
    }
    predictions = {
        entity_id: int(model.predict([row])[0])
        for entity_id, row in target_matrix.items()
    }
    metadata = {
        "implementation": "sklearn.ensemble.IsolationForest",
        "sklearn_version": sklearn.__version__,
        "decision_strategy": "sklearn_predict",
        "n_estimators": config.n_estimators,
        "max_samples": sample_size,
        "contamination": config.contamination,
        "random_state": config.random_state,
        "reference_score_q85": round(_quantile(reference_scores, 0.85), 6),
        "reference_score_max": round(max(reference_scores), 6),
        "score_samples_direction": "lower native score means more anomalous; reported anomaly_score is sign-inverted",
    }
    return anomaly_scores, decision_scores, predictions, metadata


def _statistical_finding(
    *,
    check_id: str,
    check_method: str,
    target: FeatureRow,
    message: str,
    observed_value: Any,
    expected: Any,
    feature_names: list[str],
    reference_profile: _ReferenceProfile,
    severity: str = "info",
    confidence: float | None = None,
    extra_evidence: dict[str, Any] | None = None,
) -> AnomalyFinding:
    """Create one statistical/ML finding with common metadata."""
    evidence = {
        "check_method": check_method,
        "feature_set": target.feature_set,
        "feature_names": feature_names,
        "reference_profile": reference_profile.profile_id,
        "reference_source": reference_profile.source,
        "reference_description": reference_profile.description,
        "reference_rows": len(reference_profile.rows),
        "training_rows": len(reference_profile.rows),
        "source_entity_ids": target.source_entity_ids,
    }
    if extra_evidence:
        evidence.update(extra_evidence)
    return AnomalyFinding(
        check_id=check_id,
        category="statistical",
        severity=severity,  # type: ignore[arg-type]
        message=message,
        entity_id=target.entity_id,
        entity_type=target.entity_type,
        observed_value=observed_value,
        expected=expected,
        confidence=confidence,
        evidence=evidence,
        review_action="review_feature_pattern_against_reference_batch",
    )


def _ml_metadata(
    *,
    options: MLAnomalyOptions,
    profiles: dict[tuple[str, str], _ReferenceProfile],
    rows_by_profile: dict[tuple[str, str], list[FeatureRow]],
) -> dict[str, Any]:
    """Return report metadata for the statistical/ML anomaly layer."""
    visible_profile_keys = set(rows_by_profile)
    if options.reference_rows:
        visible_profile_keys.update((row.scope_name, row.feature_set) for row in options.reference_rows)

    return {
        "statistical_ml": {
            "isolation_forest": {
                "enabled": options.isolation_forest.enabled,
                "implementation": "sklearn.ensemble.IsolationForest",
                "parameters": {
                    "n_estimators": options.isolation_forest.n_estimators,
                    "contamination": options.isolation_forest.contamination,
                    "max_samples": options.isolation_forest.max_samples,
                    "random_state": options.isolation_forest.random_state,
                },
            },
            "profiles": [
                {
                    "scope_name": profile.scope_name,
                    "feature_set": profile.feature_set,
                    "reference_profile": profile.profile_id,
                    "reference_source": profile.source,
                    "reference_rows": len(profile.rows),
                    "target_rows": len(rows_by_profile.get(key, [])),
                    "usable": len(profile.rows) >= _MIN_REFERENCE_ROWS,
                    "minimum_reference_rows": _MIN_REFERENCE_ROWS,
                    "description": profile.description,
                }
                for key, profile in sorted(profiles.items())
                if key in visible_profile_keys
            ],
        }
    }


def build_ml_anomaly_analysis(
    rows: list[FeatureRow],
    options: MLAnomalyOptions | None = None,
) -> MLAnomalyAnalysis:
    """
    Score feature rows with statistical baselines and Isolation Forest.

    The current prototype uses built-in synthetic reference batches. This keeps
    the method reproducible while making the need for a larger real reference
    population explicit in the report metadata.
    """
    options = options or MLAnomalyOptions()
    profiles = _reference_profiles()
    profiles.update(_external_reference_profiles(options))
    findings: list[AnomalyFinding] = []
    rows_by_profile: dict[tuple[str, str], list[FeatureRow]] = {}
    for row in rows:
        rows_by_profile.setdefault((row.scope_name, row.feature_set), []).append(row)

    for key, target_rows in rows_by_profile.items():
        profile = profiles.get(key)
        if profile is None:
            continue
        if len(profile.rows) < _MIN_REFERENCE_ROWS:
            findings.append(
                AnomalyFinding(
                    check_id="ml_reference_batch_too_small",
                    category="statistical",
                    severity="info",
                    message=(
                        "The statistical/ML reference batch is too small for reliable scoring; "
                        "Isolation Forest and reference-based statistical checks were skipped for this feature set."
                    ),
                    observed_value={"reference_rows": len(profile.rows)},
                    expected={"minimum_reference_rows": _MIN_REFERENCE_ROWS},
                    evidence={
                        "check_method": "reference_batch_validation",
                        "feature_set": key[1],
                        "reference_profile": profile.profile_id,
                        "reference_source": profile.source,
                        "reference_rows": len(profile.rows),
                    },
                    review_action="provide_larger_reference_batch_or_use_default_reference",
                )
            )
            continue

        for target in target_rows:
            feature_names = _common_feature_names(target, profile.rows)
            if not feature_names:
                continue

            z_deviations = _z_score_findings(target, profile.rows, feature_names)
            if z_deviations:
                findings.append(
                    _statistical_finding(
                        check_id="statistical_z_score_outlier",
                        check_method="z_score",
                        target=target,
                        message=(
                            "One or more harmonized numeric features deviate strongly from the reference batch."
                            f"{_format_top_deviations(z_deviations)}"
                        ),
                        observed_value=z_deviations[:5],
                        expected={"absolute_z_score_max": 3.0},
                        feature_names=feature_names,
                        reference_profile=profile,
                        severity="warning",
                    )
                )

            iqr_deviations = _iqr_findings(target, profile.rows, feature_names)
            if iqr_deviations:
                findings.append(
                    _statistical_finding(
                        check_id="statistical_iqr_outlier",
                        check_method="iqr",
                        target=target,
                        message=(
                            "One or more harmonized numeric features fall outside the IQR reference fences."
                            f"{_format_top_deviations(iqr_deviations)}"
                        ),
                        observed_value=iqr_deviations[:5],
                        expected={"iqr_fence": "Q1 - 1.5*IQR .. Q3 + 1.5*IQR"},
                        feature_names=feature_names,
                        reference_profile=profile,
                        severity="info",
                    )
                )

        shared_feature_names = sorted(
            set.intersection(
                *(set(_common_feature_names(target, profile.rows)) for target in target_rows),
            )
        )
        if not shared_feature_names:
            continue

        if not options.isolation_forest.enabled:
            continue

        scores, decisions, predictions, metadata = _isolation_forest_scores(
            profile.rows,
            target_rows,
            shared_feature_names,
            options.isolation_forest,
        )
        for target in target_rows:
            score = scores[target.entity_id]
            prediction = predictions[target.entity_id]
            decision = decisions[target.entity_id]
            if prediction != -1:
                continue
            top_deviations = _top_feature_deviations(target, profile.rows, shared_feature_names)
            findings.append(
                _statistical_finding(
                    check_id="isolation_forest_feature_pattern_outlier",
                    check_method="isolation_forest",
                    target=target,
                    message=(
                        "The harmonized feature vector is classified as an outlier by the Isolation Forest model."
                        f"{_format_top_deviations(top_deviations)}"
                    ),
                    observed_value={
                        "anomaly_score": score,
                        "sklearn_decision_function": decision,
                        "sklearn_prediction": prediction,
                        "top_deviating_features": top_deviations[:3],
                    },
                    expected={"sklearn_prediction": -1},
                    feature_names=shared_feature_names,
                    reference_profile=profile,
                    severity="warning",
                    extra_evidence={
                        "model_id": f"local_isolation_forest_{target.scope_name}_{target.feature_set}_v1",
                        "score": score,
                        "sklearn_decision_function": decision,
                        "sklearn_prediction": prediction,
                        "top_deviating_features": top_deviations,
                        "training_rows": len(profile.rows),
                        **metadata,
                    },
                )
            )

    return MLAnomalyAnalysis(
        findings=findings,
        metadata=_ml_metadata(options=options, profiles=profiles, rows_by_profile=rows_by_profile),
    )


def build_ml_anomaly_findings(
    rows: list[FeatureRow],
    options: MLAnomalyOptions | None = None,
) -> list[AnomalyFinding]:
    """Return only ML/statistical findings for callers that do not need metadata."""
    return build_ml_anomaly_analysis(rows, options=options).findings
