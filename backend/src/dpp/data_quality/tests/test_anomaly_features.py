from __future__ import annotations

import unittest

from dpp.data_quality.anomaly.features import build_feature_table, extract_feature_rows
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


class AnomalyFeatureTests(unittest.TestCase):
    def test_product_feature_row_contains_usage_and_graph_ratios(self) -> None:
        result = HarmonizationResult(
            scope_name="product",
            entities={
                "dpp-static-001": HarmonizedEntity(
                    entity_id="dpp-static-001",
                    entity_type="DPPStatic",
                    fields={"DPPStatic.weightGRM": _field("DPPStatic.weightGRM", 1000.0)},
                ),
                "child-static-001": HarmonizedEntity(
                    entity_id="child-static-001",
                    entity_type="PartStatic",
                    fields={"PartStatic.weightGRM": _field("PartStatic.weightGRM", 500.0)},
                ),
                "material-001": HarmonizedEntity(
                    entity_id="material-001",
                    entity_type="MaterialInstance",
                    fields={"MaterialInstance.weightGRM": _field("MaterialInstance.weightGRM", 250.0)},
                ),
                "root-part-001": HarmonizedEntity(
                    entity_id="root-part-001",
                    entity_type="PartInstance",
                    relations=[
                        PreservedRelation("root-part-001", "compositeParts", "child-part-001", "PartInstance"),
                    ],
                ),
                "child-part-001": HarmonizedEntity(
                    entity_id="child-part-001",
                    entity_type="PartInstance",
                    relations=[
                        PreservedRelation("child-part-001", "partStaticLink", "child-static-001", "PartStatic"),
                        PreservedRelation(
                            "child-part-001",
                            "compositeMaterials",
                            "material-001",
                            "MaterialInstance",
                        ),
                    ],
                ),
                "dpp-instance-001": HarmonizedEntity(
                    entity_id="dpp-instance-001",
                    entity_type="DPPInstance",
                    fields={
                        "DPPInstance.operatingHRS": _field("DPPInstance.operatingHRS", 100.0),
                        "DPPInstance.brewingCount": _field("DPPInstance.brewingCount", 200.0),
                        "DPPInstance.cleaningCount": _field("DPPInstance.cleaningCount", 20.0),
                        "DPPInstance.chalkCount": _field("DPPInstance.chalkCount", 10.0),
                        "DPPInstance.coffeeGrindingCount": _field("DPPInstance.coffeeGrindingCount", 190.0),
                    },
                    relations=[
                        PreservedRelation("dpp-instance-001", "dppStaticLink", "dpp-static-001", "DPPStatic"),
                        PreservedRelation("dpp-instance-001", "partInstanceLink", "root-part-001", "PartInstance"),
                    ],
                ),
            },
        )

        rows = extract_feature_rows(result)

        self.assertEqual(1, len(rows))
        features = rows[0].features
        self.assertEqual(0.1, features["cleaning_to_brewing_ratio"])
        self.assertEqual(0.05, features["chalk_to_brewing_ratio"])
        self.assertEqual(0.95, features["grinding_to_brewing_ratio"])
        self.assertEqual(2.0, features["brews_per_operating_hour"])
        self.assertEqual(0.5, features["active_part_weight_to_product_weight"])
        self.assertEqual(0.5, features["max_material_weight_to_part_weight"])

    def test_emission_feature_row_contains_calculation_and_unit_features(self) -> None:
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
                        "EmissionFactor.value": _field("EmissionFactor.value", 0.4),
                        "EmissionFactor.unit": _field("EmissionFactor.unit", "kgCO2e/kWh"),
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
                    relations=[
                        PreservedRelation("record-001", "activity", "activity-001", "ActivityData"),
                        PreservedRelation("record-001", "emission_factor", "factor-001", "EmissionFactor"),
                    ],
                ),
            },
        )

        table = build_feature_table(result)
        features = table["rows"][0]["features"]

        self.assertEqual(10.0, features["quantity"])
        self.assertEqual(0.4, features["factor_value"])
        self.assertEqual(5.0, features["reported_emissions"])
        self.assertEqual(4.0, features["expected_emissions"])
        self.assertEqual(1.0, features["absolute_calculation_deviation"])
        self.assertEqual(0.25, features["relative_calculation_deviation"])
        self.assertEqual(0.5, features["reported_emissions_per_quantity"])
        self.assertEqual(1.0, features["unit_compatible"])


if __name__ == "__main__":
    unittest.main()
