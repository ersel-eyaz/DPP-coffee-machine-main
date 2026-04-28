Scenario examples for the isolated harmonization layer.

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
