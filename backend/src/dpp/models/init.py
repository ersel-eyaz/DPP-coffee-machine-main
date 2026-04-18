# src/dpp/models/init.py
"""
Beanie initialization for the DPP prototype.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, List, Sequence, Type

from beanie import init_beanie

from dpp.models.db import mongodb
from dpp.models.dpp import DPPInstance, DPPStatic
from dpp.models.location import Place
from dpp.models.material import MaterialInstance, MaterialStatic
from dpp.models.organisation import (
    Importer,
    Manufacturer,
    Organisation,
    ServiceProvider,
    TransportProvider,
)
from dpp.models.part import PartInstance, PartStatic

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase

_DOCUMENT_MODELS: Sequence[Type] = (
    MaterialStatic,
    MaterialInstance,
    PartStatic,
    PartInstance,
    Organisation,
    Manufacturer,
    TransportProvider,
    Importer,
    ServiceProvider,
    DPPStatic,
    DPPInstance,
    Place,
)


def list_document_models() -> List[Type]:
    """
    Return list of Beanie document models used by the app.
    """
    return list(_DOCUMENT_MODELS)


async def initialize_beanie(
    *,
    database: "AsyncIOMotorDatabase",
    models: Iterable[Type] | None = None,
    allow_index_dropping: bool = True,
) -> None:
    """
    Initialize Beanie with the given database and document models.
    """
    await init_beanie(
        database=database,
        allow_index_dropping=allow_index_dropping,
        document_models=list(models) if models is not None else list_document_models(),
    )


# -----------------------------------------------------------------------------
# Application entrypoint
# -----------------------------------------------------------------------------
async def init_db_with_beanie() -> None:
    """
    Initialize Beanie using
    """
    await initialize_beanie(database=mongodb, allow_index_dropping=True)


__all__ = [
    "init_db_with_beanie",
    "initialize_beanie",
    "list_document_models",
]
