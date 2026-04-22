# src/dpp/data_quality/synthetic/dpp_instance.py
"""
Synthetic data generator for DPPInstance counter fields.

Normal samples are generated around seed-data-derived baselines.
Anomaly samples are injected with controlled deviations.

Normal baseline (derived from seed data):
  BaristaCore 2500 instance 1: brewing=250,  grinding=250,  hrs=6500,  cleaning=8,  chalk=3
  BaristaCore 2500 instance 2: brewing=420,  grinding=420,  hrs=7200,  cleaning=10, chalk=4
  JURA Z10 instance:           brewing=420,  grinding=420,  hrs=7200,  cleaning=10, chalk=4
"""
from __future__ import annotations

import random
import uuid
from enum import Enum
from typing import List, Optional

import numpy as np

from ..schemas import DPPInstancePayload


class AnomalyType(str, Enum):
    """Types of controlled anomalies for DPPInstance."""
    NONE = "none"
    GRIND_BREW_MISMATCH = "grind_brew_mismatch"       # grinding >> brewing
    COUNTER_FREEZE = "counter_freeze"                  # brewing high but hrs very low
    EXCESSIVE_OPERATING_HRS = "excessive_operating_hrs"  # hrs >> expected for brew count
    MISSING_CLEANING = "missing_cleaning"              # hrs high but cleaning=0 or very low
    CHALK_EXCEEDS_CLEANING = "chalk_exceeds_cleaning"  # chalk > cleaning


# ── Baseline parameters ───────────────────────────────────────────────────────

# Based on seed data patterns
_BASELINE = {
    "brewing_mean": 350.0,
    "brewing_std": 80.0,
    "brewing_min": 50.0,

    # grinding tracks brewing closely (ratio ~1.0)
    "grind_brew_ratio_mean": 1.0,
    "grind_brew_ratio_std": 0.05,

    # operating hours per brew cycle
    "hrs_per_brew_mean": 18.0,
    "hrs_per_brew_std": 4.0,
    "hrs_per_brew_min": 0.5,

    # cleaning every ~700-900 operating hours
    "hrs_per_cleaning_mean": 800.0,
    "hrs_per_cleaning_std": 150.0,

    # chalk (descaling) every ~1800-2200 operating hours
    "hrs_per_chalk_mean": 2000.0,
    "hrs_per_chalk_std": 300.0,
}


def _clip(value: float, min_val: float = 0.0) -> float:
    return max(min_val, value)


def generate_normal(n: int = 50, seed: Optional[int] = None) -> List[DPPInstancePayload]:
    """
    Generate `n` normal DPPInstance payloads.

    Values are sampled around seed-data-derived baselines with
    realistic variance. All cross-field relationships are preserved.
    """
    rng = np.random.default_rng(seed)
    payloads = []

    for _ in range(n):
        brewing = _clip(
            rng.normal(_BASELINE["brewing_mean"], _BASELINE["brewing_std"]),
            _BASELINE["brewing_min"],
        )
        brewing = round(brewing)

        grind_ratio = _clip(
            rng.normal(_BASELINE["grind_brew_ratio_mean"], _BASELINE["grind_brew_ratio_std"]),
            0.5,
        )
        grinding = round(_clip(brewing * grind_ratio))

        hrs_per_brew = _clip(
            rng.normal(_BASELINE["hrs_per_brew_mean"], _BASELINE["hrs_per_brew_std"]),
            _BASELINE["hrs_per_brew_min"],
        )
        hrs = round(_clip(brewing * hrs_per_brew), 1)

        hrs_per_clean = _clip(
            rng.normal(_BASELINE["hrs_per_cleaning_mean"], _BASELINE["hrs_per_cleaning_std"]),
            200.0,
        )
        cleaning = max(1, round(hrs / hrs_per_clean))

        hrs_per_chalk = _clip(
            rng.normal(_BASELINE["hrs_per_chalk_mean"], _BASELINE["hrs_per_chalk_std"]),
            500.0,
        )
        chalk = max(0, round(hrs / hrs_per_chalk))
        # chalk should not exceed cleaning
        chalk = min(chalk, cleaning)

        payloads.append(DPPInstancePayload(
            entity_id=f"synthetic-normal-{uuid.uuid4()}",
            cleaningCount=float(cleaning),
            chalkCount=float(chalk),
            brewingCount=float(brewing),
            coffeeGrindingCount=float(grinding),
            operatingHRS=hrs,
        ))

    return payloads


def generate_anomalous(
    anomaly_type: AnomalyType = AnomalyType.GRIND_BREW_MISMATCH,
    n: int = 10,
    seed: Optional[int] = None,
) -> List[DPPInstancePayload]:
    """
    Generate `n` anomalous DPPInstance payloads of the given type.
    Each anomaly type represents a specific plausibility violation.
    """
    rng = np.random.default_rng(seed)
    # Start with normal samples and inject anomalies
    base = generate_normal(n, seed=seed)
    payloads = []

    for p in base:
        if anomaly_type == AnomalyType.GRIND_BREW_MISMATCH:
            # grinding >> brewing (ratio 2x-5x)
            factor = rng.uniform(2.0, 5.0)
            payloads.append(DPPInstancePayload(
                entity_id=f"synthetic-anomaly-{anomaly_type}-{uuid.uuid4()}",
                cleaningCount=p.cleaningCount,
                chalkCount=p.chalkCount,
                brewingCount=p.brewingCount,
                coffeeGrindingCount=round(p.brewingCount * factor),
                operatingHRS=p.operatingHRS,
            ))

        elif anomaly_type == AnomalyType.COUNTER_FREEZE:
            # brewing count very high but operating hours implausibly low
            payloads.append(DPPInstancePayload(
                entity_id=f"synthetic-anomaly-{anomaly_type}-{uuid.uuid4()}",
                cleaningCount=p.cleaningCount,
                chalkCount=p.chalkCount,
                brewingCount=p.brewingCount,
                coffeeGrindingCount=p.coffeeGrindingCount,
                operatingHRS=round(p.brewingCount * 0.001, 1),  # < 1 min per brew
            ))

        elif anomaly_type == AnomalyType.EXCESSIVE_OPERATING_HRS:
            # operating hours >> expected for brew count
            factor = rng.uniform(10.0, 20.0)
            payloads.append(DPPInstancePayload(
                entity_id=f"synthetic-anomaly-{anomaly_type}-{uuid.uuid4()}",
                cleaningCount=p.cleaningCount,
                chalkCount=p.chalkCount,
                brewingCount=p.brewingCount,
                coffeeGrindingCount=p.coffeeGrindingCount,
                operatingHRS=round(p.operatingHRS * factor, 1),
            ))

        elif anomaly_type == AnomalyType.MISSING_CLEANING:
            # high operating hours but cleaning count = 0 or 1
            payloads.append(DPPInstancePayload(
                entity_id=f"synthetic-anomaly-{anomaly_type}-{uuid.uuid4()}",
                cleaningCount=0.0,
                chalkCount=0.0,
                brewingCount=p.brewingCount,
                coffeeGrindingCount=p.coffeeGrindingCount,
                operatingHRS=p.operatingHRS,
            ))

        elif anomaly_type == AnomalyType.CHALK_EXCEEDS_CLEANING:
            # chalk > cleaning (logically impossible)
            chalk = p.cleaningCount + rng.integers(1, 5)
            payloads.append(DPPInstancePayload(
                entity_id=f"synthetic-anomaly-{anomaly_type}-{uuid.uuid4()}",
                cleaningCount=p.cleaningCount,
                chalkCount=float(chalk),
                brewingCount=p.brewingCount,
                coffeeGrindingCount=p.coffeeGrindingCount,
                operatingHRS=p.operatingHRS,
            ))

        else:
            payloads.append(p)

    return payloads


def generate_mixed(
    n_normal: int = 80,
    n_anomalous: int = 20,
    seed: Optional[int] = None,
) -> List[DPPInstancePayload]:
    """
    Generate a mixed dataset with normal and anomalous samples.
    Anomalies are distributed across all anomaly types.
    """
    normal = generate_normal(n_normal, seed=seed)

    anomaly_types = [t for t in AnomalyType if t != AnomalyType.NONE]
    per_type = max(1, n_anomalous // len(anomaly_types))
    anomalous = []
    for i, atype in enumerate(anomaly_types):
        anomalous.extend(
            generate_anomalous(atype, n=per_type, seed=(seed or 0) + i)
        )

    combined = normal + anomalous[:n_anomalous]
    random.shuffle(combined)
    return combined
