# Feedback Learning Policy

This document defines how human feedback may support data-quality harmonization
without mutating seeded registries or silently changing canonical model
semantics.

The current prototype does not implement application-level user accounts, role
management, or authorization enforcement for this workflow. Feedback records
therefore represent controlled manual review evidence in a prototype setting,
not verified user identity.

## Scope

Feedback learning is currently limited to service-text harmonization and
service-relation review prompts.

The feedback layer may support:

- unresolved or ambiguous service-text mappings
- matches to `review_candidate` service concepts
- service diagnosis/part relation warnings
- service concept/service-type warnings
- proposed surface forms for existing service concepts

It must not directly overwrite:

- `harmonization/service_concepts.py`
- seeded concept descriptions
- core concept inventory status
- deterministic unit normalization
- hard validation rules

## Terminology

- Seeded registry: curated concept and alias data shipped with the prototype.
- Surface form: an alternative textual formulation for an existing canonical
  service concept.
- Learned feedback: approved user feedback stored separately from the seeded
  registry.
- Proposal: feedback that has been recorded but not approved.
- Approved feedback: feedback that may influence runtime suggestions or
  matching behavior.
- Rejected feedback: feedback kept for auditability but not used.

## Feedback Actions

The prototype supports these feedback action types:

- `accept_mapping`: confirm that a proposed mapping is correct.
- `reject_mapping`: mark a proposed mapping as incorrect.
- `propose_surface_form`: propose a new surface form for an existing concept.
- `propose_relation_hint`: propose a soft relation hint between a concept,
  service type, and part keywords.

## Runtime Effect

Approved feedback may affect runtime behavior only through a separate learned
feedback layer.

Approved surface forms may be merged into service-text matching as local learned
matching phrases. They should be reported with source `learned_feedback`.

Approved relation hints may support future soft anomaly/review prompts. They
must remain non-binding and should not be treated as hard compatibility rules.

Rejected feedback must not affect matching or anomaly checks.

## Safety Rules

- Original input text must always be preserved.
- A seeded mapping must remain distinguishable from a learned mapping.
- Feedback must include provenance: action, status, review source, timestamp,
  original value, and proposed concept.
- The prototype should not claim to verify a reviewer identity or role unless a
  future user/authorization layer is implemented.
- A single approved feedback record must not silently promote a concept to the
  core registry.
- Embedding-based matches must not automatically become learned surface forms.
  User approval is required.
- Learned feedback should be reversible by removing or rejecting the feedback
  record.

## Recommended Storage

The prototype should store feedback records as JSON artifacts before introducing
database persistence.

Recommended fields:

- `proposal_id`
- `action`
- `status`
- `scope_name`
- `entity_type`
- `field_path`
- `original_value`
- `concept_id`
- `proposed_surface_form`
- `proposed_service_type`
- `proposed_part_keywords`
- `reviewer` or `review_source` as a non-verified prototype metadata field
- `source`
- `created_at_utc`

The storage path should be configurable. A small example artifact may live under
`backend/src/dpp/data_quality/examples/feedback/`.

## Reporting

Reports should make feedback provenance visible.

For learned service-text mappings, report entries should indicate:

- normalized concept
- confidence or match method where available
- source: `learned_feedback`
- proposal id or feedback record id where available

For learned relation hints, anomaly findings should indicate:

- support level: `learned_feedback`
- originating proposal ids where available
- interpretation: `review_prompt_not_hard_error`

## Non-Goals

The feedback layer is not intended to:

- retrain the embedding model
- update Python seed files automatically
- make LLM suggestions authoritative
- create new canonical concepts without separate review
- replace deterministic validation or normalization logic

## Next Implementation Step

Implement a small runtime loader for approved feedback records and merge approved
service surface forms into service-text matching without changing seeded
concepts. Add tests that show an approved learned surface form can improve
matching and that its provenance remains visible.
