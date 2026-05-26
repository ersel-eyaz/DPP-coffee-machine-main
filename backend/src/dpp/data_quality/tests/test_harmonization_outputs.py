"""Tests for semantic JSON-LD serialization of harmonization output."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from dpp.data_quality.harmonization.outputs import build_clean_jsonld, build_harmonization_report
from dpp.data_quality.harmonization.services import harmonize_document


EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples" / "harmonization"


def _load_example(filename: str) -> dict:
    with (EXAMPLES_DIR / filename).open("r", encoding="utf-8") as source:
        return json.load(source)


def _node_by_id(document: dict, entity_id: str) -> dict:
    return next(node for node in document["@graph"] if node["@id"] == entity_id)


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
                "schema:name": "weight",
                "schema:value": 2500.0,
                "schema:unitCode": "GRM",
            },
            product["schema:weight"],
        )
        self.assertEqual({"@id": "dpp-static-001"}, instance["schema:isVariantOf"])
        self.assertEqual({"@id": "part-instance-top-001"}, instance["schema:hasPart"])

        roundtrip = harmonize_document(output, "product")
        roundtrip_instance = roundtrip.entities["dpp-instance-001"]
        roundtrip_part = roundtrip.entities["part-instance-top-001"]
        self.assertEqual(
            ["dppStaticLink", "partInstanceLink"],
            [relation.relation_name for relation in roundtrip_instance.relations],
        )
        self.assertEqual(
            ["material-instance-001"],
            [child.entity_id for child in roundtrip_part.embedded_entities["compositeMaterials"]],
        )
        self.assertEqual([], roundtrip.entities["dpp-static-001"].unmapped_fields)

    def test_output_context_defines_semantic_prefixes(self) -> None:
        document = _load_example("emission_dirty.json")
        document["@context"]["dpp"] = "https://incoming.example/dpp#"
        output = build_clean_jsonld(harmonize_document(document, "emission"), document=document)

        self.assertEqual("https://schema.org/", output["@context"]["schema"])
        self.assertEqual("https://example.org/dpp#", output["@context"]["dpp"])


if __name__ == "__main__":
    unittest.main()
