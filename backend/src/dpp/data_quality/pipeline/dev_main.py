"""
Local development entry point for the data quality harmonization flow.

This script is intentionally not wired into FastAPI or the existing prototype
backend. It is only used to run the isolated data_quality module locally.

Usage:
    PYTHONPATH=src python -m dpp.data_quality.pipeline.dev_main product
    PYTHONPATH=src python -m dpp.data_quality.pipeline.dev_main emission
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from dpp.data_quality.harmonization.services import harmonize_document


EXAMPLE_FILES = {
    "product": "product_dirty.json",
    "emission": "emission_dirty.json",
}


def _examples_dir() -> Path:
    """Return the examples directory inside the data_quality package."""
    return Path(__file__).resolve().parents[1] / "examples"


def _load_example(scope_name: str) -> dict[str, Any]:
    """Load the example JSON document for a scope."""
    filename = EXAMPLE_FILES.get(scope_name)
    if filename is None:
        supported = ", ".join(sorted(EXAMPLE_FILES))
        raise ValueError(f"Unsupported example scope {scope_name!r}. Supported: {supported}")

    path = _examples_dir() / filename
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def main() -> None:
    """Run one local harmonization example and print the result as JSON."""
    scope_name = sys.argv[1] if len(sys.argv) > 1 else "product"

    document = _load_example(scope_name)
    result = harmonize_document(document, scope_name)

    print(json.dumps(asdict(result), indent=2, ensure_ascii=False))
    print(f"has_errors: {result.has_errors()}")


if __name__ == "__main__":
    main()
