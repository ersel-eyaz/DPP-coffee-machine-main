"""
Local development entry point for the data quality harmonization flow.

This script is intentionally not wired into FastAPI or the existing prototype
backend. It is only used to run the isolated data_quality module locally.

Usage:
    PYTHONPATH=src python -m dpp.data_quality.pipeline.dev_main product
    PYTHONPATH=src python -m dpp.data_quality.pipeline.dev_main emission
    PYTHONPATH=src python -m dpp.data_quality.pipeline.dev_main label_fuzzy_candidate
    PYTHONPATH=src python -m dpp.data_quality.pipeline.dev_main emission --output data
    PYTHONPATH=src python -m dpp.data_quality.pipeline.dev_main emission --output report
    PYTHONPATH=src python -m dpp.data_quality.pipeline.dev_main service_text --output full
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from dpp.data_quality.harmonization.outputs import (
    build_clean_jsonld,
    build_full_output,
    build_harmonization_report,
)
from dpp.data_quality.harmonization.services import harmonize_document


EXAMPLES = {
    "product": ("product", "product_dirty.json"),
    "emission": ("emission", "emission_dirty.json"),

    # Controlled scenario examples.
    "label_exact_alias": ("product", "harmonization/label_exact_alias_input.json"),
    "label_fuzzy_candidate": ("product", "harmonization/label_fuzzy_candidate_input.json"),
    "label_ambiguous": ("product", "harmonization/label_ambiguous_input.json"),
    "unit_exact_alias": ("product", "harmonization/unit_exact_alias_input.json"),
    "unit_fuzzy_candidate": ("product", "harmonization/unit_fuzzy_candidate_input.json"),
    "unit_ambiguous": ("emission", "harmonization/unit_ambiguous_input.json"),
    "unit_unsupported": ("product", "harmonization/unit_unsupported_input.json"),
    "enum_alias": ("emission", "harmonization/enum_alias_input.json"),
    "enum_fuzzy": ("emission", "harmonization/enum_fuzzy_input.json"),
    "enum_semantic": ("emission", "harmonization/enum_semantic_input.json"),
    "mixed_dirty": ("product", "harmonization/mixed_dirty_input.json"),
    "service_text": ("service", "harmonization/service_text_input.json"),
}


def _examples_dir() -> Path:
    """Return the examples directory inside the data_quality package."""
    return Path(__file__).resolve().parents[1] / "examples"


def _load_example(example_name: str) -> tuple[str, dict[str, Any]]:
    """Load the example JSON document and return its scope name."""
    entry = EXAMPLES.get(example_name)
    if entry is None:
        supported = ", ".join(sorted(EXAMPLES))
        raise ValueError(f"Unsupported example {example_name!r}. Supported: {supported}")

    scope_name, filename = entry
    path = _examples_dir() / filename
    with path.open("r", encoding="utf-8") as file:
        return scope_name, json.load(file)


def _parse_output_mode(args: list[str]) -> str:
    """Parse the optional --output argument."""
    if "--output" not in args:
        return "full"

    index = args.index("--output")
    try:
        output_mode = args[index + 1]
    except IndexError as exc:
        raise ValueError("--output requires one of: data, report, full") from exc

    if output_mode not in {"data", "report", "full"}:
        raise ValueError("--output requires one of: data, report, full")

    return output_mode


def main() -> None:
    """Run one local harmonization example and print valid JSON."""
    args = sys.argv[1:]
    example_name = args[0] if args and not args[0].startswith("--") else "product"
    output_mode = _parse_output_mode(args)

    scope_name, document = _load_example(example_name)
    result = harmonize_document(document, scope_name)

    if output_mode == "data":
        payload = build_clean_jsonld(result, document=document)
    elif output_mode == "report":
        payload = {
            "report": build_harmonization_report(result),
            "has_errors": result.has_errors(),
        }
    else:
        payload = build_full_output(result, document=document)

    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
