from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import patch

from dpp.data_quality.anomaly.llm_review import _findings_from_reviews, build_service_llm_review_findings
from dpp.data_quality.harmonization.schemas import HarmonizationResult, HarmonizedEntity


class ServiceLlmReviewTests(unittest.TestCase):
    def test_missing_api_key_returns_info_finding(self) -> None:
        result = HarmonizationResult(
            scope_name="service",
            entities={
                "pending-service-step": HarmonizedEntity(
                    entity_id="pending-service-step",
                    entity_type="RepairServiceStep",
                    text_harmonization={
                        "diagnose": {
                            "original_value": "pump is dead",
                            "status": "normalized",
                            "normalized_value": "pump_not_working",
                            "confidence": 0.92,
                            "method": "semantic",
                        }
                    },
                )
            },
        )

        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            findings = asyncio.run(
                build_service_llm_review_findings(
                    result,
                    deterministic_findings=[],
                    review_context={"selectedPartLabel": "Water pump"},
                )
            )

        self.assertEqual(1, len(findings))
        self.assertEqual("service_llm_review_unavailable", findings[0].check_id)
        self.assertEqual("llm_service_review", findings[0].evidence["check_method"])

    def test_ok_review_is_reported_as_info_finding(self) -> None:
        findings = _findings_from_reviews(
            [
                {
                    "entity_id": "pending-service-step",
                    "verdict": "ok",
                    "severity": "info",
                    "message": "No additional service consistency concern was identified.",
                    "confidence": 0.72,
                    "evidence_ids": ["pending-service-step:diagnose:1"],
                }
            ],
            model="test-model",
        )

        self.assertEqual(1, len(findings))
        self.assertEqual("service_llm_review_ok", findings[0].check_id)
        self.assertEqual("info", findings[0].severity)
        self.assertEqual("ok", findings[0].evidence["verdict"])


if __name__ == "__main__":
    unittest.main()
