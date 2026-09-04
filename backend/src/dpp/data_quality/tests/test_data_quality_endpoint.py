"""HTTP contract tests for the stateless data-quality run endpoint."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

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


if __name__ == "__main__":
    unittest.main()
