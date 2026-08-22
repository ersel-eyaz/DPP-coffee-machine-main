"""
Candidate service-concept evidence reports from local service-text observations.

This module intentionally does not create or promote canonical concepts. It
clusters observed service free text and reports neutral evidence that can later
support a governed vocabulary review.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from typing import Any, Literal

from dpp.data_quality.harmonization.feedback import LearnedServiceTextMapping
from dpp.data_quality.harmonization.free_text import TextNormalizationError, resolve_text_value
from dpp.data_quality.harmonization.service_concepts import (
    TEXT_CONCEPTS_BY_KIND,
    TextConcept,
    TextConceptKind,
)

ObservationSource = Literal["learned_feedback", "unresolved_observation"]


@dataclass(frozen=True)
class ServiceTextObservation:
    """One service free-text observation used as candidate-concept evidence."""

    observation_id: str
    kind: TextConceptKind
    text: str
    source: ObservationSource
    concept_id: str | None = None
    feedback_id: str | None = None
    field_path: str | None = None
    service_type: str | None = None
    part_label: str | None = None
    instance_id: str | None = None
    service_step_id: str | None = None
    part_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in asdict(self).items()
            if value is not None and value != "" and value != ()
        }


@dataclass(frozen=True)
class CoreAnchorEvidence:
    """Nearest current core/review concept used only as an interpretation anchor."""

    concept_id: str
    label: str
    similarity: float
    inventory_status: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CoreAliasCandidate:
    """Approved learned surface forms grouped for possible later core review."""

    concept_id: str
    kind: TextConceptKind
    surface_forms: tuple[str, ...]
    support_count: int
    feedback_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CandidateConceptCluster:
    """Neutral evidence for one cluster of observed service free-text phrases."""

    cluster_id: str
    kind: TextConceptKind
    observations: tuple[ServiceTextObservation, ...]
    n_total: int
    n_unresolved: int
    n_learned: int
    source_counts: dict[str, int]
    learned_target_counts: dict[str, int]
    top_learned_target: str | None
    top_learned_target_share: float | None
    nearest_core_id: str | None
    nearest_core_ids: tuple[str, ...]
    nearest_core_similarity: float | None
    second_core_similarity: float | None
    core_margin: float | None
    representative_texts: tuple[str, ...]
    candidate_surface_forms: tuple[str, ...]
    core_anchors: tuple[CoreAnchorEvidence, ...]

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["observations"] = [observation.as_dict() for observation in self.observations]
        payload["core_anchors"] = [anchor.as_dict() for anchor in self.core_anchors]
        return payload


@dataclass(frozen=True)
class CandidateConceptEvidenceReport:
    """JSON-serializable evidence report for later human vocabulary review."""

    parameters: dict[str, Any]
    clustering_quality: dict[str, Any]
    clusters: tuple[CandidateConceptCluster, ...]
    core_alias_candidates: tuple[CoreAliasCandidate, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "parameters": dict(self.parameters),
            "clustering_quality": dict(self.clustering_quality),
            "clusters": [cluster.as_dict() for cluster in self.clusters],
            "core_alias_candidates": [candidate.as_dict() for candidate in self.core_alias_candidates],
        }


@dataclass(frozen=True)
class HistoricalServiceTextRecord:
    """One persisted raw service-text occurrence with record provenance."""

    observation_id: str
    kind: TextConceptKind
    text: str
    canonical_value: str | None = None
    field_path: str | None = None
    service_type: str | None = None
    part_label: str | None = None
    instance_id: str | None = None
    service_step_id: str | None = None
    part_id: str | None = None


@dataclass(frozen=True)
class HistoricalObservationSelection:
    """Result of re-evaluating persisted raw service text for candidate evidence."""

    unresolved_observations: tuple[ServiceTextObservation, ...]
    inspected_count: int
    resolved_count: int
    learned_feedback_count: int


def select_unresolved_historical_observations(
    records: tuple[HistoricalServiceTextRecord, ...] | list[HistoricalServiceTextRecord],
    learned_mappings: tuple[LearnedServiceTextMapping, ...] | list[LearnedServiceTextMapping],
    *,
    enable_semantic: bool = True,
) -> HistoricalObservationSelection:
    """Re-evaluate historical originals and keep only unresolved/ambiguous evidence.

    Learned feedback remains review-only and is therefore not an automatic
    normalization rule. A historical occurrence is excluded as learned evidence
    only when its stored canonical value and original text match an approved
    mapping; this prevents that persisted occurrence from also being counted as
    unresolved evidence.
    """
    unresolved: list[ServiceTextObservation] = []
    inspected_count = 0
    resolved_count = 0
    learned_feedback_count = 0

    for record in records:
        text = " ".join(record.text.strip().split())
        if not text:
            continue
        inspected_count += 1

        try:
            resolved = resolve_text_value(record.kind, text, enable_semantic=enable_semantic)
        except TextNormalizationError:
            resolved = None
        if resolved is not None:
            resolved_count += 1
            continue

        if _matches_applied_learned_mapping(record, learned_mappings):
            learned_feedback_count += 1
            continue

        unresolved.append(
            unresolved_service_observation(
                observation_id=record.observation_id,
                kind=record.kind,
                text=text,
                field_path=record.field_path,
                service_type=record.service_type,
                part_label=record.part_label,
                instance_id=record.instance_id,
                service_step_id=record.service_step_id,
                part_id=record.part_id,
            )
        )

    return HistoricalObservationSelection(
        unresolved_observations=tuple(unresolved),
        inspected_count=inspected_count,
        resolved_count=resolved_count,
        learned_feedback_count=learned_feedback_count,
    )


def observations_from_learned_feedback(
    mappings: tuple[LearnedServiceTextMapping, ...] | list[LearnedServiceTextMapping],
) -> tuple[ServiceTextObservation, ...]:
    """Convert approved learned feedback mappings into clusterable observations."""
    observations: list[ServiceTextObservation] = []
    for mapping in mappings:
        surface_form = mapping.surface_form.strip()
        if not surface_form:
            continue
        observations.append(
            ServiceTextObservation(
                observation_id=f"learned:{mapping.feedback_id}",
                kind=mapping.kind,
                text=surface_form,
                source="learned_feedback",
                concept_id=mapping.concept_id,
                feedback_id=mapping.feedback_id,
                field_path=mapping.field_path,
            )
        )
    return tuple(observations)


def unresolved_service_observation(
    *,
    observation_id: str,
    kind: TextConceptKind,
    text: str,
    field_path: str | None = None,
    service_type: str | None = None,
    part_label: str | None = None,
    instance_id: str | None = None,
    service_step_id: str | None = None,
    part_id: str | None = None,
) -> ServiceTextObservation:
    """Create an unresolved/ambiguous service-text observation for reporting."""
    return ServiceTextObservation(
        observation_id=observation_id,
        kind=kind,
        text=text,
        source="unresolved_observation",
        field_path=field_path,
        service_type=service_type,
        part_label=part_label,
        instance_id=instance_id,
        service_step_id=service_step_id,
        part_id=part_id,
    )


def _matches_applied_learned_mapping(
    record: HistoricalServiceTextRecord,
    mappings: tuple[LearnedServiceTextMapping, ...] | list[LearnedServiceTextMapping],
) -> bool:
    canonical_key = _normalized_text_key(record.canonical_value or "")
    if not canonical_key:
        return False

    text_key = _normalized_text_key(record.text)
    for mapping in mappings:
        if mapping.kind != record.kind:
            continue
        if canonical_key != _normalized_text_key(mapping.concept_id):
            continue
        mapping_text_keys = {
            _normalized_text_key(mapping.original_value),
            _normalized_text_key(mapping.surface_form),
        }
        if text_key in mapping_text_keys:
            return True
    return False


def _normalized_text_key(value: str) -> str:
    cleaned = value.strip().lower().replace("_", " ").replace("-", " ")
    return " ".join(cleaned.split())


def build_candidate_concept_evidence_report(
    observations: tuple[ServiceTextObservation, ...] | list[ServiceTextObservation],
    *,
    cluster_similarity_threshold: float = 0.72,
    max_representatives: int = 5,
    max_core_anchors: int = 3,
) -> CandidateConceptEvidenceReport:
    """
    Cluster learned/unresolved observations and attach nearest current core anchors.

    The report is deliberately descriptive. It does not assign review actions
    such as "extend existing concept" or "possible new concept"; that
    interpretation layer is kept for thesis discussion or future work.
    """
    clean_observations = tuple(
        observation for observation in observations if observation.text.strip()
    )
    clusters: list[CandidateConceptCluster] = []
    for kind in ("symptom", "diagnosis"):
        kind_observations = tuple(
            observation for observation in clean_observations if observation.kind == kind
        )
        for index, members in enumerate(
            _cluster_observations(kind_observations, threshold=cluster_similarity_threshold),
            start=1,
        ):
            clusters.append(
                _build_cluster(
                    cluster_id=f"{kind}-{index:03d}",
                    kind=kind,
                    observations=members,
                    max_representatives=max_representatives,
                    max_core_anchors=max_core_anchors,
                )
            )

    clusters.sort(key=lambda cluster: (cluster.kind, -cluster.n_total, cluster.cluster_id))
    return CandidateConceptEvidenceReport(
        parameters={
            "cluster_similarity_threshold": cluster_similarity_threshold,
            "max_representatives": max_representatives,
            "max_core_anchors": max_core_anchors,
            "interpretation": "neutral_evidence_only",
            "core_registry_role": "semantic_anchor_not_cluster_member",
            "core_alias_candidates_role": "review_candidates_not_runtime_mutations",
        },
        clustering_quality=_clustering_quality(clusters),
        clusters=tuple(clusters),
        core_alias_candidates=_core_alias_candidates(clean_observations),
    )


def _build_cluster(
    *,
    cluster_id: str,
    kind: TextConceptKind,
    observations: tuple[ServiceTextObservation, ...],
    max_representatives: int,
    max_core_anchors: int,
) -> CandidateConceptCluster:
    source_counts = Counter(observation.source for observation in observations)
    learned_target_counts = Counter(
        observation.concept_id
        for observation in observations
        if observation.source == "learned_feedback" and observation.concept_id
    )
    top_learned_target: str | None = None
    top_learned_target_share: float | None = None
    if learned_target_counts:
        top_learned_target, top_count = learned_target_counts.most_common(1)[0]
        top_learned_target_share = round(top_count / sum(learned_target_counts.values()), 3)

    anchors = _nearest_core_anchors(
        kind=kind,
        cluster_text=" ".join(observation.text for observation in observations),
        max_core_anchors=max_core_anchors,
        preferred_concept_ids=set(learned_target_counts),
    )
    nearest_similarity = anchors[0].similarity if anchors else None
    nearest_core_ids = tuple(
        anchor.concept_id
        for anchor in anchors
        if nearest_similarity is not None and anchor.similarity == nearest_similarity
    )
    lower_ranked_similarities = [
        anchor.similarity
        for anchor in anchors
        if nearest_similarity is not None and anchor.similarity < nearest_similarity
    ]
    second_similarity = lower_ranked_similarities[0] if lower_ranked_similarities else None
    core_margin = (
        round(nearest_similarity - second_similarity, 3)
        if nearest_similarity is not None and second_similarity is not None
        else None
    )

    return CandidateConceptCluster(
        cluster_id=cluster_id,
        kind=kind,
        observations=observations,
        n_total=len(observations),
        n_unresolved=source_counts.get("unresolved_observation", 0),
        n_learned=source_counts.get("learned_feedback", 0),
        source_counts=dict(source_counts),
        learned_target_counts=dict(learned_target_counts),
        top_learned_target=top_learned_target,
        top_learned_target_share=top_learned_target_share,
        nearest_core_id=anchors[0].concept_id if anchors else None,
        nearest_core_ids=nearest_core_ids,
        nearest_core_similarity=nearest_similarity,
        second_core_similarity=second_similarity,
        core_margin=core_margin,
        representative_texts=_representative_texts(observations, max_representatives),
        candidate_surface_forms=_candidate_surface_forms(observations, max_representatives),
        core_anchors=anchors,
    )


def _core_alias_candidates(
    observations: tuple[ServiceTextObservation, ...],
) -> tuple[CoreAliasCandidate, ...]:
    by_concept: dict[tuple[TextConceptKind, str], list[ServiceTextObservation]] = {}
    for observation in observations:
        if observation.source != "learned_feedback" or observation.concept_id is None:
            continue
        by_concept.setdefault((observation.kind, observation.concept_id), []).append(observation)

    candidates: list[CoreAliasCandidate] = []
    for (kind, concept_id), concept_observations in by_concept.items():
        surface_forms = _candidate_surface_forms(tuple(concept_observations), max_forms=25)
        feedback_ids = tuple(
            sorted(
                {
                    observation.feedback_id
                    for observation in concept_observations
                    if observation.feedback_id is not None
                }
            )
        )
        candidates.append(
            CoreAliasCandidate(
                concept_id=concept_id,
                kind=kind,
                surface_forms=surface_forms,
                support_count=len(concept_observations),
                feedback_ids=feedback_ids,
            )
        )
    candidates.sort(key=lambda candidate: (candidate.kind, -candidate.support_count, candidate.concept_id))
    return tuple(candidates)


def _clustering_quality(clusters: list[CandidateConceptCluster]) -> dict[str, Any]:
    observations = [observation for cluster in clusters for observation in cluster.observations]
    cluster_sizes = [cluster.n_total for cluster in clusters]
    singleton_count = sum(1 for size in cluster_sizes if size == 1)
    intra_scores = [
        _mean_pairwise_similarity(cluster.observations)
        for cluster in clusters
        if cluster.n_total > 1
    ]
    nearest_other_scores = [
        _nearest_other_cluster_similarity(cluster, clusters)
        for cluster in clusters
        if len(clusters) > 1
    ]
    silhouette_scores = _approximate_silhouette_scores(clusters)
    core_margins = [
        cluster.core_margin
        for cluster in clusters
        if cluster.core_margin is not None
    ]
    nearest_core_scores = [
        cluster.nearest_core_similarity
        for cluster in clusters
        if cluster.nearest_core_similarity is not None
    ]

    return {
        "observations_total": len(observations),
        "clusters_total": len(clusters),
        "singleton_clusters_total": singleton_count,
        "singleton_cluster_share": _round_or_none(singleton_count / len(clusters) if clusters else None),
        "mean_cluster_size": _round_or_none(sum(cluster_sizes) / len(cluster_sizes) if cluster_sizes else None),
        "largest_cluster_size": max(cluster_sizes) if cluster_sizes else 0,
        "mean_intra_cluster_similarity": _mean_or_none(intra_scores),
        "min_intra_cluster_similarity": _round_or_none(min(intra_scores) if intra_scores else None),
        "mean_nearest_other_cluster_similarity": _mean_or_none(nearest_other_scores),
        "approximate_silhouette": _mean_or_none(silhouette_scores),
        "mean_nearest_core_similarity": _mean_or_none(nearest_core_scores),
        "mean_core_margin": _mean_or_none(core_margins),
        "metric_note": (
            "Internal lexical clustering diagnostics for review triage only; "
            "not a validated performance score or ground-truth evaluation."
        ),
    }


def _cluster_observations(
    observations: tuple[ServiceTextObservation, ...],
    *,
    threshold: float,
) -> tuple[tuple[ServiceTextObservation, ...], ...]:
    if not observations:
        return ()

    adjacency: dict[int, set[int]] = {index: set() for index in range(len(observations))}
    for left_index, left in enumerate(observations):
        for right_index in range(left_index + 1, len(observations)):
            right = observations[right_index]
            if _text_similarity(left.text, right.text) >= threshold:
                adjacency[left_index].add(right_index)
                adjacency[right_index].add(left_index)

    visited: set[int] = set()
    clusters: list[tuple[ServiceTextObservation, ...]] = []
    for start_index in range(len(observations)):
        if start_index in visited:
            continue
        stack = [start_index]
        component: list[int] = []
        visited.add(start_index)
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor in sorted(adjacency[current]):
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
        members = tuple(observations[index] for index in sorted(component))
        clusters.append(members)

    clusters.sort(key=lambda members: (-len(members), members[0].observation_id))
    return tuple(clusters)


def _mean_pairwise_similarity(observations: tuple[ServiceTextObservation, ...]) -> float | None:
    if len(observations) < 2:
        return None
    scores: list[float] = []
    for left_index, left in enumerate(observations):
        for right in observations[left_index + 1 :]:
            scores.append(_text_similarity(left.text, right.text))
    return _mean_or_none(scores)


def _nearest_other_cluster_similarity(
    cluster: CandidateConceptCluster,
    clusters: list[CandidateConceptCluster],
) -> float | None:
    scores: list[float] = []
    for other in clusters:
        if other.cluster_id == cluster.cluster_id:
            continue
        scores.append(_cluster_similarity(cluster.observations, other.observations))
    return _round_or_none(max(scores) if scores else None)


def _cluster_similarity(
    left: tuple[ServiceTextObservation, ...],
    right: tuple[ServiceTextObservation, ...],
) -> float:
    scores: list[float] = []
    for left_observation in left:
        for right_observation in right:
            scores.append(_text_similarity(left_observation.text, right_observation.text))
    return _mean_or_none(scores) or 0.0


def _approximate_silhouette_scores(clusters: list[CandidateConceptCluster]) -> list[float]:
    if len(clusters) < 2:
        return []

    scores: list[float] = []
    for cluster in clusters:
        for observation in cluster.observations:
            own_neighbors = [
                other
                for other in cluster.observations
                if other.observation_id != observation.observation_id
            ]
            own_distance = (
                1.0 - (_mean_or_none([
                    _text_similarity(observation.text, other.text)
                    for other in own_neighbors
                ]) or 0.0)
                if own_neighbors
                else 0.0
            )
            other_distances: list[float] = []
            for other_cluster in clusters:
                if other_cluster.cluster_id == cluster.cluster_id:
                    continue
                other_similarity = _mean_or_none([
                    _text_similarity(observation.text, other.text)
                    for other in other_cluster.observations
                ])
                if other_similarity is not None:
                    other_distances.append(1.0 - other_similarity)
            if not other_distances:
                continue
            nearest_other_distance = min(other_distances)
            denominator = max(own_distance, nearest_other_distance)
            if denominator > 0:
                scores.append(round((nearest_other_distance - own_distance) / denominator, 3))
    return scores


def _nearest_core_anchors(
    *,
    kind: TextConceptKind,
    cluster_text: str,
    max_core_anchors: int,
    preferred_concept_ids: set[str] | None = None,
) -> tuple[CoreAnchorEvidence, ...]:
    preferred_concept_ids = preferred_concept_ids or set()
    anchors: list[CoreAnchorEvidence] = []
    for concept in TEXT_CONCEPTS_BY_KIND[kind]:
        anchors.append(
            CoreAnchorEvidence(
                concept_id=concept.concept_id,
                label=concept.label,
                similarity=round(_text_similarity(cluster_text, _concept_profile_text(concept)), 3),
                inventory_status=concept.inventory_status,
            )
        )
    anchors.sort(
        key=lambda anchor: (
            -anchor.similarity,
            0 if anchor.concept_id in preferred_concept_ids else 1,
            anchor.concept_id,
        )
    )
    if len(anchors) <= max_core_anchors:
        return tuple(anchors)

    boundary_score = anchors[max_core_anchors - 1].similarity
    return tuple(anchor for anchor in anchors if anchor.similarity >= boundary_score)


def _representative_texts(
    observations: tuple[ServiceTextObservation, ...],
    max_representatives: int,
) -> tuple[str, ...]:
    scored: list[tuple[float, str]] = []
    for candidate in observations:
        if len(observations) == 1:
            average_similarity = 1.0
        else:
            total = sum(
                _text_similarity(candidate.text, other.text)
                for other in observations
                if other is not candidate
            )
            average_similarity = total / (len(observations) - 1)
        scored.append((average_similarity, candidate.text))
    scored.sort(key=lambda item: (-item[0], _normalize_text(item[1])))

    representatives: list[str] = []
    seen: set[str] = set()
    for _, text in scored:
        normalized = _normalize_text(text)
        if normalized in seen:
            continue
        seen.add(normalized)
        representatives.append(text)
        if len(representatives) >= max_representatives:
            break
    return tuple(representatives)


def _candidate_surface_forms(
    observations: tuple[ServiceTextObservation, ...],
    max_forms: int,
) -> tuple[str, ...]:
    forms: list[str] = []
    seen: set[str] = set()
    for observation in sorted(observations, key=lambda item: _normalize_text(item.text)):
        normalized = _normalize_text(observation.text)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        forms.append(observation.text.strip())
        if len(forms) >= max_forms:
            break
    return tuple(forms)


def _concept_profile_text(concept: TextConcept) -> str:
    return " ".join(
        part
        for part in (
            concept.label,
            concept.description,
            " ".join(concept.examples),
        )
        if part
    )


def _text_similarity(left: str, right: str) -> float:
    normalized_left = _normalize_text(left)
    normalized_right = _normalize_text(right)
    if not normalized_left or not normalized_right:
        return 0.0
    if normalized_left == normalized_right:
        return 1.0

    sequence_score = SequenceMatcher(None, normalized_left, normalized_right).ratio()
    left_tokens = set(normalized_left.split())
    right_tokens = set(normalized_right.split())
    token_score = (
        len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
        if left_tokens and right_tokens
        else 0.0
    )
    containment_score = (
        len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))
        if left_tokens and right_tokens
        else 0.0
    )
    return max(sequence_score, token_score, containment_score)


def _mean_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 3)


def _round_or_none(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 3)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.lower())).strip()
