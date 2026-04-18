# src/dpp/routers/jsonld_export.py
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Callable, Dict, Type, TypeVar

from beanie import Link, PydanticObjectId
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

try:
    from bson import ObjectId as BsonObjectId
except Exception:
    BsonObjectId = None


from dpp.jsonld_exporter import (
    export_dpp_instance,
    export_dpp_static,
    export_material_instance,
    export_material_static,
    export_organisation,
    export_part_instance,
    export_part_static,
    export_place,
)
from dpp.models.dpp import DPPInstance, DPPStatic
from dpp.models.location import Place
from dpp.models.material import MaterialInstance, MaterialStatic
from dpp.models.organisation import Organisation
from dpp.models.part import PartInstance, PartStatic

logger = logging.getLogger(__name__)
router = APIRouter()

MEDIA_TYPE = "application/ld+json"
T = TypeVar("T")


def _jsonld_response(payload: Dict[str, Any]) -> JSONResponse:
    """Return payload as JSON-LD with the proper media type."""
    return JSONResponse(content=payload, media_type=MEDIA_TYPE)


async def _get_or_404(model: Type[T], obj_id: str) -> T:
    """Fetch a document with links; raise 404 if it doesn't exist."""
    doc = await model.get(obj_id, fetch_links=True)
    if not doc:
        raise HTTPException(status_code=404, detail=f"{model.__name__} not found")
    return doc


def _export_or_500(exporter: Callable[[Dict[str, Any]], Dict[str, Any]], payload: Dict[str, Any]) -> Dict[str, Any]:
    """Run an exporter and normalize exporter failures to HTTP 500."""
    try:
        return exporter(payload)
    except Exception as e:
        logger.exception("JSON-LD export failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to render JSON-LD") from e


# ---------------------------------------------------------------------------
# deep Link deref
# ---------------------------------------------------------------------------


def _to_jsonable_scalar(x: Any) -> Any:
    """
    Convert non-JSON-native scalars to JSON-safe values.
    - datetime/date -> ISO 8601 string
    - PydanticObjectId / bson.ObjectId -> str
    """
    if isinstance(x, (str, int, float, bool)) or x is None:
        return x
    if isinstance(x, (datetime, date)):
        return x.isoformat()
    if isinstance(x, PydanticObjectId):
        return str(x)
    if BsonObjectId is not None and isinstance(x, BsonObjectId):
        return str(x)
    return x


async def _deep_dump_by_alias(obj: Any) -> Any:
    """
    Recursively convert Beanie/Pydantic models to plain dicts (by_alias),
    **fetching every Link[...]** encountered, and coercing special scalars
    (PydanticObjectId/bson.ObjectId/datetime) into JSON-safe types.

    This keeps exporters pure (no DB I/O) while ensuring deep-nested links
    such as process-step places are fully embedded.
    """
    # 1) Links
    if isinstance(obj, Link):
        try:
            fetched = await obj.fetch()
        except Exception as e:
            logger.warning("Failed to fetch Link target (%s): %s", type(obj), e)
            return None
        return await _deep_dump_by_alias(fetched)

    # 2) Pydantic/Beanie models
    if isinstance(obj, BaseModel):
        out: Dict[str, Any] = {}
        for field_name, field_info in obj.model_fields.items():
            key = getattr(field_info, "serialization_alias", None) or field_info.alias or field_name
            try:
                value = getattr(obj, field_name)
            except AttributeError:
                continue
            out[key] = await _deep_dump_by_alias(value)
        return out

    # 3) Containers
    if isinstance(obj, (list, tuple, set)):
        return [await _deep_dump_by_alias(v) for v in obj]
    if isinstance(obj, dict):
        return {k: await _deep_dump_by_alias(v) for k, v in obj.items()}

    # 4) else
    return _to_jsonable_scalar(obj)


async def _export_doc(
    exporter: Callable[[Dict[str, Any]], Dict[str, Any]],
    document_model: BaseModel,
) -> Dict[str, Any]:
    """
    Resolve nested Links, then feed the plain dict to the exporter.
    """
    payload_deep = await _deep_dump_by_alias(document_model)
    return _export_or_500(exporter, payload_deep)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/organisation/{organisation_id}", response_class=JSONResponse, summary="Organisation as JSON-LD")
async def organisation_jsonld(organisation_id: str) -> JSONResponse:
    org = await _get_or_404(Organisation, organisation_id)
    data = await _export_doc(export_organisation, org)
    return _jsonld_response(data)


@router.get("/place/{place_id}", response_class=JSONResponse, summary="Place as JSON-LD")
async def place_jsonld(place_id: str) -> JSONResponse:
    place = await _get_or_404(Place, place_id)
    data = await _export_doc(export_place, place)
    return _jsonld_response(data)


@router.get("/material/static/{material_id}", response_class=JSONResponse, summary="MaterialStatic as JSON-LD")
async def material_static_jsonld(material_id: str) -> JSONResponse:
    mat = await _get_or_404(MaterialStatic, material_id)
    data = await _export_doc(export_material_static, mat)
    return _jsonld_response(data)


@router.get("/material/instance/{instance_id}", response_class=JSONResponse, summary="MaterialInstance as JSON-LD")
async def material_instance_jsonld(instance_id: str) -> JSONResponse:
    inst = await _get_or_404(MaterialInstance, instance_id)
    data = await _export_doc(export_material_instance, inst)
    return _jsonld_response(data)


@router.get("/part/static/{part_id}", response_class=JSONResponse, summary="PartStatic as JSON-LD")
async def part_static_jsonld(part_id: str) -> JSONResponse:
    part = await _get_or_404(PartStatic, part_id)
    data = await _export_doc(export_part_static, part)
    return _jsonld_response(data)


@router.get("/part/instance/{instance_id}", response_class=JSONResponse, summary="PartInstance as JSON-LD")
async def part_instance_jsonld(instance_id: str) -> JSONResponse:
    inst = await _get_or_404(PartInstance, instance_id)
    data = await _export_doc(export_part_instance, inst)
    return _jsonld_response(data)


@router.get("/dpp/static/{dpp_id}", response_class=JSONResponse, summary="DPPStatic as JSON-LD")
async def dpp_static_jsonld(dpp_id: str) -> JSONResponse:
    dpp = await _get_or_404(DPPStatic, dpp_id)
    data = await _export_doc(export_dpp_static, dpp)
    return _jsonld_response(data)


@router.get("/dpp/instance/{instance_id}", response_class=JSONResponse, summary="DPPInstance as JSON-LD")
async def dpp_instance_jsonld(instance_id: str) -> JSONResponse:
    inst = await _get_or_404(DPPInstance, instance_id)
    data = await _export_doc(export_dpp_instance, inst)
    return _jsonld_response(data)


@router.get(
    "/export/{dpp_id}",
    response_class=JSONResponse,
    summary="Bundle DPPStatic + all associated DPPInstances as JSON-LD (array)",
)
async def export_dpp_and_instances(dpp_id: str) -> JSONResponse:
    """
    Return a JSON-LD array:
        [ export_dpp_static(dppStatic), export_dpp_instance(inst_1), export_dpp_instance(inst_2), ... ]

    """
    dpp_static = await _get_or_404(DPPStatic, dpp_id)
    instances = await DPPInstance.find(
        DPPInstance.dppStaticLink.id == dpp_static.id,  # filter by DBRef
        fetch_links=True,
    ).to_list()
    payload = []
    payload.append(await _export_doc(export_dpp_static, dpp_static))
    for inst in instances:
        payload.append(await _export_doc(export_dpp_instance, inst))
    return JSONResponse(content=payload, media_type=MEDIA_TYPE)


@router.get(
    "/dpp/instance/{instance_id}/download",
    response_class=JSONResponse,
    summary="Download DPPInstance JSON-LD as a file",
)
async def download_dpp_instance_jsonld(instance_id: str) -> JSONResponse:
    inst = await _get_or_404(DPPInstance, instance_id)
    payload = await _export_doc(export_dpp_instance, inst)
    fname = f"dpp-instance-{instance_id}.jsonld"
    return JSONResponse(
        content=payload,
        media_type=MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get(
    "/export/{dpp_id}/download",
    response_class=JSONResponse,
    summary="Download DPPStatic + all its DPPInstances JSON-LD (array) as a file",
)
async def download_dpp_and_instances(dpp_id: str) -> JSONResponse:
    dpp_static = await _get_or_404(DPPStatic, dpp_id)
    instances = await DPPInstance.find(DPPInstance.dppStaticLink.id == dpp_static.id, fetch_links=True).to_list()

    payload: List[Dict[str, Any]] = []
    payload.append(await _export_doc(export_dpp_static, dpp_static))
    for inst in instances:
        payload.append(await _export_doc(export_dpp_instance, inst))

    fname = f"dpp-bundle-{dpp_id}.jsonld"
    return JSONResponse(
        content=payload,
        media_type=MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
