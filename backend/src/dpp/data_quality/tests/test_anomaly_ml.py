from __future__ import annotations

import unittest

from dpp.data_quality.anomaly.features import FeatureRow
from dpp.data_quality.anomaly.ml import build_ml_anomaly_findings


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


if __name__ == "__main__":
    unittest.main()
