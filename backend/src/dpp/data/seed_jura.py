# src/dpp/data/seed_dpp_jura_z10.py
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple

import httpx

from dpp.config import API_BASE_URL as BASE_URL
from dpp.models.init import init_db_with_beanie

from ..models.constants import (
    generate_eori_number,
    generate_gln_number,
    generate_lucid_number,
    generate_transport_authority_number,
)
from ..models.dpp import DPPInstance, DPPStatic
from ..models.ghg import (
    ActivityData,
    ActivityType,
    EmissionFactor,
    GHGEmissionRecord,
    GHGScope,
    Scope3Category,
    UnitCode,
)
from ..models.location import Place
from ..models.material import MaterialInstance, MaterialStatic
from ..models.organisation import Importer, Manufacturer, Organisation, OrganisationRead, TransportProvider
from ..models.part import PartInstance, PartStatic
from ..models.processstep import (
    CleaningServiceStep,
    ModeOfTransport,
    ProductionStep,
    RefurbishmentServiceStep,
    RepairServiceStep,
    ReplaceServiceStep,
    TransportReason,
    TransportStep,
)
from ..models.quantitativqualitativvalue import DigitalDocument, QualificationForRepair

logger = logging.getLogger(__name__)

TODAY_FIXED = datetime(2025, 10, 1, tzinfo=timezone.utc)


# --------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------
def _ef_electric(description: str, value_kg_per_kwh: float) -> EmissionFactor:
    return EmissionFactor(description=description, value=value_kg_per_kwh, unit=UnitCode.KG_CO2E_PER_KWH)


def _ef_truck(description: str, value_kg_per_km: float) -> EmissionFactor:
    return EmissionFactor(description=description, value=value_kg_per_km, unit=UnitCode.KG_CO2E_PER_KM)


def _ef_material(description: str, value_kg_per_kg: float) -> EmissionFactor:
    return EmissionFactor(description=description, value=value_kg_per_kg, unit=UnitCode.KG_CO2E_PER_KG)


def ghg_from(
    activity_type: ActivityType,
    qty: float,
    unit: UnitCode,
    ef: EmissionFactor,
    *,
    scope: GHGScope,
    cat: Scope3Category | None = None,
    prov: str | None = None,
) -> GHGEmissionRecord:
    ad = ActivityData(activity_type=activity_type, quantity=qty, unit=unit)
    return GHGEmissionRecord(
        scope=scope,
        scope3_category=cat,
        activity=ad,
        emission_factor=ef,
        emissions_kg_co2e=qty * ef.value,
        calculation_method="activity.quantity * emission_factor.value",
        provenance=prov,
    )


EF_EU_ELECTRIC_2023 = _ef_electric("EU grid electricity ~2023 avg", 0.25)  # kgCO2e/kWh
EF_CH_ELECTRIC = _ef_electric("CH grid electricity (low-carbon mix)", 0.10)
EF_TRUCK_EU = _ef_truck("EU road freight (rigid/van, mixed)", 0.09)  # kgCO2e/km
EF_SEA = _ef_truck("Container ship (per-km proxy per t-km scaled)", 0.015)
EF_GENERIC_PROCESS = _ef_material("Generic process (kg basis)", 0.20)


class PostError(RuntimeError):
    def __init__(self, url: str, status: int, body: str):
        super().__init__(f"POST {url} failed: {status} {body}")
        self.url = url
        self.status = status
        self.body = body


async def post_json(client: httpx.AsyncClient, url: str, payload) -> dict:
    if hasattr(payload, "model_dump_json"):
        r = await client.post(
            url,
            content=payload.model_dump_json(by_alias=True),
            headers={"Content-Type": "application/json"},
        )
    else:
        r = await client.post(url, json=payload)

    if r.status_code >= 400:
        body = (await r.aread()).decode("utf-8", errors="replace")
        logger.error("POST %s failed: %s", url, body)
        raise PostError(url, r.status_code, body)
    return r.json() if r.content else {}


async def create_or_skip_duplicate(client: httpx.AsyncClient, url: str, payload, what: str, obj_id: str | None = None):
    try:
        return await post_json(client, url, payload)
    except PostError as e:
        if e.status == 400 and "already exists" in e.body.lower():
            logger.info("%s %s already exists – skipping create.", what, obj_id or "")
            return None
        raise


# --------------------------------------------------------------------------------------
# Organisations
# --------------------------------------------------------------------------------------
async def make_orgs() -> Tuple[List[OrganisationRead], Dict[str, str]]:
    ids = {
        "jura_de": generate_gln_number(),
        "importer": generate_gln_number(),
        "transport": generate_gln_number(),
        "service_de": generate_gln_number(),
        "recycler": generate_gln_number(),
        "pcb_fab": generate_gln_number(),
        "plastics": generate_gln_number(),
        "metal": generate_gln_number(),
        "valve": generate_gln_number(),
        "magnet": generate_gln_number(),
    }
    orgs: List[OrganisationRead] = [
        Manufacturer(
            id=ids["jura_de"],
            name="JURA Elektrogeräte Vertriebs-GmbH",
            tradeName="JURA",
            eoriNumber=generate_eori_number(),
            lucidNumber=generate_lucid_number(),
            url="https://www.jura.com",
        ),
        Importer(
            id=ids["importer"],
            name="JURA Deutschland Import",
            tradeName="JURA DE Import",
            eoriNumber=generate_eori_number(),
            lucidNumber=generate_lucid_number(),
            url="https://www.jura.com/de",
        ),
        TransportProvider(
            id=ids["transport"],
            name="EuroFreight Logistics",
            transportAuthorityNumber=generate_transport_authority_number(),
            url="https://example.com/logistics.eu",
        ),
        Organisation(id=ids["service_de"], name="JURA Service Center Nürnberg", url="https://www.jura.com/de/service"),
        Organisation(id=ids["recycler"], name="RecycleTech Services", url="https://example.com/recycletech"),
        Manufacturer(
            id=ids["pcb_fab"],
            name="EU PCB Works",
            tradeName="EUPCB",
            eoriNumber=generate_eori_number(),
            lucidNumber=generate_lucid_number(),
            url="https://example.com/eupcb",
        ),
        Manufacturer(
            id=ids["plastics"],
            name="PolyForm Polymers AG",
            tradeName="PolyForm",
            eoriNumber=generate_eori_number(),
            lucidNumber=generate_lucid_number(),
            url="https://example.com/polyform",
        ),
        Manufacturer(
            id=ids["metal"],
            name="EuroSteel & Tubes GmbH",
            tradeName="EuroSteel",
            eoriNumber=generate_eori_number(),
            lucidNumber=generate_lucid_number(),
            url="https://example.com/eurosteel",
        ),
        Manufacturer(
            id=ids["valve"],
            name="ValveTech Europe",
            tradeName="ValveTech",
            eoriNumber=generate_eori_number(),
            lucidNumber=generate_lucid_number(),
            url="https://example.com/valvetech",
        ),
        Manufacturer(
            id=ids["magnet"],
            name="NordMag Rare Earths",
            tradeName="NordMag",
            eoriNumber=generate_eori_number(),
            lucidNumber=generate_lucid_number(),
            url="https://example.com/nordmag",
        ),
    ]
    return orgs, ids


# --------------------------------------------------------------------------------------
# Places
# --------------------------------------------------------------------------------------
async def make_places(org_ids: Dict[str, str]) -> Dict[str, Place]:
    return {
        # Manufacturing & assembly
        "ch_factory": Place(  # Jura HQ/production (CH, Niederbuchsiten region)
            name="JURA Factory (CH)",
            latitude=47.3,
            longitude=7.7,
            country="CH",
            city="Niederbuchsiten",
            postalCode="4626",
            managedBy={"id": org_ids["jura_de"], "collection": "organisation"},
        ),
        "de_distribution": Place(
            name="Distribution Center (DE)",
            latitude=49.4,
            longitude=11.1,
            country="DE",
            city="Nürnberg",
            postalCode="90402",
            managedBy={"id": org_ids["transport"], "collection": "organisation"},
        ),
        "service_center": Place(
            name="JURA Service Center Nürnberg",
            latitude=49.4521,
            longitude=11.0767,
            country="DE",
            city="Nürnberg",
            postalCode="90402",
            managedBy={"id": org_ids["service_de"], "collection": "organisation"},
        ),
        "recycling_facility": Place(
            name="Recycling Facility (DE)",
            latitude=51.23,
            longitude=6.77,
            country="DE",
            city="Düsseldorf",
            postalCode="40213",
            managedBy={"id": org_ids["recycler"], "collection": "organisation"},
        ),
        # Sub-suppliers (generic EU)
        "pcb_fab": Place(
            name="EU PCB Works",
            latitude=48.4,
            longitude=8.9,
            country="DE",
            city="Baden-Württemberg",
            postalCode="70173",
            managedBy={"id": org_ids["pcb_fab"], "collection": "organisation"},
        ),
        "plastics": Place(
            name="PolyForm Plant",
            latitude=48.1,
            longitude=11.6,
            country="DE",
            city="München",
            postalCode="80331",
            managedBy={"id": org_ids["plastics"], "collection": "organisation"},
        ),
        "steel_mill": Place(
            name="EuroSteel Mill",
            latitude=51.5,
            longitude=7.4,
            country="DE",
            city="Dortmund",
            postalCode="44135",
            managedBy={"id": org_ids["metal"], "collection": "organisation"},
        ),
        "valve_plant": Place(
            name="ValveTech Plant",
            latitude=50.1,
            longitude=8.7,
            country="DE",
            city="Frankfurt",
            postalCode="60311",
            managedBy={"id": org_ids["valve"], "collection": "organisation"},
        ),
        "magnet_plant": Place(
            name="NordMag Plant",
            latitude=53.6,
            longitude=10.0,
            country="DE",
            city="Hamburg",
            postalCode="20095",
            managedBy={"id": org_ids["magnet"], "collection": "organisation"},
        ),
    }


# --------------------------------------------------------------------------------------
# Materials (statics)
# --------------------------------------------------------------------------------------
def material_statics(org_ids: Dict[str, str]) -> Dict[str, MaterialStatic]:
    return {
        # Metals
        "martensitic_ss_420": MaterialStatic(
            name="Martensitic Stainless Steel (AISI 420)",
            description="Hardened stainless steel used for conical grinder burrs.",
            materialManufacturer={"id": org_ids["metal"], "collection": "organisation"},
            casNumber=None,  # alloy family; no single CAS
            isoDesignation="X20Cr13 / AISI 420",
            hazardous=False,
            warnings=[],
            rareEarth=False,
        ),
        "stainless_304": MaterialStatic(
            name="Stainless Steel 304",
            description="Corrosion-resistant steel for trays/wands.",
            materialManufacturer={"id": org_ids["metal"], "collection": "organisation"},
            casNumber=None,
            isoDesignation="EN 1.4301 / AISI 304",
            hazardous=False,
            warnings=[],
            rareEarth=False,
        ),
        "aluminum_6061": MaterialStatic(
            name="Aluminum Alloy 6061",
            description="Thermoblock/heater body for rapid heating.",
            materialManufacturer={"id": org_ids["metal"], "collection": "organisation"},
            casNumber="7429-90-5",
            isoDesignation="AA 6061",
            hazardous=False,
            warnings=[],
            rareEarth=False,
        ),
        "copper": MaterialStatic(
            name="Copper (Cu)",
            description="High-conductivity copper for windings, traces.",
            materialManufacturer={"id": org_ids["metal"], "collection": "organisation"},
            casNumber="7440-50-8",
            hazardous=False,
            warnings=[],
            rareEarth=False,
        ),
        "brass": MaterialStatic(
            name="Brass (Cu-Zn)",
            description="Valve body/material for fittings.",
            materialManufacturer={"id": org_ids["valve"], "collection": "organisation"},
            hazardous=False,
            warnings=[],
            rareEarth=False,
        ),
        # Polymers / elastomers
        "pctg_tritan": MaterialStatic(
            name="Copolyester PCTG (BPA-free, Tritan-like)",
            description="BPA-free transparent copolyester for water tanks.",
            materialManufacturer={"id": org_ids["plastics"], "collection": "organisation"},
            casNumber=None,  # copolymer system; monomers have CAS
            hazardous=False,
            warnings=[],
            rareEarth=False,
        ),
        "silicone": MaterialStatic(
            name="Food-grade Silicone (PDMS)",
            description="Hoses and seals in water circuit.",
            materialManufacturer={"id": org_ids["plastics"], "collection": "organisation"},
            casNumber="63231-66-3",
            hazardous=False,
            warnings=[],
            rareEarth=False,
        ),
        "ptfe": MaterialStatic(
            name="PTFE",
            description="Valve/thermoblock gaskets; low friction.",
            materialManufacturer={"id": org_ids["plastics"], "collection": "organisation"},
            casNumber="9002-84-0",
            hazardous=False,
            warnings=[],
            rareEarth=False,
        ),
        "nbr": MaterialStatic(
            name="NBR (Nitrile Rubber)",
            description="O-rings; oil/water resistant.",
            materialManufacturer={"id": org_ids["plastics"], "collection": "organisation"},
            casNumber="9003-18-3",
            hazardous=False,
            warnings=[],
            rareEarth=False,
        ),
        # Electronics
        "fr4": MaterialStatic(
            name="FR-4 laminate (glass-epoxy, brominated FR)",
            description="Printed circuit board base laminate with brominated FR.",
            materialManufacturer={"id": org_ids["pcb_fab"], "collection": "organisation"},
            hazardous=True,
            warnings=["Contains halogenated flame retardants; manage EoL accordingly."],
            rareEarth=False,
        ),
        "solder_sac305": MaterialStatic(
            name="Lead-free solder (SAC305)",
            description="Tin-silver-copper lead-free electronics solder.",
            materialManufacturer={"id": org_ids["pcb_fab"], "collection": "organisation"},
            hazardous=False,
            warnings=[],
            rareEarth=False,
        ),
        # Rare earth
        "ndfeb": MaterialStatic(
            name="NdFeB Magnet",
            description="Neodymium-iron-boron magnet for motor.",
            materialManufacturer={"id": org_ids["magnet"], "collection": "organisation"},
            hazardous=False,
            warnings=[],
            rareEarth=True,
        ),
    }


def mat_inst(
    static: MaterialStatic,
    batch: str,
    grams: float,
    recycled_pct: float,
    purity: float,
    steps: List[ProductionStep | TransportStep],
) -> MaterialInstance:
    return MaterialInstance(
        materialStaticLink={"id": static.id, "collection": "material_static"},
        batchNumber=batch,
        weightGRM=grams,
        percentRecycled=recycled_pct,
        purityLevel=purity,
        materialProcessTracking=steps,
    )


# --------------------------------------------------------------------------------------
# Part statics (Z10 structure)
# --------------------------------------------------------------------------------------
def part_statics(org_ids: Dict[str, str]) -> Dict[str, PartStatic]:
    P: Dict[str, PartStatic] = {}

    def add(key, name, desc, w, mtbf, avv=None, dims=(10, 10, 10)):
        P[key] = PartStatic(
            name=name,
            description=desc,
            partManufacturer={"id": org_ids["jura_de"], "collection": "organisation"},
            heightCM=dims[0],
            widthCM=dims[1],
            depthCM=dims[2],
            weightGRM=w,
            mtbfHRS=mtbf,
            avv_dispose=avv,
        )

    add(
        "machine",
        "JURA Z10 Aluminium Black (EB, 15609)",
        "Premium automatic bean-to-cup with hot & cold extraction; P.R.G. grinder.",
        w=12300,
        mtbf=50000,
        avv="160214",
        dims=(36.3, 32, 47),
    )

    # Major assemblies
    add(
        "housing",
        "Outer Housing",
        "Convex-concave aluminium front + polymer shell",
        3800,
        25000,
        "160214",
        (38, 32, 10),
    )
    add("brew_group", "Brew Group", "Brew unit with piston & chamber (3D brewing)", 1200, 20000, "160214", (15, 12, 12))
    add("drip_tray", "Drip Tray", "Stainless tray & cup grid", 600, 12000, "160214", (3, 25, 20))
    add("waste_bin", "Waste Bin", "Puck container", 350, 10000, "150102", (15, 12, 12))
    add("water_tank", "Water Tank", "2.4 L BPA-free copolyester tank", 700, 15000, "200102", (30, 20, 10))
    add("milk_system", "Milk/Steam System", "HP3 milk system components", 250, 15000, "160214", (10, 10, 10))

    add(
        "grinder",
        "Grinder Module (P.R.G.)",
        "Electronically controlled conical burr grinder",
        900,
        15000,
        "160214",
        (12, 12, 12),
    )
    add("motor", "Grinder Motor", "DC motor with NdFeB rotor magnets", 350, 15000, "160214", (8, 8, 8))
    add("burrs", "Conical Burr Set", "Hardened martensitic stainless steel burrs", 160, 8000, "160214", (3, 3, 3))
    add("gearbox", "Grinder Geartrain", "PA housing + steel gears", 180, 12000, "160214", (6, 6, 6))

    add(
        "water_system",
        "Water System",
        "Pump, flowmeter, thermoblock, valves & hoses",
        1100,
        20000,
        "160214",
        (18, 18, 18),
    )
    add("pump", "Vibration Pump", "Typical 15-bar vibro pump", 350, 12000, "160214", (8, 8, 8))
    add("flowmeter", "Flowmeter", "Turbine flow sensor", 80, 12000, "160214", (5, 5, 5))
    add("thermoblock", "Thermoblock", "Aluminum heater block", 380, 12000, "160214", (10, 10, 6))
    add("solenoid", "3-Way Solenoid Valve", "Brass body, PTFE seals", 120, 12000, "160214", (4, 4, 8))
    add("hoses", "Hoses & Seals", "Silicone hoses, NBR o-rings", 90, 8000, "150102", (10, 10, 5))

    add("electronics", "Main Electronics", "Power/logic boards, sensors, interfaces", 480, 20000, "160214", (20, 15, 3))
    add("main_pcb", "Main PCB", "FR-4 board with SAC305 solder", 180, 20000, "160214", (1, 15, 10))
    add("ui_pcb", "UI PCB", "Display/keys board", 80, 20000, "160214", (1, 12, 8))
    return P


# --------------------------------------------------------------------------------------
# Instance helpers
# --------------------------------------------------------------------------------------
def prod_step(place_id: str, *, grid="EU", kwh: float = 200.0) -> ProductionStep:
    ef = EF_CH_ELECTRIC if grid == "CH" else EF_EU_ELECTRIC_2023
    return ProductionStep(
        description=f"Manufacturing ({grid})",
        processedAt={"id": place_id, "collection": "place"},
        ghgEmissionRecords=[
            ghg_from(
                ActivityType.ELECTRICITY_CONSUMPTION,
                kwh,
                UnitCode.KWH,
                ef,
                scope=GHGScope.SCOPE_2,
                prov=f"assembly-{grid}",
            )
        ],
    )


def road(frm: str, to: str, km: float) -> TransportStep:
    return TransportStep(
        processedAt={"id": frm, "collection": "place"},
        destination={"id": to, "collection": "place"},
        modeOfTransport=ModeOfTransport.ROAD,
        distanceKM=km,
        reasonForTransport=TransportReason.SUPPLY_CHAIN,
        ghgEmissionRecords=[
            ghg_from(
                ActivityType.DISTANCE_TRAVELED,
                km,
                UnitCode.KM,
                EF_TRUCK_EU,
                scope=GHGScope.SCOPE_3,
                cat=Scope3Category.UPSTREAM_TRANSPORTATION_AND_DISTRIBUTION,
                prov="eu-truck",
            )
        ],
    )


def sea(frm: str, to: str, km: float) -> TransportStep:
    return TransportStep(
        processedAt={"id": frm, "collection": "place"},
        destination={"id": to, "collection": "place"},
        modeOfTransport=ModeOfTransport.SEA,
        distanceKM=km,
        reasonForTransport=TransportReason.SUPPLY_CHAIN,
        ghgEmissionRecords=[
            ghg_from(
                ActivityType.DISTANCE_TRAVELED,
                km,
                UnitCode.KM,
                EF_SEA,
                scope=GHGScope.SCOPE_3,
                cat=Scope3Category.UPSTREAM_TRANSPORTATION_AND_DISTRIBUTION,
                prov="sea-ship",
            )
        ],
    )


def part_inst(
    ps: PartStatic, batch: str, steps: List[ProductionStep | TransportStep], *, modular=False
) -> PartInstance:
    return PartInstance(
        partStaticLink={"id": ps.id, "collection": "part_static"},
        batchNumber=batch,
        serialNumber=f"SN-{ps.name}-{uuid.uuid4()}",
        isModular=modular,
        compositeParts=[],
        compositeMaterials=[],
        partProcessTracking=steps,
    )


# --------------------------------------------------------------------------------------
# Build artifacts container
# --------------------------------------------------------------------------------------
@dataclass
class BuildArtifacts:
    minst: Dict[str, MaterialInstance] = field(default_factory=dict)
    leafs: Dict[str, PartInstance] = field(default_factory=dict)
    mid: Dict[str, PartInstance] = field(default_factory=dict)
    machine: PartInstance | None = None
    dpp_static: DPPStatic | None = None
    dpp_instance: DPPInstance | None = None


# --------------------------------------------------------------------------------------
# Registration helpers
# --------------------------------------------------------------------------------------
async def register_orgs(client: httpx.AsyncClient) -> tuple[Dict[str, str], List[OrganisationRead]]:
    orgs, org_ids = await make_orgs()
    for o in orgs:
        ep = "organisation/"
        if isinstance(o, Manufacturer):
            ep += "manufacturer"
        elif isinstance(o, TransportProvider):
            ep += "transport"
        elif isinstance(o, Importer):
            ep += "importer"
        await post_json(client, f"{BASE_URL}/{ep}", o.model_dump(by_alias=True))
    return org_ids, orgs


async def register_places(
    client: httpx.AsyncClient, org_ids: Dict[str, str]
) -> tuple[Dict[str, Place], Dict[str, str]]:
    places = await make_places(org_ids)
    for p in places.values():
        await post_json(client, f"{BASE_URL}/place/", p.model_dump(by_alias=False, exclude_none=True))
    pid = {k: v.id for k, v in places.items()}
    return places, pid


async def register_material_statics(client: httpx.AsyncClient, org_ids: Dict[str, str]) -> Dict[str, MaterialStatic]:
    mstat = material_statics(org_ids)
    for m in mstat.values():
        await post_json(client, f"{BASE_URL}/material/", m.model_dump(by_alias=True))
    return mstat


async def register_part_statics(client: httpx.AsyncClient, org_ids: Dict[str, str]) -> Dict[str, PartStatic]:
    pstat = part_statics(org_ids)
    for ps in pstat.values():
        await post_json(client, f"{BASE_URL}/part/", ps.model_dump(by_alias=True))
    return pstat


# --------------------------------------------------------------------------------------
# Instance build (single EU/CH build with real Z10 static)
# --------------------------------------------------------------------------------------
async def build_instance_z10(
    client: httpx.AsyncClient,
    *,
    org_ids: Dict[str, str],
    places: Dict[str, Place],
    pid: Dict[str, str],
    mstat: Dict[str, MaterialStatic],
    pstat: Dict[str, PartStatic],
) -> BuildArtifacts:
    BA = BuildArtifacts()

    # Materials
    def msteps(origin: str, dest: str, km=250.0, grid="EU", kwh=120.0):
        return [prod_step(origin, grid=grid, kwh=kwh), road(origin, dest, km)]

    BA.minst = {
        "burr_steel": mat_inst(
            mstat["martensitic_ss_420"],
            "BATCH-BURR-420-001",
            160,
            0.0,
            0.99,
            msteps(pid["steel_mill"], pid["ch_factory"], 300.0, grid="EU", kwh=50),
        ),
        "stl_general": mat_inst(
            mstat["stainless_304"],
            "BATCH-SS304-001",
            1400,
            35.0,
            0.995,
            msteps(pid["steel_mill"], pid["ch_factory"], 300.0),
        ),
        "al_block": mat_inst(
            mstat["aluminum_6061"],
            "BATCH-AL-6061-001",
            420,
            15.0,
            0.985,
            msteps(pid["steel_mill"], pid["ch_factory"], 300.0),
        ),
        "copper": mat_inst(
            mstat["copper"], "BATCH-CU-001", 520, 25.0, 0.999, msteps(pid["steel_mill"], pid["ch_factory"], 300.0)
        ),
        "brass": mat_inst(
            mstat["brass"], "BATCH-BR-001", 140, 20.0, 0.985, msteps(pid["valve_plant"], pid["ch_factory"], 300.0)
        ),
        "pctg": mat_inst(
            mstat["pctg_tritan"], "BATCH-PCTG-001", 700, 15.0, 0.99, msteps(pid["plastics"], pid["ch_factory"], 250.0)
        ),
        "sil": mat_inst(
            mstat["silicone"], "BATCH-SIL-001", 120, 10.0, 0.96, msteps(pid["plastics"], pid["ch_factory"], 250.0)
        ),
        "ptfe": mat_inst(
            mstat["ptfe"], "BATCH-PTFE-001", 35, 0.0, 0.9999, msteps(pid["plastics"], pid["ch_factory"], 250.0)
        ),
        "nbr": mat_inst(
            mstat["nbr"], "BATCH-NBR-001", 60, 20.0, 0.95, msteps(pid["plastics"], pid["ch_factory"], 250.0)
        ),
        "fr4": mat_inst(
            mstat["fr4"], "BATCH-FR4-001", 180, 0.0, 0.97, msteps(pid["pcb_fab"], pid["ch_factory"], 350.0)
        ),
        "solder": mat_inst(
            mstat["solder_sac305"], "BATCH-SAC305-001", 22, 0.0, 0.998, msteps(pid["pcb_fab"], pid["ch_factory"], 350.0)
        ),
        "ndfeb": mat_inst(
            mstat["ndfeb"],
            "BATCH-NDFEB-001",
            80,
            0.0,
            0.97,
            msteps(pid["magnet_plant"], pid["ch_factory"], 800.0, grid="EU", kwh=60),
        ),
    }
    for mi in BA.minst.values():
        await post_json(client, f"{BASE_URL}/material/instance/", mi)

    # Leaf parts
    def psteps(origin, dest, *, grid="CH"):
        return [prod_step(origin, grid=grid, kwh=80.0), road(origin, dest, 120.0)]

    BA.leafs = {
        "burrs": part_inst(pstat["burrs"], "BATCH-BURR-001", psteps(pid["ch_factory"], pid["ch_factory"])),
        "motor": part_inst(pstat["motor"], "BATCH-MOTOR-001", psteps(pid["ch_factory"], pid["ch_factory"])),
        "gearbox": part_inst(pstat["gearbox"], "BATCH-GBX-001", psteps(pid["ch_factory"], pid["ch_factory"])),
        "pump": part_inst(pstat["pump"], "BATCH-PUMP-001", psteps(pid["ch_factory"], pid["ch_factory"])),
        "flowmeter": part_inst(pstat["flowmeter"], "BATCH-FM-001", psteps(pid["ch_factory"], pid["ch_factory"])),
        "thermoblock": part_inst(pstat["thermoblock"], "BATCH-TB-001", psteps(pid["ch_factory"], pid["ch_factory"])),
        "solenoid": part_inst(pstat["solenoid"], "BATCH-SOL-001", psteps(pid["valve_plant"], pid["ch_factory"])),
        "hoses": part_inst(pstat["hoses"], "BATCH-HOSE-001", psteps(pid["plastics"], pid["ch_factory"])),
        "main_pcb": part_inst(pstat["main_pcb"], "BATCH-PCB-001", psteps(pid["pcb_fab"], pid["ch_factory"])),
        "ui_pcb": part_inst(pstat["ui_pcb"], "BATCH-UI-001", psteps(pid["pcb_fab"], pid["ch_factory"])),
        "drip_tray": part_inst(pstat["drip_tray"], "BATCH-DRIP-001", psteps(pid["ch_factory"], pid["ch_factory"])),
        "waste_bin": part_inst(pstat["waste_bin"], "BATCH-BIN-001", psteps(pid["ch_factory"], pid["ch_factory"])),
        "water_tank": part_inst(pstat["water_tank"], "BATCH-TANK-001", psteps(pid["plastics"], pid["ch_factory"])),
        "milk_system": part_inst(pstat["milk_system"], "BATCH-MILK-001", psteps(pid["ch_factory"], pid["ch_factory"])),
        "housing": part_inst(pstat["housing"], "BATCH-HOUS-001", psteps(pid["ch_factory"], pid["ch_factory"])),
    }

    # Attach materials
    BA.leafs["burrs"].compositeMaterials.extend([BA.minst["burr_steel"]])
    BA.leafs["motor"].compositeMaterials.extend([BA.minst["copper"], BA.minst["ndfeb"]])
    BA.leafs["gearbox"].compositeMaterials.extend([BA.minst["stl_general"]])
    BA.leafs["pump"].compositeMaterials.extend([BA.minst["brass"], BA.minst["stl_general"], BA.minst["nbr"]])
    BA.leafs["flowmeter"].compositeMaterials.extend([BA.minst["brass"], BA.minst["ptfe"]])
    BA.leafs["thermoblock"].compositeMaterials.extend([BA.minst["al_block"], BA.minst["ptfe"]])
    BA.leafs["solenoid"].compositeMaterials.extend([BA.minst["brass"], BA.minst["ptfe"]])
    BA.leafs["hoses"].compositeMaterials.extend([BA.minst["sil"]])
    BA.leafs["main_pcb"].compositeMaterials.extend([BA.minst["fr4"], BA.minst["solder"], BA.minst["copper"]])
    BA.leafs["ui_pcb"].compositeMaterials.extend([BA.minst["fr4"], BA.minst["solder"]])
    BA.leafs["drip_tray"].compositeMaterials.extend([BA.minst["stl_general"]])
    BA.leafs["waste_bin"].compositeMaterials.extend([BA.minst["stl_general"]])  # cover grid; keep simple
    BA.leafs["water_tank"].compositeMaterials.extend([BA.minst["pctg"]])
    BA.leafs["milk_system"].compositeMaterials.extend([BA.minst["sil"], BA.minst["ptfe"]])
    BA.leafs["housing"].compositeMaterials.extend([BA.minst["stl_general"], BA.minst["pctg"]])

    for pi in BA.leafs.values():
        await post_json(client, f"{BASE_URL}/part/instance/", pi)

    # Mid-level assemblies
    BA.mid["grinder"] = part_inst(
        pstat["grinder"], "BATCH-GRND-001", [prod_step(pid["ch_factory"], grid="CH", kwh=60)], modular=True
    )
    BA.mid["grinder"].compositeParts.extend([BA.leafs["motor"], BA.leafs["burrs"], BA.leafs["gearbox"]])

    BA.mid["water_system"] = part_inst(
        pstat["water_system"], "BATCH-WTR-001", [prod_step(pid["ch_factory"], grid="CH", kwh=50)]
    )
    BA.mid["water_system"].compositeParts.extend(
        [BA.leafs["pump"], BA.leafs["flowmeter"], BA.leafs["thermoblock"], BA.leafs["solenoid"], BA.leafs["hoses"]]
    )

    BA.mid["electronics"] = part_inst(
        pstat["electronics"], "BATCH-EL-001", [prod_step(pid["ch_factory"], grid="CH", kwh=40)]
    )
    BA.mid["electronics"].compositeParts.extend([BA.leafs["main_pcb"], BA.leafs["ui_pcb"]])

    BA.mid["brew_group"] = part_inst(
        pstat["brew_group"], "BATCH-BREW-001", [prod_step(pid["ch_factory"], grid="CH", kwh=40)], modular=True
    )

    for mid in BA.mid.values():
        await post_json(client, f"{BASE_URL}/part/instance/", mid)

    # Root machine
    BA.machine = part_inst(
        pstat["machine"],
        "BATCH-Z10-EB-15609-001",
        [prod_step(pid["ch_factory"], grid="CH", kwh=220), road(pid["ch_factory"], pid["de_distribution"], 400.0)],
    )
    BA.machine.compositeParts.extend(
        [
            BA.leafs["housing"],
            BA.mid["grinder"],
            BA.mid["water_system"],
            BA.mid["electronics"],
            BA.mid["brew_group"],
            BA.leafs["water_tank"],
            BA.leafs["waste_bin"],
            BA.leafs["drip_tray"],
            BA.leafs["milk_system"],
        ]
    )
    await post_json(client, f"{BASE_URL}/part/instance/", BA.machine)

    # DPP Static
    dpp_static = DPPStatic(
        name="JURA Z10 Aluminium Black (EB)",
        description="High-end automatic coffee machine with hot & cold extraction, P.R.G. grinder.",
        EAN="7610917156092",  # EB 15609
        GS1DigitalLink="https://id.gs1.org/01/07610917156092",
        productClass="Automatic coffee machine",
        heightCM=36.3,
        widthCM=32.0,
        depthCM=47.0,  # W×H×D from official specs
        weightGRM=12300,
        dataSheet=DigitalDocument(
            name="Specification Sheet (Z10)",
            url="https://us.jura.com/en/homeproducts/machines/Z10-Diamond-Black-NAA-15464/Specifications",
        ),
        installationOperatingGuide=DigitalDocument(
            name="Instructions for Use (Z10, NA)",
            url="https://us.jura.com/-/media/global/pdf/manuals-na/Home/Z10/download_manual_z10_naa.pdf",
        ),
        ceConformityDeclaration=DigitalDocument(name="CE Declaration", url="https://example.com/ce.pdf"),
        ecodesignConformityDeclaration=DigitalDocument(
            name="Ecodesign Declaration", url="https://example.com/ecodesign.pdf"
        ),
        repairAndServiceManual=DigitalDocument(name="Service Manual", url="https://example.com/service.pdf"),
        DisassemblyInstructions=DigitalDocument(
            name="Disassembly Instructions", url="https://example.com/disassembly.pdf"
        ),
        recyclingEOLInstructions=DigitalDocument(
            name="Recycling Instructions", url="https://example.com/recycling.pdf"
        ),
        guaranteeDescription="2-year guarantee with user maintenance.",
        expectedMtbfHRS=50000,
        taricCode="8516710000",
        weeeRegistrationNumber="WEEE-DE-0000000000",
        responsibleOperator={"id": org_ids["jura_de"], "collection": "organisation"},
        importer={"id": org_ids["importer"], "collection": "organisation"},
        productManufacturer={"id": org_ids["jura_de"], "collection": "organisation"},
        has_spare_parts=[
            {"id": pstat["burrs"].id, "collection": "part_static"},
            {"id": pstat["pump"].id, "collection": "part_static"},
        ],
        toolsForMaintenance=["Torx T10", "Phillips #2", "Pick set", "ESD strap"],
        qualificationForRepair=QualificationForRepair.ENDUSER,
        backupLink="https://example.com/backup",
        returningPlaces=[
            {"id": places["service_center"].id, "collection": "place"},
            {"id": places["recycling_facility"].id, "collection": "place"},
        ],
    )
    dpp_static_resp = await post_json(client, f"{BASE_URL}/dpp/", dpp_static)
    BA.dpp_static = DPPStatic.model_validate(dpp_static_resp)

    # DPP Instance
    BA.dpp_instance = DPPInstance(
        dppStaticLink={"id": BA.dpp_static.id, "collection": "dpp_static"},
        partInstanceLink={"id": BA.machine.id, "collection": "part_instance"},
        dateOfDeclaration=TODAY_FIXED - timedelta(days=730),
        cleaningCount=10,
        chalkCount=4,
        brewingCount=420,
        coffeeGrindingCount=420,
        operatingHRS=7200,
        discontinued=False,
        backupLink="https://example.com/backup",
    )
    dpp_inst_resp = await post_json(client, f"{BASE_URL}/dpp/instance/", BA.dpp_instance)
    BA.dpp_instance = DPPInstance.model_validate(dpp_inst_resp)

    # Sub-component DPPs (Grinder & Main Electronics)
    # -- Grinder
    dpp_grinder_s = DPPStatic(
        name="Z10 Grinder Module (P.R.G.)",
        description="Component-level DPP for electronically controlled conical burr grinder.",
        EAN=generate_gln_number(),
        GS1DigitalLink=f"https://id.gs1.org/01/{generate_gln_number()}",
        productClass="Appliance Component",
        heightCM=12,
        widthCM=12,
        depthCM=12,
        weightGRM=pstat["grinder"].weightGRM,
        dataSheet=DigitalDocument(name="Grinder Module Spec", url="https://www.jura.com"),
        installationOperatingGuide=DigitalDocument(name="Grinder Install Guide", url="https://www.jura.com"),
        ceConformityDeclaration=DigitalDocument(name="CE Declaration", url="https://example.com/ce.pdf"),
        ecodesignConformityDeclaration=DigitalDocument(
            name="Ecodesign Declaration", url="https://example.com/ecodesign.pdf"
        ),
        repairAndServiceManual=DigitalDocument(name="Repair Manual", url="https://example.com/repair.pdf"),
        DisassemblyInstructions=DigitalDocument(name="Disassembly", url="https://example.com/disassembly.pdf"),
        recyclingEOLInstructions=DigitalDocument(name="Recycling", url="https://example.com/recycling.pdf"),
        guaranteeDescription="2-year module warranty.",
        expectedMtbfHRS=pstat["grinder"].mtbfHRS,
        taricCode="8503009900",
        weeeRegistrationNumber="WEEE-DE-0000000001",
        responsibleOperator={"id": org_ids["jura_de"], "collection": "organisation"},
        importer={"id": org_ids["importer"], "collection": "organisation"},
        productManufacturer={"id": org_ids["jura_de"], "collection": "organisation"},
        has_spare_parts=[{"id": pstat["burrs"].id, "collection": "part_static"}],
        toolsForMaintenance=["Torx T10", "Feeler gauge"],
        qualificationForRepair=QualificationForRepair.ENDUSER,
        backupLink="https://example.com/backup",
        returningPlaces=[{"id": places["service_center"].id, "collection": "place"}],
    )
    await create_or_skip_duplicate(client, f"{BASE_URL}/dpp/", dpp_grinder_s, "DPPStatic", dpp_grinder_s.id)
    await create_or_skip_duplicate(
        client,
        f"{BASE_URL}/dpp/instance/",
        DPPInstance(
            dppStaticLink={"id": dpp_grinder_s.id, "collection": "dpp_static"},
            partInstanceLink={"id": BA.mid["grinder"].id, "collection": "part_instance"},
            dateOfDeclaration=TODAY_FIXED - timedelta(days=700),
            backupLink="https://example.com/backup",
        ),
        "DPPInstance",
    )

    # -- Main Electronics
    dpp_elec_s = DPPStatic(
        name="Z10 Main Electronics Module",
        description="Power & logic boards on FR-4 with SAC305 solder.",
        EAN=generate_gln_number(),
        GS1DigitalLink=f"https://id.gs1.org/01/{generate_gln_number()}",
        productClass="Electronics Module",
        heightCM=3,
        widthCM=20,
        depthCM=15,
        weightGRM=pstat["electronics"].weightGRM,
        dataSheet=DigitalDocument(name="Electronics Spec", url="https://www.jura.com"),
        installationOperatingGuide=DigitalDocument(name="Electronics Install Guide", url="https://www.jura.com"),
        ceConformityDeclaration=DigitalDocument(name="CE Declaration", url="https://example.com/ce.pdf"),
        ecodesignConformityDeclaration=DigitalDocument(
            name="Ecodesign Declaration", url="https://example.com/ecodesign.pdf"
        ),
        repairAndServiceManual=DigitalDocument(name="Repair Manual", url="https://example.com/repair.pdf"),
        DisassemblyInstructions=DigitalDocument(name="Disassembly", url="https://example.com/disassembly.pdf"),
        recyclingEOLInstructions=DigitalDocument(name="Recycling", url="https://example.com/recycling.pdf"),
        guaranteeDescription="2-year module warranty.",
        expectedMtbfHRS=pstat["electronics"].mtbfHRS,
        taricCode="8538909900",
        weeeRegistrationNumber="WEEE-DE-0000000002",
        responsibleOperator={"id": org_ids["jura_de"], "collection": "organisation"},
        importer={"id": org_ids["importer"], "collection": "organisation"},
        productManufacturer={"id": org_ids["jura_de"], "collection": "organisation"},
        has_spare_parts=[{"id": pstat["ui_pcb"].id, "collection": "part_static"}],
        toolsForMaintenance=["ESD strap", "Phillips #1", "Hot-air station"],
        qualificationForRepair=QualificationForRepair.ENDUSER,
        backupLink="https://example.com/backup",
        returningPlaces=[{"id": places["service_center"].id, "collection": "place"}],
    )
    await create_or_skip_duplicate(client, f"{BASE_URL}/dpp/", dpp_elec_s, "DPPStatic", dpp_elec_s.id)
    await create_or_skip_duplicate(
        client,
        f"{BASE_URL}/dpp/instance/",
        DPPInstance(
            dppStaticLink={"id": dpp_elec_s.id, "collection": "dpp_static"},
            partInstanceLink={"id": BA.mid["electronics"].id, "collection": "part_instance"},
            dateOfDeclaration=TODAY_FIXED - timedelta(days=690),
            backupLink="https://example.com/backup",
        ),
        "DPPInstance",
    )

    return BA


# --------------------------------------------------------------------------------------
# Services
# --------------------------------------------------------------------------------------
async def add_services(
    client: httpx.AsyncClient, *, BA: BuildArtifacts, places: Dict[str, Place], pstat: Dict[str, PartStatic]
) -> None:
    start = BA.dpp_instance.dateOfDeclaration

    def t(mo, day, h=10):
        base = start + timedelta(days=30 * mo + day)
        return datetime(base.year, base.month, min(28, base.day), h, 0, tzinfo=timezone.utc)

    # Repair
    await post_json(
        client,
        f"{BASE_URL}/dpp/instance/{BA.dpp_instance.id}/service/repair/",
        RepairServiceStep(
            processedAt={"id": places["service_center"].id, "collection": "place"},
            costEur=79.0,
            diagnose="Seal wear in 3-way valve",
            observedSymptoms=["Dripping after brew", "Pressure fluctuations"],
            repairedPartId=BA.leafs["solenoid"].id,
            ghgEmissionRecords=[
                ghg_from(
                    ActivityType.DISTANCE_TRAVELED,
                    10.0,
                    UnitCode.KM,
                    EF_TRUCK_EU,
                    scope=GHGScope.SCOPE_3,
                    cat=Scope3Category.BUSINESS_TRAVEL,
                    prov="van-callout",
                ),
                ghg_from(
                    ActivityType.ELECTRICITY_CONSUMPTION,
                    2.0,
                    UnitCode.KWH,
                    EF_EU_ELECTRIC_2023,
                    scope=GHGScope.SCOPE_2,
                    prov="bench",
                ),
            ],
            beginDate=t(2, 3),
            endDate=t(2, 3, h=12),
        ),
    )
    new_burrs = part_inst(
        pstat["burrs"],
        "BATCH-BURR-REPL-001",
        [
            prod_step(places["ch_factory"].id, grid="CH", kwh=30),
            road(places["ch_factory"].id, places["service_center"].id, 400.0),
        ],
    )
    await post_json(
        client,
        f"{BASE_URL}/dpp/instance/{BA.dpp_instance.id}/service/replace/",
        ReplaceServiceStep(
            processedAt={"id": places["service_center"].id, "collection": "place"},
            costEur=59.0,
            diagnose="Dull burrs",
            observedSymptoms=["Inconsistent grind", "Longer extraction"],
            replacedPartId=BA.leafs["burrs"].id,
            newPart=new_burrs,
            ghgEmissionRecords=[
                ghg_from(
                    ActivityType.ELECTRICITY_CONSUMPTION,
                    1.0,
                    UnitCode.KWH,
                    EF_EU_ELECTRIC_2023,
                    scope=GHGScope.SCOPE_2,
                    prov="rework",
                )
            ],
            beginDate=t(10, 12),
            endDate=t(10, 12, h=11),
        ),
    )
    await post_json(
        client,
        f"{BASE_URL}/dpp/instance/{BA.dpp_instance.id}/service/cleaning/",
        CleaningServiceStep(
            processedAt={"id": places["service_center"].id, "collection": "place"},
            costEur=25.0,
            cleanedPartId=BA.mid["brew_group"].id,
            cleaningMethod="Ultrasonic soak + food-safe grease",
            diagnose="Residue buildup",
            observedSymptoms=["Sticky motion", "Creak noise"],
            ghgEmissionRecords=[
                ghg_from(
                    ActivityType.ELECTRICITY_CONSUMPTION,
                    3.0,
                    UnitCode.KWH,
                    EF_EU_ELECTRIC_2023,
                    scope=GHGScope.SCOPE_2,
                    prov="ultrasonic",
                )
            ],
            beginDate=t(15, 5, h=13),
            endDate=t(15, 5, h=15),
        ),
    )


# --------------------------------------------------------------------------------------
# Optional image upload (if files exist locally)
# --------------------------------------------------------------------------------------
async def upload_images_if_available(client: httpx.AsyncClient, dpp_static: DPPStatic) -> None:
    try:
        image_dir = Path(__file__).resolve().parent / "images"
        filenames = ["jura_1.png", "jura_2.png", "jura_3.png", "jura_4.png"]
        files = [
            ("files", (fn, open(image_dir / fn, "rb"), "image/png")) for fn in filenames if (image_dir / fn).exists()
        ]
        if files:
            r = await client.post(f"{BASE_URL}/dpp/{dpp_static.id}/images/", files=files)
            for _, f in files:
                f[1].close()
            r.raise_for_status()
            logger.info("Uploaded images: %s", r.json())
    except Exception as e:
        logger.warning("Skipping image upload: %s", e)


# --------------------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------------------
async def init():
    """
    Seed JURA Z10 (Aluminium Black, 15609) dataset with component sub-DPPs.
    """
    logger.info("Seeding JURA Z10…")
    await init_db_with_beanie()

    async with httpx.AsyncClient() as client:
        org_ids, _ = await register_orgs(client)
        places, pid = await register_places(client, org_ids)
        mstat = await register_material_statics(client, org_ids)
        pstat = await register_part_statics(client, org_ids)

        build = await build_instance_z10(client, org_ids=org_ids, places=places, pid=pid, mstat=mstat, pstat=pstat)
        await add_services(client, BA=build, places=places, pstat=pstat)
        await upload_images_if_available(client, build.dpp_static)

    logger.info("Seeding JURA Z10 done.")
    return 0
