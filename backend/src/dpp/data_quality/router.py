# src/dpp/data_quality/router.py
"""
FastAPI router for data quality analysis endpoints.
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException, status

from .pipeline import analyze_dpp_instances, analyze_material_instances
from .schemas import (
    BatchAnalysisResult,
    DPPInstanceBatchPayload,
    DPPInstancePayload,
    MaterialInstanceBatchPayload,
    MaterialInstancePayload,
)
from .synthetic.dpp_instance import (
    AnomalyType as DPPAnomalyType,
    generate_anomalous as gen_dpp_anomalous,
    generate_mixed as gen_dpp_mixed,
    generate_normal as gen_dpp_normal,
)
from .synthetic.material_instance import (
    MaterialAnomalyType,
    generate_anomalous as gen_mat_anomalous,
    generate_mixed as gen_mat_mixed,
    generate_normal as gen_mat_normal,
)

router = APIRouter()


# ── DPPInstance endpoints ─────────────────────────────────────────────────────

@router.post(
    "/analyze/dpp-instance",
    response_model=BatchAnalysisResult,
    status_code=status.HTTP_200_OK,
    summary="Analyze a batch of DPPInstance counter values for anomalies",
)
async def analyze_dpp_instance_batch(payload: DPPInstanceBatchPayload) -> BatchAnalysisResult:
    """
    Run rule-based, statistical, and ML anomaly detection
    on a batch of DPPInstance counter payloads.

    Minimum batch size for statistical/ML layers: 3 / 5 instances.
    Smaller batches still receive rule-based results.
    """
    if not payload.instances:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Batch must contain at least one instance.",
        )
    return analyze_dpp_instances(payload.instances)


@router.post(
    "/analyze/dpp-instance/single",
    response_model=BatchAnalysisResult,
    status_code=status.HTTP_200_OK,
    summary="Analyze a single DPPInstance (rule-based only)",
)
async def analyze_dpp_instance_single(payload: DPPInstancePayload) -> BatchAnalysisResult:
    """
    Analyze a single DPPInstance payload.
    Only rule-based checks are applied (statistical/ML require a batch).
    """
    return analyze_dpp_instances([payload])


# ── MaterialInstance endpoints ────────────────────────────────────────────────

@router.post(
    "/analyze/material-instance",
    response_model=BatchAnalysisResult,
    status_code=status.HTTP_200_OK,
    summary="Analyze a batch of MaterialInstance values for anomalies",
)
async def analyze_material_instance_batch(payload: MaterialInstanceBatchPayload) -> BatchAnalysisResult:
    """
    Run rule-based, statistical, and ML anomaly detection
    on a batch of MaterialInstance payloads.
    """
    if not payload.instances:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Batch must contain at least one instance.",
        )
    return analyze_material_instances(payload.instances)


@router.post(
    "/analyze/material-instance/single",
    response_model=BatchAnalysisResult,
    status_code=status.HTTP_200_OK,
    summary="Analyze a single MaterialInstance (rule-based only)",
)
async def analyze_material_instance_single(payload: MaterialInstancePayload) -> BatchAnalysisResult:
    """
    Analyze a single MaterialInstance payload.
    Only rule-based checks are applied.
    """
    return analyze_material_instances([payload])


# ── Synthetic data endpoints ──────────────────────────────────────────────────

@router.get(
    "/synthetic/dpp-instance/normal",
    response_model=List[DPPInstancePayload],
    summary="Generate normal DPPInstance synthetic data",
)
async def synthetic_dpp_normal(n: int = 50, seed: int = 42) -> List[DPPInstancePayload]:
    """Generate `n` normal DPPInstance payloads based on seed-data baselines."""
    if n < 1 or n > 1000:
        raise HTTPException(status_code=422, detail="n must be between 1 and 1000.")
    return gen_dpp_normal(n=n, seed=seed)


@router.get(
    "/synthetic/dpp-instance/anomalous",
    response_model=List[DPPInstancePayload],
    summary="Generate anomalous DPPInstance synthetic data",
)
async def synthetic_dpp_anomalous(
    anomaly_type: DPPAnomalyType = DPPAnomalyType.GRIND_BREW_MISMATCH,
    n: int = 10,
    seed: int = 42,
) -> List[DPPInstancePayload]:
    """Generate `n` anomalous DPPInstance payloads of a specific anomaly type."""
    if n < 1 or n > 200:
        raise HTTPException(status_code=422, detail="n must be between 1 and 200.")
    return gen_dpp_anomalous(anomaly_type=anomaly_type, n=n, seed=seed)


@router.get(
    "/synthetic/dpp-instance/mixed",
    response_model=List[DPPInstancePayload],
    summary="Generate mixed (normal + anomalous) DPPInstance synthetic data",
)
async def synthetic_dpp_mixed(
    n_normal: int = 80,
    n_anomalous: int = 20,
    seed: int = 42,
) -> List[DPPInstancePayload]:
    """Generate a mixed dataset for use in batch analysis and evaluation."""
    return gen_dpp_mixed(n_normal=n_normal, n_anomalous=n_anomalous, seed=seed)


@router.get(
    "/synthetic/material-instance/normal",
    response_model=List[MaterialInstancePayload],
    summary="Generate normal MaterialInstance synthetic data",
)
async def synthetic_material_normal(n: int = 50, seed: int = 42) -> List[MaterialInstancePayload]:
    """Generate `n` normal MaterialInstance payloads."""
    if n < 1 or n > 1000:
        raise HTTPException(status_code=422, detail="n must be between 1 and 1000.")
    return gen_mat_normal(n=n, seed=seed)


@router.get(
    "/synthetic/material-instance/anomalous",
    response_model=List[MaterialInstancePayload],
    summary="Generate anomalous MaterialInstance synthetic data",
)
async def synthetic_material_anomalous(
    anomaly_type: MaterialAnomalyType = MaterialAnomalyType.PURITY_AS_PERCENTAGE,
    n: int = 10,
    seed: int = 42,
) -> List[MaterialInstancePayload]:
    """Generate `n` anomalous MaterialInstance payloads."""
    if n < 1 or n > 200:
        raise HTTPException(status_code=422, detail="n must be between 1 and 200.")
    return gen_mat_anomalous(anomaly_type=anomaly_type, n=n, seed=seed)


@router.get(
    "/synthetic/material-instance/mixed",
    response_model=List[MaterialInstancePayload],
    summary="Generate mixed MaterialInstance synthetic data",
)
async def synthetic_material_mixed(
    n_normal: int = 80,
    n_anomalous: int = 20,
    seed: int = 42,
) -> List[MaterialInstancePayload]:
    """Generate a mixed MaterialInstance dataset."""
    return gen_mat_mixed(n_normal=n_normal, n_anomalous=n_anomalous, seed=seed)
