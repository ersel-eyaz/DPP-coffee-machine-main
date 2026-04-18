from __future__ import annotations

from pprint import pprint

from dpp.harmonization.parser import parse_jsonld_document
from dpp.harmonization.sample_inputs import EXAMPLE_JSONLD_DOCUMENT


def main() -> None:
    parsed = parse_jsonld_document(EXAMPLE_JSONLD_DOCUMENT)

    print()
    print("Parsed JSON-LD document")
    print(f" - property_count: {len(parsed.properties)}")
    print(f" - relation_count: {len(parsed.relations)}")

    print()
    print("Properties")
    for index, item in enumerate(parsed.properties, start=1):
        print(f"[{index}]")
        pprint(item.model_dump())

    print()
    print("Relations")
    for index, item in enumerate(parsed.relations, start=1):
        print(f"[{index}]")
        pprint(item.model_dump())


if __name__ == "__main__":
    main()