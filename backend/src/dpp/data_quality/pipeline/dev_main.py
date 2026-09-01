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
    PYTHONPATH=src python -m dpp.data_quality.pipeline.dev_main emission --output anomaly
    PYTHONPATH=src python -m dpp.data_quality.pipeline.dev_main product_anomaly --output features
    PYTHONPATH=src python -m dpp.data_quality.pipeline.dev_main emission_anomaly --output quality
    PYTHONPATH=src python -m dpp.data_quality.pipeline.dev_main service_text --output full
    PYTHONPATH=src python -m dpp.data_quality.pipeline.dev_main --scope product --input path/to/input.json --output quality
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from dpp.data_quality.anomaly.features import build_feature_table
from dpp.data_quality.anomaly.outputs import build_anomaly_report
from dpp.data_quality.anomaly.services import analyze_harmonization_result
from dpp.data_quality.harmonization.outputs import (
    build_clean_jsonld,
    build_full_output,
    build_harmonization_report,
)
from dpp.data_quality.harmonization.services import harmonize_document

EXAMPLES = {
    "product": ("product", "harmonization/product_dirty.json"),
    "emission": ("emission", "harmonization/emission_dirty.json"),

    # Controlled scenario examples.
    "label_exact_alias": ("product", "harmonization/label_exact_alias_input.json"),
    "label_fuzzy_candidate": ("product", "harmonization/label_fuzzy_candidate_input.json"),
    "label_ambiguous": ("product", "harmonization/label_ambiguous_input.json"),
    "product_anomaly": ("product", "harmonization/product_anomaly_input.json"),
    "product_relation_issues": ("product", "harmonization/product_relation_issues_input.json"),
    "product_profile": ("product", "harmonization/product_profile_input.json"),
    "unit_exact_alias": ("product", "harmonization/unit_exact_alias_input.json"),
    "unit_fuzzy_candidate": ("product", "harmonization/unit_fuzzy_candidate_input.json"),
    "unit_ambiguous": ("emission", "harmonization/unit_ambiguous_input.json"),
    "unit_unsupported": ("product", "harmonization/unit_unsupported_input.json"),
    "enum_alias": ("emission", "harmonization/enum_alias_input.json"),
    "enum_fuzzy": ("emission", "harmonization/enum_fuzzy_input.json"),
    "enum_semantic": ("emission", "harmonization/enum_semantic_input.json"),
    "emission_anomaly": ("emission", "harmonization/emission_anomaly_input.json"),
    "emission_relation_issues": ("emission", "harmonization/emission_relation_issues_input.json"),
    "mixed_dirty": ("product", "harmonization/mixed_dirty_input.json"),
    "service_anomaly": ("service", "harmonization/service_anomaly_input.json"),
    "service_relation_issues": ("service", "harmonization/service_relation_issues_input.json"),
    "service_text": ("service", "harmonization/service_text_input.json"),
    "service_semantic": ("service", "harmonization/service_semantic_input.json"),
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


def _parse_option(args: list[str], option_name: str) -> str | None:
    """Return an option value from CLI args, if present."""
    if option_name not in args:
        return None

    index = args.index(option_name)
    try:
        value = args[index + 1]
    except IndexError as exc:
        raise ValueError(f"{option_name} requires a value") from exc

    if value.startswith("--"):
        raise ValueError(f"{option_name} requires a value")

    return value


def _parse_output_mode(args: list[str]) -> str:
    """Parse the optional --output argument."""
    output_mode = _parse_option(args, "--output")
    if output_mode is None:
        return "full"

    if output_mode not in {"data", "report", "anomaly", "features", "quality", "full"}:
        raise ValueError("--output requires one of: data, report, anomaly, features, quality, full")

    return output_mode


def _load_input_document(args: list[str]) -> tuple[str, dict[str, Any]]:
    """Load either a registered example or a custom JSON input file."""
    input_path = _parse_option(args, "--input")
    scope_name = _parse_option(args, "--scope")

    if input_path is not None:
        if scope_name is None:
            raise ValueError("--input requires --scope with one of: product, emission, service")

        with Path(input_path).open("r", encoding="utf-8") as file:
            return scope_name, json.load(file)

    if scope_name is not None:
        raise ValueError("--scope is only used together with --input")

    example_name = args[0] if args and not args[0].startswith("--") else "product"
    return _load_example(example_name)


def main() -> None:
    """Run one local harmonization example or custom input and print valid JSON."""
    args = sys.argv[1:]
    output_mode = _parse_output_mode(args)

    scope_name, document = _load_input_document(args)
    result = harmonize_document(document, scope_name)

    if output_mode == "data":
        payload = build_clean_jsonld(result, document=document)
    elif output_mode == "report":
        payload = {
            "report": build_harmonization_report(result),
            "has_errors": result.has_errors(),
        }
    elif output_mode == "anomaly":
        anomaly_result = analyze_harmonization_result(result)
        payload = {
            "report": build_anomaly_report(anomaly_result),
            "has_errors": anomaly_result.has_errors(),
        }
    elif output_mode == "features":
        payload = {
            "feature_table": build_feature_table(result),
            "has_errors": result.has_errors(),
        }
    elif output_mode == "quality":
        anomaly_result = analyze_harmonization_result(result)
        payload = {
            "data": build_clean_jsonld(result, document=document),
            "harmonization_report": build_harmonization_report(result),
            "anomaly_report": build_anomaly_report(anomaly_result),
            "has_errors": result.has_errors() or anomaly_result.has_errors(),
        }
    else:
        payload = build_full_output(result, document=document)

    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
