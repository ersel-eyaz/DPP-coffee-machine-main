# Chapter 7 evaluation scenarios

This directory contains thesis-facing evaluation inputs. They are kept separate
from the development examples in `examples/harmonization` so that historical
fixture syntax does not introduce unrelated harmonization effects.

All derived scenarios start from one of the three export-conform baseline
documents. Each focused scenario should change only the data required for its
stated purpose.

| ID | Scope | Input file | Purpose | Processing mode | Expected result | Status |
|---|---|---|---|---|---|---|
| P0 | Product | `product_baseline.json` | Export-conform baseline and round-trip stability | both | Stable clean output; no unmapped field, issue, or anomaly finding | verified |
| P1 | Product | `product_harmonization.json` | Focused label and unit harmonization | harmonize | `modelWeight` with 9.3 kg becomes `schema:weight` with 9300 GRM; no unrelated finding | verified |
| P2 | Product | `product_similarity.json` | Character-sequence matching for a field label and unit | harmonize | `modelWeigh` and `kilogrm` are accepted by fuzzy matching; the clean output reconstructs P0 | verified |
| P3 | Product | `product_anomaly.json` | Deterministic and statistical/ML product findings | both | 12 frozen findings: 9 rule-based, one Z-Score, one IQR, and one Isolation Forest | verified |
| E0 | Emission | `emission_baseline.json` | Export-conform baseline and round-trip stability | both | Stable clean output; no unmapped field, issue, or anomaly finding | verified |
| E1 | Emission | `emission_harmonization.json` | Focused label, unit, and controlled-value harmonization | harmonize | Reconstructs E0; one intended informational alias note and no anomaly finding | verified |
| E2 | Emission | `emission_similarity.json` | Character-sequence and semantic matching of controlled values | harmonize | `power consumptin` is resolved by fuzzy matching and the Scope paraphrase by semantic matching; the clean output reconstructs E0 | verified |
| E3 | Emission | `emission_anomaly.json` | Calculation, unit, scope/category, and statistical findings | both | Five frozen findings: four rule-based and one IQR | verified |
| S0 | Service | `service_baseline.json` | Export-conform baseline and round-trip stability | both | Stable clean output; no unmapped field, issue, or anomaly finding | verified |
| S1 | Service | `service_harmonization.json` | Field-label and service-text harmonization, including review behaviour | both | Two normalized texts, one unresolved text retained, and one review finding | verified |
| S2 | Service | `service_similarity.json` | Semantic and character-sequence matching of service texts | harmonize | The diagnosis is resolved semantically and the symptom by fuzzy matching; the clean output reconstructs S0 | verified |
| S3 | Service | `service_structure.json` | Required embedded object, relation target type, replacement identity, and static-part consistency | both | Four frozen structural findings; the two consistency errors support integrated save blocking | verified |

For every implemented scenario, freeze the intended deviation, expected
harmonization summary, expected finding IDs, reference-data input (if any), and
round-trip expectation before using its result in the thesis.

## Frozen anomaly expectations

- P3: `product_height_range`, `product_profile_range_mismatch`,
  `material_weight_exceeds_part_weight`,
  `active_part_tree_weight_exceeds_product_weight`,
  `part_weight_exceeds_product_weight`,
  `grinding_brewing_counter_deviation`,
  `brewing_per_operating_hour_high`, two
  `maintenance_to_brewing_ratio_high` findings,
  `statistical_z_score_outlier`, `statistical_iqr_outlier`, and
  `isolation_forest_feature_pattern_outlier`.
- E3: `emission_unit_incompatibility`,
  `zero_reported_emissions_with_positive_inputs`,
  `emission_record_calculation_mismatch`, `scope3_category_missing`, and
  `statistical_iqr_outlier`.
- S1 in `both` mode: `service_text_requires_review` for the unresolved symptom.
- S3: `missing_required_embedded_object`,
  `relation_target_type_mismatch`,
  `replacement_part_static_mismatch`, and
  `replacement_instance_id_reused`.

## External reference-data variant

P3 is additionally verified with the ten-row
`examples/reference/product_raw_usage_reference.csv` batch used by the frontend
upload path. The report must identify the profile as `user_uploaded`, record all
ten reference rows, and retain the three statistical/ML finding types. This is a
configuration variant of P3 rather than a separate JSON-LD scenario.
