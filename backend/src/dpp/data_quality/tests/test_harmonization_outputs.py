"""Tests for semantic JSON-LD serialization of harmonization output."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from dpp.data_quality.harmonization.mapper import map_field_label
from dpp.data_quality.harmonization.normalizers import normalize_enum_value
from dpp.data_quality.harmonization.outputs import build_clean_jsonld, build_harmonization_report
from dpp.data_quality.harmonization.services import harmonize_document
from dpp.data_quality.harmonization.free_text import normalize_text_value
from dpp.data_quality.harmonization.feedback import (
    approve_feedback_proposal,
    create_feedback_proposal,
)


EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples" / "harmonization"


def _load_example(filename: str) -> dict:
    with (EXAMPLES_DIR / filename).open("r", encoding="utf-8") as source:
        return json.load(source)


def _node_by_id(document: dict, entity_id: str) -> dict:
    return next(node for node in document["@graph"] if node["@id"] == entity_id)


class VocabularyAliasTests(unittest.TestCase):
    def test_minimal_llm_product_field_aliases_map_to_canonical_paths(self) -> None:
        expected_paths = {
            ("product name", "DPPStatic"): "DPPStatic.name",
            ("product type", "DPPStatic"): "DPPStatic.productClass",
            ("modular part", "PartInstance"): "PartInstance.isModular",
            ("failure state", "PartInstance"): "PartInstance.hasFailstate",
        }

        for (label, entity_type), expected_path in expected_paths.items():
            with self.subTest(label=label, entity_type=entity_type):
                candidate = map_field_label(label, "product", entity_type)
                self.assertIsNotNone(candidate)
                self.assertEqual(expected_path, candidate.canonical_path)

    def test_minimal_llm_emission_field_aliases_map_to_canonical_paths(self) -> None:
        expected_paths = {
            ("type of activity", "ActivityData"): "ActivityData.activity_type",
            ("ghg scope", "GHGEmissionRecord"): "GHGEmissionRecord.scope",
            ("scope3 category", "GHGEmissionRecord"): "GHGEmissionRecord.scope3_category",
            ("calculation method", "GHGEmissionRecord"): "GHGEmissionRecord.calculation_method",
            ("data provenance", "GHGEmissionRecord"): "GHGEmissionRecord.provenance",
        }

        for (label, entity_type), expected_path in expected_paths.items():
            with self.subTest(label=label, entity_type=entity_type):
                candidate = map_field_label(label, "emission", entity_type)
                self.assertIsNotNone(candidate)
                self.assertEqual(expected_path, candidate.canonical_path)

    def test_minimal_llm_emission_enum_aliases_normalize_to_canonical_values(self) -> None:
        expected_values = {
            ("ActivityData.activity_type", "travel distance"): "distance_traveled",
            ("ActivityData.activity_type", "fuel used"): "fuel_consumption",
            ("GHGEmissionRecord.scope", "scope1"): "scope_1",
            ("GHGEmissionRecord.scope3_category", "work travel"): "business_travel",
            ("GHGEmissionRecord.scope3_category", "sold product use"): "use_of_sold_products",
        }

        for (canonical_path, value), expected_value in expected_values.items():
            with self.subTest(canonical_path=canonical_path, value=value):
                self.assertEqual(
                    expected_value,
                    normalize_enum_value(canonical_path, value),
                )


class ServiceSurfaceFormTests(unittest.TestCase):
    def test_core_symptom_surface_forms_normalize_without_semantic_fallback(self) -> None:
        expected_concepts = {
            "water leak": "water_leakage",
            "not grinding": "grinder_not_working",
            "no coffee coming out": "no_coffee_output",
            "not heating water": "water_not_heating",
            "not piercing coffee capsules": "pod_not_pierced",
        }

        for text, expected_concept in expected_concepts.items():
            with self.subTest(text=text):
                result = normalize_text_value("symptom", text, enable_semantic=False)
                self.assertEqual("normalized", result.status)
                self.assertEqual(expected_concept, result.normalized_concept)
                self.assertEqual("alias", result.method)

    def test_core_diagnosis_surface_forms_normalize_without_semantic_fallback(self) -> None:
        expected_concepts = {
            "pump dead": "pump_fault",
            "clogged with limescale": "limescale_or_scale_build_up",
            "faulty solenoid": "valve_or_solenoid_fault",
            "plug fuse blown": "fuse_or_thermal_fuse_fault",
            "plunger cannot pierce capsules": "pod_mechanism_or_lid_fault",
        }

        for text, expected_concept in expected_concepts.items():
            with self.subTest(text=text):
                result = normalize_text_value("diagnosis", text, enable_semantic=False)
                self.assertEqual("normalized", result.status)
                self.assertEqual(expected_concept, result.normalized_concept)
                self.assertEqual("alias", result.method)

    def test_review_candidate_service_concept_is_reported_separately(self) -> None:
        document = {
            "@context": {"dpp": "https://example.org/dpp#"},
            "@graph": [
                {
                    "@id": "service-001",
                    "@type": "dpp:ReplaceServiceStep",
                    "diagnose": "dull burrs",
                }
            ],
        }

        result = harmonize_document(document, "service")
        entity = result.entities["service-001"]
        report_entry = entity.text_harmonization["diagnose"]

        self.assertEqual("dull_burrs", report_entry["normalized_value"])
        self.assertEqual("review_candidate", report_entry["inventory_status"])
        self.assertTrue(
            any("review-candidate" in issue.message for issue in entity.issues)
        )


class FeedbackProposalTests(unittest.TestCase):
    def test_feedback_proposal_stays_separate_from_core_registry(self) -> None:
        proposal = create_feedback_proposal(
            action="propose_surface_form",
            scope_name="service",
            entity_type="RepairServiceStep",
            field_path="RepairServiceStep.diagnose",
            original_value="pump sounds dead",
            concept_id="pump_fault",
            proposed_surface_form="pump sounds dead",
            reviewer="local_user",
        )
        approved = approve_feedback_proposal(
            proposal,
            reviewer="local_user",
            rationale="Accepted as local evidence only.",
        )

        self.assertEqual("proposed", proposal.status)
        self.assertEqual("approved", approved.status)
        self.assertEqual("pump_fault", approved.as_dict()["concept_id"])
        self.assertEqual("pump sounds dead", approved.as_dict()["proposed_surface_form"])


class CleanJsonLdOutputTests(unittest.TestCase):
    def test_emission_output_uses_legacy_jsonld_vocabulary_terms(self) -> None:
        document = _load_example("enum_alias_input.json")
        result = harmonize_document(document, "emission")

        output = build_clean_jsonld(result, document=document)
        record = _node_by_id(output, "record-enum-001")
        activity = record["dpp:activity"]

        self.assertEqual("dpp:ActivityData", activity["@type"])
        self.assertEqual("electricity_consumption", activity["dpp:activityType"])
        self.assertNotIn("@id", activity)
        self.assertNotIn("dpp:activity_type", activity)
        self.assertEqual("purchased_goods_and_services", record["dpp:scope3Category"])
        self.assertEqual("dpp:EmissionFactor", record["dpp:emissionFactor"]["@type"])
        self.assertNotIn("dpp:emission_factor", record)

        roundtrip = harmonize_document(output, "emission")
        roundtrip_record = roundtrip.entities["record-enum-001"]
        self.assertEqual(
            "ActivityData",
            roundtrip_record.embedded_entities["activity"][0].entity_type,
        )
        self.assertEqual([], roundtrip_record.relations)

        report = build_harmonization_report(result)
        fields = report["entities"]["record-enum-001/activity/0"]["fields"]
        self.assertEqual("dpp:activityType", fields["ActivityData.activity_type"]["jsonld_term"])
        self.assertEqual("unit_validation", fields["ActivityData.quantity"]["value_method"])

    def test_product_output_keeps_entity_identity_and_emits_schema_measurements(self) -> None:
        document = _load_example("product_dirty.json")
        result = harmonize_document(document, "product")

        output = build_clean_jsonld(result, document=document)
        product = _node_by_id(output, "dpp-static-001")
        instance = _node_by_id(output, "dpp-instance-001")

        self.assertEqual(["dpp:DPPStatic", "schema:ProductModel"], product["@type"])
        self.assertEqual(
            {
                "@type": "schema:QuantitativeValue",
                "name": "weight",
                "value": 2500.0,
                "unitCode": "GRM",
            },
            product["schema:weight"],
        )
        self.assertEqual({"@id": "dpp-static-001"}, instance["isVariantOf"])
        self.assertEqual({"@id": "part-instance-top-001"}, instance["schema:hasPart"])
        additional_properties = {
            item["name"]: item for item in instance["schema:additionalProperty"]
        }
        self.assertEqual(120.0, additional_properties["operatingHRS"]["value"])
        self.assertEqual("HRS", additional_properties["operatingHRS"]["unitCode"])
        self.assertEqual(300.0, additional_properties["brewingCount"]["value"])
        self.assertEqual(12.0, additional_properties["cleaningCount"]["value"])
        self.assertEqual(3.0, additional_properties["chalkCount"]["value"])
        self.assertEqual(295.0, additional_properties["coffeeGrindingCount"]["value"])
        self.assertNotIn("unitCode", additional_properties["brewingCount"])
        self.assertNotIn("dpp:operatingHRS", instance)

        material = output["@graph"][2]["dpp:compositeMaterials"][0]
        self.assertEqual(
            [
                {
                    "@type": "schema:PropertyValue",
                    "name": "percentRecycled",
                    "value": 30.0,
                }
            ],
            material["additionalProperty"],
        )
        self.assertEqual(0.95, material["dpp:purityLevel"])

        roundtrip = harmonize_document(output, "product")
        roundtrip_instance = roundtrip.entities["dpp-instance-001"]
        roundtrip_part = roundtrip.entities["part-instance-top-001"]
        self.assertEqual(
            120.0,
            roundtrip_instance.fields["DPPInstance.operatingHRS"].normalized_value,
        )
        self.assertEqual(
            ["dppStaticLink", "partInstanceLink"],
            [relation.relation_name for relation in roundtrip_instance.relations],
        )
        self.assertEqual(
            ["material-instance-001"],
            [child.entity_id for child in roundtrip_part.embedded_entities["compositeMaterials"]],
        )
        self.assertEqual([], roundtrip.entities["dpp-static-001"].unmapped_fields)

    def test_service_cost_output_uses_legacy_price_specification_container(self) -> None:
        document = _load_example("service_anomaly_input.json")
        result = harmonize_document(document, "service")

        output = build_clean_jsonld(result, document=document)
        replacement = _node_by_id(output, "service-anomaly-replace-001")

        self.assertEqual(
            {
                "@type": "schema:PriceSpecification",
                "schema:price": 89.0,
                "schema:priceCurrency": "EUR",
            },
            replacement["priceSpecification"],
        )
        self.assertNotIn("dpp:costEur", replacement)

        roundtrip = harmonize_document(output, "service")
        self.assertEqual(
            89.0,
            roundtrip.entities["service-anomaly-replace-001"].fields[
                "ReplaceServiceStep.costEur"
            ].original_value,
        )

    def test_refurbishment_replacement_pairs_roundtrip_as_legacy_nested_parts(self) -> None:
        document = {
            "@context": {"dpp": "https://example.org/dpp#"},
            "@graph": [
                {
                    "@id": "refurbishment-001",
                    "@type": "dpp:RefurbishmentServiceStep",
                    "diagnose": "dull burrs",
                    "observedSymptoms": ["watery espresso"],
                    "replacedAndNewParts": [
                        [
                            "part-old-001",
                            {"@id": "part-new-001", "@type": "dpp:PartInstance"},
                        ]
                    ],
                    "costEur": 120.0,
                }
            ],
        }
        result = harmonize_document(document, "service")

        output = build_clean_jsonld(result, document=document)
        refurbishment = _node_by_id(output, "refurbishment-001")
        self.assertEqual(
            "part-old-001",
            refurbishment["dpp:replacedAndNewParts"][0][0],
        )
        self.assertEqual(
            "part-new-001",
            refurbishment["dpp:replacedAndNewParts"][0][1]["@id"],
        )

        roundtrip = harmonize_document(output, "service")
        self.assertEqual(
            [("part-old-001", "part-new-001")],
            [
                (existing_id, new_part.entity_id)
                for existing_id, new_part in roundtrip.entities[
                    "refurbishment-001"
                ].paired_embedded_entities["replacedAndNewParts"]
            ],
        )

    def test_output_context_defines_semantic_prefixes(self) -> None:
        document = _load_example("emission_dirty.json")
        document["@context"]["dpp"] = "https://incoming.example/dpp#"
        output = build_clean_jsonld(harmonize_document(document, "emission"), document=document)

        self.assertEqual("https://schema.org/", output["@context"]["schema"])
        self.assertEqual("https://example.org/dpp#", output["@context"]["dpp"])


if __name__ == "__main__":
    unittest.main()
