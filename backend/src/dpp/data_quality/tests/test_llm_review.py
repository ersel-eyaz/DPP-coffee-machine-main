from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch

from dpp.data_quality.anomaly.llm_review import (
    _build_review_context,
    _concept_context,
    _findings_from_reviews,
    build_service_llm_review_findings,
)
from dpp.data_quality.anomaly.schemas import AnomalyFinding, AnomalyResult
from dpp.data_quality.harmonization.schemas import HarmonizationResult, HarmonizedEntity
from dpp.routers.data_quality import DataQualityRunRequest, run_data_quality


class ServiceLlmReviewTests(unittest.TestCase):
    def test_run_endpoint_preserves_anomaly_metadata_when_llm_findings_are_added(self) -> None:
        harmonization_result = HarmonizationResult(scope_name="service")
        anomaly_result = AnomalyResult(
            scope_name="service",
            metadata={"statistical_ml": {"profiles": []}},
        )
        llm_finding = AnomalyFinding(
            check_id="service_llm_review_ok",
            category="review",
            severity="info",
            message="No additional concern.",
        )
        request = DataQualityRunRequest(
            scope="service",
            mode="both",
            document={"@id": "service-001", "@type": "dpp:RepairServiceStep"},
            enable_llm_review=True,
        )

        with (
            patch("dpp.routers.data_quality.harmonize_document", return_value=harmonization_result),
            patch("dpp.routers.data_quality.build_clean_jsonld", return_value={}),
            patch("dpp.routers.data_quality.build_harmonization_report", return_value={}),
            patch("dpp.routers.data_quality.analyze_harmonization_result", return_value=anomaly_result),
            patch(
                "dpp.routers.data_quality.build_service_llm_review_findings",
                new=AsyncMock(return_value=[llm_finding]),
            ),
        ):
            payload = asyncio.run(run_data_quality(request))

        self.assertEqual(anomaly_result.metadata, payload["anomaly_report"]["metadata"])
        self.assertEqual(1, payload["anomaly_report"]["summary"]["findings_total"])

    def test_concept_context_uses_weak_terms_without_generated_service_types(self) -> None:
        context = _concept_context("does_not_turn_on")

        self.assertIsNotNone(context)
        assert context is not None
        self.assertIn("related_context_terms", context)
        self.assertNotIn("related_part_keywords", context)
        self.assertNotIn("applicable_service_types", context)

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
        self.assertIsNone(findings[0].confidence)
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

    def test_review_context_includes_learned_feedback_from_closest_candidates(self) -> None:
        result = HarmonizationResult(
            scope_name="service",
            entities={
                "pending-service-step": HarmonizedEntity(
                    entity_id="pending-service-step",
                    entity_type="RepairServiceStep",
                    text_harmonization={
                        "diagnose": {
                            "original_value": "pump makes a hydraulic humming noise",
                            "status": "unresolved",
                            "closest_candidates": [
                                {
                                    "concept_id": "pump_fault",
                                    "label": "Pump fault",
                                    "confidence": 0.64,
                                    "match_type": "learned_feedback_semantic",
                                    "source": "learned_feedback",
                                    "feedback_id": "feedback-001",
                                }
                            ],
                        }
                    },
                )
            },
        )

        context = _build_review_context(
            result,
            deterministic_findings=[],
            review_context={"selectedPartLabel": "Vibration Pump"},
        )

        text_entry = context["service_steps"][0]["text_entries"][0]
        learned_candidates = text_entry["learned_feedback_candidates"]

        self.assertEqual(["learned_feedback"], text_entry["evidence_sources"])
        self.assertEqual(1, len(learned_candidates))
        self.assertEqual("pump_fault", learned_candidates[0]["concept_id"])
        self.assertEqual("learned_feedback_semantic", learned_candidates[0]["match_type"])
        self.assertEqual("feedback-001", learned_candidates[0]["feedback_id"])
        self.assertEqual("candidate", learned_candidates[0]["decision_role"])

    def test_review_context_omits_trace_only_learned_feedback_below_candidate_threshold(self) -> None:
        result = HarmonizationResult(
            scope_name="service",
            entities={
                "pending-service-step": HarmonizedEntity(
                    entity_id="pending-service-step",
                    entity_type="RepairServiceStep",
                    text_harmonization={
                        "diagnose": {
                            "original_value": "grinder motor burned out",
                            "status": "unresolved",
                            "closest_candidates": [
                                {
                                    "concept_id": "pump_fault",
                                    "label": "Pump fault",
                                    "confidence": 0.22,
                                    "match_type": "learned_feedback_semantic",
                                    "source": "learned_feedback",
                                    "feedback_id": "feedback-001",
                                }
                            ],
                        }
                    },
                )
            },
        )

        context = _build_review_context(
            result,
            deterministic_findings=[],
            review_context={"selectedPartLabel": "Vibration Pump"},
        )

        text_entry = context["service_steps"][0]["text_entries"][0]

        self.assertEqual([], text_entry["learned_feedback_candidates"])
        self.assertEqual([], text_entry["candidate_concepts"])
        self.assertEqual([], text_entry["evidence_sources"])
        self.assertEqual(1, text_entry["trace_only_candidates_omitted"])


if __name__ == "__main__":
    unittest.main()
