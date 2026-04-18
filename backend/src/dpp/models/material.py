# src/dpp/models/material.py
"""
Material models for the DPP prototype.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional, Type, TypeVar, Union

from beanie import Document, Insert, Link, before_event
from beanie.operators import And, Eq
from fastapi import HTTPException, status
from pydantic import ConfigDict, Field, field_validator

from dpp.models.constants import UUID_URN_REGEX

from .location import Place
from .organisation import Manufacturer
from .processstep import ProcessUnion
from .quantitativqualitativvalue import DigitalDocument

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_urn_uuid(value: str) -> bool:
    """Return True if `value` matches 'urn:uuid:<UUID>'."""
    return bool(UUID_URN_REGEX.fullmatch(value))


async def _resolve_link_or_instance(
    maybe_link: Union[Link[T], T, None],
    expected_type: Type[T],
    *,
    field_name: str,
    parent_label: str,
) -> T:
    """
    Resolve a Beanie Link to its instance
    """
    obj: Any
    if maybe_link is None:
        msg = f"Missing {field_name} for {parent_label}"
        logger.error(msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    obj = await maybe_link.fetch() if isinstance(maybe_link, Link) else maybe_link
    if obj is None or not isinstance(obj, expected_type):
        msg = f"Invalid {field_name} reference for {parent_label}"
        logger.error(msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return obj


async def _ensure_unique_document_id(model: type[Document], doc_id: str, *, label: str) -> None:
    """
    Provide uniqueness check
    """
    if await model.get(doc_id):
        msg = f"{label} with id {doc_id} already exists"
        logger.error(msg)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)


# ---------------------------------------------------------------------------
# MATERIAL MODELS
# ---------------------------------------------------------------------------


class MaterialStatic(Document):
    """
    Static data for a material.
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
            raise ValueError("id for MaterialStatic must be a valid 'urn:uuid:<UUID>' string")
        return value

    type_: str = Field(default="MaterialStatic", alias="type")

    name: str = Field(...)
    description: str = Field(...)
    materialManufacturer: Link[Manufacturer] = Field(...)
    casNumber: Optional[str] = Field(default=None)
    isoDesignation: Optional[str] = Field(default=None)
    eclassClassification: Optional[str] = Field(default=None)
    hazardous: bool = Field(default=False)
    warnings: list[str] = Field(default_factory=list)
    reachCertification: Optional[DigitalDocument] = Field(default=None)
    additionalDocuments: list[DigitalDocument] = Field(default_factory=list)
    rareEarth: bool = Field(
        default=False,
        description="Indicates if the material contains rare earth elements.",
    )

    @field_validator("name", "description")
    @classmethod
    def _strip_nonempty(cls, v: str) -> str:
        value = (v or "").strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @before_event(Insert)
    async def _validate_manufacturer_and_uniqueness(self) -> None:
        """
        Before insert:
        - Ensure manufacturer link resolves.
        - Ensure `_id` is unique
        - Prevent duplicate pairs.
        """
        manufacturer_obj = await _resolve_link_or_instance(
            self.materialManufacturer,
            Manufacturer,
            field_name="materialManufacturer",
            parent_label=f"MaterialStatic {self.name}",
        )

        await _ensure_unique_document_id(MaterialStatic, self.id, label="MaterialStatic")

        dup = await MaterialStatic.find(
            And(
                Eq(MaterialStatic.name, self.name),
                Eq(MaterialStatic.materialManufacturer.id, manufacturer_obj.id),
            )
        ).first_or_none()
        if dup:
            msg = f"MaterialStatic with name '{self.name}' and the same manufacturer already exists"
            logger.error(msg)
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)

    class Settings:
        name = "material_static"
        is_root = True
        smart_union = True

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
    )


class MaterialInstance(Document):
    """
    Concrete material batch/instance with process tracking.
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
            raise ValueError("id for MaterialInstance must be a valid 'urn:uuid:<UUID>' string")
        return value

    type_: str = Field(default="MaterialInstance", alias="type")

    materialStaticLink: Link[MaterialStatic]
    batchNumber: str
    weightGRM: float
    percentRecycled: float
    purityLevel: float
    materialProcessTracking: list[ProcessUnion] = Field(default_factory=list)

    @field_validator("batchNumber")
    @classmethod
    def _batch_nonempty(cls, v: str) -> str:
        value = (v or "").strip()
        if not value:
            raise ValueError("batchNumber must not be empty")
        return value

    @field_validator("weightGRM")
    @classmethod
    def _weight_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("weightGRM must be non-negative")
        return float(v)

    @field_validator("percentRecycled")
    @classmethod
    def _percent_range(cls, v: float) -> float:
        if v < 0 or v > 100:
            raise ValueError("percentRecycled must be between 0 and 100")
        return float(v)

    @field_validator("purityLevel")
    @classmethod
    def _purity_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("purityLevel must be non-negative")
        return float(v)

    @before_event(Insert)
    async def _validate_and_uniquify(self) -> None:
        """
        Before insert:
        - Ensure the static link resolves.
        - Ensure `_id` is unique.
        - Validate each process step's place links.
        """
        await _resolve_link_or_instance(
            self.materialStaticLink,
            MaterialStatic,
            field_name="materialStaticLink",
            parent_label=f"MaterialInstance {self.id}",
        )

        await _ensure_unique_document_id(MaterialInstance, self.id, label="MaterialInstance")

        for step in self.materialProcessTracking:
            step_id = getattr(step, "id", "<no-id>")
            if not hasattr(step, "processedAt") or step.processedAt is None:
                msg = f"Missing processedAt in process step {step_id}"
                logger.error(msg)
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

            await _resolve_link_or_instance(
                step.processedAt,
                Place,
                field_name="processedAt",
                parent_label=f"process step {step_id}",
            )

            if getattr(step, "destination", None) is not None:
                await _resolve_link_or_instance(
                    step.destination,
                    Place,
                    field_name="destination",
                    parent_label=f"process step {step_id}",
                )

    class Settings:
        name = "material_instance"
        is_root = True
        smart_union = True

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
    )


__all__ = [
    "MaterialStatic",
    "MaterialInstance",
]
