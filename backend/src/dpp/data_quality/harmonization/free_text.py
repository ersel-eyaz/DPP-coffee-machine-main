"""
Free-text harmonization helpers for service and secondary-value data.

The normalizer maps open service texts such as observed symptoms and diagnoses
onto a small seeded canonical concept registry. This keeps the original free
text available in the input while adding stable concept identifiers for later
aggregation, reporting, and prototype analytics.

The matching strategy is intentionally conservative:
1. canonical id / label / example exact match
2. clear lexical fuzzy fallback for close spelling variants
3. optional semantic embedding fallback for paraphrases
4. ambiguous or unresolved result

The semantic fallback is lazy and optional. The module can still be imported and
lexical matching can still run without sentence-transformers installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
from math import sqrt
from typing import Any, Literal


TextConceptKind = Literal["symptom", "diagnosis"]
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
class TextConcept:
    """
    Canonical free-text concept used for service-text harmonization.

    Attributes:
        concept_id: Stable machine-readable identifier.
        label: Human-readable canonical label.
        kind: Concept registry kind, e.g. symptom or diagnosis.
        description: Short semantic description used for embedding matching.
        examples: Seed phrases from the prototype data and dirty variants.
        applicable_service_types: Optional service-step types where the concept is especially plausible.
        related_part_keywords: Optional part-name keywords that can later be used for context-aware scoring.
    """

    concept_id: str
    label: str
    kind: TextConceptKind
    description: str
    examples: tuple[str, ...] = ()
    applicable_service_types: tuple[str, ...] = ()
    related_part_keywords: tuple[str, ...] = ()


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
                }
                for candidate in self.candidates
            ]
        return payload


SYMPTOM_CONCEPTS: tuple[TextConcept, ...] = (
    TextConcept(
        concept_id="water_leakage",
        label="Water leakage or dripping",
        kind="symptom",
        description="water leaks, dripping after brewing, intermittent dripping, visible leakage around hoses or valves",
        examples=(
            "Water leakage",
            "Dripping after brew",
            "Intermittent dripping",
            "water leaking",
            "leaking after brew",
        ),
        applicable_service_types=("RepairServiceStep", "ReplaceServiceStep", "RefurbishmentServiceStep"),
        related_part_keywords=("water_system", "hose", "hoses", "seal", "valve", "solenoid"),
    ),
    TextConcept(
        concept_id="low_brew_pressure",
        label="Low or unstable brew pressure",
        kind="symptom",
        description="low brew pressure, pressure fluctuations, irregular pressure ramp, flow oscillation during brewing",
        examples=(
            "Low brew pressure",
            "Pressure fluctuations",
            "Irregular pressure ramp",
            "Flow oscillation",
        ),
        applicable_service_types=("RepairServiceStep", "ReplaceServiceStep", "CleaningServiceStep"),
        related_part_keywords=("water_system", "pump", "flowmeter", "thermoblock", "solenoid"),
    ),
    TextConcept(
        concept_id="inconsistent_grind_or_extraction",
        label="Inconsistent grind or extraction",
        kind="symptom",
        description="watery espresso, channeling, inconsistent grind, uneven puck surface, longer or unstable extraction",
        examples=(
            "Watery espresso",
            "Channeling",
            "Inconsistent grind",
            "Increased extraction time variance",
            "Uneven puck surface",
            "Longer extraction",
        ),
        applicable_service_types=("RepairServiceStep", "ReplaceServiceStep", "CleaningServiceStep"),
        related_part_keywords=("grinder", "burr", "burrs", "brew_group"),
    ),
    TextConcept(
        concept_id="brew_group_friction",
        label="Brew group friction or sticky motion",
        kind="symptom",
        description="brew group moves slowly, sticky motion, creaking noise, slower cycle or mechanical friction",
        examples=(
            "Creaking noise",
            "Creak noise",
            "Slower cycle",
            "Sticky motion",
        ),
        applicable_service_types=("CleaningServiceStep", "RepairServiceStep", "RefurbishmentServiceStep"),
        related_part_keywords=("brew_group", "brew", "piston", "chamber"),
    ),
    TextConcept(
        concept_id="limescale_flow_restriction",
        label="Limescale or water-flow restriction",
        kind="symptom",
        description="reduced flow rate, steam sputtering, noisy pump priming, water circuit restriction caused by limescale",
        examples=(
            "Reduced flow rate",
            "Steam sputtering",
            "Noisy pump priming",
            "Flow oscillation",
        ),
        applicable_service_types=("CleaningServiceStep", "RepairServiceStep"),
        related_part_keywords=("water_system", "pump", "thermoblock", "flowmeter", "hoses"),
    ),
    TextConcept(
        concept_id="grinder_motor_issue",
        label="Grinder motor or start-up issue",
        kind="symptom",
        description="intermittent grinding noise, grinder stalls on start, abnormal grinding noise at start",
        examples=(
            "Intermittent grinding noise",
            "Stall on start",
            "Grinding noise at start",
        ),
        applicable_service_types=("RepairServiceStep", "ReplaceServiceStep"),
        related_part_keywords=("grinder", "motor", "gearbox"),
    ),
    TextConcept(
        concept_id="ui_input_failure",
        label="User-interface input failure",
        kind="symptom",
        description="buttons do not respond, stuck button matrix, user interface input not accepted",
        examples=(
            "Buttons unresponsive",
            "buttons do not respond",
            "button is stuck",
        ),
        applicable_service_types=("RepairServiceStep", "ReplaceServiceStep", "RefurbishmentServiceStep"),
        related_part_keywords=("ui", "pcb", "electronics", "button", "display"),
    ),
)


DIAGNOSIS_CONCEPTS: tuple[TextConcept, ...] = (
    TextConcept(
        concept_id="seal_wear_or_leak_path",
        label="Seal wear or leak path",
        kind="diagnosis",
        description="worn seal, worn valve seal, loose hose clamp, damaged gasket or leak path in water circuit",
        examples=(
            "Seal wear in 3-way valve",
            "Loose clamp on silicone hose",
            "worn seal",
            "valve seal wear",
        ),
        applicable_service_types=("RepairServiceStep", "ReplaceServiceStep", "RefurbishmentServiceStep"),
        related_part_keywords=("seal", "valve", "solenoid", "hose", "hoses", "water_system"),
    ),
    TextConcept(
        concept_id="dull_burrs",
        label="Dull grinder burrs",
        kind="diagnosis",
        description="grinder burrs are worn or dull and cause inconsistent particle size or extraction quality",
        examples=(
            "Dull burrs",
            "Dull burrs causing inconsistent grind size",
            "worn grinder burrs",
        ),
        applicable_service_types=("ReplaceServiceStep", "RepairServiceStep", "RefurbishmentServiceStep"),
        related_part_keywords=("grinder", "burr", "burrs"),
    ),
    TextConcept(
        concept_id="residue_buildup",
        label="Residue buildup",
        kind="diagnosis",
        description="coffee residue, oil or dirt buildup in brew group causing friction or sticky movement",
        examples=(
            "Residue buildup",
            "Brew group friction",
            "coffee residue buildup",
        ),
        applicable_service_types=("CleaningServiceStep", "RefurbishmentServiceStep"),
        related_part_keywords=("brew_group", "brew", "piston", "chamber"),
    ),
    TextConcept(
        concept_id="limescale_buildup",
        label="Limescale buildup",
        kind="diagnosis",
        description="lime scale or mineral accumulation in water system, thermoblock, pump or flow path",
        examples=(
            "Lime scale buildup",
            "Limescale accumulation",
            "scale buildup",
        ),
        applicable_service_types=("CleaningServiceStep", "RepairServiceStep", "RefurbishmentServiceStep"),
        related_part_keywords=("water_system", "thermoblock", "pump", "flowmeter", "hoses"),
    ),
    TextConcept(
        concept_id="motor_brush_wear",
        label="Motor brush wear",
        kind="diagnosis",
        description="grinder motor brush wear or motor wear causing intermittent start or grinding noise",
        examples=(
            "Motor brush wear",
            "worn motor brushes",
        ),
        applicable_service_types=("RepairServiceStep", "ReplaceServiceStep"),
        related_part_keywords=("grinder", "motor"),
    ),
    TextConcept(
        concept_id="check_valve_fatigue",
        label="Check valve fatigue",
        kind="diagnosis",
        description="check valve fatigue or pump valve problem causing unstable pressure ramp",
        examples=(
            "Check valve fatigue",
            "pump check valve fatigue",
        ),
        applicable_service_types=("RepairServiceStep", "ReplaceServiceStep"),
        related_part_keywords=("pump", "valve", "water_system"),
    ),
    TextConcept(
        concept_id="ui_board_fault",
        label="UI board or button-matrix fault",
        kind="diagnosis",
        description="stuck button matrix, defective user interface board or input electronics fault",
        examples=(
            "Stuck button matrix on UI board",
            "UI board fault",
            "button matrix fault",
        ),
        applicable_service_types=("RepairServiceStep", "ReplaceServiceStep", "RefurbishmentServiceStep"),
        related_part_keywords=("ui", "pcb", "electronics", "button", "display"),
    ),
    TextConcept(
        concept_id="pump_inspection_or_ui_refresh",
        label="Pump inspection and UI refresh",
        kind="diagnosis",
        description="refurbishment action combining user interface refresh and pump inspection",
        examples=(
            "UI refresh and pump inspection",
            "pump inspection and UI refresh",
        ),
        applicable_service_types=("RefurbishmentServiceStep", "RemanufacturingServiceStep"),
        related_part_keywords=("pump", "ui", "electronics"),
    ),
)


_CONCEPTS_BY_KIND: dict[TextConceptKind, tuple[TextConcept, ...]] = {
    "symptom": SYMPTOM_CONCEPTS,
    "diagnosis": DIAGNOSIS_CONCEPTS,
}


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

    try:
        candidate = resolve_text_value(kind, stripped, enable_semantic=enable_semantic)
    except TextNormalizationError:
        # Keep the workflow robust if optional ML dependencies are unavailable.
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
    if not candidates and enable_semantic:
        try:
            candidates = find_text_semantic_candidates(kind, stripped)
        except TextNormalizationError:
            candidates = []

    if candidates:
        return TextNormalizationResult(
            original_text=stripped,
            normalized_concept=None,
            normalized_label=None,
            confidence=None,
            method=None,
            status="ambiguous",
            candidates=tuple(candidates[:3]),
        )

    return TextNormalizationResult(
        original_text=stripped,
        normalized_concept=None,
        normalized_label=None,
        confidence=None,
        method=None,
        status="unresolved",
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
