# src/dpp/routers/organisation.py
from __future__ import annotations

import logging
from typing import List, Type, TypeVar

from fastapi import APIRouter, HTTPException, status
from pymongo.errors import DuplicateKeyError

from ..models.organisation import Importer, Manufacturer, Organisation, TransportProvider

logger = logging.getLogger(__name__)
router = APIRouter()

T = TypeVar("T")


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


async def _insert_with_handling(doc: T, *, label: str, noun: str) -> T:
    """
    Insert a Beanie document with consistent error handling.
    """
    try:
        await doc.insert()
    except HTTPException:
        raise
    except DuplicateKeyError as err:
        doc_id = getattr(doc, "id", "<unknown>")
        logger.warning("Duplicate %s insert attempt (id=%s)", label, doc_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{label} with id {doc_id} already exists",
        ) from err
    except Exception as error:
        logger.error("Error inserting %s: %s", label, error, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred while creating the {noun}.",
        ) from error

    logger.info("Created %s %s", label, getattr(doc, "id", "<unknown>"))
    return doc


async def _get_or_404(model: Type[T], obj_id: str) -> T:
    """Fetch a Beanie document by id; raise 404 if not found."""
    doc = await model.get(obj_id, fetch_links=True)  # type: ignore[arg-type]
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{model.__name__} not found")
    return doc


# ──────────────────────────────────────────────────────────────────────────────
# Create routes
# ──────────────────────────────────────────────────────────────────────────────


@router.post(
    "/",
    response_model=Organisation,
    status_code=status.HTTP_201_CREATED,
    response_model_by_alias=True,
    summary="Create a new organisation",
)
async def create_organization(organisation: Organisation) -> Organisation:
    """
    Create a new `Organisation`.
    """
    return await _insert_with_handling(organisation, label="Organisation", noun="organisation")


@router.post(
    "/transport",
    response_model=TransportProvider,
    status_code=status.HTTP_201_CREATED,
    response_model_by_alias=True,
    summary="Create a new transport provider",
)
async def create_transport_provider(provider: TransportProvider) -> TransportProvider:
    """
    Create a new `TransportProvider`.
    """
    return await _insert_with_handling(provider, label="TransportProvider", noun="transport provider")


@router.post(
    "/manufacturer",
    response_model=Manufacturer,
    status_code=status.HTTP_201_CREATED,
    response_model_by_alias=True,
    summary="Create a new manufacturer",
)
async def create_manufacturer(manufacturer: Manufacturer) -> Manufacturer:
    """
    Create a new `Manufacturer`.
    """
    return await _insert_with_handling(manufacturer, label="Manufacturer", noun="manufacturer")


@router.post(
    "/importer",
    response_model=Importer,
    status_code=status.HTTP_201_CREATED,
    response_model_by_alias=True,
    summary="Create a new importer",
)
async def create_importer(importer: Importer) -> Importer:
    """
    Create a new `Importer`
    """
    return await _insert_with_handling(importer, label="Importer", noun="importer")


# ──────────────────────────────────────────────────────────────────────────────
# Read routes
# ──────────────────────────────────────────────────────────────────────────────


@router.get(
    "/",
    response_model=List[Organisation],
    response_model_by_alias=True,
    summary="List all organisations",
)
async def list_organisations() -> List[Organisation]:
    """
    List all `Organisation` documents, including subtypes.
    """
    return await Organisation.find_all(fetch_links=True).to_list()


@router.get(
    "/{org_id}",
    response_model=Organisation,
    response_model_by_alias=True,
    summary="Get an organisation by GLN",
)
async def get_organisation(org_id: str) -> Organisation:
    """
    Fetch a single `Organisation` (or subtype).
    """
    return await _get_or_404(Organisation, org_id)
