# src/dpp/models/organisation.py
"""
Organisation models for the DPP prototype.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal, Union

from beanie import Document, Insert, before_event
from fastapi import HTTPException, status
from pydantic import ConfigDict, Field, field_validator

from dpp.models.constants import generate_gln_number


def _is_digits_of_len(value: str, expected_len: int) -> bool:
    """Return True if `value` contains only digits and has length `expected_len`."""
    return value.isdigit() and len(value) == expected_len


_EORI_DE_REGEX = re.compile(r"^DE\d{10}$")  # 'DE' + 10 digits
_LUCID_DE_REGEX = re.compile(r"^DE\d{20}$")  # 'DE' + 20 digits
_BAG_NUM_REGEX = re.compile(r"^DE-BAG-\d{4}-\d{6}$")  # 'DE-BAG-<YYYY>-<6 digits>'


# ---------------------------------------------------------------------------
# Base organisation
# ---------------------------------------------------------------------------


class Organisation(Document):
    """
    Base class for organisations.
    Subclasses specialize.
    """

    id: str = Field(
        default_factory=generate_gln_number,
        alias="_id",
        serialization_alias="id",
        description="GLN (13 digits); stored as MongoDB _id.",
    )

    @field_validator("id")
    @classmethod
    def _validate_gln(cls, value: str) -> str:
        """GLN must be exactly 13 digits."""
        if not _is_digits_of_len(value, 13):
            raise ValueError("ID (GLN) must be exactly 13 digits")
        return value

    type_: Literal["Organisation"] = Field(default="Organisation", alias="type")

    name: str = Field(..., example="Coffee Roasters Inc.")
    url: str = Field(..., description="Homepage or documentation URL.")

    @field_validator("name", "url")
    @classmethod
    def _strip_nonempty(cls, v: str) -> str:
        value = (v or "").strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("url")
    @classmethod
    def _url_basic_sanity(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("url must start with 'http://' or 'https://'")
        return v

    @before_event(Insert)
    async def _ensure_id_is_unique(self) -> None:
        """
        Provide a error when inserting a duplicate _id.
        """
        if await Organisation.get(self.id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"organisation with id {self.id} already exists",
            )

    class Settings:
        name = "organisation"
        is_root = True
        smart_union = True

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
    )


# ---------------------------------------------------------------------------
# Specialised organisations
# ---------------------------------------------------------------------------


class Manufacturer(Organisation):
    """Represents a manufacturer organisation."""

    type_: Literal["Manufacturer"] = Field(default="Manufacturer", alias="type")
    tradeName: str = Field(..., example="Steelmium")
    eoriNumber: str = Field(..., description="German EORI: 'DE' + 10 digits")
    lucidNumber: str = Field(..., description="German LUCID: 'DE' + 20 digits")

    @field_validator("tradeName")
    @classmethod
    def _trade_name_nonempty(cls, v: str) -> str:
        value = (v or "").strip()
        if not value:
            raise ValueError("tradeName must not be empty")
        return value

    @field_validator("eoriNumber")
    @classmethod
    def _validate_eori(cls, v: str) -> str:
        if not _EORI_DE_REGEX.fullmatch(v or ""):
            raise ValueError("eoriNumber must match 'DE' followed by 10 digits (e.g., 'DE1234567890')")
        return v

    @field_validator("lucidNumber")
    @classmethod
    def _validate_lucid(cls, v: str) -> str:
        if not _LUCID_DE_REGEX.fullmatch(v or ""):
            raise ValueError("lucidNumber must match 'DE' followed by 20 digits")
        return v


class TransportProvider(Organisation):
    """Represents a transport provider organisation."""

    type_: Literal["TransportProvider"] = Field(default="TransportProvider", alias="type")
    transportAuthorityNumber: str = Field(..., description="e.g., 'DE-BAG-2024-123456'")

    @field_validator("transportAuthorityNumber")
    @classmethod
    def _validate_bag_number(cls, v: str) -> str:
        if not _BAG_NUM_REGEX.fullmatch(v or ""):
            raise ValueError("transportAuthorityNumber must match 'DE-BAG-<YYYY>-<6 digits>'")
        return v


class Importer(Organisation):
    """Represents an importer organisation."""

    type_: Literal["Importer"] = Field(default="Importer", alias="type")
    eoriNumber: str = Field(..., description="German EORI: 'DE' + 10 digits")
    lucidNumber: str = Field(..., description="German LUCID: 'DE' + 20 digits")

    @field_validator("eoriNumber")
    @classmethod
    def _validate_eori(cls, v: str) -> str:
        if not _EORI_DE_REGEX.fullmatch(v or ""):
            raise ValueError("eoriNumber must match 'DE' followed by 10 digits (e.g., 'DE1234567890')")
        return v

    @field_validator("lucidNumber")
    @classmethod
    def _validate_lucid(cls, v: str) -> str:
        if not _LUCID_DE_REGEX.fullmatch(v or ""):
            raise ValueError("lucidNumber must match 'DE' followed by 20 digits")
        return v


class ServiceProvider(Organisation):
    """Represents a service provider organisation."""

    type_: Literal["ServiceProvider"] = Field(default="ServiceProvider", alias="type")


# ---------------------------------------------------------------------------
# Discriminated read model
# ---------------------------------------------------------------------------
OrganisationRead = Annotated[
    Union[Manufacturer, Organisation, TransportProvider, Importer, ServiceProvider],
    Field(discriminator="type_"),
]


__all__ = [
    "Organisation",
    "Manufacturer",
    "TransportProvider",
    "Importer",
    "ServiceProvider",
    "OrganisationRead",
]
