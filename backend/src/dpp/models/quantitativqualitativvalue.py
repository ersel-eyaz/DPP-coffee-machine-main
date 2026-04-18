# src/dpp/models/quantitativqualitativvalue.py
"""
Helpers for quantitative and qualitative values used across the DPP prototype.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Static / document references
# ---------------------------------------------------------------------------


class DigitalDocument(BaseModel):
    """
    Reference to a digital document (e.g., REACH certificate, service manual).
    """

    name: str = Field(..., example="REACH Certificate")
    url: str = Field(..., example="https://www.example.com/reach-certificate.pdf")
    description: Optional[str] = Field(
        default=None,
        example="REACH certificate for compliance with EU regulations",
    )


class QualificationForRepair(str, Enum):
    """
    Qualification required for performing a repair.
    """

    ENDUSER = "End User"
    SERVICE = "Service Technician"
    COMPANY = "OEM Company"


class QualificationForRepairValue(BaseModel):
    """
    Wrapper to attach the `QualificationForRepair` to an entity.
    """

    propertyID: Literal["QualificationForRepair"] = "QualificationForRepair"
    value: QualificationForRepair


# ---------------------------------------------------------------------------
# Image metadata
# ---------------------------------------------------------------------------


class ImageReference(BaseModel):
    """
    Reference to a file stored in GridFS.
    """

    file_id: PydanticObjectId = Field(..., description="GridFS ObjectId")
    filename: str = Field(..., description="Original filename")

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=lambda x: x,
    )


class ImageMetadata(BaseModel):
    """
    Public-facing image metadata (e.g., for the frontend).
    """

    file_id: str
    filename: str
    url: str


__all__ = [
    "DigitalDocument",
    "QualificationForRepair",
    "QualificationForRepairValue",
    "ImageReference",
    "ImageMetadata",
]
