"""
Seeded service concept registry for free-text harmonization.

This module contains domain knowledge only: canonical diagnosis and symptom
concepts, aliases/examples, and optional metadata. Matching logic stays in
free_text.py, so the registry can be reviewed and extended without changing the
normalization algorithm.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


TextConceptKind = Literal["symptom", "diagnosis"]

@dataclass(frozen=True)
class TextConcept:
    """
    Canonical free-text concept used for service-text harmonization.

    Attributes:
        concept_id: Stable machine-readable identifier.
        label: Human-readable canonical label.
        kind: Concept registry kind, e.g. symptom or diagnosis.
        description: Short semantic description used for embedding matching.
        examples: Seed phrases from the prototype data and dirty variants.
        applicable_service_types: Optional service-step types where the concept is especially plausible.
        related_part_keywords: Optional part-name keywords that can later be used for context-aware scoring.
    """

    concept_id: str
    label: str
    kind: TextConceptKind
    description: str
    examples: tuple[str, ...] = ()
    applicable_service_types: tuple[str, ...] = ()
    related_part_keywords: tuple[str, ...] = ()


SYMPTOM_CONCEPTS: tuple[TextConcept, ...] = (
    TextConcept(
        concept_id="water_leakage",
        label="Water leakage or dripping",
        kind="symptom",
        description="water leaks, dripping after brewing, intermittent dripping, visible leakage around hoses or valves",
        examples=(
            "Water leakage",
            "Dripping after brew",
            "Intermittent dripping",
            "water leaking",
            "leaking after brew",
        ),
        applicable_service_types=("RepairServiceStep", "ReplaceServiceStep", "RefurbishmentServiceStep"),
        related_part_keywords=("water_system", "hose", "hoses", "seal", "valve", "solenoid"),
    ),
    TextConcept(
        concept_id="low_brew_pressure",
        label="Low or unstable brew pressure",
        kind="symptom",
        description="low brew pressure, pressure fluctuations, irregular pressure ramp, flow oscillation during brewing",
        examples=(
            "Low brew pressure",
            "Pressure fluctuations",
            "Irregular pressure ramp",
            "Flow oscillation",
        ),
        applicable_service_types=("RepairServiceStep", "ReplaceServiceStep", "CleaningServiceStep"),
        related_part_keywords=("water_system", "pump", "flowmeter", "thermoblock", "solenoid"),
    ),
    TextConcept(
        concept_id="inconsistent_grind_or_extraction",
        label="Inconsistent grind or extraction",
        kind="symptom",
        description="watery espresso, channeling, inconsistent grind, uneven puck surface, longer or unstable extraction",
        examples=(
            "Watery espresso",
            "Channeling",
            "Inconsistent grind",
            "Increased extraction time variance",
            "Uneven puck surface",
            "Longer extraction",
        ),
        applicable_service_types=("RepairServiceStep", "ReplaceServiceStep", "CleaningServiceStep"),
        related_part_keywords=("grinder", "burr", "burrs", "brew_group"),
    ),
    TextConcept(
        concept_id="brew_group_friction",
        label="Brew group friction or sticky motion",
        kind="symptom",
        description="brew group moves slowly, sticky motion, creaking noise, slower cycle or mechanical friction",
        examples=(
            "Creaking noise",
            "Creak noise",
            "Slower cycle",
            "Sticky motion",
        ),
        applicable_service_types=("CleaningServiceStep", "RepairServiceStep", "RefurbishmentServiceStep"),
        related_part_keywords=("brew_group", "brew", "piston", "chamber"),
    ),
    TextConcept(
        concept_id="limescale_flow_restriction",
        label="Limescale or water-flow restriction",
        kind="symptom",
        description="reduced flow rate, steam sputtering, noisy pump priming, water circuit restriction caused by limescale",
        examples=(
            "Reduced flow rate",
            "Steam sputtering",
            "Noisy pump priming",
            "Flow oscillation",
        ),
        applicable_service_types=("CleaningServiceStep", "RepairServiceStep"),
        related_part_keywords=("water_system", "pump", "thermoblock", "flowmeter", "hoses"),
    ),
    TextConcept(
        concept_id="grinder_motor_issue",
        label="Grinder motor or start-up issue",
        kind="symptom",
        description="intermittent grinding noise, grinder stalls on start, abnormal grinding noise at start",
        examples=(
            "Intermittent grinding noise",
            "Stall on start",
            "Grinding noise at start",
        ),
        applicable_service_types=("RepairServiceStep", "ReplaceServiceStep"),
        related_part_keywords=("grinder", "motor", "gearbox"),
    ),
    TextConcept(
        concept_id="ui_input_failure",
        label="User-interface input failure",
        kind="symptom",
        description="buttons do not respond, stuck button matrix, user interface input not accepted",
        examples=(
            "Buttons unresponsive",
            "buttons do not respond",
            "button is stuck",
        ),
        applicable_service_types=("RepairServiceStep", "ReplaceServiceStep", "RefurbishmentServiceStep"),
        related_part_keywords=("ui", "pcb", "electronics", "button", "display"),
    ),
)


DIAGNOSIS_CONCEPTS: tuple[TextConcept, ...] = (
    TextConcept(
        concept_id="seal_wear_or_leak_path",
        label="Seal wear or leak path",
        kind="diagnosis",
        description="worn seal, worn valve seal, loose hose clamp, damaged gasket or leak path in water circuit",
        examples=(
            "Seal wear in 3-way valve",
            "Loose clamp on silicone hose",
            "worn seal",
            "valve seal wear",
        ),
        applicable_service_types=("RepairServiceStep", "ReplaceServiceStep", "RefurbishmentServiceStep"),
        related_part_keywords=("seal", "valve", "solenoid", "hose", "hoses", "water_system"),
    ),
    TextConcept(
        concept_id="dull_burrs",
        label="Dull grinder burrs",
        kind="diagnosis",
        description="grinder burrs are worn or dull and cause inconsistent particle size or extraction quality",
        examples=(
            "Dull burrs",
            "Dull burrs causing inconsistent grind size",
            "worn grinder burrs",
        ),
        applicable_service_types=("ReplaceServiceStep", "RepairServiceStep", "RefurbishmentServiceStep"),
        related_part_keywords=("grinder", "burr", "burrs"),
    ),
    TextConcept(
        concept_id="residue_buildup",
        label="Residue buildup",
        kind="diagnosis",
        description="coffee residue, oil or dirt buildup in brew group causing friction or sticky movement",
        examples=(
            "Residue buildup",
            "Brew group friction",
            "coffee residue buildup",
        ),
        applicable_service_types=("CleaningServiceStep", "RefurbishmentServiceStep"),
        related_part_keywords=("brew_group", "brew", "piston", "chamber"),
    ),
    TextConcept(
        concept_id="limescale_buildup",
        label="Limescale buildup",
        kind="diagnosis",
        description="lime scale or mineral accumulation in water system, thermoblock, pump or flow path",
        examples=(
            "Lime scale buildup",
            "Limescale accumulation",
            "scale buildup",
        ),
        applicable_service_types=("CleaningServiceStep", "RepairServiceStep", "RefurbishmentServiceStep"),
        related_part_keywords=("water_system", "thermoblock", "pump", "flowmeter", "hoses"),
    ),
    TextConcept(
        concept_id="motor_brush_wear",
        label="Motor brush wear",
        kind="diagnosis",
        description="grinder motor brush wear or motor wear causing intermittent start or grinding noise",
        examples=(
            "Motor brush wear",
            "worn motor brushes",
        ),
        applicable_service_types=("RepairServiceStep", "ReplaceServiceStep"),
        related_part_keywords=("grinder", "motor"),
    ),
    TextConcept(
        concept_id="check_valve_fatigue",
        label="Check valve fatigue",
        kind="diagnosis",
        description="check valve fatigue or pump valve problem causing unstable pressure ramp",
        examples=(
            "Check valve fatigue",
            "pump check valve fatigue",
        ),
        applicable_service_types=("RepairServiceStep", "ReplaceServiceStep"),
        related_part_keywords=("pump", "valve", "water_system"),
    ),
    TextConcept(
        concept_id="ui_board_fault",
        label="UI board or button-matrix fault",
        kind="diagnosis",
        description="stuck button matrix, defective user interface board or input electronics fault",
        examples=(
            "Stuck button matrix on UI board",
            "UI board fault",
            "button matrix fault",
        ),
        applicable_service_types=("RepairServiceStep", "ReplaceServiceStep", "RefurbishmentServiceStep"),
        related_part_keywords=("ui", "pcb", "electronics", "button", "display"),
    ),
    TextConcept(
        concept_id="pump_inspection_or_ui_refresh",
        label="Pump inspection and UI refresh",
        kind="diagnosis",
        description="refurbishment action combining user interface refresh and pump inspection",
        examples=(
            "UI refresh and pump inspection",
            "pump inspection and UI refresh",
        ),
        applicable_service_types=("RefurbishmentServiceStep", "RemanufacturingServiceStep"),
        related_part_keywords=("pump", "ui", "electronics"),
    ),
)


TEXT_CONCEPTS_BY_KIND: dict[TextConceptKind, tuple[TextConcept, ...]] = {
    "symptom": SYMPTOM_CONCEPTS,
    "diagnosis": DIAGNOSIS_CONCEPTS,
}

