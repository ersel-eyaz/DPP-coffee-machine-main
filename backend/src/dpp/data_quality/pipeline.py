# src/dpp/data_quality/pipeline.py
"""
Data quality analysis pipeline.

Coordinates rule-based, statistical, and ML detectors
and merges their results per entity.
"""
from __future__ import annotations

from typing import List

from .detectors.ml import (
    analyze_dpp_instances_ml,
    analyze_material_instances_ml,
)
from .detectors.rules import (
    check_dpp_instance_rules,
    check_material_instance_rules,
)
from .detectors.statistical import (
    analyze_dpp_instances_statistical,
    analyze_material_instances_statistical,
)
from .schemas import (
    AnalysisResult,
    BatchAnalysisResult,
    DPPInstanceBatchPayload,
    DPPInstancePayload,
    MaterialInstanceBatchPayload,
    MaterialInstancePayload,
)


def _merge(results: List[List[AnalysisResult]]) -> List[AnalysisResult]:
    """
    Merge multiple per-entity result lists into one.
    Assumes all lists are the same length and same entity order.
    """
    if not results:
        return []

    merged = results[0]
    for extra in results[1:]:
        for base, ext in zip(merged, extra):
            for flag in ext.flags:
                base.add_flag(flag)

    return merged


# ── DPPInstance pipeline ──────────────────────────────────────────────────────

def analyze_dpp_instances(
    payloads: List[DPPInstancePayload],
) -> BatchAnalysisResult:
    """
    Run all three detector layers on a batch of DPPInstance payloads.

    Layer 1: Rule-based  — per-entity, no batch context needed
    Layer 2: Statistical — batch-level z-score and IQR
    Layer 3: ML          — Isolation Forest on the full feature matrix
    """
    # Layer 1: rules (per entity)
    rule_results = [check_dpp_instance_rules(p) for p in payloads]

    # Layer 2: statistical (batch)
    stat_results = analyze_dpp_instances_statistical(payloads)

    # Layer 3: ML (batch)
    ml_results = analyze_dpp_instances_ml(payloads)

    merged = _merge([rule_results, stat_results, ml_results])

    return BatchAnalysisResult(
        entity_type="DPPInstance",
        total_analyzed=len(payloads),
        anomalous_count=sum(1 for r in merged if r.is_anomalous),
        results=merged,
    )


# ── MaterialInstance pipeline ─────────────────────────────────────────────────

def analyze_material_instances(
    payloads: List[MaterialInstancePayload],
) -> BatchAnalysisResult:
    """
    Run all three detector layers on a batch of MaterialInstance payloads.
    """
    rule_results = [check_material_instance_rules(p) for p in payloads]
    stat_results = analyze_material_instances_statistical(payloads)
    ml_results = analyze_material_instances_ml(payloads)

    merged = _merge([rule_results, stat_results, ml_results])

    return BatchAnalysisResult(
        entity_type="MaterialInstance",
        total_analyzed=len(payloads),
        anomalous_count=sum(1 for r in merged if r.is_anomalous),
        results=merged,
    )
