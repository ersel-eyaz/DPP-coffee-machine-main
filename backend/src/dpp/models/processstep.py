# src/dpp/models/processstep.py
"""
Process step models used across the DPP prototype.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Annotated, List, Literal, Optional, Tuple, Union

from beanie import Link
from pydantic import BaseModel, ConfigDict, Field

from .ghg import GHGEmissionRecord
from .location import Place

if TYPE_CHECKING:
    from dpp.models.part import PartInstance


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Base & shared types
# ---------------------------------------------------------------------------


class ProcessStep(BaseModel):
    """
    Base class for lifecycle steps.

    """

    type_: Literal["ProcessStep"] = Field(default="ProcessStep", alias="type")
    beginDate: Optional[datetime] = Field(default_factory=_utc_now)
    endDate: Optional[datetime] = Field(default_factory=_utc_now)
    processedAt: Link[Place]
    ghgEmissionRecords: List[GHGEmissionRecord] = Field(default_factory=list)

    class Settings:
        name = "process_step"
        is_root = True
        smart_union = True

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
    )


class TransportReason(str, Enum):
    SUPPLY_CHAIN = "Supply Chain"
    DISTRIBUTION = "Distribution"
    RETURN = "Return"
    CUSTOMER_DELIVERY = "Customer Delivery"
    OTHER = "Other"


class ModeOfTransport(str, Enum):
    ROAD = "road"
    RAIL = "rail"
    SEA = "sea"
    AIR = "air"


# ---------------------------------------------------------------------------
# Concrete step types
# ---------------------------------------------------------------------------


class ProductionStep(ProcessStep):
    """A manufacturing/assembly operation performed at a place."""

    type_: Literal["ProductionStep"] = Field(default="ProductionStep", alias="type")
    description: str


class TransportStep(ProcessStep):
    """A movement from `processedAt` to `destination` with distance and mode."""

    type_: Literal["TransportStep"] = Field(default="TransportStep", alias="type")
    destination: Link[Place]
    modeOfTransport: ModeOfTransport = Field(default=ModeOfTransport.ROAD)
    distanceKM: float = Field(..., ge=0.0, description="Distance in kilometers (>= 0).")
    reasonForTransport: TransportReason = Field(default=TransportReason.SUPPLY_CHAIN)


class SecondaryValueStep(ProcessStep):
    """
    A service-type step that occurs after initial production
    """

    type_: Literal["SecondaryValueStep"] = Field(default="SecondaryValueStep", alias="type")
    costEur: float = Field(..., ge=0.0, description="Direct cost of the step in EUR (>= 0).")
    diagnose: str = Field(default="", description="Diagnosis captured during the step.")
    observedSymptoms: List[str] = Field(default_factory=list, description="Symptoms observed prior to the step.")
    originalDiagnose: Optional[str] = Field(
        default=None,
        description="Original diagnosis text before optional data-quality harmonization.",
    )
    originalObservedSymptoms: List[str] = Field(
        default_factory=list,
        description="Original observed symptom texts before optional data-quality harmonization.",
    )


class RepairServiceStep(SecondaryValueStep):
    """Repair applied to a nested part within the product tree."""

    type_: Literal["RepairServiceStep"] = Field(default="RepairServiceStep", alias="type")
    repairedPartId: str


class ReplaceServiceStep(SecondaryValueStep):
    """Replacement of a nested part with a new part instance."""

    type_: Literal["ReplaceServiceStep"] = Field(default="ReplaceServiceStep", alias="type")
    replacedPartId: str
    newPart: "PartInstance"


class CleaningServiceStep(SecondaryValueStep):
    """Cleaning performed on a part using a specific method."""

    type_: Literal["CleaningServiceStep"] = Field(default="CleaningServiceStep", alias="type")
    cleanedPartId: str
    cleaningMethod: str = Field(default="", description="Method used for cleaning.")


class RemanufacturingServiceStep(SecondaryValueStep):
    """
    A compound service step that may include multiple repairs/replacements/cleanings.
    """

    type_: Literal["RemanufacturingServiceStep"] = Field(default="RemanufacturingServiceStep", alias="type")
    repairedPartIds: List[str] = Field(default_factory=list)
    replacedAndNewParts: List[Tuple[str, "PartInstance"]] = Field(
        default_factory=list,
        description="Pairs of (replaced_part_id, new_part_instance).",
    )
    cleanedPartIds: List[str] = Field(default_factory=list)


class RefurbishmentServiceStep(SecondaryValueStep):
    """A refurbishment action encompassing various secondary value steps."""

    type_: Literal["RefurbishmentServiceStep"] = Field(default="RefurbishmentServiceStep", alias="type")
    repairedPartIds: List[str] = Field(default_factory=list)
    replacedAndNewParts: List[Tuple[str, "PartInstance"]] = Field(
        default_factory=list,
        description="Pairs of (replaced_part_id, new_part_instance).",
    )
    cleanedPartIds: List[str] = Field(default_factory=list)


class RecyclingStep(SecondaryValueStep):
    """A recycling action (usually moving parts into the detached history)."""

    type_: Literal["RecyclingStep"] = Field(default="RecyclingStep", alias="type")
    reason: str = Field(default="", description="Reason for recycling.")


# ---------------------------------------------------------------------------
# Discriminated union for (de)serialization
# ---------------------------------------------------------------------------

ProcessUnion = Annotated[
    Union[
        ProductionStep,
        TransportStep,
        ProcessStep,
        SecondaryValueStep,
        RepairServiceStep,
        ReplaceServiceStep,
        CleaningServiceStep,
        RemanufacturingServiceStep,
        RefurbishmentServiceStep,
        RecyclingStep,
    ],
    Field(discriminator="type_"),
]


__all__ = [
    "ProcessStep",
    "TransportReason",
    "ModeOfTransport",
    "ProductionStep",
    "TransportStep",
    "SecondaryValueStep",
    "RepairServiceStep",
    "ReplaceServiceStep",
    "CleaningServiceStep",
    "RemanufacturingServiceStep",
    "RefurbishmentServiceStep",
    "RecyclingStep",
    "ProcessUnion",
]
