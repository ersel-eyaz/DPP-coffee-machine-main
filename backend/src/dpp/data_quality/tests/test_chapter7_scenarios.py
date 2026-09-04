"""Regression checks for the Chapter 7 evaluation scenarios."""

from __future__ import annotations

import csv
import json
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from dpp.data_quality.anomaly.features import FeatureRow
from dpp.data_quality.anomaly.ml import MLAnomalyOptions
from dpp.data_quality.anomaly.outputs import build_anomaly_report
from dpp.data_quality.anomaly.services import analyze_harmonization_result
from dpp.data_quality.harmonization.free_text import (
    TextNormalizationCandidate,
    resolve_text_value,
)
from dpp.data_quality.harmonization.normalizers import (
    EnumNormalizationCandidate,
    resolve_enum_value,
)
from dpp.data_quality.harmonization.outputs import build_clean_jsonld, build_harmonization_report
from dpp.data_quality.harmonization.services import harmonize_document

SCENARIO_DIR = Path(__file__).resolve().parents[1] / "examples" / "evaluation" / "chapter7"
REFERENCE_DIR = Path(__file__).resolve().parents[1] / "examples" / "reference"


class Chapter7BaselineTests(unittest.TestCase):
    def _load_document(self, filename: str) -> dict:
        with (SCENARIO_DIR / filename).open("r", encoding="utf-8") as source:
            return json.load(source)

    def _process(self, filename: str, scope_name: str) -> tuple[dict, dict, dict]:
        document = self._load_document(filename)
        result = harmonize_document(document, scope_name)
        return (
            build_clean_jsonld(result, document=document),
            build_harmonization_report(result),
            build_anomaly_report(analyze_harmonization_result(result)),
        )

    def _load_product_reference_rows(self) -> list[FeatureRow]:
        with (REFERENCE_DIR / "product_raw_usage_reference.csv").open(
            "r",
            encoding="utf-8",
            newline="",
        ) as source:
            records = list(csv.DictReader(source))

        rows: list[FeatureRow] = []
        for index, record in enumerate(records, start=1):
            operating = float(record["operatingHRS"])
            brewing = float(record["brewingCount"])
            cleaning = float(record["cleaningCount"])
            chalk = float(record["chalkCount"])
            grinding = float(record["coffeeGrindingCount"])
            product_weight = float(record["product_weightGRM"])
            active_part_weight = float(record["active_part_weightGRM"])
            rows.append(
                FeatureRow(
                    scope_name="product",
                    feature_set="product_usage_graph",
                    entity_id=f"uploaded-reference-{index:03d}",
                    entity_type="UploadedReferenceRow",
                    features={
                        "operatingHRS": operating,
                        "brewingCount": brewing,
                        "cleaningCount": cleaning,
                        "chalkCount": chalk,
                        "coffeeGrindingCount": grinding,
                        "cleaning_to_brewing_ratio": round(cleaning / brewing, 6),
                        "chalk_to_brewing_ratio": round(chalk / brewing, 6),
                        "grinding_to_brewing_ratio": round(grinding / brewing, 6),
                        "brews_per_operating_hour": round(brewing / operating, 6),
                        "max_material_weight_to_part_weight": float(record["max_material_weight_to_part_weight"]),
                        "product_weightGRM": product_weight,
                        "active_part_weightGRM": active_part_weight,
                        "active_part_weight_to_product_weight": round(
                            active_part_weight / product_weight,
                            6,
                        ),
                    },
                    evidence={"upload_format": "product_raw_csv"},
                )
            )
        return rows

    def _assert_clean_baseline(self, filename: str, scope_name: str) -> None:
        document = self._load_document(filename)

        first_result = harmonize_document(document, scope_name)
        first_report = build_harmonization_report(first_result)
        first_clean = build_clean_jsonld(first_result, document=document)
        anomaly_report = build_anomaly_report(analyze_harmonization_result(first_result))

        self.assertEqual(0, first_report["summary"]["unmapped_fields_total"])
        self.assertEqual(0, first_report["summary"]["issues_total"])
        self.assertEqual(0, anomaly_report["summary"]["findings_total"])

        second_result = harmonize_document(first_clean, scope_name)
        second_report = build_harmonization_report(second_result)
        second_clean = build_clean_jsonld(second_result, document=first_clean)

        self.assertEqual(first_clean, second_clean)
        self.assertEqual(0, second_report["summary"]["unmapped_fields_total"])
        self.assertEqual(0, second_report["summary"]["issues_total"])

    def test_product_baseline_is_clean_and_round_trip_stable(self) -> None:
        self._assert_clean_baseline("product_baseline.json", "product")

    def test_emission_baseline_is_clean_and_round_trip_stable(self) -> None:
        self._assert_clean_baseline("emission_baseline.json", "emission")

    def test_service_baseline_is_clean_and_round_trip_stable(self) -> None:
        self._assert_clean_baseline("service_baseline.json", "service")

    def test_product_harmonization_scenario_changes_only_weight_representation(self) -> None:
        baseline_clean, _, _ = self._process("product_baseline.json", "product")
        scenario_clean, report, anomaly = self._process("product_harmonization.json", "product")

        self.assertEqual(baseline_clean, scenario_clean)
        self.assertEqual(0, report["summary"]["unmapped_fields_total"])
        self.assertEqual(0, report["summary"]["issues_total"])
        self.assertEqual(0, anomaly["summary"]["findings_total"])

        product_report = report["entities"]["ch7-product-static-001"]
        weight = product_report["fields"]["DPPStatic.weightGRM"]
        self.assertEqual("modelWeight", weight["original_label"])
        self.assertEqual({"value": 9300.0, "unit": "GRM"}, weight["normalized_value"])
        self.assertEqual("unit_conversion", weight["value_method"])

    def test_product_similarity_scenario_uses_fuzzy_field_and_unit_matching(self) -> None:
        baseline_clean, _, _ = self._process("product_baseline.json", "product")
        scenario_clean, report, anomaly = self._process("product_similarity.json", "product")

        self.assertEqual(baseline_clean, scenario_clean)
        self.assertEqual(0, report["summary"]["unmapped_fields_total"])
        self.assertEqual(2, report["summary"]["issues_total"])
        self.assertEqual(0, anomaly["summary"]["findings_total"])

        weight = report["entities"]["ch7-product-static-001"]["fields"]["DPPStatic.weightGRM"]
        self.assertEqual("modelWeigh", weight["original_label"])
        self.assertEqual("fuzzy", weight["field_method"])
        self.assertAlmostEqual(0.9523809523809523, weight["field_confidence"])
        self.assertEqual({"value": 9300.0, "unit": "GRM"}, weight["normalized_value"])
        self.assertEqual("unit_conversion", weight["value_method"])
        self.assertAlmostEqual(0.9333333333333333, weight["value_confidence"])

    def test_emission_harmonization_scenario_reconstructs_the_baseline_output(self) -> None:
        baseline_clean, _, _ = self._process("emission_baseline.json", "emission")
        scenario_clean, report, anomaly = self._process("emission_harmonization.json", "emission")

        self.assertEqual(baseline_clean, scenario_clean)
        self.assertEqual(0, report["summary"]["unmapped_fields_total"])
        self.assertEqual(1, report["summary"]["issues_total"])
        self.assertEqual({"info": 1, "warning": 0, "error": 0}, report["summary"]["issue_severity_counts"])
        self.assertEqual(0, anomaly["summary"]["findings_total"])

    def test_emission_similarity_scenario_uses_fuzzy_and_semantic_value_matching(self) -> None:
        semantic_text = "indirect emissions from electricity bought by the company"
        semantic_candidate = EnumNormalizationCandidate(
            original_value=semantic_text,
            canonical_value="scope_2",
            confidence=0.7133847540373284,
            match_type="semantic",
        )

        def resolve_with_frozen_semantic_candidate(
            canonical_path: str,
            value: object,
            auto_threshold: float = 0.95,
            semantic_threshold: float = 0.55,
            enable_semantic: bool = True,
        ) -> EnumNormalizationCandidate | None:
            if canonical_path == "GHGEmissionRecord.scope" and value == semantic_text and enable_semantic:
                return semantic_candidate
            return resolve_enum_value(
                canonical_path,
                value,
                auto_threshold=auto_threshold,
                semantic_threshold=semantic_threshold,
                enable_semantic=enable_semantic,
            )

        # The real model result was verified when the fixture was frozen. The
        # stub keeps the deterministic test suite independent of model downloads.
        with (
            patch(
                "dpp.data_quality.harmonization.normalizers.resolve_enum_value",
                side_effect=resolve_with_frozen_semantic_candidate,
            ),
            patch(
                "dpp.data_quality.harmonization.services.resolve_enum_value",
                side_effect=resolve_with_frozen_semantic_candidate,
            ),
        ):
            baseline_clean, _, _ = self._process("emission_baseline.json", "emission")
            scenario_clean, report, anomaly = self._process("emission_similarity.json", "emission")

        self.assertEqual(baseline_clean, scenario_clean)
        self.assertEqual(0, report["summary"]["unmapped_fields_total"])
        self.assertEqual(2, report["summary"]["issues_total"])
        self.assertEqual(0, anomaly["summary"]["findings_total"])

        scope = report["entities"]["ch7-emission-record-001"]["fields"]["GHGEmissionRecord.scope"]
        activity_type = report["entities"]["ch7-emission-record-001/activity/0"]["fields"]["ActivityData.activity_type"]
        self.assertEqual("scope_2", scope["normalized_value"])
        self.assertEqual("semantic", scope["value_method"])
        self.assertAlmostEqual(0.7133847540373284, scope["value_confidence"])
        self.assertEqual("electricity_consumption", activity_type["normalized_value"])
        self.assertEqual("fuzzy", activity_type["value_method"])
        self.assertAlmostEqual(0.9696969696969697, activity_type["value_confidence"])

    def test_service_harmonization_scenario_preserves_unresolved_text_for_review(self) -> None:
        clean, report, anomaly = self._process("service_harmonization.json", "service")
        service_node = next(entity for entity in clean["@graph"] if entity["@id"] == "ch7-service-replace-001")
        service_report = report["entities"]["ch7-service-replace-001"]

        self.assertEqual("heating_element_failure", service_node["dpp:diagnose"])
        self.assertEqual(
            ["water_not_heating", "machine behaves strangely"],
            service_node["dpp:observedSymptoms"],
        )
        self.assertEqual(
            {"normalized": 2, "unresolved": 1},
            report["summary"]["text_harmonization_status_counts"],
        )
        unresolved = service_report["text_harmonization"]["observedSymptoms"][1]
        self.assertEqual("unresolved", unresolved["status"])
        self.assertEqual(["service_text_requires_review"], [item["check_id"] for item in anomaly["findings"]])

    def test_service_similarity_scenario_uses_semantic_and_fuzzy_text_matching(self) -> None:
        semantic_text = "the electric heating component has suffered an electrical failure"
        semantic_candidate = TextNormalizationCandidate(
            original_text=semantic_text,
            concept_id="heating_element_failure",
            label="Heating element failure",
            confidence=0.7402395355200592,
            match_type="semantic",
        )

        def resolve_with_frozen_semantic_candidate(
            kind: str,
            text: object,
            *,
            enable_semantic: bool = True,
        ) -> TextNormalizationCandidate | None:
            if kind == "diagnosis" and text == semantic_text and enable_semantic:
                return semantic_candidate
            return resolve_text_value(kind, text, enable_semantic=enable_semantic)

        # The real model result was verified when the fixture was frozen. The
        # stub keeps the deterministic test suite independent of model downloads.
        with patch(
            "dpp.data_quality.harmonization.free_text.resolve_text_value",
            side_effect=resolve_with_frozen_semantic_candidate,
        ):
            baseline_clean, _, _ = self._process("service_baseline.json", "service")
            scenario_clean, report, anomaly = self._process("service_similarity.json", "service")

        self.assertEqual(baseline_clean, scenario_clean)
        self.assertEqual(0, report["summary"]["unmapped_fields_total"])
        self.assertEqual(2, report["summary"]["issues_total"])
        self.assertEqual(0, anomaly["summary"]["findings_total"])

        text_report = report["entities"]["ch7-service-replace-001"]["text_harmonization"]
        diagnosis = text_report["diagnose"]
        symptom = text_report["observedSymptoms"][0]
        self.assertEqual("heating_element_failure", diagnosis["normalized_value"])
        self.assertEqual("semantic", diagnosis["method"])
        self.assertAlmostEqual(0.7402395355200592, diagnosis["confidence"])
        self.assertEqual("water_not_heating", symptom["normalized_value"])
        self.assertEqual("fuzzy", symptom["method"])
        self.assertAlmostEqual(0.9696969696969697, symptom["confidence"])

    def test_product_anomaly_scenario_has_the_frozen_findings(self) -> None:
        _, report, anomaly = self._process("product_anomaly.json", "product")

        self.assertEqual(0, report["summary"]["issues_total"])
        self.assertEqual(
            Counter(
                {
                    "product_height_range": 1,
                    "product_profile_range_mismatch": 1,
                    "material_weight_exceeds_part_weight": 1,
                    "active_part_tree_weight_exceeds_product_weight": 1,
                    "part_weight_exceeds_product_weight": 1,
                    "grinding_brewing_counter_deviation": 1,
                    "brewing_per_operating_hour_high": 1,
                    "maintenance_to_brewing_ratio_high": 2,
                    "statistical_z_score_outlier": 1,
                    "statistical_iqr_outlier": 1,
                    "isolation_forest_feature_pattern_outlier": 1,
                }
            ),
            Counter(item["check_id"] for item in anomaly["findings"]),
        )

    def test_product_anomaly_scenario_accepts_the_external_csv_reference_batch(self) -> None:
        document = self._load_document("product_anomaly.json")
        result = harmonize_document(document, "product")
        anomaly = build_anomaly_report(
            analyze_harmonization_result(
                result,
                ml_options=MLAnomalyOptions(
                    reference_rows=self._load_product_reference_rows(),
                    reference_description="Chapter 7 product CSV reference batch.",
                ),
            )
        )
        profile = anomaly["metadata"]["statistical_ml"]["profiles"][0]

        self.assertEqual("user_uploaded", profile["reference_source"])
        self.assertEqual(10, profile["reference_rows"])
        self.assertTrue(profile["usable"])
        self.assertEqual(
            {
                "statistical_z_score_outlier",
                "statistical_iqr_outlier",
                "isolation_forest_feature_pattern_outlier",
            },
            {item["check_id"] for item in anomaly["findings"] if item["category"] == "statistical"},
        )

    def test_emission_anomaly_scenario_has_the_frozen_findings(self) -> None:
        _, report, anomaly = self._process("emission_anomaly.json", "emission")

        self.assertEqual(0, report["summary"]["issues_total"])
        self.assertEqual(
            {
                "emission_unit_incompatibility",
                "zero_reported_emissions_with_positive_inputs",
                "emission_record_calculation_mismatch",
                "scope3_category_missing",
                "statistical_iqr_outlier",
            },
            {item["check_id"] for item in anomaly["findings"]},
        )

    def test_service_structure_scenario_has_the_frozen_findings(self) -> None:
        _, report, anomaly = self._process("service_structure.json", "service")

        self.assertEqual(0, report["summary"]["issues_total"])
        self.assertTrue(anomaly["summary"]["has_errors"])
        self.assertEqual(
            {
                "missing_required_embedded_object",
                "replacement_part_static_mismatch",
                "replacement_instance_id_reused",
            },
            {item["check_id"] for item in anomaly["findings"]},
        )


if __name__ == "__main__":
    unittest.main()
