from __future__ import annotations

import unittest

from dpp.data_quality.anomaly.features import FeatureRow
from dpp.data_quality.anomaly.ml import (
    IsolationForestConfig,
    MLAnomalyOptions,
    build_ml_anomaly_analysis,
    build_ml_anomaly_findings,
)


class AnomalyMlTests(unittest.TestCase):
    def test_product_feature_row_gets_statistical_and_isolation_forest_findings(self) -> None:
        row = FeatureRow(
            scope_name="product",
            feature_set="product_usage_graph",
            entity_id="product-row-001",
            entity_type="DPPInstance",
            features={
                "operatingHRS": 120.0,
                "brewingCount": 100.0,
                "cleaningCount": 140.0,
                "chalkCount": 130.0,
                "coffeeGrindingCount": 30.0,
                "cleaning_to_brewing_ratio": 1.4,
                "chalk_to_brewing_ratio": 1.3,
                "grinding_to_brewing_ratio": 0.3,
                "brews_per_operating_hour": 0.833333,
                "max_material_weight_to_part_weight": 1.6,
                "product_weightGRM": 750.0,
                "active_part_weightGRM": 2400.0,
                "active_part_weight_to_product_weight": 3.2,
            },
        )

        findings = build_ml_anomaly_findings([row])
        check_methods = {finding.evidence["check_method"] for finding in findings}

        self.assertIn("z_score", check_methods)
        self.assertIn("iqr", check_methods)
        self.assertIn("isolation_forest", check_methods)

    def test_service_scope_without_feature_rows_returns_no_ml_findings(self) -> None:
        self.assertEqual([], build_ml_anomaly_findings([]))

    def test_isolation_forest_can_be_disabled_while_statistical_findings_remain(self) -> None:
        row = FeatureRow(
            scope_name="product",
            feature_set="product_usage_graph",
            entity_id="product-row-001",
            entity_type="DPPInstance",
            features={
                "operatingHRS": 120.0,
                "brewingCount": 100.0,
                "cleaningCount": 140.0,
                "chalkCount": 130.0,
                "coffeeGrindingCount": 30.0,
                "cleaning_to_brewing_ratio": 1.4,
                "chalk_to_brewing_ratio": 1.3,
                "grinding_to_brewing_ratio": 0.3,
                "brews_per_operating_hour": 0.833333,
                "max_material_weight_to_part_weight": 1.6,
                "product_weightGRM": 750.0,
                "active_part_weightGRM": 2400.0,
                "active_part_weight_to_product_weight": 3.2,
            },
        )

        findings = build_ml_anomaly_findings(
            [row],
            options=MLAnomalyOptions(isolation_forest=IsolationForestConfig(enabled=False)),
        )
        check_methods = {finding.evidence["check_method"] for finding in findings}

        self.assertIn("z_score", check_methods)
        self.assertIn("iqr", check_methods)
        self.assertNotIn("isolation_forest", check_methods)

    def test_uploaded_reference_rows_are_used_as_the_reference_profile(self) -> None:
        reference_rows = [
            FeatureRow(
                scope_name="product",
                feature_set="product_usage_graph",
                entity_id=f"uploaded-{index}",
                entity_type="UploadedReferenceRow",
                features={
                    "operatingHRS": float(100 + index * 10),
                    "brewingCount": float(400 + index * 20),
                },
            )
            for index in range(8)
        ]
        target = FeatureRow(
            scope_name="product",
            feature_set="product_usage_graph",
            entity_id="target-product",
            entity_type="DPPInstance",
            features={
                "operatingHRS": 5000.0,
                "brewingCount": 5.0,
                "target_only_feature": 1.0,
            },
        )

        analysis = build_ml_anomaly_analysis(
            [target],
            options=MLAnomalyOptions(
                isolation_forest=IsolationForestConfig(
                    n_estimators=50,
                    contamination=0.2,
                    max_samples=4,
                    random_state=7,
                ),
                reference_rows=reference_rows,
                reference_description="Test uploaded reference rows.",
            ),
        )

        profile = next(
            item
            for item in analysis.metadata["statistical_ml"]["profiles"]
            if item["scope_name"] == "product" and item["feature_set"] == "product_usage_graph"
        )
        self.assertEqual("user_uploaded", profile["reference_source"])
        self.assertEqual(8, profile["reference_rows"])
        self.assertEqual(["brewingCount", "operatingHRS"], profile["used_feature_names"])
        self.assertEqual(
            ["brewingCount", "operatingHRS"],
            profile["isolation_forest_feature_names"],
        )

        isolation_findings = [
            finding
            for finding in analysis.findings
            if finding.evidence["check_method"] == "isolation_forest"
        ]
        self.assertTrue(isolation_findings)
        self.assertEqual("user_uploaded", isolation_findings[0].evidence["reference_source"])
        self.assertEqual(50, isolation_findings[0].evidence["n_estimators"])
        self.assertEqual(0.2, isolation_findings[0].evidence["contamination"])
        self.assertEqual(4, isolation_findings[0].evidence["max_samples"])
        self.assertEqual(7, isolation_findings[0].evidence["random_state"])

    def test_uploaded_reference_batch_below_minimum_is_reported(self) -> None:
        target = FeatureRow(
            scope_name="product",
            feature_set="product_usage_graph",
            entity_id="target-product",
            entity_type="DPPInstance",
            features={"operatingHRS": 5000.0, "brewingCount": 5.0},
        )
        reference_rows = [
            FeatureRow(
                scope_name="product",
                feature_set="product_usage_graph",
                entity_id="uploaded-001",
                entity_type="UploadedReferenceRow",
                features={"operatingHRS": 100.0, "brewingCount": 400.0},
            )
        ]

        analysis = build_ml_anomaly_analysis(
            [target],
            options=MLAnomalyOptions(reference_rows=reference_rows),
        )

        finding = next(
            item
            for item in analysis.findings
            if item.check_id == "ml_reference_batch_too_small"
        )
        self.assertEqual("info", finding.severity)
        self.assertEqual("user_uploaded", finding.evidence["reference_source"])
        self.assertEqual({"minimum_reference_rows": 8}, finding.expected)


if __name__ == "__main__":
    unittest.main()
