Scenario examples for the isolated data-quality pipeline.

All files in this folder are JSON-LD inputs. They enter the same pipeline:

  raw JSON-LD input
    -> harmonize_document(...)
    -> HarmonizationResult
    -> optional anomaly/plausibility analysis over the harmonized result

The anomaly layer intentionally works on harmonized, model-near values rather
than on raw heterogeneous input labels or units.


Running registered examples
---------------------------

From backend/:

  PYTHONPATH=src python -m dpp.data_quality.pipeline.dev_main product_anomaly --output anomaly
  PYTHONPATH=src python -m dpp.data_quality.pipeline.dev_main service_anomaly --output anomaly
  PYTHONPATH=src python -m dpp.data_quality.pipeline.dev_main emission_anomaly --output quality

From backend/src/:

  python -m dpp.data_quality.pipeline.dev_main product_anomaly --output anomaly
  python -m dpp.data_quality.pipeline.dev_main service_anomaly --output anomaly
  python -m dpp.data_quality.pipeline.dev_main emission_anomaly --output quality

Registered example keys are defined in pipeline/dev_main.py. They are kept for
repeatable demos and regression checks.


Running a custom JSON-LD file
-----------------------------

Custom files can be passed directly without adding them to the EXAMPLES
dictionary. A scope is required because the file is not registered.

From backend/src/:

  python -m dpp.data_quality.pipeline.dev_main --scope product --input dpp/data_quality/examples/harmonization/product_anomaly_input.json --output quality

Supported scopes:

  product
  emission
  service


Output modes
------------

data
  Clean canonical JSON-LD only.

report
  Harmonization report only.

anomaly
  Anomaly/plausibility report only.

quality
  Clean data, harmonization report, and anomaly report together.

full
  Default combined harmonization output used by early development.


Core examples
-------------

product_dirty.json
  Product-scope dirty input with label and unit harmonization.

emission_dirty.json
  Emission-scope dirty input with activity, factor, and GHG record structure.

service_text_input.json
  Service-scope free-text input for symptom and diagnosis harmonization.


Anomaly/plausibility examples
-----------------------------

product_anomaly_input.json
  Product-scope example designed to trigger relationship, numeric range,
  product profile, graph/material-weight, and cross-field consistency findings.

product_profile_input.json
  Product-scope example for the synthetic BaristaCore 2500 profile check.

emission_anomaly_input.json
  Emission-scope example designed to trigger negative numeric values,
  unit compatibility, calculation mismatch, zero reported emissions, possible
  duplicate records, and Scope 3 category consistency findings.

service_anomaly_input.json
  Service-scope example designed to trigger high/negative cost checks,
  semantic service-type mismatch, and unresolved text review findings.


Harmonization scenario examples
-------------------------------

label_exact_alias_input.json
  Field labels are covered by exact alias mappings.

label_fuzzy_candidate_input.json
  Field labels contain small typos or near-aliases. These are handled by the
  conservative entity-aware fuzzy fallback if confidence is high enough.

label_ambiguous_input.json
  Labels are intentionally generic and should remain unmapped or produce
  candidate warnings rather than being accepted automatically.

unit_exact_alias_input.json
  Units are covered by exact unit aliases and converted to canonical units.

unit_fuzzy_candidate_input.json
  Units contain small spelling variants and are handled without embeddings.

unit_ambiguous_input.json
  Unit labels are intentionally generic. They are meant to show safe failure or
  warning behavior.

unit_unsupported_input.json
  Units are outside the supported conversion families.

mixed_dirty_input.json
  A compact demo input combining exact labels, fuzzy labels, unit conversion,
  fuzzy unit spelling, and unmapped fields.

enum_alias_input.json
  Controlled vocabulary values are covered by exact enum aliases.

enum_fuzzy_input.json
  Controlled vocabulary values contain small spelling variants.

enum_semantic_input.json
  Controlled vocabulary values require semantic matching beyond exact aliases.

service_semantic_input.json
  Service free-text values are intentionally phrased more freely to exercise
  semantic matching and review behavior.
