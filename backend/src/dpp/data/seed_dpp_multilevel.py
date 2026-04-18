# /data/seed_dpp_multilevel.py
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple

import httpx

from dpp.config import API_BASE_URL as BASE_URL

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
from ..models.init import init_db_with_beanie
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

# Fixed “today” per request: 08 August 2025 (UTC)
TODAY_FIXED = datetime(2025, 8, 8, tzinfo=timezone.utc)


# -----------------------------
# Helpers
# -----------------------------
def ghg(step: str, qty: float, *, scope=GHGScope.SCOPE_3, cat: Scope3Category | None = None) -> GHGEmissionRecord:
    """Tiny helper to create a simple GHGEmissionRecord (kept for the first instance)."""
    if step == "production":
        ef = EmissionFactor(description="EU electricity avg", value=0.35, unit=UnitCode.KG_CO2E_PER_KWH)
        ad = ActivityData(
            activity_type=ActivityType.ELECTRICITY_CONSUMPTION, quantity=max(1.0, qty * 5), unit=UnitCode.KWH
        )
        scope = GHGScope.SCOPE_2
    elif step == "transport-road":
        ef = EmissionFactor(description="Truck EU avg", value=0.1, unit=UnitCode.KG_CO2E_PER_KM)
        ad = ActivityData(activity_type=ActivityType.DISTANCE_TRAVELED, quantity=max(1.0, qty * 150), unit=UnitCode.KM)
        cat = Scope3Category.UPSTREAM_TRANSPORTATION_AND_DISTRIBUTION
    elif step == "transport-air":
        ef = EmissionFactor(description="Air freight avg", value=0.6, unit=UnitCode.KG_CO2E_PER_KM)
        ad = ActivityData(activity_type=ActivityType.DISTANCE_TRAVELED, quantity=max(1.0, qty * 500), unit=UnitCode.KM)
        cat = Scope3Category.UPSTREAM_TRANSPORTATION_AND_DISTRIBUTION
    else:
        ef = EmissionFactor(description=f"{step} generic", value=0.2, unit=UnitCode.KG_CO2E_PER_KG)
        ad = ActivityData(activity_type=ActivityType.MATERIAL_PURCHASE, quantity=max(0.1, qty), unit=UnitCode.KG)
    return GHGEmissionRecord(
        scope=scope,
        scope3_category=cat,
        activity=ad,
        emission_factor=ef,
        emissions_kg_co2e=ad.quantity * ef.value,
        calculation_method="activity.quantity * factor.value",
        provenance=step,
    )


def ghg_mix(records: List[tuple]) -> List[GHGEmissionRecord]:
    """
    Create a list of GHGEmissionRecord with richer coverage.
    Each record tuple:
      (scope, scope3_category_or_None, activity_type, quantity, unit, factor_value, factor_unit, description, provenance)
    """
    out: List[GHGEmissionRecord] = []
    for scope, cat, atype, qty, unit, fval, funit, desc, prov in records:
        ad = ActivityData(activity_type=atype, quantity=qty, unit=unit)
        ef = EmissionFactor(description=desc, value=fval, unit=funit)
        out.append(
            GHGEmissionRecord(
                scope=scope,
                scope3_category=cat,
                activity=ad,
                emission_factor=ef,
                emissions_kg_co2e=qty * fval,
                calculation_method="activity.quantity * factor.value",
                provenance=prov,
            )
        )
    return out


class PostError(RuntimeError):
    def __init__(self, url: str, status: int, body: str):
        super().__init__(f"POST {url} failed: {status} {body}")
        self.url = url
        self.status = status
        self.body = body


async def post_json(client: httpx.AsyncClient, url: str, payload) -> dict:
    """
    POST JSON and raise on 4xx/5xx. Never return an error JSON.
    Accepts plain dicts or Pydantic models.
    """
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


async def create_or_skip_duplicate(
    client: httpx.AsyncClient,
    url: str,
    payload,
    what: str,
    obj_id: str | None = None,
) -> dict | None:
    """
    Create once; if the API returns a 400 "already exists", log and continue.
    """
    try:
        return await post_json(client, url, payload)
    except PostError as e:
        if e.status == 400 and "already exists" in e.body:
            logger.info("%s %s already exists – skipping create.", what, obj_id or "")
            return None
        raise


_posted_dpp_static_ids: set[str] = set()


async def create_dpp_static_once(client: httpx.AsyncClient, dpp_static) -> None:
    if dpp_static.id in _posted_dpp_static_ids:
        logger.info("DPPStatic %s already posted in this run – skipping.", dpp_static.id)
        return
    await create_or_skip_duplicate(client, f"{BASE_URL}/dpp/", dpp_static, what="DPPStatic", obj_id=dpp_static.id)
    _posted_dpp_static_ids.add(dpp_static.id)


def spread_dates(start: datetime, end: datetime, n: int) -> List[datetime]:
    """
    Evenly distribute n timestamps strictly between start and end (not including endpoints).
    """
    if n <= 0:
        return []
    total_seconds = (end - start).total_seconds()
    step = total_seconds / (n + 1)
    return [start + timedelta(seconds=step * (i + 1)) for i in range(n)]


# -----------------------------
# 1) Organisations
# -----------------------------
async def make_orgs() -> Tuple[List[OrganisationRead], Dict[str, str]]:
    ids = {
        k: generate_gln_number()
        for k in [
            "metal_supplier",
            "plastics_supplier",
            "pcb_fab",
            "magnet_supplier",
            "valve_supplier",
            "machine_manu",
            "importer",
            "transport",
            "service",
            "recycler",
            "asia_metal",
            "asia_plastics",
            "asia_pcb",
            "asia_magnet",
            "asia_valve",
            "ocean_carrier",
            "eu_assembler",
            "eu_service_2",
        ]
    }
    orgs: List[OrganisationRead] = [
        Manufacturer(
            id=ids["metal_supplier"],
            name="EuroSteel & Tubes GmbH",
            tradeName="EuroSteel",
            eoriNumber=generate_eori_number(),
            lucidNumber=generate_lucid_number(),
            url="https://example.com/eurosteel",
        ),
        Manufacturer(
            id=ids["plastics_supplier"],
            name="PolyForm Polymers AG",
            tradeName="PolyForm",
            eoriNumber=generate_eori_number(),
            lucidNumber=generate_lucid_number(),
            url="https://example.com/polyform",
        ),
        Manufacturer(
            id=ids["pcb_fab"],
            name="Bavaria PCB Works",
            tradeName="BavPCB",
            eoriNumber=generate_eori_number(),
            lucidNumber=generate_lucid_number(),
            url="https://example.com/bavpcb",
        ),
        Manufacturer(
            id=ids["magnet_supplier"],
            name="NordMag Rare Earths",
            tradeName="NordMag",
            eoriNumber=generate_eori_number(),
            lucidNumber=generate_lucid_number(),
            url="https://example.com/nordmag",
        ),
        Manufacturer(
            id=ids["valve_supplier"],
            name="ValveTech Europe",
            tradeName="ValveTech",
            eoriNumber=generate_eori_number(),
            lucidNumber=generate_lucid_number(),
            url="https://example.com/valvetech",
        ),
        Manufacturer(
            id=ids["machine_manu"],
            name="BeanMaster Appliances",
            tradeName="BeanMaster",
            eoriNumber=generate_eori_number(),
            lucidNumber=generate_lucid_number(),
            url="https://example.com/beanmaster",
        ),
        Importer(
            id=ids["importer"],
            name="Global Imports GmbH",
            tradeName="GlobImp",
            eoriNumber=generate_eori_number(),
            lucidNumber=generate_lucid_number(),
            url="https://example.com/globimp",
        ),
        TransportProvider(
            id=ids["transport"],
            name="FastTrans Logistics",
            url="https://example.com/fasttrans",
            transportAuthorityNumber=generate_transport_authority_number(),
        ),
        Organisation(id=ids["service"], name="ProBrew Service Center", url="https://example.com/probrew"),
        Organisation(id=ids["recycler"], name="RecycleTech Services", url="https://example.com/recycletech"),
        Manufacturer(
            id=ids["asia_metal"],
            name="SinoSteel Shanghai",
            tradeName="SinoSteel",
            eoriNumber=generate_eori_number(),
            lucidNumber=generate_lucid_number(),
            url="https://example.com/sinosteel",
        ),
        Manufacturer(
            id=ids["asia_plastics"],
            name="Hanoi Polymer Works",
            tradeName="HanoiPoly",
            eoriNumber=generate_eori_number(),
            lucidNumber=generate_lucid_number(),
            url="https://example.com/hanoipoly",
        ),
        Manufacturer(
            id=ids["asia_pcb"],
            name="Penang PCB Tech",
            tradeName="PenangPCB",
            eoriNumber=generate_eori_number(),
            lucidNumber=generate_lucid_number(),
            url="https://example.com/penangpcb",
        ),
        Manufacturer(
            id=ids["asia_magnet"],
            name="Shenzhen NeoMag",
            tradeName="NeoMag",
            eoriNumber=generate_eori_number(),
            lucidNumber=generate_lucid_number(),
            url="https://example.com/neomag",
        ),
        Manufacturer(
            id=ids["asia_valve"],
            name="Izmit Valves Ltd.",
            tradeName="IzmitValve",
            eoriNumber=generate_eori_number(),
            lucidNumber=generate_lucid_number(),
            url="https://example.com/izmitvalve",
        ),
        TransportProvider(
            id=ids["ocean_carrier"],
            name="BlueOcean Shipping",
            url="https://example.com/blueocean",
            transportAuthorityNumber=generate_transport_authority_number(),
        ),
        Manufacturer(
            id=ids["eu_assembler"],
            name="BeanMaster EU Assembly",
            tradeName="BM Katowice",
            eoriNumber=generate_eori_number(),
            lucidNumber=generate_lucid_number(),
            url="https://example.com/bmeu",
        ),
        Organisation(id=ids["eu_service_2"], name="EuroBrew Service Hub", url="https://example.com/eurobrew"),
    ]
    return orgs, ids


# -----------------------------
# 2) Places
# -----------------------------
async def make_places(org_ids: Dict[str, str]) -> Dict[str, Place]:
    places: Dict[str, Place] = {
        "steel_mill": Place(
            name="EuroSteel Mill",
            latitude=51.5,
            longitude=7.4,
            country="DE",
            city="Dortmund",
            postalCode="44135",
            managedBy={"id": org_ids["metal_supplier"], "collection": "organisation"},
        ),
        "plastics_plant": Place(
            name="PolyForm Plant",
            latitude=48.1,
            longitude=11.6,
            country="DE",
            city="Munich",
            postalCode="80331",
            managedBy={"id": org_ids["plastics_supplier"], "collection": "organisation"},
        ),
        "pcb_fab": Place(
            name="BavPCB Fab",
            latitude=48.4,
            longitude=10.0,
            country="DE",
            city="Augsburg",
            postalCode="86150",
            managedBy={"id": org_ids["pcb_fab"], "collection": "organisation"},
        ),
        "magnet_plant": Place(
            name="NordMag Plant",
            latitude=53.6,
            longitude=10.0,
            country="DE",
            city="Hamburg",
            postalCode="20095",
            managedBy={"id": org_ids["magnet_supplier"], "collection": "organisation"},
        ),
        "valve_plant": Place(
            name="ValveTech Plant",
            latitude=50.1,
            longitude=8.7,
            country="DE",
            city="Frankfurt",
            postalCode="60311",
            managedBy={"id": org_ids["valve_supplier"], "collection": "organisation"},
        ),
        "factory": Place(
            name="BeanMaster Factory",
            latitude=48.8,
            longitude=9.2,
            country="DE",
            city="Stuttgart",
            postalCode="70173",
            managedBy={"id": org_ids["machine_manu"], "collection": "organisation"},
        ),
        "assembly_hall": Place(
            name="Assembly Hall",
            latitude=49.0,
            longitude=8.4,
            country="DE",
            city="Karlsruhe",
            postalCode="76133",
            managedBy={"id": org_ids["machine_manu"], "collection": "organisation"},
        ),
        "warehouse": Place(
            name="Importer Warehouse",
            latitude=50.0,
            longitude=8.2,
            country="DE",
            city="Wiesbaden",
            postalCode="65183",
            managedBy={"id": org_ids["importer"], "collection": "organisation"},
        ),
        "distribution": Place(
            name="Distribution Center",
            latitude=49.4,
            longitude=8.7,
            country="DE",
            city="Heidelberg",
            postalCode="69115",
            managedBy={"id": org_ids["transport"], "collection": "organisation"},
        ),
        "service_center": Place(
            name="ProBrew Service",
            latitude=52.5,
            longitude=13.4,
            country="DE",
            city="Berlin",
            postalCode="10115",
            managedBy={"id": org_ids["service"], "collection": "organisation"},
        ),
        "return_center": Place(
            name="Return Center",
            latitude=53.55,
            longitude=9.99,
            country="DE",
            city="Hamburg",
            postalCode="20095",
            managedBy={"id": org_ids["recycler"], "collection": "organisation"},
        ),
        "recycling_facility": Place(
            name="Recycling Facility",
            latitude=51.23,
            longitude=6.77,
            country="DE",
            city="Düsseldorf",
            postalCode="40213",
            managedBy={"id": org_ids["recycler"], "collection": "organisation"},
        ),
        "repair_facility": Place(
            name="Repair Facility",
            latitude=50.94,
            longitude=6.96,
            country="DE",
            city="Cologne",
            postalCode="50667",
            managedBy={"id": org_ids["service"], "collection": "organisation"},
        ),
        "cn_steel": Place(
            name="SinoSteel Shanghai Mill",
            latitude=31.23,
            longitude=121.47,
            country="CN",
            city="Shanghai",
            postalCode="200000",
            managedBy={"id": org_ids["asia_metal"], "collection": "organisation"},
        ),
        "vn_plastics": Place(
            name="Hanoi Polymer Works",
            latitude=21.03,
            longitude=105.85,
            country="VN",
            city="Hanoi",
            postalCode="100000",
            managedBy={"id": org_ids["asia_plastics"], "collection": "organisation"},
        ),
        "my_pcb": Place(
            name="Penang PCB Tech",
            latitude=5.41,
            longitude=100.34,
            country="MY",
            city="George Town",
            postalCode="10050",
            managedBy={"id": org_ids["asia_pcb"], "collection": "organisation"},
        ),
        "cn_magnet": Place(
            name="Shenzhen NeoMag Plant",
            latitude=22.54,
            longitude=114.06,
            country="CN",
            city="Shenzhen",
            postalCode="518000",
            managedBy={"id": org_ids["asia_magnet"], "collection": "organisation"},
        ),
        "tr_valve": Place(
            name="Izmit Valve Works",
            latitude=40.77,
            longitude=29.94,
            country="TR",
            city="İzmit",
            postalCode="41000",
            managedBy={"id": org_ids["asia_valve"], "collection": "organisation"},
        ),
        "pl_assembly": Place(
            name="BM EU Assembly – Katowice",
            latitude=50.26,
            longitude=19.02,
            country="PL",
            city="Katowice",
            postalCode="40-001",
            managedBy={"id": org_ids["eu_assembler"], "collection": "organisation"},
        ),
        "de_port": Place(
            name="Hamburg Port",
            latitude=53.55,
            longitude=9.99,
            country="DE",
            city="Hamburg",
            postalCode="20095",
            managedBy={"id": org_ids["ocean_carrier"], "collection": "organisation"},
        ),
        "cz_distribution": Place(
            name="Prague Distribution",
            latitude=50.08,
            longitude=14.44,
            country="CZ",
            city="Prague",
            postalCode="11000",
            managedBy={"id": org_ids["transport"], "collection": "organisation"},
        ),
        "at_service": Place(
            name="EuroBrew Service Hub",
            latitude=48.21,
            longitude=16.37,
            country="AT",
            city="Vienna",
            postalCode="1010",
            managedBy={"id": org_ids["eu_service_2"], "collection": "organisation"},
        ),
    }
    return places


# -----------------------------
# 3) Materials (statics)
# -----------------------------
def material_statics(org_ids: Dict[str, str]) -> Dict[str, MaterialStatic]:
    return {
        # metals
        "stainless_304": MaterialStatic(
            name="Stainless Steel 304",
            description="Corrosion-resistant steel (contains nickel).",
            materialManufacturer={"id": org_ids["metal_supplier"], "collection": "organisation"},
            casNumber=None,
            isoDesignation="ISO 304",
            eclassClassification="0173-1#01-AEJ430#013",
            hazardous=True,
            warnings=["Contains nickel; may cause allergic reactions."],
            reachCertification=None,
            additionalDocuments=[],
            rareEarth=False,
        ),
        "copper": MaterialStatic(
            name="Copper (Cu)",
            description="High-conductivity copper for wiring.",
            materialManufacturer={"id": org_ids["metal_supplier"], "collection": "organisation"},
            casNumber="7440-50-8",
            hazardous=False,
            warnings=[],
            additionalDocuments=[],
            rareEarth=False,
        ),
        "aluminum_6061": MaterialStatic(
            name="Aluminum Alloy 6061",
            description="Thermoblock/heater body.",
            materialManufacturer={"id": org_ids["metal_supplier"], "collection": "organisation"},
            casNumber="7429-90-5",
            isoDesignation="ISO 6061",
            hazardous=False,
            warnings=[],
            rareEarth=False,
        ),
        # rare earth magnets
        "ndfeb_magnet": MaterialStatic(
            name="NdFeB Magnet",
            description="Neodymium-iron-boron permanent magnet",
            materialManufacturer={"id": org_ids["magnet_supplier"], "collection": "organisation"},
            casNumber=None,
            hazardous=False,
            warnings=[],
            additionalDocuments=[],
            rareEarth=True,
        ),
        # polymers / elastomers
        "silicone": MaterialStatic(
            name="Food-grade Silicone",
            description="Hoses and seals.",
            materialManufacturer={"id": org_ids["plastics_supplier"], "collection": "organisation"},
            casNumber="63231-66-3",
            hazardous=False,
            warnings=[],
            rareEarth=False,
        ),
        "pp": MaterialStatic(
            name="Polypropylene (PP)",
            description="Waste bin / container.",
            materialManufacturer={"id": org_ids["plastics_supplier"], "collection": "organisation"},
            hazardous=False,
            warnings=[],
            rareEarth=False,
        ),
        "abs": MaterialStatic(
            name="ABS",
            description="Front housing/trim.",
            materialManufacturer={"id": org_ids["plastics_supplier"], "collection": "organisation"},
            hazardous=False,
            warnings=[],
            rareEarth=False,
        ),
        "pa66_gf30": MaterialStatic(
            name="PA66-GF30",
            description="Glass‑fiber reinforced nylon for gearbox.",
            materialManufacturer={"id": org_ids["plastics_supplier"], "collection": "organisation"},
            hazardous=False,
            warnings=[],
            rareEarth=False,
        ),
        "nbr": MaterialStatic(
            name="NBR (Buna‑N)",
            description="O‑rings.",
            materialManufacturer={"id": org_ids["plastics_supplier"], "collection": "organisation"},
            hazardous=False,
            warnings=[],
            rareEarth=False,
        ),
        "ptfe": MaterialStatic(
            name="PTFE",
            description="Valve/thermoblock gaskets.",
            materialManufacturer={"id": org_ids["plastics_supplier"], "collection": "organisation"},
            hazardous=False,
            warnings=[],
            rareEarth=False,
        ),
        # electronics
        "fr4": MaterialStatic(
            name="FR‑4 laminate",
            description="Glass‑epoxy laminate with brominated flame retardant (PCB).",
            materialManufacturer={"id": org_ids["pcb_fab"], "collection": "organisation"},
            hazardous=True,
            warnings=["Contains brominated flame retardants."],
            rareEarth=False,
        ),
        "solder_snagcu": MaterialStatic(
            name="Lead‑free solder (SnAgCu)",
            description="Electronics solder.",
            materialManufacturer={"id": org_ids["pcb_fab"], "collection": "organisation"},
            hazardous=False,
            warnings=[],
            rareEarth=False,
        ),
        # others
        "brass": MaterialStatic(
            name="Brass",
            description="Valve body (Cu‑Zn).",
            materialManufacturer={"id": org_ids["valve_supplier"], "collection": "organisation"},
            hazardous=False,
            warnings=[],
            rareEarth=False,
        ),
        "glass": MaterialStatic(
            name="Soda‑lime Glass",
            description="Water tank.",
            materialManufacturer={"id": org_ids["plastics_supplier"], "collection": "organisation"},
            hazardous=False,
            warnings=[],
            rareEarth=False,
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


# -----------------------------
# 4) Part statics (definitions)
# -----------------------------
def part_statics(org_ids: Dict[str, str]) -> Dict[str, PartStatic]:
    P = {}
    add = lambda key, name, desc, w, mtbf, avv=None: P.setdefault(
        key,
        PartStatic(
            name=name,
            description=desc,
            partManufacturer={"id": org_ids["machine_manu"], "collection": "organisation"},
            heightCM=10,
            widthCM=10,
            depthCM=10,
            weightGRM=w,
            mtbfHRS=mtbf,
            avv_dispose=avv,
        ),
    )
    add("machine", "Automatic Coffee Machine", "Fully automatic bean‑to‑cup.", 10000, 50000, "160214")
    add("housing", "Outer Housing", "Main enclosure ABS/steel", 4000, 25000, "160214")
    add("brew_group", "Brew Group", "Brew unit with piston & chamber", 1200, 20000, "160214")
    add("drip_tray", "Drip Tray", "Stainless tray", 600, 12000, "160214")
    add("waste_bin", "Waste Bin", "PP puck container", 350, 10000, "150102")
    add("water_tank", "Water Tank", "Glass tank with cap", 800, 15000, "200102")
    add("steam_wand", "Steam Wand", "For milk frothing", 200, 15000, "160214")

    add("grinder", "Grinder Assembly", "Motor + burrs + gearbox", 900, 15000, "160214")
    add("motor", "Grinder Motor", "DC motor with magnets & copper", 350, 15000, "160214")
    add("burrs", "Burr Set", "Steel burrs", 150, 8000, "160214")
    add("gearbox", "Gearbox", "PA66‑GF30 housing, steel gears", 200, 12000, "160214")

    add("water_system", "Water System", "Pump, flowmeter, thermoblock, valves & hoses", 1200, 20000, "160214")
    add("pump", "Vibration Pump", "Vibration pump for pressure", 350, 12000, "160214")
    add("flowmeter", "Flowmeter", "Turbine flow sensor", 80, 12000, "160214")
    add("thermoblock", "Thermoblock", "Aluminum heater block", 400, 12000, "160214")
    add("solenoid", "3‑Way Solenoid Valve", "Brass body, PTFE seals", 120, 12000, "160214")
    add("hoses", "Hoses & Seals", "Silicone hoses, NBR o‑rings", 120, 8000, "150102")

    add("electronics", "Main Electronics", "Control + power boards", 500, 20000, "160214")
    add("main_pcb", "Main PCB", "FR‑4 board with solder", 180, 20000, "160214")
    add("ui_pcb", "UI PCB", "Buttons/display board", 80, 20000, "160214")
    return P


# -----------------------------
# Build the *instance* tree + materials
# -----------------------------
def prod_step(place_id: str, qty=1.0) -> ProductionStep:
    return ProductionStep(
        description="Manufacturing",
        processedAt={"id": place_id, "collection": "place"},
        ghgEmissionRecords=[ghg("production", qty)],
    )


def road(place_from: str, place_to: str, km: float) -> TransportStep:
    return TransportStep(
        processedAt={"id": place_from, "collection": "place"},
        destination={"id": place_to, "collection": "place"},
        modeOfTransport=ModeOfTransport.ROAD,
        distanceKM=km,
        reasonForTransport=TransportReason.SUPPLY_CHAIN,
        ghgEmissionRecords=[ghg("transport-road", km / 100.0)],
    )


def air(place_from: str, place_to: str, km: float) -> TransportStep:
    return TransportStep(
        processedAt={"id": place_from, "collection": "place"},
        destination={"id": place_to, "collection": "place"},
        modeOfTransport=ModeOfTransport.AIR,
        distanceKM=km,
        reasonForTransport=TransportReason.SUPPLY_CHAIN,
        ghgEmissionRecords=[ghg("transport-air", km / 100.0)],
    )


def sea(place_from: str, place_to: str, km: float) -> TransportStep:
    return TransportStep(
        processedAt={"id": place_from, "collection": "place"},
        destination={"id": place_to, "collection": "place"},
        modeOfTransport=ModeOfTransport.SEA,
        distanceKM=km,
        reasonForTransport=TransportReason.SUPPLY_CHAIN,
        ghgEmissionRecords=ghg_mix(
            [
                (
                    GHGScope.SCOPE_3,
                    Scope3Category.UPSTREAM_TRANSPORTATION_AND_DISTRIBUTION,
                    ActivityType.DISTANCE_TRAVELED,
                    km,
                    UnitCode.KM,
                    0.015,  # kgCO2e/km (illustrative)
                    UnitCode.KG_CO2E_PER_KM,
                    "Container ship avg intensity",
                    "sea-ship segment",
                )
            ]
        ),
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


# -----------------------------
# create DPPs for sub-assemblies
# -----------------------------
async def create_subpart_component_dpps(
    client: httpx.AsyncClient,
    *,
    org_ids: Dict[str, str],
    places: Dict[str, Place],
    pstat: Dict[str, PartStatic],
    housing_pi: PartInstance,
    electronics_pi: PartInstance,
    grinder_pi: PartInstance,
) -> Tuple[DPPInstance, DPPInstance, DPPInstance]:
    """
    Create stand-alone DPPs (Static + one Instance each) for selected sub-assemblies,
    while leaving their composition in the main machine intact.

    Returns the three created DPPInstance objects (housing, electronics, grinder) as models.
    """
    # ---- Outer Housing (component DPP) ----------------------------------
    dpp_housing_static = DPPStatic(
        name="Outer Housing Assembly",
        description="Component-level DPP for the ABS/steel outer enclosure of BaristaCore products.",
        EAN=generate_gln_number(),
        GS1DigitalLink=f"https://id.gs1.org/01/{generate_gln_number()}",
        productClass="Appliance Component",
        heightCM=pstat["housing"].heightCM,
        widthCM=pstat["housing"].widthCM,
        depthCM=pstat["housing"].depthCM,
        weightGRM=pstat["housing"].weightGRM,
        dataSheet=DigitalDocument(name="Data Sheet (Housing)", url="https://example.com/housing-ds.pdf"),
        installationOperatingGuide=DigitalDocument(name="Installation Guide", url="https://example.com/housing-ig.pdf"),
        ceConformityDeclaration=DigitalDocument(name="CE Declaration", url="https://example.com/housing-ce.pdf"),
        ecodesignConformityDeclaration=DigitalDocument(
            name="Ecodesign Declaration", url="https://example.com/housing-eco.pdf"
        ),
        repairAndServiceManual=DigitalDocument(name="Repair Manual", url="https://example.com/housing-repair.pdf"),
        DisassemblyInstructions=DigitalDocument(
            name="Disassembly Instructions", url="https://example.com/housing-disassembly.pdf"
        ),
        recyclingEOLInstructions=DigitalDocument(
            name="Recycling Instructions", url="https://example.com/housing-recycling.pdf"
        ),
        guaranteeDescription="1-year component warranty.",
        expectedMtbfHRS=pstat["housing"].mtbfHRS,
        taricCode="3926909790",
        weeeRegistrationNumber="WEEE-CH-0000000001",
        responsibleOperator={"id": org_ids["machine_manu"], "collection": "organisation"},
        importer={"id": org_ids["importer"], "collection": "organisation"},
        productManufacturer={"id": org_ids["machine_manu"], "collection": "organisation"},
        has_spare_parts=[],
        toolsForMaintenance=["Torx T10", "Plastic pry tool"],
        qualificationForRepair=QualificationForRepair.ENDUSER,
        backupLink="https://example.com/backup",
        returningPlaces=[
            {"id": places["return_center"].id, "collection": "place"},
            {"id": places["repair_facility"].id, "collection": "place"},
        ],
    )
    await create_dpp_static_once(client, dpp_housing_static)

    dpp_housing_instance = DPPInstance(
        dppStaticLink={"id": dpp_housing_static.id, "collection": "dpp_static"},
        partInstanceLink={"id": housing_pi.id, "collection": "part_instance"},
        dateOfDeclaration=TODAY_FIXED - timedelta(days=750),
        cleaningCount=0,
        chalkCount=0,
        brewingCount=0,
        coffeeGrindingCount=0,
        operatingHRS=0,
        discontinued=False,
        backupLink="https://example.com/backup",
    )
    await create_or_skip_duplicate(
        client,
        f"{BASE_URL}/dpp/instance/",
        dpp_housing_instance,
        what="DPPInstance",
        obj_id=dpp_housing_instance.id,
    )

    # ---- Main Electronics (component DPP) -------------------------------
    dpp_elec_static = DPPStatic(
        name="Main Electronics Module",
        description="Component-level DPP for control & power electronics module.",
        EAN=generate_gln_number(),
        GS1DigitalLink=f"https://id.gs1.org/01/{generate_gln_number()}",
        productClass="Electronics Module",
        heightCM=pstat["electronics"].heightCM,
        widthCM=pstat["electronics"].widthCM,
        depthCM=pstat["electronics"].depthCM,
        weightGRM=pstat["electronics"].weightGRM,
        dataSheet=DigitalDocument(name="Data Sheet (Electronics)", url="https://example.com/elec-ds.pdf"),
        installationOperatingGuide=DigitalDocument(name="Installation Guide", url="https://example.com/elec-ig.pdf"),
        ceConformityDeclaration=DigitalDocument(name="CE Declaration", url="https://example.com/elec-ce.pdf"),
        ecodesignConformityDeclaration=DigitalDocument(
            name="Ecodesign Declaration", url="https://example.com/elec-eco.pdf"
        ),
        repairAndServiceManual=DigitalDocument(name="Repair Manual", url="https://example.com/elec-repair.pdf"),
        DisassemblyInstructions=DigitalDocument(
            name="Disassembly Instructions", url="https://example.com/elec-disassembly.pdf"
        ),
        recyclingEOLInstructions=DigitalDocument(
            name="Recycling Instructions", url="https://example.com/elec-recycling.pdf"
        ),
        guaranteeDescription="2-year module warranty.",
        expectedMtbfHRS=pstat["electronics"].mtbfHRS,
        taricCode="8538909900",
        weeeRegistrationNumber="WEEE-CH-0000000002",
        responsibleOperator={"id": org_ids["machine_manu"], "collection": "organisation"},
        importer={"id": org_ids["importer"], "collection": "organisation"},
        productManufacturer={"id": org_ids["machine_manu"], "collection": "organisation"},
        has_spare_parts=[
            {"id": pstat["main_pcb"].id, "collection": "part_static"},
            {"id": pstat["ui_pcb"].id, "collection": "part_static"},
        ],
        toolsForMaintenance=["ESD strap", "Phillips #1", "Hot air rework station"],
        qualificationForRepair=QualificationForRepair.ENDUSER,
        backupLink="https://example.com/backup",
        returningPlaces=[
            {"id": places["repair_facility"].id, "collection": "place"},
            {"id": places["return_center"].id, "collection": "place"},
        ],
    )
    await create_dpp_static_once(client, dpp_elec_static)

    dpp_elec_instance = DPPInstance(
        dppStaticLink={"id": dpp_elec_static.id, "collection": "dpp_static"},
        partInstanceLink={"id": electronics_pi.id, "collection": "part_instance"},
        dateOfDeclaration=TODAY_FIXED - timedelta(days=740),
        cleaningCount=0,
        chalkCount=0,
        brewingCount=0,
        coffeeGrindingCount=0,
        operatingHRS=0,
        discontinued=False,
        backupLink="https://example.com/backup",
    )
    await create_or_skip_duplicate(
        client,
        f"{BASE_URL}/dpp/instance/",
        dpp_elec_instance,
        what="DPPInstance",
        obj_id=dpp_elec_instance.id,
    )

    # ---- Grinder Assembly (component DPP) -------------------------------
    dpp_grinder_static = DPPStatic(
        name="Grinder Assembly",
        description="Component-level DPP for grinder module incl. motor, burrs, gearbox.",
        EAN=generate_gln_number(),
        GS1DigitalLink=f"https://id.gs1.org/01/{generate_gln_number()}",
        productClass="Appliance Component",
        heightCM=pstat["grinder"].heightCM,
        widthCM=pstat["grinder"].widthCM,
        depthCM=pstat["grinder"].depthCM,
        weightGRM=pstat["grinder"].weightGRM,
        dataSheet=DigitalDocument(name="Data Sheet (Grinder)", url="https://example.com/grinder-ds.pdf"),
        installationOperatingGuide=DigitalDocument(name="Installation Guide", url="https://example.com/grinder-ig.pdf"),
        ceConformityDeclaration=DigitalDocument(name="CE Declaration", url="https://example.com/grinder-ce.pdf"),
        ecodesignConformityDeclaration=DigitalDocument(
            name="Ecodesign Declaration", url="https://example.com/grinder-eco.pdf"
        ),
        repairAndServiceManual=DigitalDocument(name="Repair Manual", url="https://example.com/grinder-repair.pdf"),
        DisassemblyInstructions=DigitalDocument(
            name="Disassembly Instructions", url="https://example.com/grinder-disassembly.pdf"
        ),
        recyclingEOLInstructions=DigitalDocument(
            name="Recycling Instructions", url="https://example.com/grinder-recycling.pdf"
        ),
        guaranteeDescription="2-year grinder module warranty.",
        expectedMtbfHRS=pstat["grinder"].mtbfHRS,
        taricCode="8503009900",
        weeeRegistrationNumber="WEEE-CH-0000000003",
        responsibleOperator={"id": org_ids["machine_manu"], "collection": "organisation"},
        importer={"id": org_ids["importer"], "collection": "organisation"},
        productManufacturer={"id": org_ids["machine_manu"], "collection": "organisation"},
        has_spare_parts=[{"id": pstat["burrs"].id, "collection": "part_static"}],
        toolsForMaintenance=["Torx T10", "Feeler gauge", "Bearing puller"],
        qualificationForRepair=QualificationForRepair.ENDUSER,
        backupLink="https://example.com/backup",
        returningPlaces=[
            {"id": places["repair_facility"].id, "collection": "place"},
            {"id": places["return_center"].id, "collection": "place"},
        ],
    )
    await create_dpp_static_once(client, dpp_grinder_static)

    dpp_grinder_instance = DPPInstance(
        dppStaticLink={"id": dpp_grinder_static.id, "collection": "dpp_static"},
        partInstanceLink={"id": grinder_pi.id, "collection": "part_instance"},
        dateOfDeclaration=TODAY_FIXED - timedelta(days=730),
        cleaningCount=0,
        chalkCount=0,
        brewingCount=0,
        coffeeGrindingCount=0,
        operatingHRS=0,
        discontinued=False,
        backupLink="https://example.com/backup",
    )
    await create_or_skip_duplicate(
        client,
        f"{BASE_URL}/dpp/instance/",
        dpp_grinder_instance,
        what="DPPInstance",
        obj_id=dpp_grinder_instance.id,
    )
    return dpp_housing_instance, dpp_elec_instance, dpp_grinder_instance


# -----------------------------
# Structured seeding (helpers + orchestration)
# -----------------------------
@dataclass
class BuildArtifacts:
    """Everything we may want to reference after an instance is built."""

    minst: Dict[str, MaterialInstance] = field(default_factory=dict)
    leafs: Dict[str, PartInstance] = field(default_factory=dict)
    mid: Dict[str, PartInstance] = field(default_factory=dict)
    machine: PartInstance | None = None
    dpp_static: DPPStatic | None = None
    dpp_instance: DPPInstance | None = None


# --- Registration helpers -------------------------------------------------
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
        else:
            ep = "organisation/"
        await create_or_skip_duplicate(client, f"{BASE_URL}/{ep}", o, what="Organisation", obj_id=o.id)
    return org_ids, orgs


async def register_places(
    client: httpx.AsyncClient, org_ids: Dict[str, str]
) -> tuple[Dict[str, Place], Dict[str, str]]:
    places = await make_places(org_ids)
    for p in places.values():
        await create_or_skip_duplicate(client, f"{BASE_URL}/place/", p, "Place", p.id)
    pid = {k: v.id for k, v in places.items()}
    return places, pid


async def register_material_statics(client: httpx.AsyncClient, org_ids: Dict[str, str]) -> Dict[str, MaterialStatic]:
    mstat = material_statics(org_ids)
    for m in mstat.values():
        await create_or_skip_duplicate(client, f"{BASE_URL}/material/", m, "MaterialStatic", m.id)
    return mstat


async def register_part_statics(client: httpx.AsyncClient, org_ids: Dict[str, str]) -> Dict[str, PartStatic]:
    pstat = part_statics(org_ids)
    for ps in pstat.values():
        await create_or_skip_duplicate(client, f"{BASE_URL}/part/", ps, "PartStatic", ps.id)
    return pstat


# --- Instance #1 build ----------------------------------------------------
async def build_instance_1(
    client: httpx.AsyncClient,
    *,
    org_ids: Dict[str, str],
    places: Dict[str, Place],
    pid: Dict[str, str],
    mstat: Dict[str, MaterialStatic],
    pstat: Dict[str, PartStatic],
) -> BuildArtifacts:
    BA = BuildArtifacts()

    # Materials (instances)
    def msteps(origin: str, dest: str, km=150.0):
        return [prod_step(origin), road(origin, dest, km)]

    BA.minst = {
        "steel": mat_inst(
            mstat["stainless_304"], "BATCH-STEEL-001", 1200, 30.0, 0.995, msteps(pid["steel_mill"], pid["factory"])
        ),
        "copper": mat_inst(
            mstat["copper"], "BATCH-CU-001", 600, 20.0, 0.999, msteps(pid["steel_mill"], pid["factory"])
        ),
        "al": mat_inst(
            mstat["aluminum_6061"], "BATCH-AL-001", 800, 15.0, 0.985, msteps(pid["steel_mill"], pid["factory"])
        ),
        "ndfeb": mat_inst(
            mstat["ndfeb_magnet"],
            "BATCH-ND-001",
            80,
            0.0,
            0.97,
            [prod_step(pid["magnet_plant"]), air(pid["magnet_plant"], pid["factory"], 800.0)],
        ),
        "sil": mat_inst(
            mstat["silicone"], "BATCH-SIL-001", 180, 5.0, 0.96, msteps(pid["plastics_plant"], pid["factory"])
        ),
        "pp": mat_inst(mstat["pp"], "BATCH-PP-001", 350, 40.0, 0.94, msteps(pid["plastics_plant"], pid["factory"])),
        "abs": mat_inst(mstat["abs"], "BATCH-ABS-001", 800, 35.0, 0.95, msteps(pid["plastics_plant"], pid["factory"])),
        "pa66": mat_inst(
            mstat["pa66_gf30"], "BATCH-PA-001", 140, 10.0, 0.93, msteps(pid["plastics_plant"], pid["factory"])
        ),
        "nbr": mat_inst(mstat["nbr"], "BATCH-NBR-001", 60, 15.0, 0.92, msteps(pid["plastics_plant"], pid["factory"])),
        "ptfe": mat_inst(
            mstat["ptfe"], "BATCH-PTFE-001", 30, 0.0, 0.9999, msteps(pid["plastics_plant"], pid["factory"])
        ),
        "fr4": mat_inst(mstat["fr4"], "BATCH-FR4-001", 160, 0.0, 0.97, msteps(pid["pcb_fab"], pid["factory"])),
        "solder": mat_inst(
            mstat["solder_snagcu"], "BATCH-SAC-001", 20, 0.0, 0.998, msteps(pid["pcb_fab"], pid["factory"])
        ),
        "brass": mat_inst(mstat["brass"], "BATCH-BR-001", 120, 25.0, 0.985, msteps(pid["valve_plant"], pid["factory"])),
        "glass": mat_inst(
            mstat["glass"], "BATCH-GL-001", 780, 30.0, 0.97, msteps(pid["plastics_plant"], pid["factory"])
        ),
    }
    for mi in BA.minst.values():
        await post_json(client, f"{BASE_URL}/material/instance/", mi)

    # Parts (instances)
    def psteps(origin, dest):
        return [prod_step(origin), road(origin, dest, 200.0)]

    # leafs
    BA.leafs = {
        "burrs": part_inst(pstat["burrs"], "BATCH-BURR-001", psteps(pid["factory"], pid["assembly_hall"])),
        "motor": part_inst(pstat["motor"], "BATCH-MOTOR-001", psteps(pid["factory"], pid["assembly_hall"])),
        "gearbox": part_inst(pstat["gearbox"], "BATCH-GBX-001", psteps(pid["factory"], pid["assembly_hall"])),
        "pump": part_inst(pstat["pump"], "BATCH-PUMP-001", psteps(pid["factory"], pid["assembly_hall"])),
        "flowmeter": part_inst(pstat["flowmeter"], "BATCH-FM-001", psteps(pid["factory"], pid["assembly_hall"])),
        "thermoblock": part_inst(pstat["thermoblock"], "BATCH-TB-001", psteps(pid["factory"], pid["assembly_hall"])),
        "solenoid": part_inst(pstat["solenoid"], "BATCH-SOL-001", psteps(pid["valve_plant"], pid["assembly_hall"])),
        "hoses": part_inst(pstat["hoses"], "BATCH-HOSE-001", psteps(pid["factory"], pid["assembly_hall"])),
        "main_pcb": part_inst(pstat["main_pcb"], "BATCH-PCB-001", psteps(pid["pcb_fab"], pid["assembly_hall"])),
        "ui_pcb": part_inst(pstat["ui_pcb"], "BATCH-UI-001", psteps(pid["pcb_fab"], pid["assembly_hall"])),
        "drip_tray": part_inst(pstat["drip_tray"], "BATCH-DRIP-001", psteps(pid["factory"], pid["assembly_hall"])),
        "waste_bin": part_inst(pstat["waste_bin"], "BATCH-BIN-001", psteps(pid["factory"], pid["assembly_hall"])),
        "water_tank": part_inst(pstat["water_tank"], "BATCH-TANK-001", psteps(pid["factory"], pid["assembly_hall"])),
        "steam_wand": part_inst(pstat["steam_wand"], "BATCH-WAND-001", psteps(pid["factory"], pid["assembly_hall"])),
        "housing": part_inst(pstat["housing"], "BATCH-HOUS-001", psteps(pid["factory"], pid["assembly_hall"])),
    }
    # attach materials
    BA.leafs["burrs"].compositeMaterials.extend([BA.minst["steel"]])
    BA.leafs["motor"].compositeMaterials.extend([BA.minst["copper"], BA.minst["ndfeb"]])
    BA.leafs["gearbox"].compositeMaterials.extend([BA.minst["pa66"], BA.minst["steel"]])
    BA.leafs["pump"].compositeMaterials.extend([BA.minst["brass"], BA.minst["steel"], BA.minst["nbr"]])
    BA.leafs["flowmeter"].compositeMaterials.extend([BA.minst["brass"], BA.minst["ptfe"]])
    BA.leafs["thermoblock"].compositeMaterials.extend([BA.minst["al"], BA.minst["ptfe"]])
    BA.leafs["solenoid"].compositeMaterials.extend([BA.minst["brass"], BA.minst["ptfe"]])
    BA.leafs["hoses"].compositeMaterials.extend([BA.minst["sil"]])
    BA.leafs["main_pcb"].compositeMaterials.extend([BA.minst["fr4"], BA.minst["solder"], BA.minst["copper"]])
    BA.leafs["ui_pcb"].compositeMaterials.extend([BA.minst["fr4"], BA.minst["solder"]])
    BA.leafs["drip_tray"].compositeMaterials.extend([BA.minst["steel"]])
    BA.leafs["waste_bin"].compositeMaterials.extend([BA.minst["pp"]])
    BA.leafs["water_tank"].compositeMaterials.extend([BA.minst["glass"]])
    BA.leafs["steam_wand"].compositeMaterials.extend([BA.minst["steel"]])
    BA.leafs["housing"].compositeMaterials.extend([BA.minst["abs"], BA.minst["steel"]])

    for pi in BA.leafs.values():
        await post_json(client, f"{BASE_URL}/part/instance/", pi)

    # mid-level assemblies
    BA.mid["grinder"] = part_inst(
        pstat["grinder"], "BATCH-GRIND-001", psteps(pid["factory"], pid["assembly_hall"]), modular=True
    )
    BA.mid["grinder"].compositeParts.extend([BA.leafs["motor"], BA.leafs["burrs"], BA.leafs["gearbox"]])

    BA.mid["water_system"] = part_inst(
        pstat["water_system"], "BATCH-WTR-001", psteps(pid["factory"], pid["assembly_hall"])
    )
    BA.mid["water_system"].compositeParts.extend(
        [BA.leafs["pump"], BA.leafs["flowmeter"], BA.leafs["thermoblock"], BA.leafs["solenoid"], BA.leafs["hoses"]]
    )

    BA.mid["electronics"] = part_inst(
        pstat["electronics"], "BATCH-EL-001", psteps(pid["pcb_fab"], pid["assembly_hall"])
    )
    BA.mid["electronics"].compositeParts.extend([BA.leafs["main_pcb"], BA.leafs["ui_pcb"]])

    BA.mid["brew_group"] = part_inst(
        pstat["brew_group"], "BATCH-BREW-001", psteps(pid["factory"], pid["assembly_hall"]), modular=True
    )

    for mid in BA.mid.values():
        await post_json(client, f"{BASE_URL}/part/instance/", mid)

    # root machine
    BA.machine = part_inst(
        pstat["machine"],
        "BATCH-MACH-001",
        [prod_step(pid["factory"]), road(pid["assembly_hall"], pid["warehouse"], 120.0)],
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
            BA.leafs["steam_wand"],
        ]
    )
    await post_json(client, f"{BASE_URL}/part/instance/", BA.machine)

    # DPP static + instance
    BA.dpp_static = DPPStatic(
        name="BaristaCore 2500",
        description="High-quality automatic bean-to-cup coffee machine.",
        EAN=generate_gln_number(),
        GS1DigitalLink=f"https://id.gs1.org/01/{generate_gln_number()}",
        productClass="Appliance",
        heightCM=45,
        widthCM=35,
        depthCM=40,
        weightGRM=10000,
        dataSheet=DigitalDocument(name="Data Sheet", url="https://example.com/ds.pdf"),
        installationOperatingGuide=DigitalDocument(name="Installation Guide", url="https://example.com/ig.pdf"),
        ceConformityDeclaration=DigitalDocument(name="CE Declaration", url="https://example.com/ce.pdf"),
        ecodesignConformityDeclaration=DigitalDocument(name="Ecodesign Declaration", url="https://example.com/ed.pdf"),
        dateOfPublication=datetime.now(timezone.utc),
        guaranteeDescription="2-year guarantee; user maintenance required.",
        taricCode="8516710000",
        responsibleOperator={"id": org_ids["machine_manu"], "collection": "organisation"},
        importer={"id": org_ids["importer"], "collection": "organisation"},
        productManufacturer={"id": org_ids["machine_manu"], "collection": "organisation"},
        expectedMtbfHRS=50000,
        has_spare_parts=[
            {"id": pstat["burrs"].id, "collection": "part_static"},
            {"id": pstat["pump"].id, "collection": "part_static"},
        ],
        repairAndServiceManual=DigitalDocument(name="Repair Manual", url="https://example.com/repair.pdf"),
        DisassemblyInstructions=DigitalDocument(
            name="Disassembly Instructions", url="https://example.com/disassembly.pdf"
        ),
        toolsForMaintenance=["Torx T10", "Phillips #2", "Pick set"],
        qualificationForRepair=QualificationForRepair.ENDUSER,
        recyclingEOLInstructions=DigitalDocument(
            name="Recycling Instructions", url="https://example.com/recycling.pdf"
        ),
        weeeRegistrationNumber="WEEE-1234567890",
        backupLink="https://example.com/backup",
        returningPlaces=[
            {"id": places["return_center"].id, "collection": "place"},
            {"id": places["recycling_facility"].id, "collection": "place"},
            {"id": places["repair_facility"].id, "collection": "place"},
        ],
    )
    await post_json(client, f"{BASE_URL}/dpp/", BA.dpp_static)

    declaration_date_1 = TODAY_FIXED - timedelta(days=800)
    BA.dpp_instance = DPPInstance(
        dppStaticLink={"id": BA.dpp_static.id, "collection": "dpp_static"},
        partInstanceLink={"id": BA.machine.id, "collection": "part_instance"},
        dateOfDeclaration=declaration_date_1,
        cleaningCount=8,
        chalkCount=3,
        brewingCount=250,
        coffeeGrindingCount=250,
        operatingHRS=6500,
        discontinued=False,
        backupLink="https://example.com/backup",
    )
    dpp_resp = await post_json(client, f"{BASE_URL}/dpp/instance/", BA.dpp_instance)
    BA.dpp_instance = DPPInstance.model_validate(dpp_resp)

    # Component DPPs for select sub-assemblies
    await create_subpart_component_dpps(
        client,
        org_ids=org_ids,
        places=places,
        pstat=pstat,
        housing_pi=BA.leafs["housing"],
        electronics_pi=BA.mid["electronics"],
        grinder_pi=BA.mid["grinder"],
    )
    return BA


async def add_services_instance_1(
    client: httpx.AsyncClient,
    *,
    BA: BuildArtifacts,
    places: Dict[str, Place],
    pstat: Dict[str, PartStatic],
) -> None:
    # Evenly spread 7 service steps
    service_dates_1 = spread_dates(BA.dpp_instance.dateOfDeclaration, TODAY_FIXED, 7)

    def window(ds: List[datetime], i: int) -> tuple[datetime, datetime]:
        begin = ds[i]
        end = begin + timedelta(hours=2)
        return begin, end

    # 1) Repair
    b, e = window(service_dates_1, 0)
    await post_json(
        client,
        f"{BASE_URL}/dpp/instance/{BA.dpp_instance.id}/service/repair/",
        RepairServiceStep(
            processedAt={"id": places["service_center"].id, "collection": "place"},
            costEur=75.0,
            diagnose="Seal wear in 3-way valve",
            observedSymptoms=["Water leakage", "Low brew pressure"],
            repairedPartId=BA.leafs["solenoid"].id,
            ghgEmissionRecords=[ghg("transport-road", 2.0), ghg("repair", 0.5)],
            beginDate=b,
            endDate=e,
        ),
    )

    # 2) Replace – burrs
    new_burrs_1 = part_inst(
        pstat["burrs"],
        "BATCH-BURR-REPL-001",
        [prod_step(places["factory"].id), road(places["factory"].id, places["service_center"].id, 300.0)],
    )
    b, e = window(service_dates_1, 1)
    await post_json(
        client,
        f"{BASE_URL}/dpp/instance/{BA.dpp_instance.id}/service/replace/",
        ReplaceServiceStep(
            processedAt={"id": places["service_center"].id, "collection": "place"},
            costEur=59.0,
            diagnose="Dull burrs causing inconsistent grind size",
            observedSymptoms=["Watery espresso", "Channeling"],
            replacedPartId=BA.leafs["burrs"].id,
            newPart=new_burrs_1,
            ghgEmissionRecords=[ghg("replace", 0.5)],
            beginDate=b,
            endDate=e,
        ),
    )

    # 3) Cleaning – brew group
    b, e = window(service_dates_1, 2)
    await post_json(
        client,
        f"{BASE_URL}/dpp/instance/{BA.dpp_instance.id}/service/cleaning/",
        CleaningServiceStep(
            processedAt={"id": places["service_center"].id, "collection": "place"},
            costEur=25.0,
            cleanedPartId=BA.mid["brew_group"].id,
            cleaningMethod="Deep clean + food-safe grease",
            diagnose="Brew group friction",
            observedSymptoms=["Creaking noise", "Slower cycle"],
            ghgEmissionRecords=[ghg("cleaning", 0.2)],
            beginDate=b,
            endDate=e,
        ),
    )

    # 4) Cleaning – descale & calibration
    b, e = window(service_dates_1, 3)
    await post_json(
        client,
        f"{BASE_URL}/dpp/instance/{BA.dpp_instance.id}/service/cleaning/",
        CleaningServiceStep(
            processedAt={"id": places["service_center"].id, "collection": "place"},
            costEur=18.0,
            cleanedPartId=BA.mid["water_system"].id,
            cleaningMethod="Descale cycle + flow calibration",
            diagnose="Lime scale buildup",
            observedSymptoms=["Reduced flow rate", "Steam sputtering"],
            ghgEmissionRecords=ghg_mix(
                [
                    (
                        GHGScope.SCOPE_2,
                        None,
                        ActivityType.ELECTRICITY_CONSUMPTION,
                        3.0,
                        UnitCode.KWH,
                        0.35,
                        UnitCode.KG_CO2E_PER_KWH,
                        "Service power draw",
                        "bench supply",
                    ),
                ]
            ),
            beginDate=b,
            endDate=e,
        ),
    )

    # 5) Repair – motor brush wear
    b, e = window(service_dates_1, 4)
    await post_json(
        client,
        f"{BASE_URL}/dpp/instance/{BA.dpp_instance.id}/service/repair/",
        RepairServiceStep(
            processedAt={"id": places["service_center"].id, "collection": "place"},
            costEur=45.0,
            diagnose="Motor brush wear",
            observedSymptoms=["Intermittent grinding noise", "Stall on start"],
            repairedPartId=BA.leafs["motor"].id,
            ghgEmissionRecords=ghg_mix(
                [
                    (
                        GHGScope.SCOPE_1,
                        None,
                        ActivityType.FUEL_CONSUMPTION,
                        0.3,
                        UnitCode.LTR,
                        2.68,
                        UnitCode.KG_CO2E_PER_KG,
                        "Compressed-air tool",
                        "workbench",
                    ),
                ]
            ),
            beginDate=b,
            endDate=e,
        ),
    )

    # 6) Replace – pump
    b, e = window(service_dates_1, 5)
    new_pump_1 = part_inst(
        pstat["pump"],
        "BATCH-PUMP-REPL-001",
        [prod_step(places["factory"].id), road(places["factory"].id, places["service_center"].id, 180.0)],
    )
    await post_json(
        client,
        f"{BASE_URL}/dpp/instance/{BA.dpp_instance.id}/service/replace/",
        ReplaceServiceStep(
            processedAt={"id": places["service_center"].id, "collection": "place"},
            costEur=69.0,
            diagnose="Check valve fatigue",
            observedSymptoms=["Irregular pressure ramp"],
            replacedPartId=BA.leafs["pump"].id,
            newPart=new_pump_1,
            ghgEmissionRecords=[ghg("replace", 0.4)],
            beginDate=b,
            endDate=e,
        ),
    )

    # 7) Refurbishment – UI & pump check
    b, e = window(service_dates_1, 6)
    await post_json(
        client,
        f"{BASE_URL}/dpp/instance/{BA.dpp_instance.id}/service/refurbishment/",
        RefurbishmentServiceStep(
            processedAt={"id": places["repair_facility"].id, "collection": "place"},
            costEur=120.0,
            diagnose="UI refresh and pump inspection",
            repairedPartIds=[new_pump_1.id],
            cleanedPartIds=[BA.mid["brew_group"].id],
            replacedAndNewParts=[],
            ghgEmissionRecords=[ghg("refurbishment", 0.8)],
            beginDate=b,
            endDate=e,
        ),
    )


# --- Instance #2 build ----------------------------------------------------
async def build_instance_2(
    client: httpx.AsyncClient,
    *,
    org_ids: Dict[str, str],
    places: Dict[str, Place],
    pid: Dict[str, str],
    mstat: Dict[str, MaterialStatic],
    pstat: Dict[str, PartStatic],
    dpp_static: DPPStatic,
) -> BuildArtifacts:
    BA = BuildArtifacts()

    # MATERIALS (Asia -> EU)
    def msteps_asia_to_eu(
        origin: str, seaport: str, eu_port: str, assembly: str, km_to_port: float, sea_km: float, km_to_assembly: float
    ):
        prod = ProductionStep(
            description="Manufacturing (Asia)",
            processedAt={"id": origin, "collection": "place"},
            ghgEmissionRecords=ghg_mix(
                [
                    (
                        GHGScope.SCOPE_2,
                        None,
                        ActivityType.ELECTRICITY_CONSUMPTION,
                        800,
                        UnitCode.KWH,
                        0.55,
                        UnitCode.KG_CO2E_PER_KWH,
                        "Grid electricity mix (Asia)",
                        "metered kWh",
                    ),
                    (
                        GHGScope.SCOPE_1,
                        None,
                        ActivityType.FUEL_CONSUMPTION,
                        120,
                        UnitCode.LTR,
                        2.68,
                        UnitCode.KG_CO2E_PER_KG,
                        "Natural gas process heat (approx. kgCO2e/ltr eq.)",
                        "boiler estimate",
                    ),
                    (
                        GHGScope.SCOPE_3,
                        Scope3Category.PURCHASED_GOODS_AND_SERVICES,
                        ActivityType.MATERIAL_PURCHASE,
                        1000,
                        UnitCode.KG,
                        1.9,
                        UnitCode.KG_CO2E_PER_KG,
                        "Purchased materials embodied carbon",
                        "supplier EPD",
                    ),
                    (
                        GHGScope.SCOPE_3,
                        Scope3Category.WASTE_GENERATED_IN_OPERATIONS,
                        ActivityType.WASTE_TREATMENT,
                        50,
                        UnitCode.KG,
                        0.5,
                        UnitCode.KG_CO2E_PER_KG,
                        "Scrap treatment",
                        "on-site waste contractor",
                    ),
                ]
            ),
        )
        pre_carriage = TransportStep(
            processedAt={"id": origin, "collection": "place"},
            destination={"id": seaport, "collection": "place"},
            modeOfTransport=ModeOfTransport.ROAD,
            distanceKM=km_to_port,
            reasonForTransport=TransportReason.SUPPLY_CHAIN,
            ghgEmissionRecords=ghg_mix(
                [
                    (
                        GHGScope.SCOPE_3,
                        Scope3Category.UPSTREAM_TRANSPORTATION_AND_DISTRIBUTION,
                        ActivityType.DISTANCE_TRAVELED,
                        km_to_port,
                        UnitCode.KM,
                        0.08,
                        UnitCode.KG_CO2E_PER_KM,
                        "Asian trucking avg",
                        "to seaport",
                    )
                ]
            ),
        )
        ocean = sea(seaport, eu_port, sea_km)
        on_carriage = TransportStep(
            processedAt={"id": eu_port, "collection": "place"},
            destination={"id": assembly, "collection": "place"},
            modeOfTransport=ModeOfTransport.ROAD,
            distanceKM=km_to_assembly,
            reasonForTransport=TransportReason.SUPPLY_CHAIN,
            ghgEmissionRecords=ghg_mix(
                [
                    (
                        GHGScope.SCOPE_3,
                        Scope3Category.UPSTREAM_TRANSPORTATION_AND_DISTRIBUTION,
                        ActivityType.DISTANCE_TRAVELED,
                        km_to_assembly,
                        UnitCode.KM,
                        0.09,
                        UnitCode.KG_CO2E_PER_KM,
                        "EU trucking avg",
                        "from port to assembly",
                    )
                ]
            ),
        )
        return [prod, pre_carriage, ocean, on_carriage]

    BA.minst = {
        "steel2": mat_inst(
            mstat["stainless_304"],
            "BATCH-STEEL-ASIA-001",
            1200,
            20.0,
            0.995,
            msteps_asia_to_eu(
                pid["cn_steel"], pid["cn_steel"], pid["de_port"], pid["pl_assembly"], 50.0, 20000.0, 500.0
            ),
        ),
        "copper2": mat_inst(
            mstat["copper"],
            "BATCH-CU-ASIA-001",
            650,
            18.0,
            0.999,
            msteps_asia_to_eu(
                pid["cn_steel"], pid["cn_steel"], pid["de_port"], pid["pl_assembly"], 30.0, 20000.0, 500.0
            ),
        ),
        "al2": mat_inst(
            mstat["aluminum_6061"],
            "BATCH-AL-ASIA-001",
            820,
            10.0,
            0.985,
            msteps_asia_to_eu(
                pid["cn_steel"], pid["cn_steel"], pid["de_port"], pid["pl_assembly"], 40.0, 20000.0, 500.0
            ),
        ),
        "ndfeb2": mat_inst(
            mstat["ndfeb_magnet"],
            "BATCH-ND-ASIA-001",
            75,
            0.0,
            0.97,
            msteps_asia_to_eu(
                pid["cn_magnet"], pid["cn_magnet"], pid["de_port"], pid["pl_assembly"], 60.0, 19900.0, 500.0
            ),
        ),
        "sil2": mat_inst(
            mstat["silicone"],
            "BATCH-SIL-ASIA-001",
            170,
            8.0,
            0.96,
            msteps_asia_to_eu(
                pid["vn_plastics"], pid["vn_plastics"], pid["de_port"], pid["pl_assembly"], 20.0, 19000.0, 500.0
            ),
        ),
        "pp2": mat_inst(
            mstat["pp"],
            "BATCH-PP-ASIA-001",
            360,
            35.0,
            0.94,
            msteps_asia_to_eu(
                pid["vn_plastics"], pid["vn_plastics"], pid["de_port"], pid["pl_assembly"], 25.0, 19000.0, 500.0
            ),
        ),
        "abs2": mat_inst(
            mstat["abs"],
            "BATCH-ABS-ASIA-001",
            780,
            30.0,
            0.95,
            msteps_asia_to_eu(
                pid["vn_plastics"], pid["vn_plastics"], pid["de_port"], pid["pl_assembly"], 25.0, 19000.0, 500.0
            ),
        ),
        "pa66_2": mat_inst(
            mstat["pa66_gf30"],
            "BATCH-PA66-ASIA-001",
            150,
            12.0,
            0.93,
            msteps_asia_to_eu(
                pid["vn_plastics"], pid["vn_plastics"], pid["de_port"], pid["pl_assembly"], 25.0, 19000.0, 500.0
            ),
        ),
        "nbr2": mat_inst(
            mstat["nbr"],
            "BATCH-NBR-ASIA-001",
            65,
            10.0,
            0.92,
            msteps_asia_to_eu(
                pid["vn_plastics"], pid["vn_plastics"], pid["de_port"], pid["pl_assembly"], 25.0, 19000.0, 500.0
            ),
        ),
        "ptfe2": mat_inst(
            mstat["ptfe"],
            "BATCH-PTFE-ASIA-001",
            32,
            0.0,
            0.9999,
            msteps_asia_to_eu(
                pid["vn_plastics"], pid["vn_plastics"], pid["de_port"], pid["pl_assembly"], 25.0, 19000.0, 500.0
            ),
        ),
        "fr4_2": mat_inst(
            mstat["fr4"],
            "BATCH-FR4-ASIA-001",
            170,
            0.0,
            0.97,
            msteps_asia_to_eu(pid["my_pcb"], pid["my_pcb"], pid["de_port"], pid["pl_assembly"], 15.0, 18500.0, 500.0),
        ),
        "solder2": mat_inst(
            mstat["solder_snagcu"],
            "BATCH-SAC-ASIA-001",
            22,
            0.0,
            0.998,
            msteps_asia_to_eu(pid["my_pcb"], pid["my_pcb"], pid["de_port"], pid["pl_assembly"], 10.0, 18500.0, 500.0),
        ),
        "brass2": mat_inst(
            mstat["brass"],
            "BATCH-BR-TR-001",
            125,
            15.0,
            0.985,
            [
                ProductionStep(
                    description="Valve machining (TR)",
                    processedAt={"id": pid["tr_valve"], "collection": "place"},
                    ghgEmissionRecords=ghg_mix(
                        [
                            (
                                GHGScope.SCOPE_2,
                                None,
                                ActivityType.ELECTRICITY_CONSUMPTION,
                                300,
                                UnitCode.KWH,
                                0.45,
                                UnitCode.KG_CO2E_PER_KWH,
                                "TR grid electricity",
                                "metered",
                            ),
                            (
                                GHGScope.SCOPE_1,
                                None,
                                ActivityType.FUEL_CONSUMPTION,
                                60,
                                UnitCode.LTR,
                                2.68,
                                UnitCode.KG_CO2E_PER_KG,
                                "Natural gas for heat",
                                "estimate",
                            ),
                        ]
                    ),
                ),
                TransportStep(
                    processedAt={"id": pid["tr_valve"], "collection": "place"},
                    destination={"id": pid["pl_assembly"], "collection": "place"},
                    modeOfTransport=ModeOfTransport.ROAD,
                    distanceKM=1800.0,
                    reasonForTransport=TransportReason.SUPPLY_CHAIN,
                    ghgEmissionRecords=ghg_mix(
                        [
                            (
                                GHGScope.SCOPE_3,
                                Scope3Category.UPSTREAM_TRANSPORTATION_AND_DISTRIBUTION,
                                ActivityType.DISTANCE_TRAVELED,
                                1800.0,
                                UnitCode.KM,
                                0.09,
                                UnitCode.KG_CO2E_PER_KM,
                                "Long-haul trucking TR->PL",
                                "supply chain",
                            )
                        ]
                    ),
                ),
            ],
        ),
        "glass2": mat_inst(
            mstat["glass"],
            "BATCH-GL-ASIA-001",
            760,
            28.0,
            0.97,
            msteps_asia_to_eu(
                pid["vn_plastics"], pid["vn_plastics"], pid["de_port"], pid["pl_assembly"], 30.0, 19000.0, 500.0
            ),
        ),
    }
    for mi in BA.minst.values():
        await post_json(client, f"{BASE_URL}/material/instance/", mi)

    # PARTS (instance #2)
    def psteps_pl_assembly(origin_place: str, assembly_place: str):
        return [
            ProductionStep(
                description="Component fabrication (sub-supplier)",
                processedAt={"id": origin_place, "collection": "place"},
                ghgEmissionRecords=ghg_mix(
                    [
                        (
                            GHGScope.SCOPE_2,
                            None,
                            ActivityType.ELECTRICITY_CONSUMPTION,
                            250,
                            UnitCode.KWH,
                            0.55,
                            UnitCode.KG_CO2E_PER_KWH,
                            "Grid electricity (Asia)",
                            "metered",
                        ),
                        (
                            GHGScope.SCOPE_1,
                            None,
                            ActivityType.FUEL_CONSUMPTION,
                            20,
                            UnitCode.LTR,
                            2.68,
                            UnitCode.KG_CO2E_PER_KG,
                            "Diesel for generators",
                            "on-site genset",
                        ),
                    ]
                ),
            ),
            TransportStep(
                processedAt={"id": origin_place, "collection": "place"},
                destination={"id": pid["de_port"], "collection": "place"},
                modeOfTransport=ModeOfTransport.ROAD,
                distanceKM=40.0,
                reasonForTransport=TransportReason.SUPPLY_CHAIN,
                ghgEmissionRecords=ghg_mix(
                    [
                        (
                            GHGScope.SCOPE_3,
                            Scope3Category.UPSTREAM_TRANSPORTATION_AND_DISTRIBUTION,
                            ActivityType.DISTANCE_TRAVELED,
                            40.0,
                            UnitCode.KM,
                            0.08,
                            UnitCode.KG_CO2E_PER_KM,
                            "Local trucking",
                            "origin to port",
                        )
                    ]
                ),
            ),
            sea(pid["de_port"], assembly_place, 0.0),
            TransportStep(
                processedAt={"id": pid["de_port"], "collection": "place"},
                destination={"id": assembly_place, "collection": "place"},
                modeOfTransport=ModeOfTransport.ROAD,
                distanceKM=500.0,
                reasonForTransport=TransportReason.SUPPLY_CHAIN,
                ghgEmissionRecords=ghg_mix(
                    [
                        (
                            GHGScope.SCOPE_3,
                            Scope3Category.UPSTREAM_TRANSPORTATION_AND_DISTRIBUTION,
                            ActivityType.DISTANCE_TRAVELED,
                            500.0,
                            UnitCode.KM,
                            0.09,
                            UnitCode.KG_CO2E_PER_KM,
                            "EU trucking",
                            "port to assembly",
                        )
                    ]
                ),
            ),
        ]

    BA.leafs = {
        "burrs2": part_inst(
            pstat["burrs"], "BATCH-BURR-ASIA-001", psteps_pl_assembly(pid["cn_steel"], pid["pl_assembly"])
        ),
        "motor2": part_inst(
            pstat["motor"], "BATCH-MOTOR-ASIA-001", psteps_pl_assembly(pid["cn_magnet"], pid["pl_assembly"])
        ),
        "gearbox2": part_inst(
            pstat["gearbox"], "BATCH-GBX-ASIA-001", psteps_pl_assembly(pid["vn_plastics"], pid["pl_assembly"])
        ),
        "pump2": part_inst(
            pstat["pump"],
            "BATCH-PUMP-TR-001",
            [
                ProductionStep(
                    description="Pump assembly (TR)",
                    processedAt={"id": pid["tr_valve"], "collection": "place"},
                    ghgEmissionRecords=ghg_mix(
                        [
                            (
                                GHGScope.SCOPE_2,
                                None,
                                ActivityType.ELECTRICITY_CONSUMPTION,
                                180,
                                UnitCode.KWH,
                                0.45,
                                UnitCode.KG_CO2E_PER_KWH,
                                "TR grid electricity",
                                "metered",
                            )
                        ]
                    ),
                ),
                TransportStep(
                    processedAt={"id": pid["tr_valve"], "collection": "place"},
                    destination={"id": pid["pl_assembly"], "collection": "place"},
                    modeOfTransport=ModeOfTransport.ROAD,
                    distanceKM=1800.0,
                    reasonForTransport=TransportReason.SUPPLY_CHAIN,
                    ghgEmissionRecords=ghg_mix(
                        [
                            (
                                GHGScope.SCOPE_3,
                                Scope3Category.UPSTREAM_TRANSPORTATION_AND_DISTRIBUTION,
                                ActivityType.DISTANCE_TRAVELED,
                                1800.0,
                                UnitCode.KM,
                                0.09,
                                UnitCode.KG_CO2E_PER_KM,
                                "Long-haul trucking TR->PL",
                                "supply chain",
                            )
                        ]
                    ),
                ),
            ],
        ),
        "flowmeter2": part_inst(
            pstat["flowmeter"], "BATCH-FM-ASIA-001", psteps_pl_assembly(pid["my_pcb"], pid["pl_assembly"])
        ),
        "thermoblock2": part_inst(
            pstat["thermoblock"], "BATCH-TB-ASIA-001", psteps_pl_assembly(pid["cn_steel"], pid["pl_assembly"])
        ),
        "solenoid2": part_inst(
            pstat["solenoid"], "BATCH-SOL-TR-001", psteps_pl_assembly(pid["tr_valve"], pid["pl_assembly"])
        ),
        "hoses2": part_inst(
            pstat["hoses"], "BATCH-HOSE-ASIA-001", psteps_pl_assembly(pid["vn_plastics"], pid["pl_assembly"])
        ),
        "main_pcb2": part_inst(
            pstat["main_pcb"], "BATCH-PCB-ASIA-001", psteps_pl_assembly(pid["my_pcb"], pid["pl_assembly"])
        ),
        "ui_pcb2": part_inst(
            pstat["ui_pcb"], "BATCH-UI-ASIA-001", psteps_pl_assembly(pid["my_pcb"], pid["pl_assembly"])
        ),
        "drip_tray2": part_inst(
            pstat["drip_tray"], "BATCH-DRIP-ASIA-001", psteps_pl_assembly(pid["cn_steel"], pid["pl_assembly"])
        ),
        "waste_bin2": part_inst(
            pstat["waste_bin"], "BATCH-BIN-ASIA-001", psteps_pl_assembly(pid["vn_plastics"], pid["pl_assembly"])
        ),
        "water_tank2": part_inst(
            pstat["water_tank"], "BATCH-TANK-ASIA-001", psteps_pl_assembly(pid["vn_plastics"], pid["pl_assembly"])
        ),
        "steam_wand2": part_inst(
            pstat["steam_wand"], "BATCH-WAND-ASIA-001", psteps_pl_assembly(pid["cn_steel"], pid["pl_assembly"])
        ),
        "housing2": part_inst(
            pstat["housing"], "BATCH-HOUS-ASIA-001", psteps_pl_assembly(pid["vn_plastics"], pid["pl_assembly"])
        ),
    }
    # attach materials
    BA.leafs["burrs2"].compositeMaterials.extend([BA.minst["steel2"]])
    BA.leafs["motor2"].compositeMaterials.extend([BA.minst["copper2"], BA.minst["ndfeb2"]])
    BA.leafs["gearbox2"].compositeMaterials.extend([BA.minst["pa66_2"], BA.minst["steel2"]])
    BA.leafs["pump2"].compositeMaterials.extend([BA.minst["brass2"], BA.minst["steel2"], BA.minst["nbr2"]])
    BA.leafs["flowmeter2"].compositeMaterials.extend([BA.minst["brass2"], BA.minst["ptfe2"]])
    BA.leafs["thermoblock2"].compositeMaterials.extend([BA.minst["al2"], BA.minst["ptfe2"]])
    BA.leafs["solenoid2"].compositeMaterials.extend([BA.minst["brass2"], BA.minst["ptfe2"]])
    BA.leafs["hoses2"].compositeMaterials.extend([BA.minst["sil2"]])
    BA.leafs["main_pcb2"].compositeMaterials.extend([BA.minst["fr4_2"], BA.minst["solder2"], BA.minst["copper2"]])
    BA.leafs["ui_pcb2"].compositeMaterials.extend([BA.minst["fr4_2"], BA.minst["solder2"]])
    BA.leafs["drip_tray2"].compositeMaterials.extend([BA.minst["steel2"]])
    BA.leafs["waste_bin2"].compositeMaterials.extend([BA.minst["pp2"]])
    BA.leafs["water_tank2"].compositeMaterials.extend([BA.minst["glass2"]])
    BA.leafs["steam_wand2"].compositeMaterials.extend([BA.minst["steel2"]])
    BA.leafs["housing2"].compositeMaterials.extend([BA.minst["abs2"], BA.minst["steel2"]])

    for pi in BA.leafs.values():
        await post_json(client, f"{BASE_URL}/part/instance/", pi)

    # mid-level
    BA.mid["grinder2"] = part_inst(
        pstat["grinder"],
        "BATCH-GRIND-ASIA-001",
        [
            ProductionStep(
                description="Grinder assembly (PL)",
                processedAt={"id": pid["pl_assembly"], "collection": "place"},
                ghgEmissionRecords=ghg_mix(
                    [
                        (
                            GHGScope.SCOPE_2,
                            None,
                            ActivityType.ELECTRICITY_CONSUMPTION,
                            120,
                            UnitCode.KWH,
                            0.4,
                            UnitCode.KG_CO2E_PER_KWH,
                            "PL grid electricity",
                            "metered",
                        )
                    ]
                ),
            )
        ],
        modular=True,
    )
    BA.mid["grinder2"].compositeParts.extend([BA.leafs["motor2"], BA.leafs["burrs2"], BA.leafs["gearbox2"]])

    BA.mid["water_system2"] = part_inst(
        pstat["water_system"],
        "BATCH-WTR-ASIA-001",
        [
            ProductionStep(
                description="Water system assembly (PL)",
                processedAt={"id": pid["pl_assembly"], "collection": "place"},
                ghgEmissionRecords=ghg_mix(
                    [
                        (
                            GHGScope.SCOPE_2,
                            None,
                            ActivityType.ELECTRICITY_CONSUMPTION,
                            90,
                            UnitCode.KWH,
                            0.4,
                            UnitCode.KG_CO2E_PER_KWH,
                            "PL grid electricity",
                            "metered",
                        )
                    ]
                ),
            )
        ],
    )
    BA.mid["water_system2"].compositeParts.extend(
        [BA.leafs["pump2"], BA.leafs["flowmeter2"], BA.leafs["thermoblock2"], BA.leafs["solenoid2"], BA.leafs["hoses2"]]
    )

    BA.mid["electronics2"] = part_inst(
        pstat["electronics"],
        "BATCH-EL-ASIA-001",
        [
            ProductionStep(
                description="Electronics assembly (PL)",
                processedAt={"id": pid["pl_assembly"], "collection": "place"},
                ghgEmissionRecords=ghg_mix(
                    [
                        (
                            GHGScope.SCOPE_2,
                            None,
                            ActivityType.ELECTRICITY_CONSUMPTION,
                            150,
                            UnitCode.KWH,
                            0.4,
                            UnitCode.KG_CO2E_PER_KWH,
                            "PL grid electricity",
                            "metered",
                        )
                    ]
                ),
            )
        ],
    )
    BA.mid["electronics2"].compositeParts.extend([BA.leafs["main_pcb2"], BA.leafs["ui_pcb2"]])

    BA.mid["brew_group2"] = part_inst(
        pstat["brew_group"],
        "BATCH-BREW-ASIA-001",
        [
            ProductionStep(
                description="Brew group assembly (PL)",
                processedAt={"id": pid["pl_assembly"], "collection": "place"},
                ghgEmissionRecords=ghg_mix(
                    [
                        (
                            GHGScope.SCOPE_2,
                            None,
                            ActivityType.ELECTRICITY_CONSUMPTION,
                            110,
                            UnitCode.KWH,
                            0.4,
                            UnitCode.KG_CO2E_PER_KWH,
                            "PL grid electricity",
                            "metered",
                        )
                    ]
                ),
            )
        ],
        modular=True,
    )

    for mid in [BA.mid["grinder2"], BA.mid["water_system2"], BA.mid["electronics2"], BA.mid["brew_group2"]]:
        await post_json(client, f"{BASE_URL}/part/instance/", mid)

    # machine 2
    BA.machine = part_inst(
        pstat["machine"],
        "BATCH-MACH-ASIA-001",
        [
            ProductionStep(
                description="Final assembly (PL)",
                processedAt={"id": pid["pl_assembly"], "collection": "place"},
                ghgEmissionRecords=ghg_mix(
                    [
                        (
                            GHGScope.SCOPE_2,
                            None,
                            ActivityType.ELECTRICITY_CONSUMPTION,
                            220,
                            UnitCode.KWH,
                            0.4,
                            UnitCode.KG_CO2E_PER_KWH,
                            "PL grid electricity",
                            "metered",
                        ),
                        (
                            GHGScope.SCOPE_1,
                            None,
                            ActivityType.FUEL_CONSUMPTION,
                            10,
                            UnitCode.LTR,
                            2.68,
                            UnitCode.KG_CO2E_PER_KG,
                            "LPG for process heat",
                            "shop floor",
                        ),
                    ]
                ),
            ),
            TransportStep(
                processedAt={"id": pid["pl_assembly"], "collection": "place"},
                destination={"id": pid["cz_distribution"], "collection": "place"},
                modeOfTransport=ModeOfTransport.ROAD,
                distanceKM=90.0,
                reasonForTransport=TransportReason.SUPPLY_CHAIN,
                ghgEmissionRecords=ghg_mix(
                    [
                        (
                            GHGScope.SCOPE_3,
                            Scope3Category.DOWNSTREAM_TRANSPORTATION_AND_DISTRIBUTION,
                            ActivityType.DISTANCE_TRAVELED,
                            90.0,
                            UnitCode.KM,
                            0.09,
                            UnitCode.KG_CO2E_PER_KM,
                            "Regional trucking",
                            "to distribution",
                        )
                    ]
                ),
            ),
        ],
    )
    BA.machine.compositeParts.extend(
        [
            BA.leafs["housing2"],
            BA.mid["grinder2"],
            BA.mid["water_system2"],
            BA.mid["electronics2"],
            BA.mid["brew_group2"],
            BA.leafs["water_tank2"],
            BA.leafs["waste_bin2"],
            BA.leafs["drip_tray2"],
            BA.leafs["steam_wand2"],
        ]
    )
    await post_json(client, f"{BASE_URL}/part/instance/", BA.machine)

    # DPP instance #2 (shared static)
    declaration_date_2 = datetime(2022, 3, 1, tzinfo=timezone.utc)
    BA.dpp_static = dpp_static
    BA.dpp_instance = DPPInstance(
        dppStaticLink={"id": dpp_static.id, "collection": "dpp_static"},
        partInstanceLink={"id": BA.machine.id, "collection": "part_instance"},
        dateOfDeclaration=declaration_date_2,
        cleaningCount=11,
        chalkCount=4,
        brewingCount=410,
        coffeeGrindingCount=410,
        operatingHRS=7800,
        discontinued=False,
        backupLink="https://example.com/backup",
    )
    dpp2_resp = await post_json(client, f"{BASE_URL}/dpp/instance/", BA.dpp_instance)
    BA.dpp_instance = DPPInstance.model_validate(dpp2_resp)

    return BA


async def add_services_instance_2(
    client: httpx.AsyncClient, *, BA: BuildArtifacts, places: Dict[str, Place], pstat: Dict[str, PartStatic]
) -> None:
    def dt(d, m, y, h=9, minute=0):
        return datetime(y, m, d, h, minute, tzinfo=timezone.utc)

    # 1) Repair – 7.11.2023
    await post_json(
        client,
        f"{BASE_URL}/dpp/instance/{BA.dpp_instance.id}/service/repair/",
        RepairServiceStep(
            processedAt={"id": places["at_service"].id, "collection": "place"},
            costEur=75.0,
            diagnose="Seal wear in 3-way valve",
            observedSymptoms=["Intermittent dripping", "Pressure fluctuations"],
            repairedPartId=BA.leafs["solenoid2"].id,
            ghgEmissionRecords=ghg_mix(
                [
                    (
                        GHGScope.SCOPE_3,
                        Scope3Category.BUSINESS_TRAVEL,
                        ActivityType.DISTANCE_TRAVELED,
                        10.0,
                        UnitCode.KM,
                        0.2,
                        UnitCode.KG_CO2E_PER_KM,
                        "Technician travel (van)",
                        "service callout",
                    ),
                    (
                        GHGScope.SCOPE_1,
                        None,
                        ActivityType.FUEL_CONSUMPTION,
                        2.0,
                        UnitCode.LTR,
                        2.68,
                        UnitCode.KG_CO2E_PER_KG,
                        "Workshop heater fuel",
                        "repair bay",
                    ),
                ]
            ),
            beginDate=dt(7, 11, 2023, 10),
            endDate=dt(7, 11, 2023, 12),
        ),
    )

    # 1b) Repair – 10.12.2023
    await post_json(
        client,
        f"{BASE_URL}/dpp/instance/{BA.dpp_instance.id}/service/repair/",
        RepairServiceStep(
            processedAt={"id": places["at_service"].id, "collection": "place"},
            costEur=49.0,
            diagnose="Loose clamp on silicone hose",
            observedSymptoms=["Water leakage"],
            repairedPartId=BA.leafs["hoses2"].id,
            ghgEmissionRecords=ghg_mix(
                [
                    (
                        GHGScope.SCOPE_1,
                        None,
                        ActivityType.FUEL_CONSUMPTION,
                        0.2,
                        UnitCode.LTR,
                        2.68,
                        UnitCode.KG_CO2E_PER_KG,
                        "Bench compressor",
                        "tightening/pressure test",
                    )
                ]
            ),
            beginDate=dt(10, 12, 2023, 14),
            endDate=dt(10, 12, 2023, 15),
        ),
    )

    # 2) Replace – 15.4.2024
    new_burrs_2 = part_inst(
        pstat["burrs"],
        "BATCH-BURR-REPL-ASI-002",
        [
            ProductionStep(
                description="Replacement burrs (PL stock)",
                processedAt={"id": places["pl_assembly"].id, "collection": "place"},
                ghgEmissionRecords=ghg_mix(
                    [
                        (
                            GHGScope.SCOPE_2,
                            None,
                            ActivityType.ELECTRICITY_CONSUMPTION,
                            30,
                            UnitCode.KWH,
                            0.4,
                            UnitCode.KG_CO2E_PER_KWH,
                            "PL grid electricity",
                            "packaging/inspection",
                        )
                    ]
                ),
            ),
            TransportStep(
                processedAt={"id": places["pl_assembly"].id, "collection": "place"},
                destination={"id": places["at_service"].id, "collection": "place"},
                modeOfTransport=ModeOfTransport.ROAD,
                distanceKM=380.0,
                reasonForTransport=TransportReason.SUPPLY_CHAIN,
                ghgEmissionRecords=ghg_mix(
                    [
                        (
                            GHGScope.SCOPE_3,
                            Scope3Category.DOWNSTREAM_TRANSPORTATION_AND_DISTRIBUTION,
                            ActivityType.DISTANCE_TRAVELED,
                            380.0,
                            UnitCode.KM,
                            0.09,
                            UnitCode.KG_CO2E_PER_KM,
                            "Courier van",
                            "to service hub",
                        )
                    ]
                ),
            ),
        ],
    )
    await post_json(
        client,
        f"{BASE_URL}/dpp/instance/{BA.dpp_instance.id}/service/replace/",
        ReplaceServiceStep(
            processedAt={"id": places["at_service"].id, "collection": "place"},
            costEur=59.0,
            diagnose="Dull burrs causing inconsistent grind size",
            observedSymptoms=["Increased extraction time variance", "Uneven puck surface"],
            replacedPartId=BA.leafs["burrs2"].id,
            newPart=new_burrs_2,
            ghgEmissionRecords=ghg_mix(
                [
                    (
                        GHGScope.SCOPE_1,
                        None,
                        ActivityType.FUEL_CONSUMPTION,
                        1.0,
                        UnitCode.LTR,
                        2.68,
                        UnitCode.KG_CO2E_PER_KG,
                        "Shop tools (compressed air)",
                        "on-bench",
                    )
                ]
            ),
            beginDate=dt(15, 4, 2024, 9),
            endDate=dt(15, 4, 2024, 11),
        ),
    )

    # 3) Cleaning – 22.9.2024
    await post_json(
        client,
        f"{BASE_URL}/dpp/instance/{BA.dpp_instance.id}/service/cleaning/",
        CleaningServiceStep(
            processedAt={"id": places["at_service"].id, "collection": "place"},
            costEur=25.0,
            cleanedPartId=BA.mid["brew_group2"].id,
            cleaningMethod="Ultrasonic soak + lubrication",
            diagnose="Residue buildup",
            observedSymptoms=["Sticky motion", "Grinding noise at start"],
            ghgEmissionRecords=ghg_mix(
                [
                    (
                        GHGScope.SCOPE_2,
                        None,
                        ActivityType.ELECTRICITY_CONSUMPTION,
                        5.0,
                        UnitCode.KWH,
                        0.4,
                        UnitCode.KG_CO2E_PER_KWH,
                        "Ultrasonic bath electricity",
                        "measured",
                    ),
                    (
                        GHGScope.SCOPE_3,
                        Scope3Category.WASTE_GENERATED_IN_OPERATIONS,
                        ActivityType.WASTE_TREATMENT,
                        1.0,
                        UnitCode.KG,
                        0.5,
                        UnitCode.KG_CO2E_PER_KG,
                        "Spent cleaning solution",
                        "disposal",
                    ),
                ]
            ),
            beginDate=dt(22, 9, 2024, 13),
            endDate=dt(22, 9, 2024, 15),
        ),
    )

    # 3b) Cleaning – 5.2.2025
    await post_json(
        client,
        f"{BASE_URL}/dpp/instance/{BA.dpp_instance.id}/service/cleaning/",
        CleaningServiceStep(
            processedAt={"id": places["at_service"].id, "collection": "place"},
            costEur=19.0,
            cleanedPartId=BA.mid["water_system2"].id,
            cleaningMethod="Descale cycle",
            diagnose="Limescale accumulation",
            observedSymptoms=["Noisy pump priming", "Flow oscillation"],
            ghgEmissionRecords=ghg_mix(
                [
                    (
                        GHGScope.SCOPE_2,
                        None,
                        ActivityType.ELECTRICITY_CONSUMPTION,
                        2.0,
                        UnitCode.KWH,
                        0.4,
                        UnitCode.KG_CO2E_PER_KWH,
                        "Descale heater cycle",
                        "metered",
                    )
                ]
            ),
            beginDate=dt(5, 2, 2025, 10),
            endDate=dt(5, 2, 2025, 11),
        ),
    )

    # 4) Refurbishment – 1.3.2025
    await post_json(
        client,
        f"{BASE_URL}/dpp/instance/{BA.dpp_instance.id}/service/refurbishment/",
        RefurbishmentServiceStep(
            processedAt={"id": places["at_service"].id, "collection": "place"},
            costEur=120.0,
            diagnose="UI refresh and pump inspection",
            repairedPartIds=[BA.leafs["pump2"].id],
            cleanedPartIds=[BA.mid["brew_group2"].id],
            replacedAndNewParts=[],
            ghgEmissionRecords=ghg_mix(
                [
                    (
                        GHGScope.SCOPE_2,
                        None,
                        ActivityType.ELECTRICITY_CONSUMPTION,
                        12.0,
                        UnitCode.KWH,
                        0.4,
                        UnitCode.KG_CO2E_PER_KWH,
                        "Workshop electricity",
                        "metered",
                    ),
                    (
                        GHGScope.SCOPE_1,
                        None,
                        ActivityType.FUEL_CONSUMPTION,
                        0.5,
                        UnitCode.LTR,
                        2.68,
                        UnitCode.KG_CO2E_PER_KG,
                        "Space heater",
                        "winter refurb",
                    ),
                ]
            ),
            beginDate=dt(1, 3, 2025, 10),
            endDate=dt(1, 3, 2025, 12),
        ),
    )

    # 5) Replace – 18.6.2025 (UI PCB)
    new_ui_2 = part_inst(
        pstat["ui_pcb"],
        "BATCH-UI-REPL-2025-001",
        [
            ProductionStep(
                description="UI PCB from PL stock",
                processedAt={"id": places["pl_assembly"].id, "collection": "place"},
                ghgEmissionRecords=ghg_mix(
                    [
                        (
                            GHGScope.SCOPE_2,
                            None,
                            ActivityType.ELECTRICITY_CONSUMPTION,
                            20,
                            UnitCode.KWH,
                            0.4,
                            UnitCode.KG_CO2E_PER_KWH,
                            "QC & packaging",
                            "warehouse",
                        )
                    ]
                ),
            ),
            TransportStep(
                processedAt={"id": places["pl_assembly"].id, "collection": "place"},
                destination={"id": places["at_service"].id, "collection": "place"},
                modeOfTransport=ModeOfTransport.ROAD,
                distanceKM=380.0,
                reasonForTransport=TransportReason.SUPPLY_CHAIN,
                ghgEmissionRecords=ghg_mix(
                    [
                        (
                            GHGScope.SCOPE_3,
                            Scope3Category.DOWNSTREAM_TRANSPORTATION_AND_DISTRIBUTION,
                            ActivityType.DISTANCE_TRAVELED,
                            380.0,
                            UnitCode.KM,
                            0.09,
                            UnitCode.KG_CO2E_PER_KM,
                            "Courier van",
                            "to service hub",
                        )
                    ]
                ),
            ),
        ],
    )
    await post_json(
        client,
        f"{BASE_URL}/dpp/instance/{BA.dpp_instance.id}/service/replace/",
        ReplaceServiceStep(
            processedAt={"id": places["at_service"].id, "collection": "place"},
            costEur=89.0,
            diagnose="Stuck button matrix on UI board",
            observedSymptoms=["Buttons unresponsive"],
            replacedPartId=BA.leafs["ui_pcb2"].id,
            newPart=new_ui_2,
            ghgEmissionRecords=ghg_mix(
                [
                    (
                        GHGScope.SCOPE_1,
                        None,
                        ActivityType.FUEL_CONSUMPTION,
                        0.3,
                        UnitCode.LTR,
                        2.68,
                        UnitCode.KG_CO2E_PER_KG,
                        "Rework station compressor",
                        "electronics bench",
                    )
                ]
            ),
            beginDate=dt(18, 6, 2025, 9),
            endDate=dt(18, 6, 2025, 10, 30),
        ),
    )


# --- Misc -----------------------------------------------------------------
async def upload_images_if_available(client: httpx.AsyncClient, dpp_static: DPPStatic) -> None:
    try:
        image_dir = Path(__file__).resolve().parent / "images"
        filenames = ["machine1.png", "machine2.png"]
        files = [
            ("files", (fn, open(image_dir / fn, "rb"), "image/png")) for fn in filenames if (image_dir / fn).exists()
        ]
        if files:
            r = await client.post(f"{BASE_URL}/dpp/{dpp_static.id}/images/", files=files)
            for _, f in files:
                f[1].close()
            r.raise_for_status()
            print("Uploaded images:", r.json())
    except Exception as e:
        logger.warning("Skipping image upload: %s", e)


# -----------------------------
# MAIN
# -----------------------------
async def init():
    logger.info("Seeding rich coffee machine example…")
    await init_db_with_beanie()

    async with httpx.AsyncClient() as client:
        # 1) Core statics & locations
        org_ids, _orgs = await register_orgs(client)
        places, pid = await register_places(client, org_ids)
        mstat = await register_material_statics(client, org_ids)
        pstat = await register_part_statics(client, org_ids)

        # 2) Instance #1 (EU-centric)
        build1 = await build_instance_1(client, org_ids=org_ids, places=places, pid=pid, mstat=mstat, pstat=pstat)
        await add_services_instance_1(client, BA=build1, places=places, pstat=pstat)

        # 3) Instance #2 (Asia supply → EU assembly)
        build2 = await build_instance_2(
            client, org_ids=org_ids, places=places, pid=pid, mstat=mstat, pstat=pstat, dpp_static=build1.dpp_static
        )
        await add_services_instance_2(client, BA=build2, places=places, pstat=pstat)

        # 4) Optional images for the shared static
        await upload_images_if_available(client, build1.dpp_static)

    logger.info("Seeding JURA Z10 done.")
    return 0
