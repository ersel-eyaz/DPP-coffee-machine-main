# src/dpp/models/location.py
"""
Location models for the DPP prototype.
"""

from __future__ import annotations

from typing import Optional

from beanie import Document, Insert, Link, before_event
from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from dpp.models.constants import generate_gln_number
from dpp.models.organisation import Organisation

# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


class ReturningPlaceSummary(BaseModel):
    """Compact representation of a place used by returning-places endpoints."""

    id: Optional[str] = None
    name: Optional[str] = None
    gln: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_digits_of_len(value: str, expected: int) -> bool:
    """True if `value` is composed only of digits and has expected length."""
    return value.isdigit() and len(value) == expected


async def _resolve_org(link: Link[Organisation] | Organisation, place_label: str) -> Organisation:
    """
    Resolve an Organisation Link
    """
    org = await link.fetch() if isinstance(link, Link) else link
    if org is None or not isinstance(org, Organisation):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Linked Organisation for Place {place_label} does not exist",
        )
    return org


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


class Place(Document):
    """
    Represents a physical place of an Organisation.
    """

    id: str = Field(
        default_factory=generate_gln_number,
        alias="_id",
        serialization_alias="id",
        description="GLN (13 digits); stored as MongoDB _id.",
    )

    name: str = Field(..., example="Berlin Headquarters")
    latitude: float = Field(..., ge=-90.0, le=90.0, example=52.5200)
    longitude: float = Field(..., ge=-180.0, le=180.0, example=13.4050)
    country: str = Field(..., min_length=2, max_length=3, example="DE")
    city: str = Field(..., example="Berlin")
    postalCode: str = Field(..., example="10115")
    managedBy: Link[Organisation] = Field(..., description="Owning/operating organisation.")

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
    )

    class Settings:
        name = "place"

    # ----------------------------
    # Validators & lifecycle hooks
    # ----------------------------

    @field_validator("id")
    @classmethod
    def _validate_gln_id(cls, value: str) -> str:
        """GLN must be exactly 13 digits."""
        if not _is_digits_of_len(value, 13):
            raise ValueError("ID (GLN) must be exactly 13 digits")
        return value

    @field_validator("country")
    @classmethod
    def _norm_country(cls, value: str) -> str:
        """Normalize country code to uppercase"""
        v = (value or "").strip().upper()
        if not (2 <= len(v) <= 3):
            raise ValueError("country must be a 2–3 character country code")
        return v

    @field_validator("name", "city", "postalCode")
    @classmethod
    def _strip_nonempty(cls, value: str) -> str:
        v = (value or "").strip()
        if not v:
            raise ValueError("must not be empty")
        return v

    @before_event(Insert)
    async def _ensure_unique_and_valid(self) -> None:
        """
        Ensure the GLN is unique
        """
        existing = await Place.get(self.id)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Place with ID (GLN) {self.id} already exists",
            )

        # Validate organisation link
        await _resolve_org(self.managedBy, self.name)


__all__ = [
    "ReturningPlaceSummary",
    "Place",
]
