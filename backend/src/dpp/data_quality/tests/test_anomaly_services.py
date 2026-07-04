from __future__ import annotations

import unittest

from dpp.data_quality.anomaly.outputs import build_anomaly_report
from dpp.data_quality.anomaly.schemas import AnomalyFinding, AnomalyResult
from dpp.data_quality.anomaly.services import analyze_harmonization_result
from dpp.data_quality.harmonization.services import harmonize_document
from dpp.data_quality.harmonization.schemas import (
    HarmonizationResult,
    HarmonizedEntity,
    HarmonizedField,
    PreservedRelation,
)


def _field(path: str, value: object) -> HarmonizedField:
    return HarmonizedField(
        canonical_path=path,
        original_label=path.rsplit(".", maxsplit=1)[1],
        original_value=value,
        status="mapped",
    )


class AnomalyServiceTests(unittest.TestCase):
    def test_emission_missing_children_are_reported_as_embedded_objects(self) -> None:
        result = HarmonizationResult(
            scope_name="emission",
            entities={
                "record-001": HarmonizedEntity(
                    entity_id="record-001",
                    entity_type="GHGEmissionRecord",
                )
            },
        )

        anomaly = analyze_harmonization_result(result)
        check_ids = [finding.check_id for finding in anomaly.findings]

        self.assertEqual(2, check_ids.count("missing_required_embedded_object"))
        self.assertNotIn("dangling_relation_target", check_ids)

    def test_emission_calculation_mismatch(self) -> None:
        result = HarmonizationResult(
            scope_name="emission",
            entities={
                "activity-001": HarmonizedEntity(
                    entity_id="activity-001",
                    entity_type="ActivityData",
                    fields={"ActivityData.quantity": _field("ActivityData.quantity", 10.0)},
                ),
                "factor-001": HarmonizedEntity(
                    entity_id="factor-001",
                    entity_type="EmissionFactor",
                    fields={"EmissionFactor.value": _field("EmissionFactor.value", 0.5)},
                ),
                "record-001": HarmonizedEntity(
                    entity_id="record-001",
                    entity_type="GHGEmissionRecord",
                    fields={
                        "GHGEmissionRecord.emissions_kg_co2e": _field(
                            "GHGEmissionRecord.emissions_kg_co2e",
                            9.0,
                        ),
                    },
                    embedded_entities={
                        "activity": [HarmonizedEntity(
                            entity_id="record-001/activity",
                            entity_type="ActivityData",
                            fields={"ActivityData.quantity": _field("ActivityData.quantity", 10.0)},
                        )],
                        "emission_factor": [HarmonizedEntity(
                            entity_id="record-001/emissionFactor",
                            entity_type="EmissionFactor",
                            fields={"EmissionFactor.value": _field("EmissionFactor.value", 0.5)},
                        )],
                    },
                ),
            },
        )

        anomaly = analyze_harmonization_result(result)

        self.assertIn(
            "emission_record_calculation_mismatch",
            {finding.check_id for finding in anomaly.findings},
        )

    def test_emission_unit_incompatibility(self) -> None:
        result = HarmonizationResult(
            scope_name="emission",
            entities={
                "activity-001": HarmonizedEntity(
                    entity_id="activity-001",
                    entity_type="ActivityData",
                    fields={
                        "ActivityData.quantity": _field("ActivityData.quantity", 10.0),
                        "ActivityData.unit": _field("ActivityData.unit", "kWh"),
                    },
                ),
                "factor-001": HarmonizedEntity(
                    entity_id="factor-001",
                    entity_type="EmissionFactor",
                    fields={
                        "EmissionFactor.value": _field("EmissionFactor.value", 0.5),
                        "EmissionFactor.unit": _field("EmissionFactor.unit", "kgCO2e/km"),
                    },
                ),
                "record-001": HarmonizedEntity(
                    entity_id="record-001",
                    entity_type="GHGEmissionRecord",
                    fields={
                        "GHGEmissionRecord.emissions_kg_co2e": _field(
                            "GHGEmissionRecord.emissions_kg_co2e",
                            5.0,
                        ),
                    },
                    embedded_entities={
                        "activity": [HarmonizedEntity(
                            entity_id="record-001/activity",
                            entity_type="ActivityData",
                            fields={
                                "ActivityData.quantity": _field("ActivityData.quantity", 10.0),
                                "ActivityData.unit": _field("ActivityData.unit", "kWh"),
                            },
                        )],
                        "emission_factor": [HarmonizedEntity(
                            entity_id="record-001/emissionFactor",
                            entity_type="EmissionFactor",
                            fields={
                                "EmissionFactor.value": _field("EmissionFactor.value", 0.5),
                                "EmissionFactor.unit": _field("EmissionFactor.unit", "kgCO2e/km"),
                            },
                        )],
                    },
                ),
            },
        )

        anomaly = analyze_harmonization_result(result)
        finding = next(item for item in anomaly.findings if item.check_id == "emission_unit_incompatibility")

        self.assertEqual({"emission_factor_unit": "kgCO2e/kWh"}, finding.expected)
        self.assertEqual(
            {"activity_unit": "kWh", "factor_unit": "kgCO2e/km"},
            finding.observed_value,
        )

    def test_zero_reported_emissions_with_positive_inputs(self) -> None:
        result = HarmonizationResult(
            scope_name="emission",
            entities={
                "activity-001": HarmonizedEntity(
                    entity_id="activity-001",
                    entity_type="ActivityData",
                    fields={"ActivityData.quantity": _field("ActivityData.quantity", 10.0)},
                ),
                "factor-001": HarmonizedEntity(
                    entity_id="factor-001",
                    entity_type="EmissionFactor",
                    fields={"EmissionFactor.value": _field("EmissionFactor.value", 0.5)},
                ),
                "record-001": HarmonizedEntity(
                    entity_id="record-001",
                    entity_type="GHGEmissionRecord",
                    fields={
                        "GHGEmissionRecord.emissions_kg_co2e": _field(
                            "GHGEmissionRecord.emissions_kg_co2e",
                            0.0,
                        ),
                    },
                    embedded_entities={
                        "activity": [HarmonizedEntity(
                            entity_id="record-001/activity",
                            entity_type="ActivityData",
                            fields={"ActivityData.quantity": _field("ActivityData.quantity", 10.0)},
                        )],
                        "emission_factor": [HarmonizedEntity(
                            entity_id="record-001/emissionFactor",
                            entity_type="EmissionFactor",
                            fields={"EmissionFactor.value": _field("EmissionFactor.value", 0.5)},
                        )],
                    },
                ),
            },
        )

        anomaly = analyze_harmonization_result(result)
        check_ids = [finding.check_id for finding in anomaly.findings]

        self.assertIn("zero_reported_emissions_with_positive_inputs", check_ids)
        self.assertIn("emission_record_calculation_mismatch", check_ids)

    def test_possible_duplicate_emission_record(self) -> None:
        result = HarmonizationResult(
            scope_name="emission",
            entities={
                "record-001": HarmonizedEntity(
                    entity_id="record-001",
                    entity_type="GHGEmissionRecord",
                    fields={
                        "GHGEmissionRecord.scope": _field("GHGEmissionRecord.scope", "scope_3"),
                        "GHGEmissionRecord.scope3_category": _field(
                            "GHGEmissionRecord.scope3_category",
                            "purchased_goods_and_services",
                        ),
                        "GHGEmissionRecord.emissions_kg_co2e": _field(
                            "GHGEmissionRecord.emissions_kg_co2e",
                            4.0,
                        ),
                    },
                    embedded_entities={
                        "activity": [HarmonizedEntity(
                            entity_id="record-001/activity",
                            entity_type="ActivityData",
                            fields={"ActivityData.quantity": _field("ActivityData.quantity", 10.0)},
                        )],
                        "emission_factor": [HarmonizedEntity(
                            entity_id="record-001/emissionFactor",
                            entity_type="EmissionFactor",
                            fields={"EmissionFactor.value": _field("EmissionFactor.value", 0.4)},
                        )],
                    },
                ),
                "record-002": HarmonizedEntity(
                    entity_id="record-002",
                    entity_type="GHGEmissionRecord",
                    fields={
                        "GHGEmissionRecord.scope": _field("GHGEmissionRecord.scope", "scope_3"),
                        "GHGEmissionRecord.scope3_category": _field(
                            "GHGEmissionRecord.scope3_category",
                            "purchased_goods_and_services",
                        ),
                        "GHGEmissionRecord.emissions_kg_co2e": _field(
                            "GHGEmissionRecord.emissions_kg_co2e",
                            4.0,
                        ),
                    },
                    embedded_entities={
                        "activity": [HarmonizedEntity(
                            entity_id="record-002/activity",
                            entity_type="ActivityData",
                            fields={"ActivityData.quantity": _field("ActivityData.quantity", 10.0)},
                        )],
                        "emission_factor": [HarmonizedEntity(
                            entity_id="record-002/emissionFactor",
                            entity_type="EmissionFactor",
                            fields={"EmissionFactor.value": _field("EmissionFactor.value", 0.4)},
                        )],
                    },
                ),
            },
        )

        anomaly = analyze_harmonization_result(result)
        finding = next(item for item in anomaly.findings if item.check_id == "possible_duplicate_emission_record")

        self.assertEqual("info", finding.severity)
        self.assertEqual(["record-001", "record-002"], finding.evidence["duplicate_record_ids"])

    def test_product_required_relation_and_counter_findings(self) -> None:
        result = HarmonizationResult(
            scope_name="product",
            entities={
                "dpp-static-001": HarmonizedEntity(
                    entity_id="dpp-static-001",
                    entity_type="DPPStatic",
                    fields={"DPPStatic.weightGRM": _field("DPPStatic.weightGRM", 1000.0)},
                ),
                "part-static-001": HarmonizedEntity(
                    entity_id="part-static-001",
                    entity_type="PartStatic",
                    fields={"PartStatic.weightGRM": _field("PartStatic.weightGRM", 1800.0)},
                ),
                "part-instance-001": HarmonizedEntity(
                    entity_id="part-instance-001",
                    entity_type="PartInstance",
                ),
                "dpp-instance-001": HarmonizedEntity(
                    entity_id="dpp-instance-001",
                    entity_type="DPPInstance",
                    fields={
                        "DPPInstance.brewingCount": _field("DPPInstance.brewingCount", 100),
                        "DPPInstance.cleaningCount": _field("DPPInstance.cleaningCount", 140),
                    },
                    relations=[
                        PreservedRelation("dpp-instance-001", "dppStaticLink", "dpp-static-001", "DPPStatic")
                    ],
                ),
            },
        )

        anomaly = analyze_harmonization_result(result)
        check_ids = {finding.check_id for finding in anomaly.findings}

        self.assertIn("missing_required_relation", check_ids)
        self.assertIn("part_weight_exceeds_product_weight", check_ids)
        self.assertIn("maintenance_counter_exceeds_brewing_count", check_ids)

    def test_part_static_zero_dimension_is_out_of_range(self) -> None:
        result = HarmonizationResult(
            scope_name="product",
            entities={
                "part-static-001": HarmonizedEntity(
                    entity_id="part-static-001",
                    entity_type="PartStatic",
                    fields={"PartStatic.heightCM": _field("PartStatic.heightCM", 0.0)},
                )
            },
        )

        anomaly = analyze_harmonization_result(result)
        finding = next(item for item in anomaly.findings if item.check_id == "part_height_positive")

        self.assertEqual({"min_exclusive": 0.0}, finding.expected)

    def test_material_weight_exceeds_part_weight(self) -> None:
        result = HarmonizationResult(
            scope_name="product",
            entities={
                "part-static-001": HarmonizedEntity(
                    entity_id="part-static-001",
                    entity_type="PartStatic",
                    fields={"PartStatic.weightGRM": _field("PartStatic.weightGRM", 1000.0)},
                ),
                "material-001": HarmonizedEntity(
                    entity_id="material-001",
                    entity_type="MaterialInstance",
                    fields={"MaterialInstance.weightGRM": _field("MaterialInstance.weightGRM", 700.0)},
                ),
                "material-002": HarmonizedEntity(
                    entity_id="material-002",
                    entity_type="MaterialInstance",
                    fields={"MaterialInstance.weightGRM": _field("MaterialInstance.weightGRM", 500.0)},
                ),
                "part-instance-001": HarmonizedEntity(
                    entity_id="part-instance-001",
                    entity_type="PartInstance",
                    relations=[PreservedRelation("part-instance-001", "partStaticLink", "part-static-001", "PartStatic")],
                    embedded_entities={"compositeMaterials": [
                        HarmonizedEntity(
                            entity_id="material-001",
                            entity_type="MaterialInstance",
                            fields={"MaterialInstance.weightGRM": _field("MaterialInstance.weightGRM", 700.0)},
                        ),
                        HarmonizedEntity(
                            entity_id="material-002",
                            entity_type="MaterialInstance",
                            fields={"MaterialInstance.weightGRM": _field("MaterialInstance.weightGRM", 500.0)},
                        ),
                    ]},
                ),
            },
        )

        anomaly = analyze_harmonization_result(result)
        finding = next(item for item in anomaly.findings if item.check_id == "material_weight_exceeds_part_weight")

        self.assertEqual(1200.0, finding.observed_value)
        self.assertEqual(["material-001", "material-002"], finding.evidence["material_instance_ids"])

    def test_active_part_tree_weight_exceeds_product_weight(self) -> None:
        result = HarmonizationResult(
            scope_name="product",
            entities={
                "dpp-static-001": HarmonizedEntity(
                    entity_id="dpp-static-001",
                    entity_type="DPPStatic",
                    fields={"DPPStatic.weightGRM": _field("DPPStatic.weightGRM", 1000.0)},
                ),
                "root-static-001": HarmonizedEntity(
                    entity_id="root-static-001",
                    entity_type="PartStatic",
                    fields={"PartStatic.weightGRM": _field("PartStatic.weightGRM", 500.0)},
                ),
                "child-static-001": HarmonizedEntity(
                    entity_id="child-static-001",
                    entity_type="PartStatic",
                    fields={"PartStatic.weightGRM": _field("PartStatic.weightGRM", 1500.0)},
                ),
                "detached-static-001": HarmonizedEntity(
                    entity_id="detached-static-001",
                    entity_type="PartStatic",
                    fields={"PartStatic.weightGRM": _field("PartStatic.weightGRM", 900.0)},
                ),
                "root-part-001": HarmonizedEntity(
                    entity_id="root-part-001",
                    entity_type="PartInstance",
                    relations=[PreservedRelation("root-part-001", "partStaticLink", "root-static-001", "PartStatic")],
                    embedded_entities={
                        "compositeParts": [HarmonizedEntity(
                            entity_id="child-part-001",
                            entity_type="PartInstance",
                            relations=[PreservedRelation("child-part-001", "partStaticLink", "child-static-001", "PartStatic")],
                        )],
                        "historyOfDetachedParts": [HarmonizedEntity(
                            entity_id="detached-part-001",
                            entity_type="PartInstance",
                            relations=[PreservedRelation("detached-part-001", "partStaticLink", "detached-static-001", "PartStatic")],
                        )],
                    },
                ),
                "child-part-001": HarmonizedEntity(
                    entity_id="child-part-001",
                    entity_type="PartInstance",
                    relations=[PreservedRelation("child-part-001", "partStaticLink", "child-static-001", "PartStatic")],
                ),
                "detached-part-001": HarmonizedEntity(
                    entity_id="detached-part-001",
                    entity_type="PartInstance",
                    relations=[
                        PreservedRelation("detached-part-001", "partStaticLink", "detached-static-001", "PartStatic")
                    ],
                ),
                "dpp-instance-001": HarmonizedEntity(
                    entity_id="dpp-instance-001",
                    entity_type="DPPInstance",
                    relations=[
                        PreservedRelation("dpp-instance-001", "dppStaticLink", "dpp-static-001", "DPPStatic"),
                        PreservedRelation("dpp-instance-001", "partInstanceLink", "root-part-001", "PartInstance"),
                    ],
                ),
            },
        )

        anomaly = analyze_harmonization_result(result)
        finding = next(
            item
            for item in anomaly.findings
            if item.check_id == "active_part_tree_weight_exceeds_product_weight"
        )

        self.assertEqual(1500.0, finding.observed_value)
        self.assertEqual(["child-part-001"], finding.evidence["leaf_part_ids"])
        self.assertEqual(["detached-part-001"], finding.evidence["detached_part_ids_excluded"])

    def test_product_usage_ratio_findings(self) -> None:
        result = HarmonizationResult(
            scope_name="product",
            entities={
                "dpp-instance-001": HarmonizedEntity(
                    entity_id="dpp-instance-001",
                    entity_type="DPPInstance",
                    fields={
                        "DPPInstance.operatingHRS": _field("DPPInstance.operatingHRS", 120),
                        "DPPInstance.brewingCount": _field("DPPInstance.brewingCount", 100),
                        "DPPInstance.cleaningCount": _field("DPPInstance.cleaningCount", 140),
                        "DPPInstance.chalkCount": _field("DPPInstance.chalkCount", 130),
                    },
                )
            },
        )

        anomaly = analyze_harmonization_result(result)
        check_ids = [finding.check_id for finding in anomaly.findings]

        self.assertEqual(2, check_ids.count("maintenance_to_brewing_ratio_high"))

    def test_service_unresolved_text_requires_review(self) -> None:
        result = HarmonizationResult(
            scope_name="service",
            entities={
                "service-001": HarmonizedEntity(
                    entity_id="service-001",
                    entity_type="RepairServiceStep",
                    text_harmonization={
                        "diagnose": {
                            "status": "unresolved",
                            "original_value": "unknown ceramic resonance",
                            "candidates": [],
                        }
                    },
                )
            },
        )

        anomaly = analyze_harmonization_result(result)

        self.assertEqual(["service_text_requires_review"], [finding.check_id for finding in anomaly.findings])

    def test_service_action_context_is_preserved(self) -> None:
        document = {
            "@context": {"dpp": "https://example.org/dpp#"},
            "@graph": [
                {
                    "@id": "replace-001",
                    "@type": "dpp:ReplaceServiceStep",
                    "diagnose": "pump fault",
                    "observedSymptoms": ["not pumping water"],
                    "replacedPartId": "part-old-001",
                    "newPart": {"@id": "part-new-001"},
                    "costEur": 89.0,
                }
            ],
        }

        result = harmonize_document(document, "service")
        entity = result.entities["replace-001"]

        self.assertIn("ReplaceServiceStep.replacedPartId", entity.fields)
        self.assertEqual(
            "part-old-001",
            entity.fields["ReplaceServiceStep.replacedPartId"].original_value,
        )
        self.assertEqual(["part-new-001"], [child.entity_id for child in entity.embedded_entities["newPart"]])

    def test_replaced_and_new_parts_pair_preserves_embedded_replacement_entity(self) -> None:
        replaced_pairs = [["part-old-001", {"@id": "part-new-001"}]]
        document = {
            "@context": {"dpp": "https://example.org/dpp#"},
            "@graph": [
                {
                    "@id": "refurbishment-001",
                    "@type": "dpp:RefurbishmentServiceStep",
                    "diagnose": "pump fault",
                    "observedSymptoms": ["not pumping water"],
                    "replacedAndNewParts": replaced_pairs,
                    "costEur": 120.0,
                }
            ],
        }

        result = harmonize_document(document, "service")
        entity = result.entities["refurbishment-001"]

        self.assertNotIn("RefurbishmentServiceStep.replacedAndNewParts", entity.fields)
        self.assertEqual(
            [("part-old-001", "part-new-001")],
            [
                (existing_id, new_part.entity_id)
                for existing_id, new_part in entity.paired_embedded_entities["replacedAndNewParts"]
            ],
        )
        self.assertEqual([], entity.relations)

    def test_service_diagnosis_part_evidence_mismatch_is_not_flagged_without_relation_registry(self) -> None:
        document = {
            "@context": {"dpp": "https://example.org/dpp#"},
            "@graph": [
                {
                    "@id": "replace-001",
                    "@type": "dpp:ReplaceServiceStep",
                    "diagnose": "pump fault",
                    "observedSymptoms": ["not pumping water"],
                    "replacedPartId": "part-burr-set-001",
                    "newPart": {"@id": "part-new-001"},
                    "costEur": 89.0,
                }
            ],
        }

        result = harmonize_document(document, "service")
        anomaly = analyze_harmonization_result(result)
        self.assertNotIn(
            "service_diagnosis_part_evidence_mismatch",
            [finding.check_id for finding in anomaly.findings],
        )

    def test_service_diagnosis_part_evidence_match_is_not_flagged(self) -> None:
        document = {
            "@context": {"dpp": "https://example.org/dpp#"},
            "@graph": [
                {
                    "@id": "replace-001",
                    "@type": "dpp:ReplaceServiceStep",
                    "diagnose": "pump fault",
                    "observedSymptoms": ["not pumping water"],
                    "replacedPartId": "part-pump-001",
                    "newPart": {"@id": "part-new-001"},
                    "costEur": 89.0,
                }
            ],
        }

        result = harmonize_document(document, "service")
        anomaly = analyze_harmonization_result(result)

        self.assertNotIn(
            "service_diagnosis_part_evidence_mismatch",
            [finding.check_id for finding in anomaly.findings],
        )

    def test_review_candidate_service_concept_is_flagged_for_confirmation(self) -> None:
        document = {
            "@context": {"dpp": "https://example.org/dpp#"},
            "@graph": [
                {
                    "@id": "replace-001",
                    "@type": "dpp:ReplaceServiceStep",
                    "diagnose": "thermostat not working",
                    "replacedPartId": "part-thermostat-001",
                }
            ],
        }

        result = harmonize_document(document, "service")
        anomaly = analyze_harmonization_result(result)
        finding = next(
            item
            for item in anomaly.findings
            if item.check_id == "service_review_candidate_concept"
        )

        self.assertEqual("info", finding.severity)
        self.assertEqual("thermostat_or_rheostat_fault", finding.observed_value)
        self.assertEqual("confirm_or_reject_review_candidate_concept", finding.review_action)

    def test_llm_relation_hint_part_mismatch_is_not_flagged_without_relation_registry(self) -> None:
        document = {
            "@context": {"dpp": "https://example.org/dpp#"},
            "@graph": [
                {
                    "@id": "repair-001",
                    "@type": "dpp:RepairServiceStep",
                    "diagnose": "heating element failed",
                    "repairedPartId": "part-pump-001",
                }
            ],
        }

        result = harmonize_document(document, "service")
        anomaly = analyze_harmonization_result(result)
        self.assertNotIn(
            "service_diagnosis_part_evidence_mismatch",
            [finding.check_id for finding in anomaly.findings],
        )

    def test_report_summary_counts_check_methods(self) -> None:
        result = AnomalyResult(
            scope_name="product",
            findings=[
                AnomalyFinding(
                    check_id="range_rule",
                    category="range",
                    severity="warning",
                    message="Range rule finding.",
                ),
                AnomalyFinding(
                    check_id="iforest_score",
                    category="statistical",
                    severity="info",
                    message="Isolation Forest score finding.",
                    evidence={"check_method": "isolation_forest"},
                ),
            ],
        )

        report = build_anomaly_report(result)

        self.assertEqual({"range": 1, "statistical": 1}, report["summary"]["category_counts"])
        self.assertEqual(
            {"rule_based": 1, "isolation_forest": 1},
            report["summary"]["check_method_counts"],
        )


if __name__ == "__main__":
    unittest.main()
