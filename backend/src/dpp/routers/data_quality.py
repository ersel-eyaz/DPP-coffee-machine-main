from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from dpp.data_quality.anomaly.outputs import build_anomaly_report
from dpp.data_quality.anomaly.schemas import AnomalyResult
from dpp.data_quality.anomaly.services import analyze_harmonization_result
from dpp.data_quality.anomaly.llm_review import build_service_llm_review_findings
from dpp.data_quality.harmonization.feedback import (
    append_feedback_record,
    approve_feedback_proposal,
    create_feedback_proposal,
    learned_mapping_from_feedback,
)
from dpp.data_quality.harmonization.outputs import build_clean_jsonld, build_harmonization_report
from dpp.data_quality.harmonization.parser import ParseError, parse_jsonld_document
from dpp.data_quality.harmonization.services import harmonize_document
from dpp.data_quality.harmonization.service_concepts import TEXT_CONCEPTS_BY_ID, TEXT_CONCEPTS_BY_KIND
from dpp.data_quality.scopes import SUPPORTED_SCOPES


DataQualityScope = Literal["auto", "product", "emission", "service"]
DataQualityMode = Literal["harmonization", "anomaly", "both"]


class DataQualityRunRequest(BaseModel):
    scope: DataQualityScope
    mode: DataQualityMode = "both"
    document: Dict[str, Any] = Field(..., description="JSON-LD document to check without storing it in MongoDB.")
    enable_llm_review: bool = Field(
        False,
        description="Optionally add a transparent LLM-assisted service review layer after deterministic checks.",
    )
    review_context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional caller-provided context for review-only checks, e.g. selected service part label.",
    )


class ServiceTextFeedbackRequest(BaseModel):
    entity_type: str = Field(..., description="Service-step entity type, e.g. RepairServiceStep.")
    field_path: str = Field(..., description="Canonical service-text field path, e.g. RepairServiceStep.diagnose.")
    original_value: str = Field(..., description="Original service text to store as local learned evidence.")
    concept_id: str = Field(..., description="Existing service concept id selected by the reviewer.")
    proposed_surface_form: str | None = Field(
        None,
        description="Optional surface form. Defaults to original_value.",
    )
    rationale: str | None = Field(
        None,
        description="Optional non-verified prototype review rationale.",
    )


router = APIRouter()

EXAMPLE_DOCUMENTS: Dict[str, Dict[str, str]] = {
    "product_dirty": {
        "label": "Product harmonization",
        "scope": "product",
        "path": "harmonization/product_dirty.json",
    },
    "product_anomaly": {
        "label": "Product anomaly",
        "scope": "product",
        "path": "harmonization/product_anomaly_input.json",
    },
    "emission_anomaly": {
        "label": "Emission anomaly",
        "scope": "emission",
        "path": "harmonization/emission_anomaly_input.json",
    },
    "emission_semantic": {
        "label": "Emission semantic",
        "scope": "emission",
        "path": "harmonization/enum_semantic_input.json",
    },
    "service_text": {
        "label": "Service text",
        "scope": "service",
        "path": "harmonization/service_text_input.json",
    },
    "service_semantic": {
        "label": "Service semantic",
        "scope": "service",
        "path": "harmonization/service_semantic_input.json",
    },
    "service_anomaly": {
        "label": "Service anomaly",
        "scope": "service",
        "path": "harmonization/service_anomaly_input.json",
    },
}


def _examples_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "data_quality" / "examples"


def _service_text_kind_for_field_path(field_path: str) -> str | None:
    if field_path.endswith(".diagnose"):
        return "diagnosis"
    if field_path.endswith(".observedSymptoms"):
        return "symptom"
    return None


def _detect_scope(document: Dict[str, Any]) -> str:
    """Infer a data-quality scope from JSON-LD entity types."""
    try:
        parsed = parse_jsonld_document(document)
    except ParseError as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse JSON-LD for scope detection: {exc}") from exc

    candidate_scopes = set()
    ignored_overlap_only = False

    for entity in parsed.entities:
        owners = [
            scope_name
            for scope_name, scope in SUPPORTED_SCOPES.items()
            if entity.entity_type in scope.entities
        ]
        if len(owners) == 1:
            candidate_scopes.add(owners[0])
        elif owners:
            ignored_overlap_only = True

    if len(candidate_scopes) == 1:
        return next(iter(candidate_scopes))

    if len(candidate_scopes) > 1:
        names = ", ".join(sorted(candidate_scopes))
        raise HTTPException(
            status_code=400,
            detail=f"Multiple data-quality scopes detected ({names}). Please choose one explicitly.",
        )

    if ignored_overlap_only:
        raise HTTPException(
            status_code=400,
            detail="Could not auto-detect scope from shared entity types only. Please choose product, emission, or service.",
        )

    raise HTTPException(
        status_code=400,
        detail="Could not auto-detect scope from entity types. Please choose product, emission, or service.",
    )


@router.get("/examples")
async def list_data_quality_examples() -> Dict[str, Any]:
    examples = [
        {
            "name": name,
            "label": item["label"],
            "scope": item["scope"],
        }
        for name, item in EXAMPLE_DOCUMENTS.items()
    ]
    return {"examples": examples}


@router.get("/examples/{example_name}")
async def get_data_quality_example(example_name: str) -> Dict[str, Any]:
    item = EXAMPLE_DOCUMENTS.get(example_name)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Unknown data-quality example: {example_name}")

    path = _examples_dir() / item["path"]
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not load example: {example_name}") from exc

    return {
        "name": example_name,
        "label": item["label"],
        "scope": item["scope"],
        "document": document,
    }


@router.get("/service-concepts")
async def list_service_concepts() -> Dict[str, Any]:
    """Return service concepts that can be selected for prototype feedback."""
    concepts_by_kind: Dict[str, list[Dict[str, Any]]] = {}
    for kind, concepts in TEXT_CONCEPTS_BY_KIND.items():
        concepts_by_kind[kind] = [
            {
                "concept_id": concept.concept_id,
                "kind": concept.kind,
                "label": concept.label,
                "description": concept.description,
                "inventory_status": concept.inventory_status,
            }
            for concept in concepts
        ]
    return {"concepts_by_kind": concepts_by_kind}


@router.post("/feedback/service-text")
async def create_service_text_feedback(request: ServiceTextFeedbackRequest) -> Dict[str, Any]:
    """Store approved local learned feedback for one service free-text value."""
    original_value = request.original_value.strip()
    if not original_value:
        raise HTTPException(status_code=400, detail="Feedback original_value must not be empty.")

    field_kind = _service_text_kind_for_field_path(request.field_path)
    if field_kind is None:
        raise HTTPException(
            status_code=400,
            detail="Feedback is currently supported only for diagnose and observedSymptoms service text fields.",
        )

    concept = TEXT_CONCEPTS_BY_ID.get(request.concept_id)
    if concept is None:
        raise HTTPException(status_code=400, detail=f"Unknown service concept id: {request.concept_id}")
    if concept.kind != field_kind:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Concept {request.concept_id!r} has kind {concept.kind!r}, "
                f"but field {request.field_path!r} expects {field_kind!r}."
            ),
        )

    proposal = create_feedback_proposal(
        action="accept_mapping",
        scope_name="service",
        entity_type=request.entity_type,
        field_path=request.field_path,
        original_value=original_value,
        concept_id=concept.concept_id,
        proposed_surface_form=(request.proposed_surface_form or original_value).strip(),
        reviewer="prototype_review",
        rationale=request.rationale or "Added through the service quality feedback UI.",
    )
    approved = approve_feedback_proposal(
        proposal,
        reviewer="prototype_review",
        rationale=request.rationale or "Added through the service quality feedback UI.",
    )
    stored = append_feedback_record(approved)
    mapping = learned_mapping_from_feedback(stored)

    return {
        "status": "stored",
        "feedback": stored.as_dict(),
        "learned_mapping": mapping.as_dict() if mapping is not None else None,
    }


@router.post("/run")
async def run_data_quality(request: DataQualityRunRequest) -> Dict[str, Any]:
    """
    Run the isolated data-quality layer on an external JSON-LD document.

    This endpoint is intentionally stateless: it does not create or update DPP
    instances and does not write to MongoDB.
    """
    scope_name = _detect_scope(request.document) if request.scope == "auto" else request.scope

    try:
        result = harmonize_document(request.document, scope_name)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Harmonization failed: {exc}") from exc

    payload: Dict[str, Any] = {
        "scope": scope_name,
        "requested_scope": request.scope,
        "mode": request.mode,
        "data": build_clean_jsonld(result, document=request.document),
        "harmonization_report": build_harmonization_report(result),
        "has_errors": result.has_errors(),
    }

    if request.mode in {"anomaly", "both"}:
        try:
            anomaly_result = analyze_harmonization_result(result)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Anomaly analysis failed: {exc}") from exc

        if request.enable_llm_review and scope_name == "service":
            llm_findings = await build_service_llm_review_findings(
                result,
                deterministic_findings=anomaly_result.findings,
                review_context=request.review_context,
            )
            anomaly_result = AnomalyResult(
                scope_name=anomaly_result.scope_name,
                findings=[*anomaly_result.findings, *llm_findings],
            )

        payload["anomaly_report"] = build_anomaly_report(anomaly_result)
        payload["has_errors"] = result.has_errors() or anomaly_result.has_errors()

    return payload
