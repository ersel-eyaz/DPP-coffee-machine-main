"""HTTP contract tests for the stateless data-quality run endpoint."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dpp.data_quality.harmonization.services import harmonize_document
from dpp.routers.data_quality import router

EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples" / "harmonization"


class DataQualityRunEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        app = FastAPI()
        app.include_router(router, prefix="/data-quality")
        cls.client = TestClient(app)
        with (EXAMPLES_DIR / "product_dirty.json").open("r", encoding="utf-8") as source:
            cls.product_document = json.load(source)

    def test_request_schema_error_returns_http_422(self) -> None:
        response = self.client.post(
            "/data-quality/run",
            json={
                "scope": "product",
                "mode": "unsupported-mode",
                "document": self.product_document,
            },
        )

        self.assertEqual(422, response.status_code)

    def test_processing_error_returns_http_400(self) -> None:
        response = self.client.post(
            "/data-quality/run",
            json={"scope": "product", "mode": "harmonization", "document": {}},
        )

        self.assertEqual(400, response.status_code)
        self.assertIn("Harmonization failed", response.json()["detail"])

    def test_modes_return_the_expected_component_reports(self) -> None:
        for mode, expects_anomaly_report in (
            ("harmonization", False),
            ("anomaly", True),
            ("both", True),
        ):
            with self.subTest(mode=mode):
                response = self.client.post(
                    "/data-quality/run",
                    json={
                        "scope": "product",
                        "mode": mode,
                        "document": self.product_document,
                        "anomaly_options": {"isolation_forest": {"enabled": False}},
                    },
                )

                self.assertEqual(200, response.status_code)
                payload = response.json()
                self.assertEqual(mode, payload["mode"])
                self.assertIn("data", payload)
                self.assertIn("harmonization_report", payload)
                self.assertEqual(expects_anomaly_report, "anomaly_report" in payload)

    def test_service_run_passes_resolved_model_context_to_harmonization(self) -> None:
        document = {
            "@context": {"dpp": "https://example.org/dpp#"},
            "@graph": [
                {
                    "@id": "service-001",
                    "@type": "dpp:RepairServiceStep",
                    "diagnose": "pump is dead",
                }
            ],
        }

        with (
            patch(
                "dpp.routers.data_quality._dpp_static_id_for_instance",
                new=AsyncMock(return_value="model-a"),
            ),
            patch(
                "dpp.routers.data_quality.harmonize_document",
                wraps=harmonize_document,
            ) as harmonize_spy,
        ):
            response = self.client.post(
                "/data-quality/run",
                json={
                    "scope": "service",
                    "mode": "harmonization",
                    "document": document,
                    "selected_instance_id": "instance-a",
                },
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            "model-a",
            harmonize_spy.call_args.kwargs["learned_feedback_dpp_static_id"],
        )

    def test_feedback_endpoint_persists_resolved_product_model_context(self) -> None:
        with (
            patch(
                "dpp.routers.data_quality._dpp_static_id_for_instance",
                new=AsyncMock(return_value="model-a"),
            ),
            patch(
                "dpp.routers.data_quality.append_feedback_record",
                side_effect=lambda proposal: proposal,
            ),
        ):
            response = self.client.post(
                "/data-quality/feedback/service-text",
                json={
                    "selected_instance_id": "instance-a",
                    "entity_type": "RepairServiceStep",
                    "field_path": "RepairServiceStep.diagnose",
                    "original_value": "hydraulic humming cycle",
                    "concept_id": "pump_fault",
                },
            )

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("model-a", payload["feedback"]["dpp_static_id"])
        self.assertEqual("model-a", payload["learned_mapping"]["dpp_static_id"])

    def test_candidate_report_uses_only_feedback_from_selected_product_model(self) -> None:
        feedback_records = [
            {
                "proposal_id": "feedback-model-a",
                "action": "accept_mapping",
                "status": "approved",
                "scope_name": "service",
                "entity_type": "RepairServiceStep",
                "field_path": "RepairServiceStep.diagnose",
                "original_value": "hydraulic humming cycle",
                "dpp_static_id": "model-a",
                "concept_id": "pump_fault",
                "proposed_surface_form": "hydraulic humming cycle",
            },
            {
                "proposal_id": "feedback-model-b",
                "action": "accept_mapping",
                "status": "approved",
                "scope_name": "service",
                "entity_type": "RepairServiceStep",
                "field_path": "RepairServiceStep.diagnose",
                "original_value": "foreign model phrase",
                "dpp_static_id": "model-b",
                "concept_id": "pump_fault",
                "proposed_surface_form": "foreign model phrase",
            },
        ]
        old_path = os.environ.get("DPP_DQ_LEARNED_FEEDBACK_PATH")
        with tempfile.TemporaryDirectory() as tmpdir:
            feedback_path = Path(tmpdir) / "learned_feedback.json"
            feedback_path.write_text(json.dumps({"feedback": feedback_records}), encoding="utf-8")
            os.environ["DPP_DQ_LEARNED_FEEDBACK_PATH"] = str(feedback_path)
            try:
                with patch(
                    "dpp.routers.data_quality._same_model_instances",
                    new=AsyncMock(return_value=("model-a", [])),
                ):
                    response = self.client.post(
                        "/data-quality/service-concept-candidates",
                        json={"selected_instance_id": "instance-a"},
                    )
            finally:
                if old_path is None:
                    os.environ.pop("DPP_DQ_LEARNED_FEEDBACK_PATH", None)
                else:
                    os.environ["DPP_DQ_LEARNED_FEEDBACK_PATH"] = old_path

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(1, payload["sources"]["learned_feedback_observations"])
        self.assertEqual(
            ["feedback-model-a"],
            payload["core_alias_candidates"][0]["feedback_ids"],
        )

    def test_metric_interpretation_uses_compact_non_redundant_prompt(self) -> None:
        api_response = MagicMock()
        api_response.json.return_value = {
            "output_text": json.dumps(
                {
                    "summary": "Compact summary.",
                    "points": ["Point one."],
                    "limitations": ["Small sample."],
                }
            )
        }
        api_response.raise_for_status.return_value = None

        async_client = MagicMock()
        async_client.post = AsyncMock(return_value=api_response)
        async_context = MagicMock()
        async_context.__aenter__ = AsyncMock(return_value=async_client)
        async_context.__aexit__ = AsyncMock(return_value=None)

        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False),
            patch("dpp.routers.data_quality.httpx.AsyncClient", return_value=async_context),
        ):
            response = self.client.post(
                "/data-quality/service-concept-candidates/metric-interpretation",
                json={
                    "clustering_quality": {"clusters_total": 3},
                    "sources": {"observations_total": 4},
                    "parameters": {"cluster_similarity_threshold": 0.72},
                },
            )

        self.assertEqual(200, response.status_code)
        request_payload = async_client.post.await_args.kwargs["json"]
        user_context = json.loads(request_payload["input"][1]["content"])
        response_schema = request_payload["text"]["format"]["schema"]

        self.assertNotIn("constraints", user_context)
        self.assertEqual(4, response_schema["properties"]["points"]["maxItems"])
        self.assertEqual(3, response_schema["properties"]["limitations"]["maxItems"])
        self.assertEqual("ok", response.json()["status"])


if __name__ == "__main__":
    unittest.main()
