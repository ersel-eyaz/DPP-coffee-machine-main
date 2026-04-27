"""
Minimal JSON-LD-like parser for the harmonization layer.

The parser extracts entities, scalar fields, and trusted structural relations
from a dictionary input. It does not perform label harmonization, unit
normalization, relation harmonization, or anomaly detection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ParseError(ValueError):
    """Raised when an input document cannot be parsed safely."""


@dataclass(frozen=True)
class ParsedField:
    """
    A scalar or non-relation field extracted from an input entity.

    Attributes:
        label: Original input label without namespace prefix.
        value: Raw input value.
    """

    label: str
    value: Any


@dataclass(frozen=True)
class ParsedRelation:
    """
    A trusted structural relation extracted from an input entity.

    Attributes:
        label: Original input relation label without namespace prefix.
        target_id: Target entity id from a JSON-LD '@id' reference.
    """

    label: str
    target_id: str


@dataclass(frozen=True)
class ParsedEntity:
    """
    One parsed input entity.

    Attributes:
        entity_id: Entity id from '@id'.
        entity_type: Entity type from '@type', with namespace prefix removed.
        fields: Raw non-relation fields.
        relations: Raw relation references.
    """

    entity_id: str
    entity_type: str
    fields: list[ParsedField] = field(default_factory=list)
    relations: list[ParsedRelation] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedDocument:
    """
    Parsed representation of one JSON-LD-like input document.
    """

    entities: list[ParsedEntity] = field(default_factory=list)


def _strip_namespace(value: str) -> str:
    """
    Remove a simple namespace prefix from a JSON-LD key or type.

    Examples:
        'dpp:weight' -> 'weight'
        'DPPStatic' -> 'DPPStatic'
    """

    if ":" not in value:
        return value

    return value.split(":", maxsplit=1)[1]


def _extract_entity_type(raw_type: Any) -> str:
    """
    Extract one entity type from '@type'.

    The first parser version expects a single type string. If a list is provided,
    the first non-empty string is used.
    """

    if isinstance(raw_type, str):
        return _strip_namespace(raw_type)

    if isinstance(raw_type, list):
        for item in raw_type:
            if isinstance(item, str) and item.strip():
                return _strip_namespace(item)

    raise ParseError(f"Invalid or missing @type: {raw_type!r}")


def _extract_entity_id(raw_id: Any, *, node_index: int) -> str:
    """Extract an entity id from '@id'."""
    if isinstance(raw_id, str) and raw_id.strip():
        return raw_id.strip()

    raise ParseError(f"Invalid or missing @id for graph node at index {node_index}")


def _is_relation_value(value: Any) -> bool:
    """
    Return True if a value is a JSON-LD object reference.

    Only direct {'@id': '...'} values are treated as relations here. Lists of
    references are handled separately.
    """

    return isinstance(value, dict) and isinstance(value.get("@id"), str)


def _extract_relation_targets(value: Any) -> list[str]:
    """
    Extract target ids from a relation value.

    Supported forms:
        {'@id': 'target'}
        [{'@id': 'target-1'}, {'@id': 'target-2'}]
    """

    if _is_relation_value(value):
        return [value["@id"]]

    if isinstance(value, list):
        target_ids: list[str] = []
        for item in value:
            if _is_relation_value(item):
                target_ids.append(item["@id"])
        return target_ids

    return []


def _parse_graph_node(node: Any, *, node_index: int) -> ParsedEntity:
    """Parse one node from the '@graph' list."""
    if not isinstance(node, dict):
        raise ParseError(f"Graph node at index {node_index} must be an object.")

    entity_id = _extract_entity_id(node.get("@id"), node_index=node_index)
    entity_type = _extract_entity_type(node.get("@type"))

    fields: list[ParsedField] = []
    relations: list[ParsedRelation] = []

    for raw_label, value in node.items():
        if raw_label in {"@id", "@type", "@context"}:
            continue

        label = _strip_namespace(raw_label)
        target_ids = _extract_relation_targets(value)

        if target_ids:
            relations.extend(
                ParsedRelation(label=label, target_id=target_id)
                for target_id in target_ids
            )
            continue

        fields.append(ParsedField(label=label, value=value))

    return ParsedEntity(
        entity_id=entity_id,
        entity_type=entity_type,
        fields=fields,
        relations=relations,
    )


def parse_jsonld_document(document: dict[str, Any]) -> ParsedDocument:
    """
    Parse a minimal JSON-LD-like document.

    Supported input shape:
        {
            '@context': {...},
            '@graph': [
                {'@id': '...', '@type': 'dpp:DPPStatic', ...}
            ]
        }

    A single-node object with '@id' and '@type' is also accepted.
    """

    if not isinstance(document, dict):
        raise ParseError("Input document must be a dictionary.")

    if "@graph" in document:
        graph = document["@graph"]
        if not isinstance(graph, list):
            raise ParseError("@graph must be a list.")

        return ParsedDocument(
            entities=[
                _parse_graph_node(node, node_index=index)
                for index, node in enumerate(graph)
            ]
        )

    if "@id" in document and "@type" in document:
        return ParsedDocument(
            entities=[_parse_graph_node(document, node_index=0)]
        )

    raise ParseError("Input document must contain '@graph' or a single '@id'/'@type' node.")
