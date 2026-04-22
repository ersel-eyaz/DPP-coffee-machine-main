# src/dpp/data_quality/synthetic/material_instance.py
"""
Synthetic data generator for MaterialInstance numeric fields.

Normal baseline (derived from seed data):
  weightGRM:       20 – 1400g  (wide range, material-dependent)
  percentRecycled: 0 – 40%     (metals higher, electronics 0%)
  purityLevel:     0.92 – 0.9999  (stored as ratio 0.0–1.0)
"""
from __future__ import annotations

import random
import uuid
from enum import Enum
from typing import List, Optional

import numpy as np

from ..schemas import MaterialInstancePayload


class MaterialAnomalyType(str, Enum):
    NONE = "none"
    PURITY_AS_PERCENTAGE = "purity_as_percentage"   # purity entered as % (e.g. 97 instead of 0.97)
    NEGATIVE_RECYCLED = "negative_recycled"          # edge case: just below 0 after rounding
    WEIGHT_IMPLAUSIBLE = "weight_implausible"         # weight extreme outlier
    HIGH_RECYCLED_HIGH_PURITY = "high_recycled_high_purity"  # unlikely combination


# ── Baseline parameters ───────────────────────────────────────────────────────

_BASELINE = {
    # log-normal for weight (widely varying material amounts)
    "weight_log_mean": np.log(300.0),
    "weight_log_std": 1.0,
    "weight_min": 10.0,

    "recycled_mean": 18.0,
    "recycled_std": 12.0,
    "recycled_min": 0.0,
    "recycled_max": 100.0,

    "purity_mean": 0.975,
    "purity_std": 0.02,
    "purity_min": 0.85,
    "purity_max": 1.0,
}


def _clip(value: float, min_val: float = 0.0, max_val: float = float("inf")) -> float:
    return max(min_val, min(max_val, value))


def generate_normal(n: int = 50, seed: Optional[int] = None) -> List[MaterialInstancePayload]:
    """Generate `n` normal MaterialInstance payloads."""
    rng = np.random.default_rng(seed)
    payloads = []

    for _ in range(n):
        weight = _clip(
            rng.lognormal(_BASELINE["weight_log_mean"], _BASELINE["weight_log_std"]),
            _BASELINE["weight_min"],
        )
        weight = round(weight, 1)

        recycled = _clip(
            rng.normal(_BASELINE["recycled_mean"], _BASELINE["recycled_std"]),
            _BASELINE["recycled_min"],
            _BASELINE["recycled_max"],
        )
        recycled = round(recycled, 1)

        purity = _clip(
            rng.normal(_BASELINE["purity_mean"], _BASELINE["purity_std"]),
            _BASELINE["purity_min"],
            _BASELINE["purity_max"],
        )
        purity = round(purity, 4)

        payloads.append(MaterialInstancePayload(
            entity_id=f"synthetic-normal-{uuid.uuid4()}",
            weightGRM=weight,
            percentRecycled=recycled,
            purityLevel=purity,
        ))

    return payloads


def generate_anomalous(
    anomaly_type: MaterialAnomalyType = MaterialAnomalyType.PURITY_AS_PERCENTAGE,
    n: int = 10,
    seed: Optional[int] = None,
) -> List[MaterialInstancePayload]:
    """Generate `n` anomalous MaterialInstance payloads."""
    rng = np.random.default_rng(seed)
    base = generate_normal(n, seed=seed)
    payloads = []

    for p in base:
        if anomaly_type == MaterialAnomalyType.PURITY_AS_PERCENTAGE:
            # Common data entry error: 0.97 entered as 97.0
            payloads.append(MaterialInstancePayload(
                entity_id=f"synthetic-anomaly-{anomaly_type}-{uuid.uuid4()}",
                weightGRM=p.weightGRM,
                percentRecycled=p.percentRecycled,
                purityLevel=round(p.purityLevel * 100, 1),  # e.g. 0.97 → 97.0
            ))

        elif anomaly_type == MaterialAnomalyType.WEIGHT_IMPLAUSIBLE:
            # Extreme weight outlier (100x-1000x normal)
            factor = rng.uniform(100.0, 1000.0)
            payloads.append(MaterialInstancePayload(
                entity_id=f"synthetic-anomaly-{anomaly_type}-{uuid.uuid4()}",
                weightGRM=round(p.weightGRM * factor, 1),
                percentRecycled=p.percentRecycled,
                purityLevel=p.purityLevel,
            ))

        elif anomaly_type == MaterialAnomalyType.HIGH_RECYCLED_HIGH_PURITY:
            # Unlikely combination: high recycled + very high purity
            payloads.append(MaterialInstancePayload(
                entity_id=f"synthetic-anomaly-{anomaly_type}-{uuid.uuid4()}",
                weightGRM=p.weightGRM,
                percentRecycled=round(rng.uniform(85.0, 100.0), 1),
                purityLevel=round(rng.uniform(0.995, 1.0), 4),
            ))

        else:
            payloads.append(p)

    return payloads


def generate_mixed(
    n_normal: int = 80,
    n_anomalous: int = 20,
    seed: Optional[int] = None,
) -> List[MaterialInstancePayload]:
    """Generate a mixed dataset with normal and anomalous samples."""
    normal = generate_normal(n_normal, seed=seed)

    anomaly_types = [t for t in MaterialAnomalyType if t != MaterialAnomalyType.NONE]
    per_type = max(1, n_anomalous // len(anomaly_types))
    anomalous = []
    for i, atype in enumerate(anomaly_types):
        anomalous.extend(
            generate_anomalous(atype, n=per_type, seed=(seed or 0) + i)
        )

    combined = normal + anomalous[:n_anomalous]
    random.shuffle(combined)
    return combined
