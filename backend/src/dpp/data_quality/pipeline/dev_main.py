"""
Local development entry point for the data quality harmonization flow.

This script is intentionally not wired into FastAPI or the existing prototype
backend. It is only used to run the isolated data_quality module locally.

Usage:
    PYTHONPATH=src python -m dpp.data_quality.pipeline.dev_main product
    PYTHONPATH=src python -m dpp.data_quality.pipeline.dev_main emission
    PYTHONPATH=src python -m dpp.data_quality.pipeline.dev_main label_fuzzy_candidate
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

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
    "mixed_dirty": ("product", "harmonization/mixed_dirty_input.json"),
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


def main() -> None:
    """Run one local harmonization example and print the result as JSON."""
    example_name = sys.argv[1] if len(sys.argv) > 1 else "product"

    scope_name, document = _load_example(example_name)
    result = harmonize_document(document, scope_name)

    print(json.dumps(asdict(result), indent=2, ensure_ascii=False))
    print(f"has_errors: {result.has_errors()}")


if __name__ == "__main__":
    main()
