# src/dpp/models/dpp.py
"""
DPP (Digital Product Passport) models.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, List, Literal, Optional, Sequence, Tuple, Type, TypeVar, Union

from beanie import Document, Insert, Link, before_event
from fastapi import HTTPException, status
from pydantic import ConfigDict, Field, field_validator

from dpp.models.constants import generate_gtin_14_number, generate_sgtin_96_number
from dpp.models.location import Place
from dpp.models.organisation import Importer, Manufacturer, Organisation
from dpp.models.part import PartInstance, PartStatic

from .quantitativqualitativvalue import (
    DigitalDocument,
    ImageReference,
    QualificationForRepair,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

T = TypeVar("T")


def _utc_now() -> datetime:
    """Current UTC timestamp."""
    return datetime.now(timezone.utc)


def _digits_only_with_len(value: str, expected_len: int) -> bool:
    """True if the string has only decimal digits and exact expected length."""
    return value.isdigit() and len(value) == expected_len


async def _resolve_link_or_object(
    maybe_link: Union[Link[T], T, None],
    expected_type: Type[T],
    field_name: str,
    parent_label: str,
) -> T:
    """
    Resolve a Beanie Link to an instance.
    """
    if maybe_link is None:
        msg = f"Missing {field_name} reference in {parent_label}"
        logger.error(msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    resolved: Any
    if isinstance(maybe_link, Link):
        resolved = await maybe_link.fetch()
    else:
        resolved = maybe_link

    if resolved is None or not isinstance(resolved, expected_type):
        msg = f"Invalid {field_name} reference for {parent_label}"
        logger.error(msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    return resolved


async def _validate_and_dedupe_links(
    links: Iterable[Union[Link[T], T]],
    expected_type: Type[T],
    field_name: str,
    parent_label: str,
) -> None:
    """
    Resolve a sequence of links/objects, ensure type correctness.
    """
    seen_ids: set[str] = set()
    for idx, item in enumerate(links):
        resolved = await _resolve_link_or_object(item, expected_type, field_name, parent_label)
        ref_id = getattr(resolved, "id", None)
        if not ref_id:
            msg = f"{field_name}[{idx}] in {parent_label} has no 'id'"
            logger.error(msg)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

        if ref_id in seen_ids:
            msg = f"Duplicate {field_name} '{ref_id}' in {parent_label}"
            logger.error(msg)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

        seen_ids.add(ref_id)


def _extract_numeric(value: Any) -> float:
    """
    Extract a numeric value from either a raw number or an object with a 'value' attribute.
    """
    candidate = getattr(value, "value", value)
    if isinstance(candidate, (int, float)):
        return float(candidate)
    raise TypeError(f"Not a numeric value: {candidate!r}")


def _ensure_non_negative_counters(name_value_pairs: Sequence[Tuple[str, Any]]) -> None:
    """
    Validate that named numeric counters are >= 0.
    """
    for counter_name, raw in name_value_pairs:
        try:
            numeric = _extract_numeric(raw)
        except TypeError as exc:
            msg = f"{counter_name} does not contain a valid numeric value: {raw!r}"
            logger.error(msg)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from exc

        if numeric < 0:
            msg = f"{counter_name} must be >= 0, got {numeric}"
            logger.error(msg)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


async def _validate_current_location(place_obj: Optional[Place], instance_label: str) -> None:
    """
    If current location is present, ensure it is a Place instance that exists in the DB.
    """
    if place_obj is None:
        return

    if not isinstance(place_obj, Place):
        msg = f"currentLocation must be a Place, got {type(place_obj)} in {instance_label}"
        logger.error(msg)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="currentLocation must be a Place if provided"
        )

    existing = await Place.get(place_obj.id)
    if existing is None:
        msg = f"currentLocation refers to non-existent Place: {place_obj.id} in {instance_label}"
        logger.error(msg)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"currentLocation refers to non-existent Place: {place_obj.id}",
        )


def _validate_timeline(date_of_declaration: datetime, end_of_guarantee: datetime, instance_label: str) -> None:
    """
    Ensure guarantee end is not before declaration date.
    """
    if end_of_guarantee < date_of_declaration:
        msg = f"endOfGuarantee must be on or after dateOfDeclaration for {instance_label}"
        logger.error(msg)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="endOfGuarantee must be on or after dateOfDeclaration",
        )


# ---------------------------------------------------------------------------
# STATIC MODEL
# ---------------------------------------------------------------------------


class DPPStatic(Document):
    """
    Static representation of a product (metadata for all product instances).
    """

    id: str = Field(
        default_factory=generate_gtin_14_number,
        alias="_id",
        serialization_alias="id",
    )

    @field_validator("id")
    @classmethod
    def _validate_gtin_id(cls, value: str) -> str:
        """GTIN-14 must be 14 decimal digits."""
        if not _digits_only_with_len(value, 14):
            raise ValueError("ID  must be 14 digits")
        return value

    type_: Literal["DPPStatic"] = Field(default="DPPStatic", alias="type")
    EAN: Optional[str] = Field(default=None)
    GS1DigitalLink: str = Field(...)
    name: str = Field(...)
    description: str = Field(...)
    productClass: str
    heightCM: float
    widthCM: float
    depthCM: float
    weightGRM: float
    dataSheet: DigitalDocument
    installationOperatingGuide: DigitalDocument
    ceConformityDeclaration: DigitalDocument
    ecodesignConformityDeclaration: DigitalDocument
    repairAndServiceManual: DigitalDocument
    DisassemblyInstructions: DigitalDocument
    recyclingEOLInstructions: DigitalDocument
    dateOfPublication: datetime = Field(default_factory=_utc_now)
    guaranteeDescription: str
    expectedMtbfHRS: float = Field(...)
    taricCode: str
    weeeRegistrationNumber: str = Field(...)
    responsibleOperator: Link[Organisation] = Field(...)
    importer: Optional[Link[Importer]] = Field(default=None)
    productManufacturer: Link[Manufacturer] = Field(...)
    has_spare_parts: List[Link[PartStatic]] = Field(default_factory=list)
    toolsForMaintenance: List[str] = Field(default_factory=list)
    qualificationForRepair: QualificationForRepair = Field(...)
    backupLink: str
    returningPlaces: List[Link[Place]] = Field(default_factory=list)
    image_file_ids: List[ImageReference] = Field(
        default_factory=list,
        description="Image references.",
    )

    @field_validator("EAN")
    @classmethod
    def _validate_optional_ean(cls, value: Optional[str]) -> Optional[str]:
        """If an EAN is provided, enforce 13 digits."""
        if value is None:
            return value
        if not _digits_only_with_len(value, 13):
            raise ValueError("EAN must be 13 digits if provided")
        return value

    @before_event(Insert)
    async def validate_dpp_static(self) -> None:
        """
        Validate links and integrity before inserting a DPPStatic.
        """
        # Manufacturer
        await _resolve_link_or_object(
            self.productManufacturer, Manufacturer, "productManufacturer", f"DPPStatic {self.name}"
        )

        # Responsible operator
        await _resolve_link_or_object(
            self.responsibleOperator, Organisation, "responsibleOperator", f"DPPStatic {self.name}"
        )

        # Importer
        if self.importer:
            await _resolve_link_or_object(self.importer, Importer, "importer", f"DPPStatic {self.name}")

        # Spare parts
        await _validate_and_dedupe_links(self.has_spare_parts, PartStatic, "has_spare_parts", f"DPPStatic {self.name}")

        # Returning places
        await _validate_and_dedupe_links(self.returningPlaces, Place, "returningPlaces", f"DPPStatic {self.name}")

        # MTBF
        if hasattr(self, "expectedMtbfHRS") and self.expectedMtbfHRS < 0:
            msg = f"expectedMtbfHRS must be non-negative for DPPStatic {self.name}"
            logger.error(msg)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    class Settings:
        name = "dpp_static"
        is_root = True
        smart_union = True
        indexes: list = []

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
    )


ImageReference.model_rebuild()
DPPStatic.update_forward_refs()

# ---------------------------------------------------------------------------
# DYNAMIC MODEL
# ---------------------------------------------------------------------------


class DPPInstance(Document):
    """
    Dynamic instance of a DPP, representing a product unit with its lifecycle data.
    """

    id: str = Field(
        default_factory=generate_sgtin_96_number,
        alias="_id",
        serialization_alias="id",
    )

    @field_validator("id")
    @classmethod
    def _validate_sgtin_id(cls, value: str) -> str:
        """SGTIN-96 must be 34 decimal digits."""
        if not _digits_only_with_len(value, 34):
            raise ValueError("ID (SGTIN) must be 34 digits")
        return value

    type_: Literal["DPPInstance"] = Field(default="DPPInstance", alias="type")

    # Links to static DPP and top-level part instance
    dppStaticLink: Link[DPPStatic]
    partInstanceLink: Optional[Link[PartInstance]] = Field(default=None)

    # dates
    minimalValidityOfData: datetime = Field(default_factory=lambda: _utc_now() + timedelta(days=3650))
    dateOfDeclaration: datetime = Field(default_factory=_utc_now)
    endOfGuarantee: datetime = Field(default_factory=lambda: _utc_now() + timedelta(days=730))

    # counters
    currentLocation: Optional[Place] = Field(default=None)
    cleaningCount: float = Field(default=0.0)
    chalkCount: float = Field(default=0.0)
    brewingCount: float = Field(default=0.0)
    coffeeGrindingCount: float = Field(default=0.0)
    operatingHRS: float = Field(default=0.0)
    discontinued: bool = Field(default=False)
    backupLink: str

    @before_event(Insert)
    async def validate_dpp_instance(self) -> None:
        """
        Validate links, counters, and time logic before inserting a DPPInstance.
        """
        # Static DPP link
        await _resolve_link_or_object(self.dppStaticLink, DPPStatic, "dppStaticLink", f"DPPInstance {self.id}")

        # currentLocation must be a Place
        await _validate_current_location(self.currentLocation, f"DPPInstance {self.id}")

        # Counters must be >= 0
        _ensure_non_negative_counters(
            [
                ("cleaningCount", self.cleaningCount),
                ("chalkCount", self.chalkCount),
                ("brewingCount", self.brewingCount),
                ("coffeeGrindingCount", self.coffeeGrindingCount),
                ("operatingHRS", self.operatingHRS),
            ]
        )
        _validate_timeline(self.dateOfDeclaration, self.endOfGuarantee, f"DPPInstance {self.id}")

    class Settings:
        name = "dpp_instance"
        is_root = True
        smart_union = True
        indexes: list = []

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
    )
