"""
LLM-assisted review findings for service data quality.

The deterministic harmonization and anomaly layers remain authoritative. This
module adds transparent, review-only suggestions when requested by the caller.
If the API key or model is unavailable, it fails soft and returns an
informational finding instead of blocking deterministic checks.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from dpp.data_quality.anomaly.schemas import AnomalyFinding
from dpp.data_quality.harmonization.free_text import (
    AMBIGUOUS_TEXT_FUZZY_THRESHOLD,
    AMBIGUOUS_TEXT_SEMANTIC_THRESHOLD,
)
from dpp.data_quality.harmonization.result_access import effective_field_value
from dpp.data_quality.harmonization.schemas import HarmonizationResult, HarmonizedEntity
from dpp.data_quality.harmonization.service_concepts import TEXT_CONCEPTS_BY_ID

DEFAULT_LLM_REVIEW_MODEL = "gpt-5.4-mini"
LLM_REVIEW_PROMPT_VERSION = "service_llm_review_v1"
LLM_REVIEW_TIMEOUT_SECONDS = 30.0

_SERVICE_PART_CONTEXT_FIELDS: dict[str, tuple[str, ...]] = {
    "RepairServiceStep": ("repairedPartId",),
    "ReplaceServiceStep": ("replacedPartId",),
    "CleaningServiceStep": ("cleanedPartId",),
    "RefurbishmentServiceStep": ("repairedPartIds", "cleanedPartIds"),
    "RemanufacturingServiceStep": ("repairedPartIds", "cleanedPartIds"),
}

_REVIEW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["reviews"],
    "properties": {
        "reviews": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "entity_id",
                    "verdict",
                    "severity",
                    "message",
                    "confidence",
                    "evidence_ids",
                ],
                "properties": {
                    "entity_id": {"type": "string"},
                    "verdict": {
                        "type": "string",
                        "enum": ["ok", "review", "likely_inconsistent"],
                    },
                    "severity": {"type": "string", "enum": ["info", "warning"]},
                    "message": {"type": "string"},
                    "confidence": {"type": "number"},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _iter_text_entries(value: Any) -> list[dict[str, Any]]:
    """Flatten text harmonization entries from an entity report section."""
    if isinstance(value, dict):
        if "status" in value and "original_value" in value:
            return [value]
        entries: list[dict[str, Any]] = []
        for item in value.values():
            entries.extend(_iter_text_entries(item))
        return entries

    if isinstance(value, list):
        entries = []
        for item in value:
            entries.extend(_iter_text_entries(item))
        return entries

    return []


def _field_value(entity: HarmonizedEntity, field_name: str) -> Any | None:
    field = entity.fields.get(f"{entity.entity_type}.{field_name}")
    if field is None:
        return None
    return effective_field_value(field)


def _service_part_references(entity: HarmonizedEntity) -> list[str]:
    references: list[str] = []
    for field_name in _SERVICE_PART_CONTEXT_FIELDS.get(entity.entity_type, ()):
        value = _field_value(entity, field_name)
        if isinstance(value, list):
            references.extend(str(item) for item in value if item)
        elif value:
            references.append(str(value))

    for existing_part_id, _new_part in entity.paired_embedded_entities.get("replacedAndNewParts", []):
        references.append(existing_part_id)

    return references


def _concept_context(concept_id: str) -> dict[str, Any] | None:
    concept = TEXT_CONCEPTS_BY_ID.get(concept_id)
    if concept is None:
        return None

    return {
        "concept_id": concept.concept_id,
        "kind": concept.kind,
        "label": concept.label,
        "description": concept.description,
        "evidence_source": "core_registry",
        "inventory_status": concept.inventory_status,
        "examples": list(concept.examples[:5]),
        "related_context_terms": list(concept.related_context_terms),
    }


def _candidate_entries(entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Return report candidates and closest candidates without duplicates."""
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str | None]] = set()
    for bucket_name in ("candidates", "closest_candidates"):
        for candidate in entry.get(bucket_name, []):
            if not isinstance(candidate, dict):
                continue
            key = (
                str(candidate.get("concept_id") or ""),
                str(candidate.get("source") or "core_registry"),
                candidate.get("feedback_id"),
            )
            if key in seen:
                continue
            enriched = dict(candidate)
            enriched["candidate_bucket"] = bucket_name
            enriched["decision_role"] = _candidate_decision_role(enriched)
            candidates.append(enriched)
            seen.add(key)
    return candidates


def _candidate_threshold(candidate: dict[str, Any]) -> float:
    method = str(candidate.get("method") or candidate.get("match_type") or "")
    if "semantic" in method:
        return AMBIGUOUS_TEXT_SEMANTIC_THRESHOLD
    return AMBIGUOUS_TEXT_FUZZY_THRESHOLD


def _candidate_decision_role(candidate: dict[str, Any]) -> str:
    if candidate.get("candidate_bucket") == "candidates":
        return "candidate"

    confidence = candidate.get("confidence")
    try:
        score = float(confidence)
    except (TypeError, ValueError):
        return "trace_only"

    return "candidate" if score >= _candidate_threshold(candidate) else "trace_only"


def _collect_text_context(entity: HarmonizedEntity) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    text_entries: list[dict[str, Any]] = []
    concepts: dict[str, dict[str, Any]] = {}

    for field_name, value in entity.text_harmonization.items():
        for index, entry in enumerate(_iter_text_entries(value), start=1):
            entry_id = f"{entity.entity_id}:{field_name}:{index}"
            normalized = entry.get("normalized_value")
            candidate_entries = _candidate_entries(entry)
            llm_candidate_entries = [
                candidate
                for candidate in candidate_entries
                if candidate.get("decision_role") == "candidate"
            ]
            learned_feedback_candidates = [
                candidate
                for candidate in llm_candidate_entries
                if candidate.get("source") == "learned_feedback"
            ]
            candidate_ids = [
                candidate.get("concept_id")
                for candidate in llm_candidate_entries
            ]
            concept_ids = [
                concept_id
                for concept_id in [normalized, *candidate_ids]
                if isinstance(concept_id, str)
            ]

            text_entries.append(
                {
                    "evidence_id": entry_id,
                    "field": field_name,
                    "original_value": entry.get("original_value"),
                    "status": entry.get("status"),
                    "normalized_concept": normalized,
                    "confidence": entry.get("confidence"),
                    "method": entry.get("method"),
                    "candidate_concepts": llm_candidate_entries,
                    "learned_feedback_candidates": learned_feedback_candidates,
                    "evidence_sources": sorted(
                        {
                            str(candidate.get("source") or "core_registry")
                            for candidate in llm_candidate_entries
                        }
                    ),
                    "trace_only_candidates_omitted": len(candidate_entries) - len(llm_candidate_entries),
                }
            )

            for concept_id in concept_ids:
                concept_payload = _concept_context(concept_id)
                if concept_payload is not None:
                    concepts[concept_id] = concept_payload

    return text_entries, concepts


def _build_review_context(
    result: HarmonizationResult,
    deterministic_findings: list[AnomalyFinding],
    review_context: dict[str, Any] | None,
) -> dict[str, Any]:
    service_steps: list[dict[str, Any]] = []
    concepts: dict[str, dict[str, Any]] = {}
    caller_context = review_context or {}

    for entity in result.iter_entities():
        if entity.entity_type not in _SERVICE_PART_CONTEXT_FIELDS and not entity.text_harmonization:
            continue

        text_entries, entity_concepts = _collect_text_context(entity)
        concepts.update(entity_concepts)

        service_steps.append(
            {
                "entity_id": entity.entity_id,
                "entity_type": entity.entity_type,
                "part_references": _service_part_references(entity),
                "caller_context": caller_context,
                "text_entries": text_entries,
            }
        )

    local_findings = [
        {
            "check_id": finding.check_id,
            "severity": finding.severity,
            "category": finding.category,
            "entity_id": finding.entity_id,
            "message": finding.message,
            "field_path": finding.field_path,
            "observed_value": finding.observed_value,
            "expected": finding.expected,
        }
        for finding in deterministic_findings
        if finding.entity_type in _SERVICE_PART_CONTEXT_FIELDS or finding.entity_type is None
    ]

    return {
        "task": "review_pending_service_record",
        "prompt_version": LLM_REVIEW_PROMPT_VERSION,
        "scope": result.scope_name,
        "service_steps": service_steps,
        "retrieved_concepts": list(concepts.values()),
        "deterministic_findings": local_findings,
        "limits": {
            "no_automatic_correction": True,
            "review_only": True,
            "use_only_provided_context": True,
            "do_not_treat_learned_feedback_as_core": True,
        },
        "evidence_source_policy": {
            "core_registry": "Stable controlled vocabulary evidence.",
            "learned_feedback": "Reviewer-approved local evidence; weaker than core registry.",
            "candidate_concept": "Unpromoted concept candidate; use only as review context.",
        },
    }


def _unavailable_finding(reason: str) -> AnomalyFinding:
    return AnomalyFinding(
        check_id="service_llm_review_unavailable",
        category="review",
        severity="info",
        message=f"LLM service review was requested but is unavailable: {reason}.",
        confidence=0.0,
        evidence={
            "check_method": "llm_service_review",
            "status": "unavailable",
            "reason": reason,
            "prompt_version": LLM_REVIEW_PROMPT_VERSION,
        },
        review_action="configure_openai_api_key_or_continue_with_deterministic_checks",
    )


def _extract_response_text(response_payload: dict[str, Any]) -> str | None:
    direct = response_payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct

    for item in response_payload.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str) and text.strip():
                return text
    return None


def _findings_from_reviews(reviews: list[dict[str, Any]], model: str) -> list[AnomalyFinding]:
    findings: list[AnomalyFinding] = []
    reviews_by_entity: dict[str, list[dict[str, Any]]] = {}

    for review in reviews:
        entity_id = str(review.get("entity_id") or "service-step")
        reviews_by_entity.setdefault(entity_id, []).append(review)

    for entity_id, entity_reviews in reviews_by_entity.items():
        review = _merge_entity_reviews(entity_id, entity_reviews)
        verdict = review.get("verdict")
        severity = "warning" if verdict == "likely_inconsistent" else "info"
        if review.get("severity") in {"info", "warning"}:
            severity = review["severity"]
        check_id = "service_llm_review_ok" if verdict == "ok" else "service_llm_review_suggestion"
        message_prefix = "LLM service review"

        findings.append(
            AnomalyFinding(
                check_id=check_id,
                category="review" if verdict == "ok" else "semantic",
                severity=severity,
                message=f"{message_prefix}: {review.get('message', 'Please review this service record.')}",
                entity_id=entity_id,
                confidence=review.get("confidence"),
                expected=(
                    "no additional concern from LLM review"
                    if verdict == "ok"
                    else "human review of service type, selected part, and service text consistency"
                ),
                evidence={
                    "check_method": "llm_service_review",
                    "verdict": verdict,
                    "model": model,
                    "prompt_version": LLM_REVIEW_PROMPT_VERSION,
                    "evidence_ids": review.get("evidence_ids", []),
                },
                review_action="no_action_required" if verdict == "ok" else "review_llm_service_suggestion",
            )
        )

    return findings


def _merge_entity_reviews(entity_id: str, reviews: list[dict[str, Any]]) -> dict[str, Any]:
    if len(reviews) == 1:
        return reviews[0]

    verdict_rank = {"ok": 0, "review": 1, "likely_inconsistent": 2}
    severity_rank = {"info": 0, "warning": 1}
    primary = max(
        reviews,
        key=lambda item: (
            verdict_rank.get(item.get("verdict"), 0),
            severity_rank.get(item.get("severity"), 0),
            float(item.get("confidence") or 0.0),
        ),
    )
    messages = [
        str(item.get("message")).strip()
        for item in reviews
        if isinstance(item.get("message"), str) and str(item.get("message")).strip()
    ]
    evidence_ids: list[str] = []
    for item in reviews:
        evidence_ids.extend(
            str(evidence_id)
            for evidence_id in item.get("evidence_ids", [])
            if isinstance(evidence_id, str)
        )

    merged = dict(primary)
    merged["entity_id"] = entity_id
    merged["message"] = _compact_merged_review_message(messages)
    merged["evidence_ids"] = list(dict.fromkeys(evidence_ids))
    merged["confidence"] = max(float(item.get("confidence") or 0.0) for item in reviews)
    return merged


def _compact_merged_review_message(messages: list[str]) -> str:
    unique_messages = list(dict.fromkeys(messages))
    if not unique_messages:
        return "Review the service type, selected part, and service text before saving."

    lower_messages = " ".join(message.lower() for message in unique_messages)
    if "coverage gap" in lower_messages and "inconsisten" not in lower_messages:
        return (
            "The unresolved service texts look plausible for the selected service type and part, "
            "but are not covered by the current service concepts; review the service text before saving."
        )
    if "inconsisten" in lower_messages:
        return (
            "The selected service type, part, and service text may be inconsistent; review the record before saving."
        )
    return unique_messages[0]


async def build_service_llm_review_findings(
    result: HarmonizationResult,
    deterministic_findings: list[AnomalyFinding],
    review_context: dict[str, Any] | None = None,
) -> list[AnomalyFinding]:
    """
    Return LLM-assisted review findings for service records.

    The LLM receives a minimized local context package. If configuration is
    missing or the API call fails, this function returns an informational
    finding instead of failing the data-quality run.
    """
    if result.scope_name != "service":
        return []

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return [_unavailable_finding("OPENAI_API_KEY is not configured")]

    context = _build_review_context(result, deterministic_findings, review_context)
    if not context["service_steps"]:
        return []

    model = os.getenv("DPP_DQ_LLM_MODEL", DEFAULT_LLM_REVIEW_MODEL).strip() or DEFAULT_LLM_REVIEW_MODEL
    timeout = _env_float("DPP_DQ_LLM_TIMEOUT_SECONDS", LLM_REVIEW_TIMEOUT_SECONDS)

    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": (
                    "You are a conservative data-quality reviewer with practical domain knowledge of household "
                    "fully automatic coffee machines, also known as bean-to-cup coffee machines, and their "
                    "service records. "
                    "Use only the provided local context, canonical concepts, and deterministic findings. "
                    "Use your domain knowledge only for cautious plausibility review; do not invent "
                    "machine-specific facts beyond the provided service type, selected part, symptoms, "
                    "diagnosis, concepts, and findings. Do not normalize values. "
                    "Distinguish evidence sources carefully: core_registry is stable vocabulary evidence, "
                    "learned_feedback is weaker local review evidence, and candidate_concept is not a controlled concept. "
                    "Do not present learned_feedback or candidate_concept evidence as core vocabulary truth. "
                    "If a text entry contains learned_feedback_candidates, explicitly consider them as local "
                    "review evidence for the proposed concept, but still keep the review cautious. "
                    "A learned_feedback candidate may support plausibility; it must not be treated as an automatic correction. "
                    "Only candidate_concepts and learned_feedback_candidates in the context passed the reporting threshold; "
                    "do not refer to learned feedback unless it appears in learned_feedback_candidates. "
                    "When learned_feedback_candidates are relevant, explicitly mention learned feedback in natural language "
                    "and name the proposed concept, for example pump_fault, without using mechanical wording such as "
                    "'candidate concept id'. "
                    "Return exactly one review object for each service step, not one object per text entry. "
                    "Evaluate the selected service type, selected part, and service text together. "
                    "Pay special attention when the diagnosis text names a different subsystem or component "
                    "than the selected part label, even if one symptom still fits the selected part. "
                    "If such a different subsystem is detected, explicitly state that the selected part, "
                    "diagnosis, and symptom combination should be reviewed for consistency. "
                    "When raising a consistency concern, name the relation that is uncertain: "
                    "part-diagnosis, symptom-diagnosis, part-symptom, service-type-diagnosis, or service-type-part. "
                    "Use verdict ok when no additional attention is needed. Use review or likely_inconsistent only when the service type, "
                    "selected part, and service text relation deserves human attention. "
                    "When service text is unresolved, distinguish likely missing service-concept coverage from "
                    "possible consistency problems. If the original text appears lexically related to the "
                    "selected part or service type but is not covered by the canonical concepts, say that "
                    "it looks plausible but is not covered by the current service concepts, rather than calling it a clear inconsistency. "
                    "Messages must mention the selected service type, selected part label, and one relevant "
                    "original service text. Do not use vague phrases such as 'check with the selected service type' "
                    "or 'needs human check'. Keep messages short, cautious, and actionable."
                ),
            },
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "service_llm_review",
                "schema": _REVIEW_SCHEMA,
                "strict": True,
            }
        },
        "max_output_tokens": 1200,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                "https://api.openai.com/v1/responses",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        return [_unavailable_finding(f"OpenAI API returned HTTP {status}")]
    except httpx.HTTPError as exc:
        return [_unavailable_finding(f"OpenAI API request failed ({type(exc).__name__})")]

    response_payload = response.json()
    response_text = _extract_response_text(response_payload)
    if response_text is None:
        return [_unavailable_finding("OpenAI API response did not contain JSON text")]

    try:
        review_payload = json.loads(response_text)
    except json.JSONDecodeError:
        return [_unavailable_finding("OpenAI API response JSON could not be parsed")]

    reviews = review_payload.get("reviews", [])
    if not isinstance(reviews, list):
        return [_unavailable_finding("OpenAI API response did not match the review schema")]

    return _findings_from_reviews(reviews, model)
