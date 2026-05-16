"""Output builders for anomaly/plausibility results."""

from __future__ import annotations

from typing import Any

from dpp.data_quality.anomaly.schemas import AnomalyResult
from dpp.data_quality.anomaly.services import finding_as_dict


def _build_summary(result: AnomalyResult) -> dict[str, Any]:
    """Build compact finding counts for report output."""
    severity_counts = {
        "info": sum(1 for finding in result.findings if finding.severity == "info"),
        "warning": sum(1 for finding in result.findings if finding.severity == "warning"),
        "error": sum(1 for finding in result.findings if finding.severity == "error"),
    }
    category_counts: dict[str, int] = {}
    check_method_counts: dict[str, int] = {}
    for finding in result.findings:
        category_counts[finding.category] = category_counts.get(finding.category, 0) + 1
        check_method = finding.evidence.get("check_method", "rule_based")
        if isinstance(check_method, str):
            check_method_counts[check_method] = check_method_counts.get(check_method, 0) + 1

    return {
        "findings_total": len(result.findings),
        "severity_counts": severity_counts,
        "category_counts": category_counts,
        "check_method_counts": check_method_counts,
        "has_errors": result.has_errors(),
    }


def build_anomaly_report(result: AnomalyResult) -> dict[str, Any]:
    """
    Build a traceable anomaly/plausibility report.

    The report keeps findings explicit so the thesis can discuss each indicator
    as a review aid rather than an automatic correction.
    """
    return {
        "scope_name": result.scope_name,
        "summary": _build_summary(result),
        "findings": [finding_as_dict(finding) for finding in result.findings],
    }
