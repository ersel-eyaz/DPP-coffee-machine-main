from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from dpp.data_quality.anomaly.features import FeatureRow
from dpp.data_quality.anomaly.ml import IsolationForestConfig, MLAnomalyOptions
from dpp.data_quality.anomaly.outputs import build_anomaly_report
from dpp.data_quality.anomaly.schemas import AnomalyResult
from dpp.data_quality.anomaly.services import analyze_harmonization_result
from dpp.data_quality.anomaly.llm_review import build_service_llm_review_findings
from dpp.data_quality.harmonization.feedback import (
    append_feedback_record,
    approve_feedback_proposal,
    create_feedback_proposal,
    learned_mapping_from_feedback,
    load_learned_service_text_mappings,
)
from dpp.data_quality.harmonization.candidate_concepts import (
    build_candidate_concept_evidence_report,
    observations_from_learned_feedback,
    unresolved_service_observation,
)
from dpp.data_quality.harmonization.outputs import build_clean_jsonld, build_harmonization_report
from dpp.data_quality.harmonization.parser import ParseError, parse_jsonld_document
from dpp.data_quality.harmonization.services import harmonize_document
from dpp.data_quality.harmonization.service_concepts import TEXT_CONCEPTS_BY_ID, TEXT_CONCEPTS_BY_KIND
from dpp.data_quality.scopes import SUPPORTED_SCOPES


DataQualityScope = Literal["auto", "product", "emission", "service"]
DataQualityMode = Literal["harmonization", "anomaly", "both"]
DEFAULT_METRIC_EXPLANATION_MODEL = "gpt-5.4-mini"
METRIC_EXPLANATION_TIMEOUT_SECONDS = 20.0


_METRIC_EXPLANATION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "points", "limitations"],
    "properties": {
        "summary": {"type": "string"},
        "points": {"type": "array", "items": {"type": "string"}},
        "limitations": {"type": "array", "items": {"type": "string"}},
    },
}


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
    anomaly_options: "DataQualityAnomalyOptions" = Field(
        default_factory=lambda: DataQualityAnomalyOptions(),
        description="Optional configuration for statistical/ML anomaly checks.",
    )


class DataQualityTrainingFeatureRow(BaseModel):
    scope_name: Optional[str] = None
    feature_set: str
    entity_id: Optional[str] = None
    entity_type: str = "UploadedReferenceRow"
    features: Dict[str, float]
    source_entity_ids: List[str] = Field(default_factory=list)
    missing_features: List[str] = Field(default_factory=list)
    evidence: Dict[str, Any] = Field(default_factory=dict)


class DataQualityIsolationForestOptions(BaseModel):
    enabled: bool = True
    n_estimators: int = Field(100, ge=10, le=1000)
    contamination: float = Field(0.15, gt=0.0, le=0.5)
    max_samples: Optional[float] = Field(
        None,
        gt=0.0,
        description="None keeps the built-in default. Values <= 1 are treated as fractions; values > 1 as row counts.",
    )
    random_state: int = 42
    reference_rows: List[DataQualityTrainingFeatureRow] = Field(default_factory=list)
    reference_description: Optional[str] = None


class DataQualityAnomalyOptions(BaseModel):
    isolation_forest: DataQualityIsolationForestOptions = Field(default_factory=DataQualityIsolationForestOptions)


class ServiceTextFeedbackRequest(BaseModel):
    entity_type: str = Field(..., description="Service-step entity type, e.g. RepairServiceStep.")
    field_path: str = Field(..., description="Canonical service-text field path, e.g. RepairServiceStep.diagnose.")
    original_value: str = Field(..., description="Original service text to store as local learned evidence.")
    concept_id: str = Field(..., description="Existing service concept id selected by the reviewer.")
    proposed_surface_form: Optional[str] = Field(
        None,
        description="Optional surface form. Defaults to original_value.",
    )
    rationale: Optional[str] = Field(
        None,
        description="Optional non-verified prototype review rationale.",
    )


class ServiceTextCandidateObservationRequest(BaseModel):
    observation_id: Optional[str] = None
    kind: Literal["symptom", "diagnosis"]
    text: str
    field_path: Optional[str] = None
    service_type: Optional[str] = None
    part_label: Optional[str] = None


class ServiceConceptCandidateReportRequest(BaseModel):
    unresolved_observations: List[ServiceTextCandidateObservationRequest] = Field(default_factory=list)
    cluster_similarity_threshold: float = Field(
        0.72,
        ge=0.0,
        le=1.0,
        description="Prototype lexical similarity threshold used to group service-text observations.",
    )


class CandidateMetricInterpretationRequest(BaseModel):
    clustering_quality: Dict[str, Any] = Field(
        ...,
        description="Numeric/internal clustering diagnostics to explain.",
    )
    sources: Dict[str, Any] = Field(
        default_factory=dict,
        description="Observation source counts, without raw service text.",
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Non-sensitive report parameters, without raw service text or concept decisions.",
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


def _service_text_kind_for_field_path(field_path: str) -> Optional[str]:
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


def _ml_options_from_request(request: DataQualityRunRequest, scope_name: str) -> MLAnomalyOptions:
    """Convert request-level anomaly options into the internal ML options object."""
    isolation = request.anomaly_options.isolation_forest
    reference_rows: List[FeatureRow] = []
    for index, row in enumerate(isolation.reference_rows, start=1):
        row_scope = row.scope_name or scope_name
        if row_scope != scope_name:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Uploaded Isolation Forest reference rows must match the selected scope. "
                    f"Row {index} has scope {row_scope!r}, selected scope is {scope_name!r}."
                ),
            )
        if not row.features:
            raise HTTPException(
                status_code=400,
                detail=f"Uploaded Isolation Forest reference row {index} has no numeric features.",
            )
        reference_rows.append(
            FeatureRow(
                scope_name=row_scope,
                feature_set=row.feature_set,
                entity_id=row.entity_id or f"uploaded-reference-{index:03d}",
                entity_type=row.entity_type,
                features={key: float(value) for key, value in row.features.items()},
                source_entity_ids=row.source_entity_ids,
                missing_features=row.missing_features,
                evidence={**row.evidence, "reference_source": "user_uploaded"},
            )
        )

    return MLAnomalyOptions(
        isolation_forest=IsolationForestConfig(
            enabled=isolation.enabled,
            n_estimators=isolation.n_estimators,
            contamination=isolation.contamination,
            max_samples=isolation.max_samples,
            random_state=isolation.random_state,
        ),
        reference_rows=reference_rows or None,
        reference_description=isolation.reference_description,
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
    concepts_by_kind: Dict[str, List[Dict[str, Any]]] = {}
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


@router.post("/service-concept-candidates")
async def build_service_concept_candidate_report(request: ServiceConceptCandidateReportRequest) -> Dict[str, Any]:
    """Build a review-only service concept candidate evidence report."""
    learned_observations = observations_from_learned_feedback(load_learned_service_text_mappings())
    unresolved_observations = []
    for index, observation in enumerate(request.unresolved_observations, start=1):
        text = observation.text.strip()
        if not text:
            continue
        unresolved_observations.append(
            unresolved_service_observation(
                observation_id=observation.observation_id or f"request-unresolved-{index}",
                kind=observation.kind,
                text=text,
                field_path=observation.field_path,
                service_type=observation.service_type,
                part_label=observation.part_label,
            )
        )

    report = build_candidate_concept_evidence_report(
        (*learned_observations, *unresolved_observations),
        cluster_similarity_threshold=request.cluster_similarity_threshold,
    )
    payload = report.as_dict()
    payload["sources"] = {
        "learned_feedback_observations": len(learned_observations),
        "request_unresolved_observations": len(unresolved_observations),
    }
    return payload


@router.post("/service-concept-candidates/metric-interpretation")
async def explain_service_candidate_metrics(request: CandidateMetricInterpretationRequest) -> Dict[str, Any]:
    """Return an optional LLM explanation of clustering diagnostics only."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return {
            "status": "unavailable",
            "message": "LLM metric explanation is unavailable because OPENAI_API_KEY is not configured.",
        }

    context = {
        "task": "explain_service_candidate_clustering_metrics",
        "clustering_quality": request.clustering_quality,
        "sources": request.sources,
        "parameters": request.parameters,
        "constraints": [
            "Do not make service concept, vocabulary promotion, or alias decisions.",
            "Do not infer domain-specific machine facts.",
            "Explain whether the clustering diagnostics are interpretable and what their limitations are.",
            "Treat the metrics as internal diagnostics, not validated model performance.",
        ],
    }
    model = os.getenv("DPP_DQ_LLM_MODEL", DEFAULT_METRIC_EXPLANATION_MODEL).strip() or DEFAULT_METRIC_EXPLANATION_MODEL
    timeout = _env_float("DPP_DQ_LLM_TIMEOUT_SECONDS", METRIC_EXPLANATION_TIMEOUT_SECONDS)
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": (
                    "You explain clustering diagnostics for a data-quality review UI. "
                    "You receive only aggregate metrics, not raw service text and not concept definitions. "
                    "Give a short cautious interpretation. Do not validate performance, do not recommend "
                    "concept promotion, and do not discuss domain-specific service concepts."
                ),
            },
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "candidate_metric_interpretation",
                "schema": _METRIC_EXPLANATION_SCHEMA,
                "strict": True,
            }
        },
        "max_output_tokens": 500,
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
        return {
            "status": "unavailable",
            "message": f"LLM metric explanation is unavailable: OpenAI API returned HTTP {exc.response.status_code}.",
        }
    except httpx.HTTPError as exc:
        return {
            "status": "unavailable",
            "message": f"LLM metric explanation is unavailable: OpenAI API request failed ({type(exc).__name__}).",
        }

    response_text = _extract_response_text(response.json())
    if response_text is None:
        return {
            "status": "unavailable",
            "message": "LLM metric explanation is unavailable: OpenAI API response did not contain JSON text.",
        }

    try:
        interpretation = json.loads(response_text)
    except json.JSONDecodeError:
        return {
            "status": "unavailable",
            "message": "LLM metric explanation is unavailable: OpenAI API response JSON could not be parsed.",
        }

    return {
        "status": "ok",
        "model": model,
        "interpretation": interpretation,
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
            anomaly_result = analyze_harmonization_result(
                result,
                ml_options=_ml_options_from_request(request, scope_name),
            )
        except HTTPException:
            raise
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


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _extract_response_text(response_payload: Dict[str, Any]) -> Optional[str]:
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
