# src/dpp/models/part.py
"""
Part models for the DPP prototype.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Type, TypeVar, Union

from beanie import Document, Insert, Link, before_event
from fastapi import HTTPException, status
from pydantic import ConfigDict, Field, field_validator

from dpp.models.constants import UUID_URN_REGEX

from .location import Place
from .material import MaterialInstance
from .organisation import Manufacturer
from .processstep import ProcessUnion

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_urn_uuid(value: str) -> bool:
    """True if `value` matches the 'urn:uuid:<UUID>' pattern."""
    return bool(UUID_URN_REGEX.fullmatch(value))


async def _resolve_link_or_instance(
    maybe_link: Union[Link[T], T, None],
    expected_type: Type[T],
    *,
    field_name: str,
    parent_label: str,
) -> T:
    """
    Resolve a Beanie Link
    """
    if maybe_link is None:
        msg = f"Missing {field_name} for {parent_label}"
        logger.error(msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    obj: Any = await maybe_link.fetch() if isinstance(maybe_link, Link) else maybe_link
    if obj is None or not isinstance(obj, expected_type):
        msg = f"Invalid {field_name} reference for {parent_label}"
        logger.error(msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return obj


async def _ensure_unique_document_id(model: type[Document], doc_id: str, *, label: str) -> None:
    """
    Uniqueness check for _id before insert.
    """
    if await model.get(doc_id):
        msg = f"{label} with id {doc_id} already exists"
        logger.error(msg)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)


async def _validate_step_places(step: Any, *, parent_label: str) -> None:
    """
    Validate that a process step has a valid `processedAt` (required) and, if present,
    a valid `destination`.
    """
    step_id = getattr(step, "id", "<no-id>")
    if not hasattr(step, "processedAt") or step.processedAt is None:
        msg = f"Missing processedAt in process step {step_id} ({parent_label})"
        logger.error(msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    await _resolve_link_or_instance(
        step.processedAt,
        Place,
        field_name="processedAt",
        parent_label=f"process step {step_id} ({parent_label})",
    )
    if getattr(step, "destination", None) is not None:
        await _resolve_link_or_instance(
            step.destination,
            Place,
            field_name="destination",
            parent_label=f"process step {step_id} ({parent_label})",
        )


# ---------------------------------------------------------------------------
# PART MODELS
# ---------------------------------------------------------------------------


class PartStatic(Document):
    """
    part description with physical dimensions and a manufacturer link.
    """

    id: str = Field(
        default_factory=lambda: f"urn:uuid:{uuid.uuid4()}",
        validation_alias="_id",
        serialization_alias="id",
        description="URN UUID, e.g. 'urn:uuid:...'.",
    )

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        if not _is_urn_uuid(value):
            raise ValueError("id for PartStatic must be a valid 'urn:uuid:<UUID>' string")
        return value

    type_: str = Field(default="PartStatic", alias="type")

    name: str = Field(...)
    description: str = Field(...)
    partManufacturer: Link[Manufacturer] = Field(...)

    heightCM: float = Field(..., gt=0.0)
    widthCM: float = Field(..., gt=0.0)
    depthCM: float = Field(..., gt=0.0)
    weightGRM: float = Field(..., gt=0.0)

    avv_dispose: str | None = Field(default=None)
    mtbfHRS: float = Field(..., ge=0.0, description="Mean time between failures (hours).")

    @before_event(Insert)
    async def _validate_part_static(self) -> None:
        """
        Before insert:
        - Ensure manufacturer link resolves.
        - Ensure `_id` uniqueness.
        - Dimensions and weight are validated
        """
        manufacturer = await _resolve_link_or_instance(
            self.partManufacturer,
            Manufacturer,
            field_name="partManufacturer",
            parent_label=f"PartStatic {self.name}",
        )

        await _ensure_unique_document_id(PartStatic, self.id, label="PartStatic")

        if any(v <= 0 for v in (self.heightCM, self.widthCM, self.depthCM, self.weightGRM)):
            msg = f"All dimensions/weight must be positive for PartStatic {self.name} ({manufacturer.name})"
            logger.error(msg)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

        if self.mtbfHRS < 0:
            msg = f"MTBF must be non-negative for PartStatic {self.name}"
            logger.error(msg)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    class Settings:
        name = "part_static"
        is_root = True
        smart_union = True

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
    )


PartStatic.update_forward_refs()


class PartInstance(Document):
    """
    Dynamic instance of a part, linking to its static definition and tracking steps.
    """

    id: str = Field(
        default_factory=lambda: f"urn:uuid:{uuid.uuid4()}",
        validation_alias="_id",
        serialization_alias="id",
        description="URN UUID, e.g. 'urn:uuid:...'.",
    )

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        if not _is_urn_uuid(value):
            raise ValueError("id for PartInstance must be a valid 'urn:uuid:<UUID>' string")
        return value

    type_: str = Field(default="PartInstance", alias="type")

    partStaticLink: Link[PartStatic]
    serialNumber: str | None = None
    batchNumber: str

    isModular: bool = Field(default=False)
    hasFailstate: bool = Field(default=False)

    compositeParts: list["PartInstance"] = Field(default_factory=list)
    historyOfDetachedParts: list["PartInstance"] = Field(default_factory=list)
    compositeMaterials: list[MaterialInstance] = Field(default_factory=list)

    partProcessTracking: list[ProcessUnion] = Field(default_factory=list)

    @before_event(Insert)
    async def _validate_part_instance(self) -> None:
        """
        Before insert:
        - Ensure static link resolves.
        - Ensure `_id` uniqueness.
        - Validate required Place links on each process step.
        """
        static = await _resolve_link_or_instance(
            self.partStaticLink,
            PartStatic,
            field_name="partStaticLink",
            parent_label=f"PartInstance {self.id}",
        )

        await _ensure_unique_document_id(PartInstance, self.id, label="PartInstance")

        for step in self.partProcessTracking:
            await _validate_step_places(
                step, parent_label=f"PartInstance {self.id} (static: {getattr(static, 'name', 'unknown')})"
            )

    class Settings:
        name = "part_instance"
        is_root = True
        smart_union = True

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
    )


PartInstance.update_forward_refs()

# ---------------------------------------------------------------------------
# Forward-ref resolution for Pydantic v2
# ---------------------------------------------------------------------------
try:
    MaterialInstance.model_rebuild(_types_namespace={"PartInstance": PartInstance})
    from .processstep import ReplaceServiceStep, RemanufacturingServiceStep, RefurbishmentServiceStep

    _TYPES = {"PartInstance": PartInstance}
    ReplaceServiceStep.model_rebuild(_types_namespace=_TYPES)
    RemanufacturingServiceStep.model_rebuild(_types_namespace=_TYPES)
    RefurbishmentServiceStep.model_rebuild(_types_namespace=_TYPES)
except Exception as _e:
    logger.warning("Forward-ref rebuild skipped: %s", _e)

__all__ = ["PartStatic", "PartInstance"]
