"""Validation tests for request-level statistical/ML configuration."""

from __future__ import annotations

import unittest

from fastapi import HTTPException
from pydantic import ValidationError

from dpp.routers.data_quality import (
    DataQualityIsolationForestOptions,
    DataQualityRunRequest,
    _ml_options_from_request,
)


class AnomalyOptionTests(unittest.TestCase):
    def test_random_state_must_fit_the_supported_seed_range(self) -> None:
        with self.assertRaises(ValidationError):
            DataQualityIsolationForestOptions(random_state=-1)

        with self.assertRaises(ValidationError):
            DataQualityIsolationForestOptions(random_state=4294967296)

    def test_max_samples_above_one_must_be_an_integer_row_count(self) -> None:
        request = DataQualityRunRequest(
            scope="product",
            document={},
            anomaly_options={"isolation_forest": {"max_samples": 1.5}},
        )

        with self.assertRaises(HTTPException) as context:
            _ml_options_from_request(request, "product")

        self.assertEqual(400, context.exception.status_code)
        self.assertIn("integer row counts", context.exception.detail)

    def test_fractional_and_integer_max_samples_are_supported(self) -> None:
        for value in (0.5, 4):
            request = DataQualityRunRequest(
                scope="product",
                document={},
                anomaly_options={"isolation_forest": {"max_samples": value}},
            )

            options = _ml_options_from_request(request, "product")

            self.assertEqual(float(value), options.isolation_forest.max_samples)


if __name__ == "__main__":
    unittest.main()
