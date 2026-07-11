"""
Result schemas for plausibility and anomaly indicators.

The anomaly layer intentionally consumes harmonized, model-near data. Findings
are indicators for expert review, not final automatic data-quality judgments.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


FindingSeverity = Literal["info", "warning", "error"]
FindingCategory = Literal[
    "range",
    "consistency",
    "relationship",
    "calculation",
    "semantic",
    "review",
    "statistical",
]


@dataclass(frozen=True)
class AnomalyFinding:
    """
    One plausibility or anomaly indicator.

    Attributes:
        check_id: Stable identifier for the applied check.
        category: Broad check category.
        severity: Indicator severity.
        message: Human-readable explanation.
        entity_id: Entity where the finding was observed, if applicable.
        entity_type: Entity type where the finding was observed, if applicable.
        field_path: Canonical field path such as 'DPPStatic.weightGRM'.
        relation_path: Canonical relation path such as 'GHGEmissionRecord.activity'.
        observed_value: Value observed in harmonized data.
        expected: Compact expectation, threshold, range, or formula.
        confidence: Optional confidence score when the check includes a
            non-deterministic or heuristic scoring step.
        evidence: Additional trace context for reports. Statistical or ML-based
            checks should store model/method identifiers, feature names, scores,
            and thresholds here so the public report contract remains stable.
        review_action: Suggested human/expert review action.
    """

    check_id: str
    category: FindingCategory
    severity: FindingSeverity
    message: str
    entity_id: str | None = None
    entity_type: str | None = None
    field_path: str | None = None
    relation_path: str | None = None
    observed_value: Any | None = None
    expected: Any | None = None
    confidence: float | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    review_action: str | None = None


@dataclass(frozen=True)
class AnomalyResult:
    """
    Complete plausibility/anomaly analysis result for one harmonization result.
    """

    scope_name: str
    findings: list[AnomalyFinding] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def has_errors(self) -> bool:
        """Return True if any finding has severity 'error'."""
        return any(finding.severity == "error" for finding in self.findings)
