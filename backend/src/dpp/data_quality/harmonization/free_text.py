"""
Free-text harmonization helpers for service and secondary-value data.

The normalizer maps open service texts such as observed symptoms and diagnoses
onto a small OpenRepairData-derived canonical concept registry. This keeps the original free
text available in the input while adding stable concept identifiers for later
aggregation, reporting, and prototype analytics.

The matching strategy is intentionally conservative:
1. canonical id / label / example exact match
2. clear lexical fuzzy fallback for close spelling variants
3. review-only learned-feedback exact, fuzzy, and semantic candidates
4. optional semantic embedding fallback for core-registry paraphrases
5. ambiguous or unresolved result

The semantic fallback is lazy and optional. The module can still be imported and
lexical matching can still run without sentence-transformers installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
from math import sqrt
from typing import Any, Literal


from dpp.data_quality.harmonization.feedback import (
    LearnedServiceTextMapping,
    load_learned_service_text_mappings,
)
from dpp.data_quality.harmonization.service_concepts import (
    DIAGNOSIS_CONCEPTS,
    SYMPTOM_CONCEPTS,
    TEXT_CONCEPTS_BY_KIND,
    TextConcept,
    TextConceptKind,
)


TextMatchStatus = Literal["normalized", "ambiguous", "unresolved", "error"]

AUTO_TEXT_FUZZY_THRESHOLD = 0.92
AMBIGUOUS_TEXT_FUZZY_THRESHOLD = 0.78
AUTO_TEXT_SEMANTIC_THRESHOLD = 0.58
AMBIGUOUS_TEXT_SEMANTIC_THRESHOLD = 0.42
MIN_TEXT_SEMANTIC_MARGIN = 0.05
DEFAULT_TEXT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class TextNormalizationError(ValueError):
    """Raised when free-text normalization cannot be performed safely."""


@dataclass(frozen=True)
class TextNormalizationCandidate:
    """
    Candidate mapping from one text fragment to a canonical concept.
    """

    original_text: str
    concept_id: str
    label: str
    confidence: float
    match_type: str
    source: str = "core_registry"
    feedback_id: str | None = None


@dataclass(frozen=True)
class TextNormalizationResult:
    """
    Result for one free-text fragment.
    """

    original_text: str
    normalized_concept: str | None
    normalized_label: str | None
    confidence: float | None
    method: str | None
    status: TextMatchStatus
    candidates: tuple[TextNormalizationCandidate, ...] = ()
    closest_candidates: tuple[TextNormalizationCandidate, ...] = ()

    def as_clean_value(self) -> str | None:
        """Return the compact concept id for clean JSON-LD output."""
        return self.normalized_concept

    def as_report_value(self) -> dict[str, Any]:
        """Return a trace-friendly dictionary representation."""
        payload: dict[str, Any] = {
            "original_text": self.original_text,
            "status": self.status,
        }
        if self.normalized_concept is not None:
            payload["normalized_concept"] = self.normalized_concept
        if self.normalized_label is not None:
            payload["normalized_label"] = self.normalized_label
        if self.confidence is not None:
            payload["confidence"] = self.confidence
        if self.method is not None:
            payload["method"] = self.method
        if self.candidates:
            payload["candidates"] = [
                {
                    "concept_id": candidate.concept_id,
                    "label": candidate.label,
                    "confidence": candidate.confidence,
                    "match_type": candidate.match_type,
                    "source": candidate.source,
                    **({"feedback_id": candidate.feedback_id} if candidate.feedback_id else {}),
                }
                for candidate in self.candidates
            ]
        if self.closest_candidates:
            payload["closest_candidates"] = [
                {
                    "concept_id": candidate.concept_id,
                    "label": candidate.label,
                    "confidence": candidate.confidence,
                    "match_type": candidate.match_type,
                    "source": candidate.source,
                    **({"feedback_id": candidate.feedback_id} if candidate.feedback_id else {}),
                }
                for candidate in self.closest_candidates
            ]
        return payload


_CONCEPTS_BY_KIND = TEXT_CONCEPTS_BY_KIND


def _normalize_text_key(value: str) -> str:
    """Normalize a text fragment for exact and fuzzy lookup."""
    cleaned = value.strip().lower().replace("_", " ").replace("-", " ")
    return " ".join(cleaned.split())


def _similarity(left: str, right: str) -> float:
    """Return a normalized sequence similarity score."""
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _concept_lookup_phrases(concept: TextConcept) -> tuple[str, ...]:
    """Return all exact/fuzzy lookup phrases for a concept."""
    return (concept.concept_id, concept.label, *concept.examples)


def find_text_value_candidates(
    kind: TextConceptKind,
    text: Any,
    min_confidence: float = AMBIGUOUS_TEXT_FUZZY_THRESHOLD,
) -> list[TextNormalizationCandidate]:
    """Find exact or fuzzy candidates for one free-text fragment."""
    if not isinstance(text, str):
        return []

    key = _normalize_text_key(text)
    if not key:
        return []

    candidates_by_concept: dict[str, TextNormalizationCandidate] = {}

    for concept in _CONCEPTS_BY_KIND[kind]:
        for phrase in _concept_lookup_phrases(concept):
            phrase_key = _normalize_text_key(phrase)
            if key == phrase_key:
                return [
                    TextNormalizationCandidate(
                        original_text=text,
                        concept_id=concept.concept_id,
                        label=concept.label,
                        confidence=1.0,
                        match_type="canonical" if phrase == concept.concept_id else "alias",
                    )
                ]

            score = _similarity(key, phrase_key)
            if score < min_confidence:
                continue

            current = candidates_by_concept.get(concept.concept_id)
            if current is None or score > current.confidence:
                candidates_by_concept[concept.concept_id] = TextNormalizationCandidate(
                    original_text=text,
                    concept_id=concept.concept_id,
                    label=concept.label,
                    confidence=score,
                    match_type="fuzzy",
                )

    return sorted(candidates_by_concept.values(), key=lambda item: item.confidence, reverse=True)


def find_learned_text_value_candidates(
    kind: TextConceptKind,
    text: Any,
    min_confidence: float = AMBIGUOUS_TEXT_FUZZY_THRESHOLD,
) -> list[TextNormalizationCandidate]:
    """Find review-only candidates from approved learned feedback evidence."""
    if not isinstance(text, str):
        return []

    key = _normalize_text_key(text)
    if not key:
        return []

    candidates_by_feedback: dict[str, TextNormalizationCandidate] = {}
    concepts_by_id = {item.concept_id: item for item in TEXT_CONCEPTS_BY_KIND[kind]}

    for mapping in load_learned_service_text_mappings():
        if mapping.kind != kind:
            continue

        target_concept = concepts_by_id.get(mapping.concept_id)
        if target_concept is None:
            continue

        phrase_key = _normalize_text_key(mapping.surface_form)
        if not phrase_key:
            continue

        if key == phrase_key:
            return [
                TextNormalizationCandidate(
                    original_text=text,
                    concept_id=mapping.concept_id,
                    label=target_concept.label,
                    confidence=1.0,
                    match_type="learned_feedback_exact",
                    source="learned_feedback",
                    feedback_id=mapping.feedback_id,
                )
            ]

        score = _similarity(key, phrase_key)
        if score < min_confidence:
            continue

        candidate = TextNormalizationCandidate(
            original_text=text,
            concept_id=mapping.concept_id,
            label=target_concept.label,
            confidence=score,
            match_type="learned_feedback_fuzzy",
            source="learned_feedback",
            feedback_id=mapping.feedback_id,
        )
        current = candidates_by_feedback.get(mapping.feedback_id)
        if current is None or score > current.confidence:
            candidates_by_feedback[mapping.feedback_id] = candidate

    return sorted(candidates_by_feedback.values(), key=lambda item: item.confidence, reverse=True)


@lru_cache(maxsize=1)
def _embedding_model() -> Any:
    """Load the optional sentence-transformers model lazily."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise TextNormalizationError(
            "Semantic free-text matching requires the optional 'sentence-transformers' package. "
            "Install it or use exact/alias/fuzzy-resolvable service texts."
        ) from exc

    try:
        return SentenceTransformer(DEFAULT_TEXT_EMBEDDING_MODEL)
    except Exception as exc:
        raise TextNormalizationError(
            f"Could not load the sentence-transformers model {DEFAULT_TEXT_EMBEDDING_MODEL!r}."
        ) from exc


def _as_vector(embedding: Any) -> list[float]:
    """Convert model output to a plain Python vector."""
    if hasattr(embedding, "tolist"):
        values = embedding.tolist()
    else:
        values = embedding
    return [float(item) for item in values]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    """Return cosine similarity for two vectors."""
    dot_product = sum(a * b for a, b in zip(left, right))
    left_norm = sqrt(sum(a * a for a in left))
    right_norm = sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot_product / (left_norm * right_norm)


def _learned_mapping_embedding_text(mapping: LearnedServiceTextMapping) -> str:
    """Return the text profile used for review-only learned-feedback semantic matching."""
    parts = [mapping.surface_form]
    if mapping.original_value != mapping.surface_form:
        parts.append(mapping.original_value)
    if mapping.rationale:
        parts.append(mapping.rationale)
    return ". ".join(part for part in parts if part)


@lru_cache(maxsize=8)
def _semantic_concept_embeddings(kind: TextConceptKind) -> tuple[tuple[str, str, str, tuple[float, ...]], ...]:
    """Return cached embeddings for all concepts of one kind."""
    concepts = _CONCEPTS_BY_KIND[kind]
    model = _embedding_model()
    texts = [f"{concept.label}. {concept.description}. Examples: {'; '.join(concept.examples)}" for concept in concepts]
    embeddings = model.encode(texts, normalize_embeddings=True)

    result: list[tuple[str, str, str, tuple[float, ...]]] = []
    for concept, embedding in zip(concepts, embeddings):
        result.append((concept.concept_id, concept.label, concept.description, tuple(_as_vector(embedding))))
    return tuple(result)


def find_text_semantic_candidates(
    kind: TextConceptKind,
    text: Any,
    min_confidence: float = AMBIGUOUS_TEXT_SEMANTIC_THRESHOLD,
) -> list[TextNormalizationCandidate]:
    """Find semantic candidates for one unresolved free-text fragment."""
    if not isinstance(text, str):
        return []

    query = " ".join(text.strip().split())
    if not query:
        return []

    concept_embeddings = _semantic_concept_embeddings(kind)
    model = _embedding_model()
    query_vector = _as_vector(model.encode(query, normalize_embeddings=True))

    candidates: list[TextNormalizationCandidate] = []
    for concept_id, label, _description, concept_vector_tuple in concept_embeddings:
        score = _cosine_similarity(query_vector, list(concept_vector_tuple))
        if score < min_confidence:
            continue
        candidates.append(
            TextNormalizationCandidate(
                original_text=text,
                concept_id=concept_id,
                label=label,
                confidence=score,
                match_type="semantic",
            )
        )

    return sorted(candidates, key=lambda item: item.confidence, reverse=True)


def find_learned_text_semantic_candidates(
    kind: TextConceptKind,
    text: Any,
    min_confidence: float = AMBIGUOUS_TEXT_SEMANTIC_THRESHOLD,
) -> list[TextNormalizationCandidate]:
    """Find review-only semantic candidates from approved learned feedback evidence."""
    if not isinstance(text, str):
        return []

    query = " ".join(text.strip().split())
    if not query:
        return []

    mappings = [mapping for mapping in load_learned_service_text_mappings() if mapping.kind == kind]
    if not mappings:
        return []

    concepts_by_id = {item.concept_id: item for item in TEXT_CONCEPTS_BY_KIND[kind]}
    model = _embedding_model()
    query_vector = _as_vector(model.encode(query, normalize_embeddings=True))
    mapping_texts = [_learned_mapping_embedding_text(mapping) for mapping in mappings]
    mapping_embeddings = model.encode(mapping_texts, normalize_embeddings=True)

    candidates: list[TextNormalizationCandidate] = []
    for mapping, embedding in zip(mappings, mapping_embeddings):
        target_concept = concepts_by_id.get(mapping.concept_id)
        if target_concept is None:
            continue

        score = _cosine_similarity(query_vector, _as_vector(embedding))
        if score < min_confidence:
            continue

        candidates.append(
            TextNormalizationCandidate(
                original_text=text,
                concept_id=mapping.concept_id,
                label=target_concept.label,
                confidence=score,
                match_type="learned_feedback_semantic",
                source="learned_feedback",
                feedback_id=mapping.feedback_id,
            )
        )

    return sorted(candidates, key=lambda item: item.confidence, reverse=True)


def resolve_text_value(
    kind: TextConceptKind,
    text: Any,
    *,
    enable_semantic: bool = True,
) -> TextNormalizationCandidate | None:
    """Resolve one free-text fragment to a canonical concept if safe."""
    candidates = find_text_value_candidates(kind, text)
    if candidates:
        top = candidates[0]
        if top.match_type in {"canonical", "alias"}:
            return top

        second_score = candidates[1].confidence if len(candidates) > 1 else 0.0
        if top.confidence >= AUTO_TEXT_FUZZY_THRESHOLD and (top.confidence - second_score) >= 0.05:
            return top

    if not enable_semantic:
        return None

    semantic_candidates = find_text_semantic_candidates(kind, text)
    if not semantic_candidates:
        return None

    top_semantic = semantic_candidates[0]
    second_semantic_score = semantic_candidates[1].confidence if len(semantic_candidates) > 1 else 0.0
    if (
        top_semantic.confidence >= AUTO_TEXT_SEMANTIC_THRESHOLD
        and (top_semantic.confidence - second_semantic_score) >= MIN_TEXT_SEMANTIC_MARGIN
    ):
        return top_semantic

    return None


def _closest_diagnostic_candidates(
    kind: TextConceptKind,
    text: str,
    *,
    enable_semantic: bool,
) -> tuple[TextNormalizationCandidate, ...]:
    """Return top below-threshold fuzzy/semantic candidates for traceability only."""
    closest: list[TextNormalizationCandidate] = []
    fuzzy_candidates = find_text_value_candidates(kind, text, min_confidence=0.0)
    if fuzzy_candidates:
        closest.append(fuzzy_candidates[0])

    learned_candidates = find_learned_text_value_candidates(kind, text, min_confidence=0.0)
    if learned_candidates:
        closest.append(learned_candidates[0])
    elif enable_semantic:
        try:
            learned_semantic_candidates = find_learned_text_semantic_candidates(kind, text, min_confidence=0.0)
        except TextNormalizationError:
            learned_semantic_candidates = []
        if learned_semantic_candidates:
            closest.append(learned_semantic_candidates[0])

    if enable_semantic:
        try:
            semantic_candidates = find_text_semantic_candidates(kind, text, min_confidence=0.0)
        except TextNormalizationError:
            semantic_candidates = []
        if semantic_candidates:
            closest.append(semantic_candidates[0])

    deduplicated: list[TextNormalizationCandidate] = []
    seen: set[tuple[str, str]] = set()
    for candidate in closest:
        key = (candidate.match_type, candidate.concept_id)
        if key in seen:
            continue
        deduplicated.append(candidate)
        seen.add(key)

    return tuple(deduplicated)


def normalize_text_value(kind: TextConceptKind, text: Any, *, enable_semantic: bool = True) -> TextNormalizationResult:
    """Normalize one free-text value into a canonical concept result."""
    if not isinstance(text, str):
        return TextNormalizationResult(
            original_text=repr(text),
            normalized_concept=None,
            normalized_label=None,
            confidence=None,
            method=None,
            status="error",
        )

    stripped = " ".join(text.strip().split())
    if not stripped:
        return TextNormalizationResult(
            original_text=text,
            normalized_concept=None,
            normalized_label=None,
            confidence=None,
            method=None,
            status="unresolved",
        )

    candidate = resolve_text_value(kind, stripped, enable_semantic=False)

    if candidate is not None:
        return TextNormalizationResult(
            original_text=stripped,
            normalized_concept=candidate.concept_id,
            normalized_label=candidate.label,
            confidence=candidate.confidence,
            method=candidate.match_type,
            status="normalized",
        )

    candidates = find_text_value_candidates(kind, stripped)
    learned_candidates = find_learned_text_value_candidates(kind, stripped)
    if enable_semantic and not learned_candidates:
        try:
            learned_semantic_candidates = find_learned_text_semantic_candidates(kind, stripped)
        except TextNormalizationError:
            learned_semantic_candidates = []
        if learned_semantic_candidates:
            learned_candidates = sorted(
                [*learned_candidates, *learned_semantic_candidates[:3]],
                key=lambda item: item.confidence,
                reverse=True,
            )
    if learned_candidates:
        candidates = sorted(
            [*candidates, *learned_candidates[:3]],
            key=lambda item: item.confidence,
            reverse=True,
        )
    if not candidates and enable_semantic:
        try:
            candidate = resolve_text_value(kind, stripped, enable_semantic=True)
        except TextNormalizationError:
            candidate = None
        if candidate is not None:
            return TextNormalizationResult(
                original_text=stripped,
                normalized_concept=candidate.concept_id,
                normalized_label=candidate.label,
                confidence=candidate.confidence,
                method=candidate.match_type,
                status="normalized",
            )
        try:
            candidates = find_text_semantic_candidates(kind, stripped)
        except TextNormalizationError:
            candidates = []

    closest_candidates = _closest_diagnostic_candidates(kind, stripped, enable_semantic=enable_semantic)

    if candidates:
        return TextNormalizationResult(
            original_text=stripped,
            normalized_concept=None,
            normalized_label=None,
            confidence=None,
            method=None,
            status="ambiguous",
            candidates=tuple(candidates[:3]),
            closest_candidates=closest_candidates,
        )

    return TextNormalizationResult(
        original_text=stripped,
        normalized_concept=None,
        normalized_label=None,
        confidence=None,
        method=None,
        status="unresolved",
        closest_candidates=closest_candidates,
    )


def normalize_text_values(kind: TextConceptKind, value: Any, *, enable_semantic: bool = True) -> list[TextNormalizationResult]:
    """Normalize a string or list of strings into concept results."""
    if isinstance(value, list):
        return [normalize_text_value(kind, item, enable_semantic=enable_semantic) for item in value]

    return [normalize_text_value(kind, value, enable_semantic=enable_semantic)]


def clean_text_normalization_value(results: list[TextNormalizationResult], *, as_list: bool) -> Any:
    """Return clean output for one service text field.

    If a text fragment is normalized safely, the canonical concept id is emitted.
    If it remains unresolved or ambiguous, the original text is preserved instead
    of returning null. This is intentional for open free text: an unresolved text
    value is still useful information and should not be lost from the clean data.

    For list-valued fields such as observedSymptoms, duplicate clean values are
    removed while preserving order. The report still keeps one trace entry per
    original input phrase, so auditability is not lost.
    """
    values = [
        result.normalized_concept if result.normalized_concept is not None else result.original_text
        for result in results
    ]
    if as_list:
        seen: set[str] = set()
        deduplicated: list[str] = []
        for value in values:
            if value in seen:
                continue
            deduplicated.append(value)
            seen.add(value)
        return deduplicated
    return values[0] if values else None


def report_text_normalization_value(results: list[TextNormalizationResult], *, as_list: bool) -> Any:
    """Return trace-friendly report output for one normalized text field."""
    report_values = [result.as_report_value() for result in results]
    if as_list:
        return report_values
    return report_values[0] if report_values else None
