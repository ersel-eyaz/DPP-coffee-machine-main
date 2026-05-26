"""
Minimal JSON-LD-like parser for the harmonization layer.

The parser extracts entities, scalar fields, trusted references, and embedded
typed child objects from a dictionary input. It does not perform label
harmonization, unit normalization, relation harmonization, or anomaly detection.
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
class ParsedEmbeddedEntity:
    """A typed entity embedded below one structural input property."""

    label: str
    entity: "ParsedEntity"


@dataclass(frozen=True)
class ParsedEntity:
    """
    One parsed input entity.

    Attributes:
        entity_id: Entity id from '@id'.
        entity_type: Entity type from '@type', with namespace prefix removed.
        fields: Raw non-relation fields.
        relations: Raw relation references.
        embedded_entities: Typed owned children found below this entity.
    """

    entity_id: str
    entity_type: str
    has_explicit_id: bool = True
    fields: list[ParsedField] = field(default_factory=list)
    relations: list[ParsedRelation] = field(default_factory=list)
    embedded_entities: list[ParsedEmbeddedEntity] = field(default_factory=list)


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


def _extract_entity_id(raw_id: Any, *, fallback_id: str) -> str:
    """Extract an entity id, using a deterministic path id for embedded objects."""
    if isinstance(raw_id, str) and raw_id.strip():
        return raw_id.strip()

    return fallback_id


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


def _normalize_nested_value(value: Any) -> Any:
    """Normalize compact JSON-LD measurement objects for downstream harmonization."""
    if not isinstance(value, dict):
        return value

    scalar_value = value.get("value", value.get("schema:value"))
    unit = value.get("unit", value.get("unitCode", value.get("schema:unitCode")))
    if scalar_value is None or unit is None:
        return value

    return {"value": scalar_value, "unit": unit}


def _parse_graph_node(node: Any, *, fallback_id: str) -> ParsedEntity:
    """Parse one root or embedded typed node."""
    if not isinstance(node, dict):
        raise ParseError(f"Entity node at {fallback_id!r} must be an object.")

    entity_id = _extract_entity_id(node.get("@id"), fallback_id=fallback_id)
    entity_type = _extract_entity_type(node.get("@type"))

    fields: list[ParsedField] = []
    relations: list[ParsedRelation] = []
    embedded_entities: list[ParsedEmbeddedEntity] = []

    for raw_label, value in node.items():
        if raw_label in {"@id", "@type", "@context"}:
            continue

        label = _strip_namespace(raw_label)
        normalized_value = _normalize_nested_value(value)
        if normalized_value is not value:
            fields.append(ParsedField(label=label, value=normalized_value))
            continue

        child_values: list[dict[str, Any]] = []
        if isinstance(value, dict) and "@type" in value:
            child_values = [value]
        elif isinstance(value, list):
            child_values = [
                item
                for item in value
                if isinstance(item, dict) and "@type" in item
            ]

        if child_values:
            embedded_entities.extend(
                ParsedEmbeddedEntity(
                    label=label,
                    entity=_parse_graph_node(
                        child,
                        fallback_id=f"{entity_id}/{label}/{index}",
                    ),
                )
                for index, child in enumerate(child_values)
            )
            continue

        target_ids = _extract_relation_targets(value)

        if target_ids:
            relations.extend(
                ParsedRelation(label=label, target_id=target_id)
                for target_id in target_ids
            )
            continue

        fields.append(ParsedField(label=label, value=normalized_value))

    return ParsedEntity(
        entity_id=entity_id,
        entity_type=entity_type,
        has_explicit_id=isinstance(node.get("@id"), str) and bool(node.get("@id").strip()),
        fields=fields,
        relations=relations,
        embedded_entities=embedded_entities,
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
                _parse_graph_node(node, fallback_id=f"graph-node-{index}")
                for index, node in enumerate(graph)
            ]
        )

    if "@id" in document and "@type" in document:
        return ParsedDocument(
            entities=[_parse_graph_node(document, fallback_id="root-node-0")]
        )

    raise ParseError("Input document must contain '@graph' or a single '@id'/'@type' node.")
