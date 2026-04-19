from __future__ import annotations

import argparse
import json
from typing import Iterable

from dpp.harmonization.sample_inputs import EXAMPLE_JSONLD_DOCUMENT
from dpp.harmonization.services import harmonize_jsonld_document


PRIMARY_FIELDS = {
    "PartStatic.weightGRM",
    "PartStatic.mtbfHRS",
    "MaterialInstance.weightGRM",
    "MaterialInstance.percentRecycled",
    "MaterialInstance.purityLevel",
    "DPPInstance.operatingHRS",
    "DPPInstance.cleaningCount",
    "DPPInstance.chalkCount",
    "DPPInstance.brewingCount",
    "ActivityData.quantity",
    "EmissionFactor.value",
}


def _print_summary(result) -> None:
    print("\nPipeline summary")
    print(f" - raw properties: {result.stats.raw_property_count}")
    print(f" - raw relations: {result.stats.raw_relation_count}")
    print(f" - entities: {len(result.entities)}")
    print(f" - relations: {len(result.relations)}")
    print(f" - warnings: {result.stats.warning_count}")
    print(f" - errors: {result.stats.error_count}")


def _print_primary_field_summary(result) -> None:
    print("\nPrimary field summary")
    found_any = False

    for entity in result.entities.values():
        primary_fields = [
            field for name, field in entity.fields.items() if name in PRIMARY_FIELDS
        ]
        if not primary_fields:
            continue

        found_any = True
        print(f"- {entity.entity_type.value}: {entity.entity_id}")
        for field in primary_fields:
            print(
                f"    {field.canonical_name} = {field.normalized_value!r}"
                f" | unit={field.normalized_unit!r}"
            )

    if not found_any:
        print("- none")


def _print_relations(result) -> None:
    print("\nRelations")
    if not result.relations:
        print("- none")
        return

    for relation in result.relations:
        print(
            f"- {relation.relation_type.value}: "
            f"{relation.subject_entity_id} -> {relation.object_entity_id}"
        )


def _print_warnings_and_errors(result) -> None:
    warnings_or_errors = [
        issue for issue in result.issues if issue.severity.value in {"warning", "error"}
    ]

    print("\nWarnings / errors")
    if not warnings_or_errors:
        print("- none")
        return

    for issue in warnings_or_errors:
        print(f"- {issue.severity.value}: {issue.issue_type.value}: {issue.message}")


def _format_list(values: Iterable[str]) -> str:
    values = list(values)
    return ", ".join(repr(value) for value in values) if values else "-"


def _print_verbose_entity_dump(result) -> None:
    print("\nVerbose entity dump")
    if not result.entities:
        print("- none")
        return

    for entity in result.entities.values():
        print(f"\n[{entity.entity_type.value}] {entity.entity_id}")
        print(f"  source_ids: {_format_list(entity.source_ids)}")
        print(f"  source_node_types: {_format_list(entity.source_node_types)}")
        print(f"  source_paths: {_format_list(entity.source_paths)}")
        print(f"  tags: {_format_list(entity.tags)}")

        if not entity.fields:
            print("  fields: -")
            continue

        print("  fields:")
        for field_name, field in entity.fields.items():
            print(f"    - {field_name}")
            print(f"        role: {field.role.value}")
            print(f"        normalized_value: {field.normalized_value!r}")
            print(f"        normalized_unit: {field.normalized_unit!r}")
            print(f"        original_label: {field.original_label!r}")
            print(f"        original_value: {field.original_value!r}")
            print(f"        original_unit: {field.original_unit!r}")
            print(f"        confidence: {field.confidence}")
            print(f"        matched_by: {field.matched_by}")
            print(f"        provenance_paths: {_format_list(field.provenance_paths)}")
            print(f"        supporting_evidence: {_format_list(field.supporting_evidence)}")
            print(f"        notes: {_format_list(field.notes)}")


def _print_verbose_issues(result) -> None:
    print("\nAll issues")
    if not result.issues:
        print("- none")
        return

    for issue in result.issues:
        print(
            f"- severity={issue.severity.value}"
            f" | type={issue.issue_type.value}"
            f" | message={issue.message}"
        )
        if issue.entity_id is not None:
            print(f"    entity_id={issue.entity_id}")
        if issue.entity_type is not None:
            print(f"    entity_type={issue.entity_type.value}")
        if issue.field_name is not None:
            print(f"    field_name={issue.field_name}")
        if issue.source_path is not None:
            print(f"    source_path={issue.source_path}")
        if issue.raw_label is not None:
            print(f"    raw_label={issue.raw_label}")
        if issue.details:
            print(f"    details={json.dumps(issue.details, ensure_ascii=False, sort_keys=True)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the harmonization pipeline on the built-in sample input."
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print a full entity/field/issue dump in addition to the compact summary.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = harmonize_jsonld_document(EXAMPLE_JSONLD_DOCUMENT)

    _print_summary(result)
    _print_primary_field_summary(result)
    _print_relations(result)
    _print_warnings_and_errors(result)

    if args.verbose:
        _print_verbose_entity_dump(result)
        _print_verbose_issues(result)


if __name__ == "__main__":
    main()
