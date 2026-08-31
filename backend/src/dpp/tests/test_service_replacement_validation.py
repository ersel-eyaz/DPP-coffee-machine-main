from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from dpp.routers.dpp import _validate_replacement_part_compatibility


def _part(part_id: str, static_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=part_id,
        partStaticLink=SimpleNamespace(id=static_id),
    )


def test_distinct_instances_of_same_static_part_are_accepted() -> None:
    _validate_replacement_part_compatibility(
        _part("part-old-001", "part-static-001"),
        _part("part-new-001", "part-static-001"),
    )


def test_reused_replacement_instance_id_is_rejected() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _validate_replacement_part_compatibility(
            _part("part-001", "part-static-001"),
            _part("part-001", "part-static-001"),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Replacement part must use a new PartInstance id."


def test_different_static_part_definition_is_rejected() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _validate_replacement_part_compatibility(
            _part("part-old-001", "part-static-001"),
            _part("part-new-001", "part-static-002"),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == (
        "Replacement part must reference the same PartStatic definition as the replaced part."
    )
