from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dpp.harmonization.schemas import RawPropertyObservation, RawRelationObservation


JSONPrimitive = str | int | float | bool | None


@dataclass(slots=True)
class ParsedJSONLDDocument:
    """
    Lightweight parsed representation before semantic harmonization.

    This parser layer only extracts:
    - raw scalar/value-object properties
    - raw graph relations
    - minimal node context

    It does not perform mapping, normalization, or scope decisions.
    """

    properties: list[RawPropertyObservation]
    relations: list[RawRelationObservation]


class JSONLDParsingError(ValueError):
    """Raised when the input document is not a valid JSON-LD-like structure."""


def parse_jsonld_document(document: dict[str, Any]) -> ParsedJSONLDDocument:
    """
    Parse a JSON-LD document into raw property and relation observations.

    Supported patterns:
    - top-level single node object
    - top-level {"@graph": [...]} form
    - scalar properties
    - value objects like {"@value": ..., "unitCode": "..."}
    - node references like {"@id": "..."}
    - inline nested node objects
    - lists containing any mixture of the above

    This parser intentionally remains generic and permissive.
    """
    if not isinstance(document, dict):
        raise JSONLDParsingError("JSON-LD document must be a dictionary.")

    properties: list[RawPropertyObservation] = []
    relations: list[RawRelationObservation] = []

    if "@graph" in document:
        graph = document["@graph"]
        if not isinstance(graph, list):
            raise JSONLDParsingError("'@graph' must be a list.")
        for index, node in enumerate(graph):
            _parse_node(
                node=node,
                node_path=f"@graph[{index}]",
                properties=properties,
                relations=relations,
            )
    else:
        _parse_node(
            node=document,
            node_path="$",
            properties=properties,
            relations=relations,
        )

    return ParsedJSONLDDocument(properties=properties, relations=relations)


def _parse_node(
    node: Any,
    node_path: str,
    properties: list[RawPropertyObservation],
    relations: list[RawRelationObservation],
) -> None:
    """
    Parse one node object and append extracted observations.

    Non-dict values are ignored at node level.
    """
    if not isinstance(node, dict):
        return

    source_entity_id = _extract_node_id(node)
    source_entity_type = _extract_primary_node_type(node)
    source_node_types = _extract_all_node_types(node)
    neighbor_labels = _collect_neighbor_labels(node)

    for key, value in node.items():
        if key in {"@context", "@id", "@type"}:
            continue

        raw_label = _strip_prefix(key)
        filtered_neighbors = [label for label in neighbor_labels if label != raw_label]
        current_path = f"{node_path}.{raw_label}"

        _parse_property_value(
            value=value,
            raw_label=raw_label,
            source_path=current_path,
            source_entity_id=source_entity_id,
            source_entity_type=source_entity_type,
            source_node_types=source_node_types,
            neighbor_labels=filtered_neighbors,
            properties=properties,
            relations=relations,
        )


def _parse_property_value(
    value: Any,
    raw_label: str,
    source_path: str,
    source_entity_id: str | None,
    source_entity_type: str | None,
    source_node_types: list[str],
    neighbor_labels: list[str],
    properties: list[RawPropertyObservation],
    relations: list[RawRelationObservation],
) -> None:
    """
    Parse a property value recursively.

    Cases:
    - primitive scalar -> raw property
    - value object -> raw property
    - node reference object -> raw relation
    - inline node object -> raw relation + recursive node parse
    - list -> recurse item-wise
    """
    if _is_json_primitive(value):
        properties.append(
            RawPropertyObservation(
                source_path=source_path,
                source_entity_id=source_entity_id,
                source_entity_type=source_entity_type,
                raw_label=raw_label,
                raw_value=value,
                raw_unit=None,
                source_node_types=source_node_types,
                neighbor_labels=neighbor_labels,
            )
        )
        return

    if isinstance(value, list):
        for index, item in enumerate(value):
            _parse_property_value(
                value=item,
                raw_label=raw_label,
                source_path=f"{source_path}[{index}]",
                source_entity_id=source_entity_id,
                source_entity_type=source_entity_type,
                source_node_types=source_node_types,
                neighbor_labels=neighbor_labels,
                properties=properties,
                relations=relations,
            )
        return

    if not isinstance(value, dict):
        return

    if _is_value_object(value):
        properties.append(
            RawPropertyObservation(
                source_path=source_path,
                source_entity_id=source_entity_id,
                source_entity_type=source_entity_type,
                raw_label=raw_label,
                raw_value=_extract_value_object_value(value),
                raw_unit=_extract_value_object_unit(value),
                source_node_types=source_node_types,
                neighbor_labels=neighbor_labels,
            )
        )
        return

    referenced_object_id = _extract_node_id(value)
    referenced_object_type = _extract_primary_node_type(value)

    if _looks_like_reference_object(value):
        if source_entity_id and referenced_object_id:
            relations.append(
                RawRelationObservation(
                    source_path=source_path,
                    subject_id=source_entity_id,
                    subject_type=source_entity_type,
                    predicate_label=raw_label,
                    object_id=referenced_object_id,
                    object_type=referenced_object_type,
                    object_inline=False,
                )
            )
        return

    if _looks_like_inline_node_object(value):
        if source_entity_id and referenced_object_id:
            relations.append(
                RawRelationObservation(
                    source_path=source_path,
                    subject_id=source_entity_id,
                    subject_type=source_entity_type,
                    predicate_label=raw_label,
                    object_id=referenced_object_id,
                    object_type=referenced_object_type,
                    object_inline=True,
                )
            )

        _parse_node(
            node=value,
            node_path=source_path,
            properties=properties,
            relations=relations,
        )
        return

    # Fallback:
    # If it is a generic dict that is neither a value object nor a clear node,
    # try extracting scalar subfields as separate observations.
    for nested_key, nested_value in value.items():
        if nested_key in {"@context", "@id", "@type"}:
            continue
        nested_label = f"{raw_label}.{_strip_prefix(nested_key)}"
        _parse_property_value(
            value=nested_value,
            raw_label=nested_label,
            source_path=f"{source_path}.{_strip_prefix(nested_key)}",
            source_entity_id=source_entity_id,
            source_entity_type=source_entity_type,
            source_node_types=source_node_types,
            neighbor_labels=neighbor_labels,
            properties=properties,
            relations=relations,
        )


def _extract_node_id(node: dict[str, Any]) -> str | None:
    value = node.get("@id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _extract_primary_node_type(node: dict[str, Any]) -> str | None:
    raw_type = node.get("@type")
    if isinstance(raw_type, str):
        stripped = _strip_prefix(raw_type)
        return stripped.strip() if stripped.strip() else None

    if isinstance(raw_type, list):
        for item in raw_type:
            if isinstance(item, str):
                stripped = _strip_prefix(item)
                if stripped.strip():
                    return stripped.strip()

    return None


def _extract_all_node_types(node: dict[str, Any]) -> list[str]:
    raw_type = node.get("@type")
    collected: list[str] = []

    if isinstance(raw_type, str):
        stripped = _strip_prefix(raw_type).strip()
        if stripped:
            collected.append(stripped)
        return collected

    if isinstance(raw_type, list):
        for item in raw_type:
            if isinstance(item, str):
                stripped = _strip_prefix(item).strip()
                if stripped:
                    collected.append(stripped)

    return collected


def _collect_neighbor_labels(node: dict[str, Any]) -> list[str]:
    labels: list[str] = []

    for key in node.keys():
        if key in {"@context", "@id", "@type"}:
            continue
        labels.append(_strip_prefix(key))

    return labels


def _is_json_primitive(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool)) or value is None


def _is_value_object(value: dict[str, Any]) -> bool:
    """
    Recognize JSON-LD-like literal/value objects.
    """
    return "@value" in value or "value" in value


def _extract_value_object_value(value: dict[str, Any]) -> Any:
    if "@value" in value:
        return value["@value"]
    return value.get("value")


def _extract_value_object_unit(value: dict[str, Any]) -> str | None:
    for key in ("unitCode", "unit", "rawUnit"):
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def _looks_like_reference_object(value: dict[str, Any]) -> bool:
    """
    A reference object is something like:
    {"@id": "..."} or {"@id": "...", "@type": "..."}
    and nothing structurally richer.
    """
    if "@id" not in value:
        return False

    allowed_keys = {"@id", "@type"}
    return set(value.keys()).issubset(allowed_keys)


def _looks_like_inline_node_object(value: dict[str, Any]) -> bool:
    """
    An inline node object is a nested node carrying either:
    - @id with additional properties, or
    - @type with properties, even without @id
    """
    if _is_value_object(value):
        return False

    if "@id" in value and len(set(value.keys()) - {"@id", "@type"}) > 0:
        return True

    if "@type" in value:
        return True

    return False


def _strip_prefix(value: str) -> str:
    """
    Strip a compact IRI prefix such as 'dpp:foo' -> 'foo'.
    """
    if ":" in value:
        return value.split(":", 1)[1]
    return value