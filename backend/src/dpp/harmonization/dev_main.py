from __future__ import annotations

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


def main() -> None:
    result = harmonize_jsonld_document(EXAMPLE_JSONLD_DOCUMENT)

    print("\nPipeline summary")
    print(f" - raw properties: {result.stats.raw_property_count}")
    print(f" - raw relations: {result.stats.raw_relation_count}")
    print(f" - entities: {len(result.entities)}")
    print(f" - relations: {len(result.relations)}")
    print(f" - warnings: {result.stats.warning_count}")
    print(f" - errors: {result.stats.error_count}")

    print("\nPrimary field summary")
    for entity in result.entities.values():
        primary_fields = [
            field for name, field in entity.fields.items() if name in PRIMARY_FIELDS
        ]
        if not primary_fields:
            continue

        print(f"- {entity.entity_type.value}: {entity.entity_id}")
        for field in primary_fields:
            print(
                f"    {field.canonical_name} = {field.normalized_value!r}"
                f" | unit={field.normalized_unit!r}"
            )

    print("\nRelations")
    for relation in result.relations:
        print(
            f"- {relation.relation_type.value}: "
            f"{relation.subject_entity_id} -> {relation.object_entity_id}"
        )

    warnings_or_errors = [
        issue for issue in result.issues if issue.severity.value in {"warning", "error"}
    ]

    print("\nWarnings / errors")
    if not warnings_or_errors:
        print("- none")
        return

    for issue in warnings_or_errors:
        print(f"- {issue.severity.value}: {issue.issue_type.value}: {issue.message}")


if __name__ == "__main__":
    main()
