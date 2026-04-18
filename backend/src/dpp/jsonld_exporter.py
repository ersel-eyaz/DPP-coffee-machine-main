"""
Merged JSON-LD exporters for Organisation(+subclasses), Place, MaterialStatic/Instance,
PartStatic/Instance, ProcessStep (+ subclasses), GHG records, and DPPStatic/Instance.

Design:
- Pure sync: **no DB calls** in here. All inputs should already be fully de-referenced
  (routes should query with `fetch_links=True` and, for trees, pre-expand them).
- One clean `@context` per *top-level* export (Organisation, Place, Material*, Part*, DPP*).
- Nested objects are embedded as full objects (no `@context` duplication), falling back to
  an `{"@id": ...}` *only if* the caller passed a plain ID.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

# ----------------------------
# Shared @context (used once per top-level export)
# ----------------------------
JSONLD_CONTEXT: Dict[str, Any] = {
    "@context": {
        "schema": "https://schema.org/",
        "dpp": "https://example.org/dpp#",
        "name": "schema:name",
        "url": "schema:url",
        "identifier": "schema:identifier",
        "additionalType": "schema:additionalType",
        "address": "schema:address",
        "geo": "schema:geo",
        "latitude": "schema:latitude",
        "longitude": "schema:longitude",
        "managedBy": "dpp:managedBy",
        "isVariantOf": "schema:isVariantOf",
        "hasPart": "schema:hasPart",
        "height": "schema:height",
        "width": "schema:width",
        "depth": "schema:depth",
        "weight": "schema:weight",
        "additionalProperty": "schema:additionalProperty",
        "startTime": "schema:startTime",
        "endTime": "schema:endTime",
        "priceSpecification": "schema:priceSpecification",
        "ghgEmissionRecords": "dpp:ghgEmissionRecords",
        "scope": "dpp:scope",
        "scope3Category": "dpp:scope3Category",
        "activity": "dpp:activity",
        "emissionFactor": "dpp:emissionFactor",
        "emissionsKgCO2e": "dpp:emissionsKgCO2e",
        "calculationMethod": "dpp:calculationMethod",
        "provenance": "dpp:provenance",
        "excludedFromAggregation": "dpp:excludedFromAggregation",
        "destination": "dpp:destination",
        "modeOfTransport": "dpp:modeOfTransport",
        "distanceKM": "dpp:distanceKM",
        "reasonForTransport": "dpp:reasonForTransport",
    }
}


def _iso(v: Any) -> Any:
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def _strip_none(d: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}


def _qv(name: Optional[str], value: Optional[float], unit: Optional[str]) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    node: Dict[str, Any] = {"@type": "schema:QuantitativeValue"}
    if name is not None:
        node["name"] = name
    node["value"] = value
    if unit is not None:
        node["unitCode"] = unit
    return node


def _pv(
    property_id: Optional[str] = None,
    value: Optional[Any] = None,
    name: Optional[str] = None,
    url: Optional[str] = None,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {"@type": "schema:PropertyValue"}
    if property_id is not None:
        out["propertyID"] = property_id
    if name is not None and "propertyID" not in out:
        out["name"] = name
    out["value"] = value
    if url is not None:
        out["url"] = url
    return out


def _with_context(node: Dict[str, Any]) -> Dict[str, Any]:
    return {**JSONLD_CONTEXT, **node}


# ----------------------------
# Organisation (+subtypes)
# ----------------------------
def organisation_node(o: Dict[str, Any]) -> Dict[str, Any]:
    subtype = o.get("type") or o.get("type_")
    return _strip_none(
        {
            "@type": "schema:Organisation",
            "@id": o.get("id"),
            "schema:name": o.get("name"),
            "schema:alternateName": o.get("tradeName"),
            "schema:url": o.get("url"),
            # GLN identifier
            "schema:identifier": _pv("GLN", o.get("id")) if o.get("id") else None,
            # Optional identifiers
            "dpp:eoriNumber": _pv("EORI", o.get("eoriNumber")) if o.get("eoriNumber") else None,
            "dpp:lucidNumber": _pv("LUCID", o.get("lucidNumber")) if o.get("lucidNumber") else None,
            # subtype marker
            "dpp:subtype": subtype,
            "schema:additionalType": f"dpp:{subtype}" if subtype else None,
        }
    )


def export_organisation(o: Dict[str, Any]) -> Dict[str, Any]:
    return _with_context(organisation_node(o))


# ----------------------------
# Place
# ----------------------------


def _place_address(p: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return (
        _strip_none(
            {
                "@type": "schema:PostalAddress",
                "addressCountry": p.get("country"),
                "addressLocality": p.get("city"),
                "postalCode": p.get("postalCode"),
            }
        )
        or None
    )


def _place_geo(p: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return (
        _strip_none(
            {
                "@type": "schema:GeoCoordinates",
                "schema:latitude": p.get("latitude"),
                "schema:longitude": p.get("longitude"),
            }
        )
        or None
    )


def place_node(p: Dict[str, Any]) -> Dict[str, Any]:
    managed_by_raw = p.get("managedBy")
    managed_by_node = organisation_node(managed_by_raw) if isinstance(managed_by_raw, dict) else None
    return _strip_none(
        {
            "@type": "schema:Place",
            "@id": p.get("id"),
            "schema:name": p.get("name"),
            "schema:identifier": _pv("GLN", p.get("id")) if p.get("id") else None,
            "schema:address": _place_address(p),
            "schema:geo": _place_geo(p),
            "dpp:managedBy": managed_by_node,
        }
    )


def export_place(p: Dict[str, Any]) -> Dict[str, Any]:
    return _with_context(place_node(p))


# ----------------------------
# MaterialStatic & MaterialInstance
# ----------------------------


def _doc_node(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not doc:
        return None
    return _strip_none(
        {
            "@type": "schema:CreativeWork",
            "name": doc.get("name"),
            "url": doc.get("url"),
            "description": doc.get("description"),
        }
    )


def material_static_node(m: Dict[str, Any]) -> Dict[str, Any]:
    return _strip_none(
        {
            "@type": "schema:ProductModel",
            "@id": m.get("id"),
            "schema:name": m.get("name"),
            "schema:description": m.get("description"),
            # Fully embed manufacturer
            "schema:manufacturer": organisation_node(m.get("materialManufacturer"))
            if isinstance(m.get("materialManufacturer"), dict)
            else None,
            # PropertyValues
            "dpp:casNumber": _pv("CAS", m.get("casNumber")) if m.get("casNumber") else None,
            "dpp:isoDesignation": _pv("ISO Designation", m.get("isoDesignation")) if m.get("isoDesignation") else None,
            "dpp:eclassClassification": _pv("ECLASS", m.get("eclassClassification"))
            if m.get("eclassClassification")
            else None,
            # Flags
            "dpp:hazardous": m.get("hazardous"),
            "dpp:rareEarth": m.get("rareEarth"),
            "dpp:warnings": m.get("warnings", []),
            # Docs
            "dpp:reachCertification": _doc_node(m.get("reachCertification")),
            "dpp:additionalDocuments": [_doc_node(doc) for doc in m.get("additionalDocuments", []) if doc] or None,
        }
    )


def export_material_static(m: Dict[str, Any]) -> Dict[str, Any]:
    return _with_context(material_static_node(m))


def ghg_activity_node(a: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not a:
        return None
    return _strip_none(
        {
            "@type": "dpp:ActivityData",
            "dpp:activityType": a.get("activity_type"),
            "dpp:quantity": a.get("quantity"),
            "dpp:unit": a.get("unit"),
        }
    )


def ghg_emission_factor_node(f: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not f:
        return None
    return (
        _strip_none(
            {
                "@type": "dpp:EmissionFactor",
                "dpp:description": f.get("description"),
                "dpp:value": f.get("value"),
                "dpp:unit": f.get("unit"),
                "dpp:technology": f.get("technology"),
            }
        )
        or None
    )


def ghg_record_node(r: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not r:
        return None
    return _strip_none(
        {
            "@type": "dpp:GHGEmissionRecord",
            "dpp:scope": r.get("scope"),
            "dpp:scope3Category": r.get("scope3_category"),
            "dpp:activity": ghg_activity_node(r.get("activity")),
            "dpp:emissionFactor": ghg_emission_factor_node(r.get("emission_factor")),
            "dpp:emissionsKgCO2e": r.get("emissions_kg_co2e"),
            "dpp:calculationMethod": r.get("calculation_method"),
            "dpp:provenance": r.get("provenance"),
            "dpp:excludedFromAggregation": r.get("excluded_from_aggregation"),
        }
    )


def process_step_node(s: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not s:
        return None
    raw_type = s.get("type") or s.get("type_")
    type_map = {
        "ProductionStep": "schema:ManufactureAction",
        "TransportStep": "schema:TransferAction",
        "RepairServiceStep": "schema:RepairAction",
        "CleaningServiceStep": "schema:CleanAction",
        "ReplaceServiceStep": "schema:UpdateAction",
        "RefurbishmentServiceStep": "schema:UpdateAction",
        "RemanufacturingServiceStep": "schema:UpdateAction",
        "RecyclingStep": "dpp:RecyclingStep",
        "SecondaryValueStep": "dpp:SecondaryValueStep",
        "ProcessStep": "dpp:ProcessStep",
    }
    mapped = type_map.get(raw_type, f"dpp:{raw_type}" if raw_type else "dpp:ProcessStep")

    node: Dict[str, Any] = _strip_none(
        {
            "@type": mapped,
            "dpp:stepType": raw_type,
            "startTime": _iso(s.get("beginDate")),
            "endTime": _iso(s.get("endDate")),
            "location": place_node(s.get("processedAt")) if isinstance(s.get("processedAt"), dict) else None,
        }
    )

    if raw_type == "TransportStep":
        if isinstance(s.get("destination"), dict):
            node["dpp:destination"] = place_node(s.get("destination"))
        if s.get("modeOfTransport"):
            node["dpp:modeOfTransport"] = s.get("modeOfTransport")
        if s.get("distanceKM") is not None:
            node["dpp:distanceKM"] = _qv("distanceKM", s.get("distanceKM"), "KM")
        if s.get("reasonForTransport"):
            node["dpp:reasonForTransport"] = s.get("reasonForTransport")

    if raw_type in {
        "SecondaryValueStep",
        "RepairServiceStep",
        "ReplaceServiceStep",
        "CleaningServiceStep",
        "RefurbishmentServiceStep",
        "RemanufacturingServiceStep",
        "RecyclingStep",
    }:
        if s.get("costEur") is not None:
            node["priceSpecification"] = {
                "@type": "schema:PriceSpecification",
                "schema:price": float(s.get("costEur")),
                "schema:priceCurrency": "EUR",
            }
        if s.get("diagnose"):
            node["dpp:diagnose"] = s.get("diagnose")
        if s.get("observedSymptoms"):
            node["dpp:observedSymptoms"] = s.get("observedSymptoms")
        if raw_type == "RepairServiceStep" and s.get("repairedPartId"):
            node["dpp:repairedPartId"] = s.get("repairedPartId")
        if raw_type == "ReplaceServiceStep":
            if s.get("replacedPartId"):
                node["dpp:replacedPartId"] = s.get("replacedPartId")
            if s.get("newPart") is not None:
                new_part = s.get("newPart")
                node["dpp:newPart"] = part_instance_node(new_part) if isinstance(new_part, dict) else {"@id": new_part}
        if raw_type in {"RefurbishmentServiceStep", "RemanufacturingServiceStep"}:
            if s.get("repairedPartIds"):
                node["dpp:repairedPartIds"] = s.get("repairedPartIds")
            if s.get("replacedAndNewParts"):
                pairs: List[List[Any]] = []
                for pair in s.get("replacedAndNewParts"):
                    if isinstance(pair, (list, tuple)) and len(pair) == 2:
                        old_id, new_part = pair
                        pairs.append(
                            [old_id, part_instance_node(new_part) if isinstance(new_part, dict) else {"@id": new_part}]
                        )
                if pairs:
                    node["dpp:replacedAndNewParts"] = pairs
            if s.get("cleanedPartIds"):
                node["dpp:cleanedPartIds"] = s.get("cleanedPartIds")
        if raw_type == "RecyclingStep" and s.get("reason"):
            node["dpp:reason"] = s.get("reason")

    if s.get("ghgEmissionRecords"):
        records = [ghg_record_node(r) for r in s.get("ghgEmissionRecords", []) if r]
        node["dpp:ghgEmissionRecords"] = [r for r in records if r]

    return _strip_none(node)


# ----------------------------
# MaterialInstance (incl. process tracking)
# ----------------------------


def material_instance_node(mi: Dict[str, Any]) -> Dict[str, Any]:
    tracking = [process_step_node(s) for s in mi.get("materialProcessTracking", [])]
    tracking = [t for t in tracking if t]
    return _strip_none(
        {
            "@type": "schema:Product",
            "@id": mi.get("id"),
            # Fully inline MaterialStatic when provided as dict
            "isVariantOf": material_static_node(mi.get("materialStaticLink"))
            if isinstance(mi.get("materialStaticLink"), dict)
            else None,
            "dpp:batchNumber": mi.get("batchNumber"),
            "schema:weight": _qv("weight", mi.get("weightGRM"), "GRM"),
            "additionalProperty": [
                {"@type": "schema:PropertyValue", "name": "percentRecycled", "value": mi.get("percentRecycled")}
            ],
            "dpp:materialProcessTracking": tracking or None,
        }
    )


def export_material_instance(mi: Dict[str, Any]) -> Dict[str, Any]:
    return _with_context(material_instance_node(mi))


# ----------------------------
# PartStatic & PartInstance
# ----------------------------


def part_static_node(p: Dict[str, Any]) -> Dict[str, Any]:
    return _strip_none(
        {
            "@type": "schema:ProductModel",
            "@id": p.get("id"),
            "schema:name": p.get("name"),
            "schema:description": p.get("description"),
            "schema:manufacturer": organisation_node(p.get("partManufacturer"))
            if isinstance(p.get("partManufacturer"), dict)
            else None,
            "schema:height": _qv("height", p.get("heightCM"), "CM"),
            "schema:width": _qv("width", p.get("widthCM"), "CM"),
            "schema:depth": _qv("depth", p.get("depthCM"), "CM"),
            "schema:weight": _qv("weight", p.get("weightGRM"), "GRM"),
            "dpp:avvDispose": _pv("AVV", p.get("avv_dispose")) if p.get("avv_dispose") else None,
            "dpp:mtbf": _qv("MTBF", p.get("mtbfHRS"), "HRS"),
        }
    )


def part_instance_node(pi: Dict[str, Any]) -> Dict[str, Any]:
    # Recursively inline nested parts & materials when given as dicts
    composite_parts = [
        part_instance_node(c) if isinstance(c, dict) else {"@id": c} for c in pi.get("compositeParts", [])
    ]
    detached_parts = [
        part_instance_node(c) if isinstance(c, dict) else {"@id": c} for c in pi.get("historyOfDetachedParts", [])
    ]
    composite_materials = [
        material_instance_node(m) if isinstance(m, dict) else {"@id": m} for m in pi.get("compositeMaterials", [])
    ]
    part_tracking = [process_step_node(s) for s in pi.get("partProcessTracking", [])]
    part_tracking = [t for t in part_tracking if t]

    return _strip_none(
        {
            "@type": "schema:Product",
            "@id": pi.get("id"),
            "isVariantOf": part_static_node(pi.get("partStaticLink"))
            if isinstance(pi.get("partStaticLink"), dict)
            else None,
            "schema:serialNumber": pi.get("serialNumber"),
            "dpp:batchNumber": pi.get("batchNumber"),
            "dpp:isModular": pi.get("isModular"),
            "dpp:hasFailstate": pi.get("hasFailstate"),
            "dpp:compositeParts": composite_parts or None,
            "dpp:historyOfDetachedParts": detached_parts or None,
            "dpp:compositeMaterials": composite_materials or None,
            "dpp:partProcessTracking": part_tracking or None,
        }
    )


def export_part_static(p: Dict[str, Any]) -> Dict[str, Any]:
    return _with_context(part_static_node(p))


def export_part_instance(p: Dict[str, Any]) -> Dict[str, Any]:
    return _with_context(part_instance_node(p))


# ----------------------------
# DPPStatic & DPPInstance
# ----------------------------


def _creative_work(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not doc:
        return None
    out: Dict[str, Any] = {"@type": "schema:CreativeWork"}
    if doc.get("name") is not None:
        out["name"] = doc.get("name")
    if doc.get("url") is not None:
        out["url"] = doc.get("url")
    if doc.get("description") is not None:
        out["description"] = doc.get("description")
    return out if len(out) > 1 else None


def dpp_static_node(d: Dict[str, Any]) -> Dict[str, Any]:
    # Inline spare parts & returning places when dicts are provided
    spare_parts = [part_static_node(p) if isinstance(p, dict) else {"@id": p} for p in d.get("has_spare_parts", [])]
    returning_places = [place_node(p) if isinstance(p, dict) else {"@id": p} for p in d.get("returningPlaces", [])]

    node: Dict[str, Any] = _strip_none(
        {
            "@type": "schema:ProductModel",
            "@id": d.get("id"),
            "schema:name": d.get("name"),
            "schema:description": d.get("description"),
            # Identifiers
            "dpp:EAN": d.get("EAN"),
            "dpp:GS1DigitalLink": _pv("GS1DigitalLink", d.get("GS1DigitalLink"), url=d.get("GS1DigitalLink"))
            if d.get("GS1DigitalLink")
            else None,
            # Category & dimensions
            "schema:category": d.get("productClass"),
            "schema:height": _qv("height", d.get("heightCM"), "CM"),
            "schema:width": _qv("width", d.get("widthCM"), "CM"),
            "schema:depth": _qv("depth", d.get("depthCM"), "CM"),
            "schema:weight": _qv("weight", d.get("weightGRM"), "GRM"),
            # Publication & guarantee/tariff
            "schema:datePublished": _iso(d.get("dateOfPublication")),
            "dpp:guaranteeDescription": {"@type": "schema:CreativeWork", "name": d.get("guaranteeDescription")}
            if d.get("guaranteeDescription") is not None
            else None,
            "dpp:taricCode": d.get("taricCode"),
            # Orgs
            "schema:manufacturer": organisation_node(d.get("productManufacturer"))
            if isinstance(d.get("productManufacturer"), dict)
            else None,
            "dpp:responsibleOperator": organisation_node(d.get("responsibleOperator"))
            if isinstance(d.get("responsibleOperator"), dict)
            else None,
            "dpp:importer": organisation_node(d.get("importer")) if isinstance(d.get("importer"), dict) else None,
            # MTBF expected
            "dpp:expectedMtbfHRS": _qv("expectedMtbfHRS", d.get("expectedMtbfHRS"), "HRS"),
            # Documents
            "dpp:dataSheet": _creative_work(d.get("dataSheet")),
            "dpp:installationOperatingGuide": _creative_work(d.get("installationOperatingGuide")),
            "dpp:ceConformityDeclaration": _creative_work(d.get("ceConformityDeclaration")),
            "dpp:ecodesignConformityDeclaration": _creative_work(d.get("ecodesignConformityDeclaration")),
            "dpp:repairAndServiceManual": _creative_work(d.get("repairAndServiceManual")),
            "dpp:DisassemblyInstructions": _creative_work(d.get("DisassemblyInstructions")),
            "dpp:recyclingEOLInstructions": _creative_work(d.get("recyclingEOLInstructions")),
            # Spares & returns
            "dpp:has_spare_parts": spare_parts or None,
            "dpp:returningPlaces": returning_places or None,
            # Misc
            "dpp:toolsForMaintenance": d.get("toolsForMaintenance", []) or None,
            "dpp:qualificationForRepair": _pv("QualificationForRepair", d.get("qualificationForRepair"))
            if d.get("qualificationForRepair") is not None
            else None,
            "dpp:weeeRegistrationNumber": _pv("WEEE", d.get("weeeRegistrationNumber"))
            if d.get("weeeRegistrationNumber") is not None
            else None,
            "dpp:backupLink": _pv("BackupLink", d.get("backupLink"), url=d.get("backupLink"))
            if d.get("backupLink")
            else None,
            "dpp:imageFileIds": d.get("image_file_ids", []) or None,
        }
    )
    return node


def dpp_instance_node(inst: Dict[str, Any]) -> Dict[str, Any]:
    # Counters as additionalProperty
    additional: List[Dict[str, Any]] = []
    for name, unit in (
        ("cleaningCount", None),
        ("chalkCount", None),
        ("brewingCount", None),
        ("coffeeGrindingCount", None),
        ("operatingHRS", "HRS"),
    ):
        if name in inst and inst.get(name) is not None:
            pv = {"@type": "schema:PropertyValue", "name": name, "value": inst.get(name)}
            if unit:
                pv["unitCode"] = unit
            additional.append(pv)

    node: Dict[str, Any] = _strip_none(
        {
            "@type": "schema:Product",
            "@id": inst.get("id"),
            # Keep SGTIN as PropertyValue
            "dpp:SGTIN": _pv("SGTIN", inst.get("id")) if inst.get("id") else None,
            # Link to static DPP
            "isVariantOf": dpp_static_node(inst.get("dppStaticLink"))
            if isinstance(inst.get("dppStaticLink"), dict)
            else None,
            # Dates
            "dpp:minimalValidityOfData": _iso(inst.get("minimalValidityOfData")),
            "dpp:dateOfDeclaration": _iso(inst.get("dateOfDeclaration")),
            "dpp:endOfGuarantee": _iso(inst.get("endOfGuarantee")),
            # Location
            "schema:location": place_node(inst.get("currentLocation"))
            if isinstance(inst.get("currentLocation"), dict)
            else None,
            # Additional counters
            "schema:additionalProperty": additional or None,
            # Flags / backup
            "dpp:discontinued": inst.get("discontinued", False),
            "dpp:backupLink": _pv("BackupLink", inst.get("backupLink"), url=inst.get("backupLink"))
            if inst.get("backupLink")
            else None,
            # Has part (the full product part tree)
            "schema:hasPart": part_instance_node(inst.get("partInstanceLink"))
            if isinstance(inst.get("partInstanceLink"), dict)
            else None,
        }
    )
    return node


def export_dpp_static(d: Dict[str, Any]) -> Dict[str, Any]:
    return _with_context(dpp_static_node(d))


def export_dpp_instance(d: Dict[str, Any]) -> Dict[str, Any]:
    return _with_context(dpp_instance_node(d))


__all__ = [
    # Nodes (no @context)
    "organisation_node",
    "place_node",
    "material_static_node",
    "material_instance_node",
    "part_static_node",
    "part_instance_node",
    "dpp_static_node",
    "dpp_instance_node",
    "process_step_node",
    "ghg_record_node",
    # Top-level exporters (with @context)
    "export_organisation",
    "export_place",
    "export_material_static",
    "export_material_instance",
    "export_part_static",
    "export_part_instance",
    "export_dpp_static",
    "export_dpp_instance",
    # Shared context
    "JSONLD_CONTEXT",
]
