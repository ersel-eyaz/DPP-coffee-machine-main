# src/dpp/data_quality/schemas.py
"""
Pydantic schemas for data quality analysis results.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AnomalySeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DetectorType(str, Enum):
    RULE = "rule"
    STATISTICAL = "statistical"
    ML = "ml"


class AnomalyFlag(BaseModel):
    """A single anomaly finding from any detector."""

    field: str = Field(..., description="Field or field combination that triggered the flag.")
    detector: DetectorType
    severity: AnomalySeverity
    message: str = Field(..., description="Human-readable explanation.")
    value: Optional[Any] = Field(default=None, description="Actual value(s) that triggered the flag.")
    expected: Optional[Any] = Field(default=None, description="Expected range or value.")


class AnalysisResult(BaseModel):
    """Full analysis result for a single entity."""

    entity_type: str
    entity_id: Optional[str] = None
    anomaly_count: int = 0
    flags: List[AnomalyFlag] = Field(default_factory=list)
    is_anomalous: bool = False

    def add_flag(self, flag: AnomalyFlag) -> None:
        self.flags.append(flag)
        self.anomaly_count = len(self.flags)
        self.is_anomalous = self.anomaly_count > 0


class BatchAnalysisResult(BaseModel):
    """Results for a batch of entities."""

    entity_type: str
    total_analyzed: int
    anomalous_count: int
    results: List[AnalysisResult] = Field(default_factory=list)


# ── Request payloads ──────────────────────────────────────────────────────────

class DPPInstancePayload(BaseModel):
    """Input payload for DPPInstance analysis."""

    entity_id: Optional[str] = None
    cleaningCount: float = Field(..., ge=0)
    chalkCount: float = Field(..., ge=0)
    brewingCount: float = Field(..., ge=0)
    coffeeGrindingCount: float = Field(..., ge=0)
    operatingHRS: float = Field(..., ge=0)


class MaterialInstancePayload(BaseModel):
    """Input payload for MaterialInstance analysis."""

    entity_id: Optional[str] = None
    weightGRM: float = Field(..., ge=0)
    percentRecycled: float = Field(..., ge=0, le=100)
    purityLevel: float = Field(..., ge=0)


class DPPInstanceBatchPayload(BaseModel):
    """Batch input for DPPInstance analysis."""

    instances: List[DPPInstancePayload]


class MaterialInstanceBatchPayload(BaseModel):
    """Batch input for MaterialInstance analysis."""

    instances: List[MaterialInstancePayload]
