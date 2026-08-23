"""Tests for semantic JSON-LD serialization of harmonization output."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from dpp.data_quality.anomaly.outputs import build_anomaly_report
from dpp.data_quality.anomaly.services import analyze_harmonization_result
from dpp.data_quality.harmonization.mapper import map_field_label
from dpp.data_quality.harmonization.normalizers import (
    normalize_enum_value,
    normalize_unit_label,
    normalize_value_to_unit,
    resolve_enum_value,
)
from dpp.data_quality.harmonization.outputs import build_clean_jsonld, build_harmonization_report
from dpp.data_quality.harmonization.services import harmonize_document
from dpp.data_quality.harmonization import free_text as free_text_module
from dpp.data_quality.harmonization.free_text import normalize_text_value
from dpp.data_quality.harmonization.feedback import (
    append_feedback_record,
    approve_feedback_proposal,
    create_feedback_proposal,
    load_learned_service_text_mappings,
)


EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples" / "harmonization"


def _load_example(filename: str) -> dict:
    with (EXAMPLES_DIR / filename).open("r", encoding="utf-8") as source:
        return json.load(source)


def _node_by_id(document: dict, entity_id: str) -> dict:
    return next(node for node in document["@graph"] if node["@id"] == entity_id)


class VocabularyAliasTests(unittest.TestCase):
    def test_llm_generated_product_field_aliases_map_to_canonical_paths(self) -> None:
        expected_paths = {
            ("product name", "DPPStatic"): "DPPStatic.name",
            ("product category", "DPPStatic"): "DPPStatic.productClass",
        }

        for (label, entity_type), expected_path in expected_paths.items():
            with self.subTest(label=label, entity_type=entity_type):
                candidate = map_field_label(label, "product", entity_type)
                self.assertIsNotNone(candidate)
                self.assertEqual(expected_path, candidate.canonical_path)

    def test_llm_generated_emission_field_aliases_map_to_canonical_paths(self) -> None:
        expected_paths = {
            ("activity type", "ActivityData"): "ActivityData.activity_type",
            ("ghg scope", "GHGEmissionRecord"): "GHGEmissionRecord.scope",
            ("scope3 category", "GHGEmissionRecord"): "GHGEmissionRecord.scope3_category",
            ("calculation method", "GHGEmissionRecord"): "GHGEmissionRecord.calculation_method",
            ("data source", "GHGEmissionRecord"): "GHGEmissionRecord.provenance",
        }

        for (label, entity_type), expected_path in expected_paths.items():
            with self.subTest(label=label, entity_type=entity_type):
                candidate = map_field_label(label, "emission", entity_type)
                self.assertIsNotNone(candidate)
                self.assertEqual(expected_path, candidate.canonical_path)

    def test_llm_generated_emission_enum_aliases_normalize_to_canonical_values(self) -> None:
        expected_values = {
            ("ActivityData.activity_type", "travel distance"): "distance_traveled",
            ("ActivityData.activity_type", "fuel use"): "fuel_consumption",
            ("GHGEmissionRecord.scope", "scope 1"): "scope_1",
            ("GHGEmissionRecord.scope3_category", "work travel"): "business_travel",
            ("GHGEmissionRecord.scope3_category", "sold product use"): "use_of_sold_products",
        }

        for (canonical_path, value), expected_value in expected_values.items():
            with self.subTest(canonical_path=canonical_path, value=value):
                self.assertEqual(
                    expected_value,
                    normalize_enum_value(canonical_path, value),
                )

    def test_enum_value_uses_the_vocabulary_selected_by_the_mapped_label(self) -> None:
        scope_candidate = resolve_enum_value(
            "GHGEmissionRecord.scope",
            "scope 1",
            enable_semantic=False,
        )
        scope3_candidate = resolve_enum_value(
            "GHGEmissionRecord.scope3_category",
            "scope 1",
            enable_semantic=False,
        )

        self.assertIsNotNone(scope_candidate)
        self.assertEqual("scope_1", scope_candidate.canonical_value)
        self.assertIsNone(scope3_candidate)


class ServiceSurfaceFormTests(unittest.TestCase):
    def test_core_symptom_surface_forms_normalize_without_semantic_fallback(self) -> None:
        expected_concepts = {
            "water leak": "water_leakage",
            "coffee grinder not grinding": "grinder_not_working",
            "no coffee coming out": "no_coffee_output",
            "not heating water": "water_not_heating",
            "not piercing coffee capsules": "pod_not_pierced",
            "Leaks water from pod": "pod_area_leakage",
        }

        for text, expected_concept in expected_concepts.items():
            with self.subTest(text=text):
                result = normalize_text_value("symptom", text, enable_semantic=False)
                self.assertEqual("normalized", result.status)
                self.assertEqual(expected_concept, result.normalized_concept)
                self.assertEqual("alias", result.method)

        for generic_text in ("Leaking", "not working"):
            with self.subTest(text=generic_text):
                result = normalize_text_value("symptom", generic_text, enable_semantic=False)
                self.assertEqual("unresolved", result.status)
                self.assertIsNone(result.normalized_concept)

    def test_core_diagnosis_surface_forms_normalize_without_semantic_fallback(self) -> None:
        expected_concepts = {
            "pump is dead": "pump_fault",
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
                    "diagnose": "thermostat not working",
                }
            ],
        }

        result = harmonize_document(document, "service")
        entity = result.entities["service-001"]
        report_entry = entity.text_harmonization["diagnose"]

        self.assertEqual("thermostat_or_rheostat_fault", report_entry["normalized_value"])
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
        )

        self.assertEqual("proposed", proposal.status)
        self.assertEqual("approved", approved.status)
        self.assertEqual("pump_fault", approved.as_dict()["concept_id"])
        self.assertEqual("pump sounds dead", approved.as_dict()["proposed_surface_form"])

    def test_approved_feedback_loads_as_learned_service_text_mapping(self) -> None:
        proposal = create_feedback_proposal(
            action="accept_mapping",
            scope_name="service",
            entity_type="RepairServiceStep",
            field_path="RepairServiceStep.diagnose",
            original_value="hydraulic humming cycle",
            concept_id="pump_fault",
            proposed_surface_form="hydraulic humming cycle",
            reviewer="prototype_review",
        )
        approved = approve_feedback_proposal(
            proposal,
            reviewer="prototype_review",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            feedback_path = Path(tmpdir) / "learned_feedback.json"
            feedback_path.write_text(
                json.dumps({"feedback": [approved.as_dict()]}),
                encoding="utf-8",
            )

            mappings = load_learned_service_text_mappings(feedback_path)

        self.assertEqual(1, len(mappings))
        self.assertEqual("diagnosis", mappings[0].kind)
        self.assertEqual("pump_fault", mappings[0].concept_id)
        self.assertEqual("hydraulic humming cycle", mappings[0].surface_form)

    def test_learned_feedback_exact_match_is_reported_as_review_candidate_not_core_normalization(self) -> None:
        proposal = create_feedback_proposal(
            action="accept_mapping",
            scope_name="service",
            entity_type="RepairServiceStep",
            field_path="RepairServiceStep.diagnose",
            original_value="hydraulic humming cycle",
            concept_id="pump_fault",
            proposed_surface_form="hydraulic humming cycle",
            reviewer="prototype_review",
        )
        approved = approve_feedback_proposal(proposal, reviewer="prototype_review")

        old_path = os.environ.get("DPP_DQ_LEARNED_FEEDBACK_PATH")
        with tempfile.TemporaryDirectory() as tmpdir:
            feedback_path = Path(tmpdir) / "learned_feedback.json"
            feedback_path.write_text(
                json.dumps({"feedback": [approved.as_dict()]}),
                encoding="utf-8",
            )
            os.environ["DPP_DQ_LEARNED_FEEDBACK_PATH"] = str(feedback_path)
            try:
                result = normalize_text_value("diagnosis", "hydraulic humming cycle", enable_semantic=False)
            finally:
                if old_path is None:
                    os.environ.pop("DPP_DQ_LEARNED_FEEDBACK_PATH", None)
                else:
                    os.environ["DPP_DQ_LEARNED_FEEDBACK_PATH"] = old_path

        self.assertEqual("ambiguous", result.status)
        self.assertIsNone(result.normalized_concept)
        self.assertEqual("pump_fault", result.candidates[0].concept_id)
        self.assertEqual("learned_feedback_exact", result.candidates[0].match_type)
        self.assertEqual("learned_feedback", result.candidates[0].source)
        self.assertEqual(approved.proposal_id, result.candidates[0].feedback_id)

    def test_learned_feedback_semantic_match_is_review_only_and_separate_from_core_registry(self) -> None:
        class FakeEmbeddingModel:
            def encode(self, texts, normalize_embeddings=True):  # noqa: ANN001, ARG002
                if isinstance(texts, str):
                    return self._vector(texts)
                return [self._vector(text) for text in texts]

            def _vector(self, text: str) -> list[float]:
                key = text.lower()
                if "hydraulic" in key or "humming" in key:
                    return [1.0, 0.0]
                return [0.0, 1.0]

        proposal = create_feedback_proposal(
            action="accept_mapping",
            scope_name="service",
            entity_type="RepairServiceStep",
            field_path="RepairServiceStep.diagnose",
            original_value="hydraulic humming cycle",
            concept_id="pump_fault",
            proposed_surface_form="hydraulic humming cycle",
            reviewer="prototype_review",
        )
        approved = approve_feedback_proposal(proposal, reviewer="prototype_review")

        old_path = os.environ.get("DPP_DQ_LEARNED_FEEDBACK_PATH")
        old_embedding_model = free_text_module._embedding_model
        with tempfile.TemporaryDirectory() as tmpdir:
            feedback_path = Path(tmpdir) / "learned_feedback.json"
            feedback_path.write_text(
                json.dumps({"feedback": [approved.as_dict()]}),
                encoding="utf-8",
            )
            os.environ["DPP_DQ_LEARNED_FEEDBACK_PATH"] = str(feedback_path)
            free_text_module._embedding_model = lambda: FakeEmbeddingModel()
            try:
                result = normalize_text_value(
                    "diagnosis",
                    "pump makes a hydraulic humming noise",
                    enable_semantic=True,
                )
            finally:
                free_text_module._embedding_model = old_embedding_model
                if old_path is None:
                    os.environ.pop("DPP_DQ_LEARNED_FEEDBACK_PATH", None)
                else:
                    os.environ["DPP_DQ_LEARNED_FEEDBACK_PATH"] = old_path

        self.assertEqual("ambiguous", result.status)
        self.assertIsNone(result.normalized_concept)
        self.assertEqual("pump_fault", result.candidates[0].concept_id)
        self.assertEqual("learned_feedback_semantic", result.candidates[0].match_type)
        self.assertEqual("learned_feedback", result.candidates[0].source)
        self.assertEqual(approved.proposal_id, result.candidates[0].feedback_id)

    def test_harmonization_report_carries_learned_feedback_candidate_provenance(self) -> None:
        proposal = create_feedback_proposal(
            action="accept_mapping",
            scope_name="service",
            entity_type="RepairServiceStep",
            field_path="RepairServiceStep.diagnose",
            original_value="hydraulic humming cycle",
            concept_id="pump_fault",
            proposed_surface_form="hydraulic humming cycle",
            reviewer="prototype_review",
        )
        approved = approve_feedback_proposal(proposal, reviewer="prototype_review")
        document = {
            "@context": {"dpp": "https://example.org/dpp#"},
            "@graph": [
                {
                    "@id": "service-001",
                    "@type": "dpp:RepairServiceStep",
                    "diagnose": "hydraulic humming cycle",
                }
            ],
        }

        old_path = os.environ.get("DPP_DQ_LEARNED_FEEDBACK_PATH")
        with tempfile.TemporaryDirectory() as tmpdir:
            feedback_path = Path(tmpdir) / "learned_feedback.json"
            feedback_path.write_text(
                json.dumps({"feedback": [approved.as_dict()]}),
                encoding="utf-8",
            )
            os.environ["DPP_DQ_LEARNED_FEEDBACK_PATH"] = str(feedback_path)
            try:
                result = harmonize_document(document, "service")
            finally:
                if old_path is None:
                    os.environ.pop("DPP_DQ_LEARNED_FEEDBACK_PATH", None)
                else:
                    os.environ["DPP_DQ_LEARNED_FEEDBACK_PATH"] = old_path

        report_entry = result.entities["service-001"].text_harmonization["diagnose"]

        self.assertEqual("ambiguous", report_entry["status"])
        self.assertNotIn("normalized_value", report_entry)
        self.assertEqual("pump_fault", report_entry["candidates"][0]["concept_id"])
        self.assertEqual("learned_feedback", report_entry["candidates"][0]["source"])
        self.assertEqual(approved.proposal_id, report_entry["candidates"][0]["feedback_id"])

    def test_appending_same_feedback_record_deduplicates_local_artifact(self) -> None:
        proposal = create_feedback_proposal(
            action="accept_mapping",
            scope_name="service",
            entity_type="RepairServiceStep",
            field_path="RepairServiceStep.diagnose",
            original_value="hydraulic humming cycle",
            concept_id="pump_fault",
            proposed_surface_form="hydraulic humming cycle",
            reviewer="prototype_review",
        )
        approved = approve_feedback_proposal(proposal, reviewer="prototype_review")

        with tempfile.TemporaryDirectory() as tmpdir:
            feedback_path = Path(tmpdir) / "learned_feedback.json"
            first = append_feedback_record(approved, feedback_path)
            second = append_feedback_record(approved, feedback_path)
            mappings = load_learned_service_text_mappings(feedback_path)

        self.assertEqual(first.proposal_id, second.proposal_id)
        self.assertEqual(1, len(mappings))
        self.assertEqual("pump_fault", mappings[0].concept_id)


class FieldAwareWarningTests(unittest.TestCase):
    def test_unmapped_label_warns_without_guessing_unit_context(self) -> None:
        document = {
            "@context": {"dpp": "https://example.org/dpp#"},
            "@graph": [
                {
                    "@id": "dpp-static-unmapped-001",
                    "@type": "dpp:DPPStatic",
                    "mysteryMeasurement": {"value": 10, "unit": "kg"},
                }
            ],
        }

        result = harmonize_document(document, "product")
        entity = result.entities["dpp-static-unmapped-001"]

        self.assertEqual("mysteryMeasurement", entity.unmapped_fields[0].label)
        self.assertTrue(
            any("could not be mapped to a supported field" in issue.message for issue in entity.issues)
        )
        self.assertTrue(
            any("Available fields for 'DPPStatic'" in issue.message for issue in entity.issues)
        )
        self.assertFalse(any("accepted source units" in issue.message for issue in entity.issues))

    def test_mapped_label_unit_error_reports_expected_field_units(self) -> None:
        document = _load_example("unit_unsupported_input.json")
        result = harmonize_document(document, "product")
        entity = result.entities["dpp-static-unit-unsupported-001"]

        issue_messages = [issue.message for issue in entity.issues]
        self.assertTrue(
            any(
                "DPPStatic.weightGRM" in message
                and "accepted source units: GRM, kg, mg" in message
                for message in issue_messages
            )
        )

    def test_mapped_enum_error_reports_expected_canonical_values(self) -> None:
        document = {
            "@context": {"dpp": "https://example.org/dpp#"},
            "@graph": [
                {
                    "@id": "record-invalid-enum-001",
                    "@type": "dpp:GHGEmissionRecord",
                    "dpp:scope": 4,
                }
            ],
        }

        result = harmonize_document(document, "emission")
        entity = result.entities["record-invalid-enum-001"]

        self.assertTrue(
            any(
                "Expected values for 'GHGEmissionRecord.scope': scope_1, scope_2, scope_3"
                in issue.message
                for issue in entity.issues
            )
        )


class UnitAliasTests(unittest.TestCase):
    def test_standard_oriented_unit_aliases_normalize_to_canonical_units(self) -> None:
        expected_units = {
            "kilowatt hour": "kWh",
            "kilowatt-hour": "kWh",
            "centimetre": "CM",
            "kg CO2 equivalent": "kgCO2e",
            "kg CO2 equivalent per kilometre": "kgCO2e/km",
        }

        for dirty_unit, expected_unit in expected_units.items():
            with self.subTest(dirty_unit=dirty_unit):
                self.assertEqual(expected_unit, normalize_unit_label(dirty_unit))

    def test_source_only_units_do_not_become_general_canonical_outputs(self) -> None:
        self.assertEqual("minutes", normalize_unit_label("minutes"))

        normalized = normalize_value_to_unit(90, source_unit="minutes", target_unit="HRS")
        self.assertEqual(1.5, normalized.value)
        self.assertEqual("HRS", normalized.unit)

    def test_activity_unit_piece_value_is_accepted_as_legacy_unit_code(self) -> None:
        document = {
            "@context": {"dpp": "https://example.org/dpp#"},
            "@graph": [
                {
                    "@id": "activity-unit-001",
                    "@type": "dpp:ActivityData",
                    "dpp:activityUnit": "unit",
                }
            ],
        }

        result = harmonize_document(document, "emission")
        entity = result.entities["activity-unit-001"]

        self.assertEqual("unit", entity.fields["ActivityData.unit"].normalized_value)
        self.assertFalse(entity.issues)

    def test_emission_unit_fields_reject_units_outside_their_legacy_context(self) -> None:
        document = {
            "@context": {"dpp": "https://example.org/dpp#"},
            "@graph": [
                {
                    "@id": "activity-minutes-001",
                    "@type": "dpp:ActivityData",
                    "dpp:activityUnit": "minutes",
                },
                {
                    "@id": "factor-per-unit-001",
                    "@type": "dpp:EmissionFactor",
                    "dpp:factorUnit": "kg CO2 equivalent per unit",
                },
            ],
        }

        result = harmonize_document(document, "emission")

        activity_issues = [issue.message for issue in result.entities["activity-minutes-001"].issues]
        factor_issues = [issue.message for issue in result.entities["factor-per-unit-001"].issues]

        self.assertTrue(
            any(
                "Expected unit values for 'ActivityData.unit': kWh, kg, km, ltr, m, m3, t, unit"
                in message
                for message in activity_issues
            )
        )
        self.assertTrue(
            any(
                "Expected unit values for 'EmissionFactor.unit': kgCO2e/kWh, kgCO2e/kg, kgCO2e/km"
                in message
                for message in factor_issues
            )
        )


class HarmonizationReportGuidanceTests(unittest.TestCase):
    def test_unmapped_label_report_lists_possible_canonical_fields(self) -> None:
        document = {
            "@context": {"dpp": "https://example.org/dpp#"},
            "@graph": [
                {
                    "@id": "dpp-static-guidance-001",
                    "@type": "dpp:DPPStatic",
                    "mysteryMeasurement": {"value": 10, "unit": "kg"},
                }
            ],
        }

        result = harmonize_document(document, "product")
        report = build_harmonization_report(result)
        unmapped = report["entities"]["dpp-static-guidance-001"]["unmapped_fields"][0]

        self.assertEqual("possible_canonical_fields", unmapped["guidance"]["kind"])
        self.assertTrue(
            any(target["id"] == "DPPStatic.weightGRM" for target in unmapped["guidance"]["targets"])
        )

    def test_controlled_vocabulary_report_lists_allowed_values(self) -> None:
        document = {
            "@context": {"dpp": "https://example.org/dpp#"},
            "@graph": [
                {
                    "@id": "activity-enum-guidance-001",
                    "@type": "dpp:ActivityData",
                    "dpp:activityType": "space magic",
                    "dpp:quantity": 1,
                    "dpp:activityUnit": "km",
                }
            ],
        }

        result = harmonize_document(document, "emission")
        report = build_harmonization_report(result)
        field = report["entities"]["activity-enum-guidance-001"]["fields"]["ActivityData.activity_type"]

        self.assertEqual("error", field["status"])
        self.assertEqual("allowed_enum_values", field["guidance"]["kind"])
        self.assertTrue(
            any(target["id"] == "electricity_consumption" for target in field["guidance"]["targets"])
        )

    def test_unit_field_report_lists_expected_units(self) -> None:
        document = {
            "@context": {"dpp": "https://example.org/dpp#"},
            "@graph": [
                {
                    "@id": "activity-unit-guidance-001",
                    "@type": "dpp:ActivityData",
                    "dpp:activityType": "distance traveled",
                    "dpp:quantity": 1,
                    "dpp:activityUnit": "banana",
                }
            ],
        }

        result = harmonize_document(document, "emission")
        report = build_harmonization_report(result)
        field = report["entities"]["activity-unit-guidance-001"]["fields"]["ActivityData.unit"]

        self.assertEqual("error", field["status"])
        self.assertEqual("expected_unit_or_numeric_value", field["guidance"]["kind"])
        self.assertIn("unit field", field["guidance"]["message"])
        self.assertTrue(any(target["id"] == "km" for target in field["guidance"]["targets"]))


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

    def test_dirty_context_field_labels_map_to_canonical_service_fields(self) -> None:
        document = {
            "@context": {"dpp": "https://example.org/dpp#"},
            "@graph": [
                {
                    "@id": "service-context-001",
                    "@type": "dpp:RepairServiceStep",
                    "diagnose": "pump dead",
                    "repairCost": 79.0,
                    "partRepaired": "part-pump-001",
                }
            ],
        }

        result = harmonize_document(document, "service")
        entity = result.entities["service-context-001"]

        self.assertEqual(
            79.0,
            entity.fields["RepairServiceStep.costEur"].normalized_value,
        )
        self.assertEqual(
            "part-pump-001",
            entity.fields["RepairServiceStep.repairedPartId"].normalized_value,
        )
        self.assertEqual("mapped", entity.fields["RepairServiceStep.costEur"].status)
        self.assertEqual(
            "mapped",
            entity.fields["RepairServiceStep.repairedPartId"].status,
        )

        output = build_clean_jsonld(result, document=document)
        service = _node_by_id(output, "service-context-001")
        self.assertEqual(
            {
                "@type": "schema:PriceSpecification",
                "schema:price": 79.0,
                "schema:priceCurrency": "EUR",
            },
            service["priceSpecification"],
        )
        self.assertEqual("part-pump-001", service["dpp:repairedPartId"])
        self.assertNotIn("repairCost", service)
        self.assertNotIn("partRepaired", service)

        report = build_harmonization_report(result)
        field_report = report["entities"]["service-context-001"]["fields"]
        self.assertEqual(
            "dpp:repairedPartId",
            field_report["RepairServiceStep.repairedPartId"]["jsonld_term"],
        )
        self.assertEqual(
            0.92,
            field_report["RepairServiceStep.repairedPartId"]["field_thresholds"]["automatic_fuzzy_threshold"],
        )

    def test_service_quality_output_contains_reviewable_harmonization_and_anomaly_context(self) -> None:
        document = _load_example("service_anomaly_input.json")
        result = harmonize_document(document, "service")
        clean_data = build_clean_jsonld(result, document=document)
        harmonization_report = build_harmonization_report(result)
        anomaly_report = build_anomaly_report(analyze_harmonization_result(result))

        cleaning = _node_by_id(clean_data, "service-anomaly-cleaning-001")
        self.assertEqual("switch_or_button_fault", cleaning["dpp:diagnose"])
        self.assertEqual("part-ui-pcb-001", cleaning["dpp:cleanedPartId"])
        self.assertEqual(
            {
                "@type": "schema:PriceSpecification",
                "schema:price": 450.0,
                "schema:priceCurrency": "EUR",
            },
            cleaning["priceSpecification"],
        )

        text_entry = harmonization_report["entities"]["service-anomaly-repair-001"]["text_harmonization"]["diagnose"]
        self.assertEqual("unresolved", text_entry["status"])
        self.assertEqual(0.58, text_entry["thresholds"]["automatic_semantic_threshold"])

        review_actions = {
            finding["review_action"]
            for finding in anomaly_report["findings"]
            if "review_action" in finding
        }
        self.assertIn("confirm_or_correct_service_concept", review_actions)
        self.assertIn("confirm_or_reject_review_candidate_concept", review_actions)

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
