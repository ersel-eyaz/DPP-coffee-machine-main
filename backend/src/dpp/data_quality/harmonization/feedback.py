"""
Human-in-the-loop feedback proposals for service harmonization.

The helpers in this module do not mutate the core concept registry. They create
small auditable records that can later be reviewed, approved, rejected, or used
as local evidence for surface-form or relation-hint suggestions.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4


FeedbackAction = Literal[
    "accept_mapping",
    "reject_mapping",
    "propose_surface_form",
    "propose_relation_hint",
]
FeedbackStatus = Literal["proposed", "approved", "rejected"]

_SERVICE_TEXT_KIND_BY_FIELD_SUFFIX = {
    ".diagnose": "diagnosis",
    ".observedSymptoms": "symptom",
}
DEFAULT_LEARNED_FEEDBACK_PATH = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "feedback"
    / "learned_service_feedback.local.json"
)


@dataclass(frozen=True)
class HarmonizationFeedbackProposal:
    """Auditable user feedback that is kept separate from seeded registries."""

    proposal_id: str
    action: FeedbackAction
    status: FeedbackStatus
    scope_name: str
    entity_type: str
    field_path: str
    original_value: Any
    concept_id: str | None = None
    proposed_surface_form: str | None = None
    proposed_service_type: str | None = None
    proposed_part_keywords: tuple[str, ...] = ()
    reviewer: str | None = None
    rationale: str | None = None
    source: str = "manual_review"
    created_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation without empty optional values."""
        return {
            key: value
            for key, value in asdict(self).items()
            if value is not None and value != () and value != []
        }


@dataclass(frozen=True)
class LearnedServiceTextMapping:
    """Approved local service-text evidence kept outside the core registry."""

    feedback_id: str
    kind: Literal["symptom", "diagnosis"]
    field_path: str
    original_value: str
    concept_id: str
    surface_form: str
    status: FeedbackStatus = "approved"
    source: str = "manual_review"
    created_at_utc: str | None = None
    rationale: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return a compact JSON-serializable representation."""
        return {
            key: value
            for key, value in asdict(self).items()
            if value is not None and value != () and value != []
        }


def create_feedback_proposal(
    *,
    action: FeedbackAction,
    scope_name: str,
    entity_type: str,
    field_path: str,
    original_value: Any,
    concept_id: str | None = None,
    proposed_surface_form: str | None = None,
    proposed_service_type: str | None = None,
    proposed_part_keywords: tuple[str, ...] = (),
    reviewer: str | None = None,
    rationale: str | None = None,
) -> HarmonizationFeedbackProposal:
    """Create a proposed feedback record without changing canonical registries."""
    return HarmonizationFeedbackProposal(
        proposal_id=f"feedback-{uuid4().hex}",
        action=action,
        status="proposed",
        scope_name=scope_name,
        entity_type=entity_type,
        field_path=field_path,
        original_value=original_value,
        concept_id=concept_id,
        proposed_surface_form=proposed_surface_form,
        proposed_service_type=proposed_service_type,
        proposed_part_keywords=proposed_part_keywords,
        reviewer=reviewer,
        rationale=rationale,
    )


def learned_mapping_from_feedback(
    proposal: HarmonizationFeedbackProposal,
) -> LearnedServiceTextMapping | None:
    """Return approved service-text mapping evidence for a feedback record."""
    if proposal.status != "approved":
        return None
    if proposal.scope_name != "service":
        return None
    if proposal.action not in {"accept_mapping", "propose_surface_form"}:
        return None
    if proposal.concept_id is None:
        return None

    kind = _service_text_kind_for_field_path(proposal.field_path)
    if kind is None:
        return None

    surface_form = proposal.proposed_surface_form
    if surface_form is None and isinstance(proposal.original_value, str):
        surface_form = proposal.original_value
    if surface_form is None or not surface_form.strip():
        return None

    original_value = proposal.original_value if isinstance(proposal.original_value, str) else surface_form
    return LearnedServiceTextMapping(
        feedback_id=proposal.proposal_id,
        kind=kind,
        field_path=proposal.field_path,
        original_value=original_value,
        concept_id=proposal.concept_id,
        surface_form=surface_form,
        source=proposal.source if proposal.source != "user_feedback" else "manual_review",
        created_at_utc=proposal.created_at_utc,
        rationale=proposal.rationale,
    )


def approve_feedback_proposal(
    proposal: HarmonizationFeedbackProposal,
    *,
    reviewer: str,
    rationale: str | None = None,
) -> HarmonizationFeedbackProposal:
    """Return an approved copy of a feedback proposal."""
    return HarmonizationFeedbackProposal(
        **{
            **asdict(proposal),
            "status": "approved",
            "reviewer": reviewer,
            "rationale": rationale if rationale is not None else proposal.rationale,
        }
    )


def reject_feedback_proposal(
    proposal: HarmonizationFeedbackProposal,
    *,
    reviewer: str,
    rationale: str | None = None,
) -> HarmonizationFeedbackProposal:
    """Return a rejected copy of a feedback proposal."""
    return HarmonizationFeedbackProposal(
        **{
            **asdict(proposal),
            "status": "rejected",
            "reviewer": reviewer,
            "rationale": rationale if rationale is not None else proposal.rationale,
        }
    )


def load_learned_service_text_mappings(
    path: str | Path | None = None,
) -> tuple[LearnedServiceTextMapping, ...]:
    """Load approved learned service-text mappings from a JSON artifact.

    The path is intentionally external/configurable so runtime feedback evidence
    remains separable from the documented core concept registry.
    """
    artifact_path = _feedback_artifact_path(path)
    if artifact_path is None or not artifact_path.exists():
        return ()

    with artifact_path.open("r", encoding="utf-8") as source:
        payload = json.load(source)

    records = payload.get("feedback") if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        return ()

    mappings: list[LearnedServiceTextMapping] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        proposal = _proposal_from_record(record)
        if proposal is not None:
            mapping = learned_mapping_from_feedback(proposal)
            if mapping is not None:
                mappings.append(mapping)
            continue

        mapping = _learned_mapping_from_record(record)
        if mapping is not None:
            mappings.append(mapping)

    return tuple(mappings)


def append_feedback_record(
    proposal: HarmonizationFeedbackProposal,
    path: str | Path | None = None,
) -> HarmonizationFeedbackProposal:
    """Append one feedback record to the local JSON artifact.

    If an equivalent record already exists, the existing record is returned.
    This keeps repeated button clicks from creating noisy duplicate evidence.
    """
    artifact_path = _feedback_artifact_path(path)
    if artifact_path is None:
        artifact_path = DEFAULT_LEARNED_FEEDBACK_PATH
    artifact_path.parent.mkdir(parents=True, exist_ok=True)

    records = _load_feedback_records(artifact_path)
    proposal_dict = proposal.as_dict()
    duplicate = _find_equivalent_record(records, proposal_dict)
    if duplicate is not None:
        existing = _proposal_from_record(duplicate)
        if existing is not None:
            return existing

    records.append(proposal_dict)
    artifact_path.write_text(
        json.dumps(
            {
                "description": (
                    "Local prototype learned service-text feedback. "
                    "Generated at runtime and intentionally kept outside the core registry."
                ),
                "feedback": records,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return proposal


def _feedback_artifact_path(path: str | Path | None) -> Path | None:
    if path is not None:
        return Path(path)

    configured = os.getenv("DPP_DQ_LEARNED_FEEDBACK_PATH", "").strip()
    if not configured:
        return DEFAULT_LEARNED_FEEDBACK_PATH
    return Path(configured)


def _load_feedback_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as source:
            payload = json.load(source)
    except (OSError, json.JSONDecodeError):
        return []

    records = payload.get("feedback") if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        return []
    return [record for record in records if isinstance(record, dict)]


def _find_equivalent_record(
    records: list[dict[str, Any]],
    proposal: dict[str, Any],
) -> dict[str, Any] | None:
    for record in records:
        if record.get("status") != proposal.get("status"):
            continue
        if record.get("action") != proposal.get("action"):
            continue
        if record.get("scope_name") != proposal.get("scope_name"):
            continue
        if record.get("entity_type") != proposal.get("entity_type"):
            continue
        if record.get("field_path") != proposal.get("field_path"):
            continue
        if record.get("original_value") != proposal.get("original_value"):
            continue
        if record.get("concept_id") != proposal.get("concept_id"):
            continue
        if record.get("proposed_surface_form") != proposal.get("proposed_surface_form"):
            continue
        return record
    return None


def _service_text_kind_for_field_path(field_path: str) -> Literal["symptom", "diagnosis"] | None:
    for suffix, kind in _SERVICE_TEXT_KIND_BY_FIELD_SUFFIX.items():
        if field_path.endswith(suffix):
            return kind  # type: ignore[return-value]
    return None


def _proposal_from_record(record: dict[str, Any]) -> HarmonizationFeedbackProposal | None:
    required = {"proposal_id", "action", "status", "scope_name", "entity_type", "field_path", "original_value"}
    if not required.issubset(record):
        return None

    try:
        return HarmonizationFeedbackProposal(
            proposal_id=str(record["proposal_id"]),
            action=record["action"],
            status=record["status"],
            scope_name=str(record["scope_name"]),
            entity_type=str(record["entity_type"]),
            field_path=str(record["field_path"]),
            original_value=record["original_value"],
            concept_id=_optional_str(record.get("concept_id")),
            proposed_surface_form=_optional_str(record.get("proposed_surface_form")),
            proposed_service_type=_optional_str(record.get("proposed_service_type")),
            proposed_part_keywords=tuple(str(item) for item in record.get("proposed_part_keywords", ())),
            reviewer=_optional_str(record.get("reviewer")),
            rationale=_optional_str(record.get("rationale")),
            source=str(record.get("source") or "manual_review"),
            created_at_utc=str(record.get("created_at_utc") or datetime.now(timezone.utc).isoformat()),
        )
    except TypeError:
        return None


def _learned_mapping_from_record(record: dict[str, Any]) -> LearnedServiceTextMapping | None:
    if record.get("status", "approved") != "approved":
        return None

    kind = record.get("kind")
    field_path = str(record.get("field_path") or "")
    if kind not in {"symptom", "diagnosis"}:
        kind = _service_text_kind_for_field_path(field_path)
    if kind not in {"symptom", "diagnosis"}:
        return None

    concept_id = _optional_str(record.get("concept_id"))
    surface_form = _optional_str(record.get("surface_form") or record.get("proposed_surface_form"))
    if concept_id is None or surface_form is None:
        return None

    return LearnedServiceTextMapping(
        feedback_id=str(record.get("feedback_id") or record.get("proposal_id") or f"feedback-{uuid4().hex}"),
        kind=kind,
        field_path=field_path,
        original_value=str(record.get("original_value") or surface_form),
        concept_id=concept_id,
        surface_form=surface_form,
        status="approved",
        source=str(record.get("source") or "manual_review"),
        created_at_utc=_optional_str(record.get("created_at_utc")),
        rationale=_optional_str(record.get("rationale")),
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
