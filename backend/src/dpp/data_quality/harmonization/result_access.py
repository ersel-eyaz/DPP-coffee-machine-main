"""Shared access helpers for harmonization result objects."""

from __future__ import annotations

from typing import Any

from dpp.data_quality.harmonization.schemas import HarmonizedField


def effective_field_value(field: HarmonizedField) -> Any:
    """
    Return the value downstream consumers should read from a harmonized field.

    Harmonization keeps both the original and normalized value for traceability.
    Clean output and anomaly checks should use the normalized value when it is
    available, otherwise they fall back to the original value.
    """
    if field.normalized_value is not None:
        return field.normalized_value

    return field.original_value
