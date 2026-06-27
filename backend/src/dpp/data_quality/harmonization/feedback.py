"""
Human-in-the-loop feedback proposals for service harmonization.

The helpers in this module do not mutate the core concept registry. They create
small auditable records that can later be reviewed, approved, rejected, or used
as local evidence for surface-form or relation-hint suggestions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4


FeedbackAction = Literal[
    "accept_mapping",
    "reject_mapping",
    "propose_surface_form",
    "propose_relation_hint",
]
FeedbackStatus = Literal["proposed", "approved", "rejected"]


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
    source: str = "user_feedback"
    created_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation without empty optional values."""
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
