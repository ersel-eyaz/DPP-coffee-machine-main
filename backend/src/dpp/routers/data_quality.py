from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from dpp.data_quality.anomaly.outputs import build_anomaly_report
from dpp.data_quality.anomaly.services import analyze_harmonization_result
from dpp.data_quality.harmonization.outputs import build_clean_jsonld, build_harmonization_report
from dpp.data_quality.harmonization.services import harmonize_document


DataQualityScope = Literal["product", "emission", "service"]
DataQualityMode = Literal["harmonization", "anomaly", "both"]


class DataQualityRunRequest(BaseModel):
    scope: DataQualityScope
    mode: DataQualityMode = "both"
    document: Dict[str, Any] = Field(..., description="JSON-LD document to check without storing it in MongoDB.")


router = APIRouter()

EXAMPLE_DOCUMENTS: Dict[str, Dict[str, str]] = {
    "product_dirty": {
        "label": "Product harmonization",
        "scope": "product",
        "path": "harmonization/product_dirty.json",
    },
    "product_anomaly": {
        "label": "Product anomaly",
        "scope": "product",
        "path": "harmonization/product_anomaly_input.json",
    },
    "emission_anomaly": {
        "label": "Emission anomaly",
        "scope": "emission",
        "path": "harmonization/emission_anomaly_input.json",
    },
    "service_text": {
        "label": "Service text",
        "scope": "service",
        "path": "harmonization/service_text_input.json",
    },
    "service_anomaly": {
        "label": "Service anomaly",
        "scope": "service",
        "path": "harmonization/service_anomaly_input.json",
    },
}


def _examples_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "data_quality" / "examples"


@router.get("/examples")
async def list_data_quality_examples() -> Dict[str, Any]:
    examples = [
        {
            "name": name,
            "label": item["label"],
            "scope": item["scope"],
        }
        for name, item in EXAMPLE_DOCUMENTS.items()
    ]
    return {"examples": examples}


@router.get("/examples/{example_name}")
async def get_data_quality_example(example_name: str) -> Dict[str, Any]:
    item = EXAMPLE_DOCUMENTS.get(example_name)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Unknown data-quality example: {example_name}")

    path = _examples_dir() / item["path"]
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not load example: {example_name}") from exc

    return {
        "name": example_name,
        "label": item["label"],
        "scope": item["scope"],
        "document": document,
    }


@router.post("/run")
async def run_data_quality(request: DataQualityRunRequest) -> Dict[str, Any]:
    """
    Run the isolated data-quality layer on an external JSON-LD document.

    This endpoint is intentionally stateless: it does not create or update DPP
    instances and does not write to MongoDB.
    """
    try:
        result = harmonize_document(request.document, request.scope)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Harmonization failed: {exc}") from exc

    payload: Dict[str, Any] = {
        "scope": request.scope,
        "mode": request.mode,
        "data": build_clean_jsonld(result, document=request.document),
        "harmonization_report": build_harmonization_report(result),
        "has_errors": result.has_errors(),
    }

    if request.mode in {"anomaly", "both"}:
        try:
            anomaly_result = analyze_harmonization_result(result)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Anomaly analysis failed: {exc}") from exc

        payload["anomaly_report"] = build_anomaly_report(anomaly_result)
        payload["has_errors"] = result.has_errors() or anomaly_result.has_errors()

    return payload
