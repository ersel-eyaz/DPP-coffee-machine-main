from __future__ import annotations

from typing import Any

from dpp.harmonization.mapper import map_observations
from dpp.harmonization.normalizers import build_normalized_result
from dpp.harmonization.parser import parse_jsonld_document
from dpp.harmonization.schemas import HarmonizationResult


class HarmonizationServiceError(RuntimeError):
    """Raised when harmonization input is invalid at the service boundary."""


def harmonize_jsonld_document(document: dict[str, Any]) -> HarmonizationResult:
    """
    Run the full harmonization pipeline for one JSON-LD document.

    Pipeline:
    1. Parse raw JSON-LD into property/relation observations.
    2. Map raw observations into scope-limited canonical entities/relations.
    3. Normalize mapped values into a stable intermediate result.
    """
    if not isinstance(document, dict):
        raise HarmonizationServiceError("document must be a dictionary")

    parsed = parse_jsonld_document(document)
    mapped = map_observations(parsed.properties, parsed.relations)

    return build_normalized_result(
        mapped,
        raw_property_count=len(parsed.properties),
        raw_relation_count=len(parsed.relations),
    )


def harmonize_jsonld_payload(payload: Any) -> HarmonizationResult:
    """
    Small convenience wrapper for callers that already have a Python object
    but want a clear service-level error if the payload is not a JSON object.
    """
    if not isinstance(payload, dict):
        raise HarmonizationServiceError("JSON-LD payload must be a dictionary-like object")

    return harmonize_jsonld_document(payload)
