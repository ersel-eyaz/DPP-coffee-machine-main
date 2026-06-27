"""
Evidence-backed service relation hints.

The entries in this module are not hard domain rules. They are compact,
reviewable relation evidence derived from the legacy DPP seed service examples
and mapped to the service concept inventory. The anomaly layer can use them to
raise review prompts when a diagnosis is paired with an unusual service part.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceRelationEvidence:
    """One legacy-seed-supported service relation pattern."""

    evidence_id: str
    diagnosis_concept: str
    symptom_concepts: tuple[str, ...]
    service_types: tuple[str, ...]
    part_keywords: tuple[str, ...]
    source: str
    note: str
    support_level: str = "legacy_seed"


@dataclass(frozen=True)
class ServiceConceptRelationHint:
    """Soft LLM/evidence-derived service relation hint for review prompts."""

    hint_id: str
    concept_id: str
    concept_kind: str
    service_types: tuple[str, ...]
    part_keywords: tuple[str, ...]
    source: str
    support_level: str


SERVICE_RELATION_EVIDENCE: tuple[ServiceRelationEvidence, ...] = (
    ServiceRelationEvidence(
        evidence_id="legacy_seal_valve_leakage_repair",
        diagnosis_concept="seal_issue",
        symptom_concepts=("water_leakage", "reduced_water_flow_or_low_pressure"),
        service_types=("RepairServiceStep", "ReplaceServiceStep", "RefurbishmentServiceStep"),
        part_keywords=("seal", "gasket", "valve", "solenoid", "hose", "water_system"),
        source="seed_jura.py; seed_dpp_multilevel.py",
        note="Seal or valve wear appears with leakage and low-pressure symptoms.",
    ),
    ServiceRelationEvidence(
        evidence_id="legacy_limescale_water_system_cleaning",
        diagnosis_concept="limescale_or_scale_build_up",
        symptom_concepts=("reduced_water_flow_or_low_pressure", "steam_wand_not_working", "not_pumping_water"),
        service_types=("CleaningServiceStep", "RepairServiceStep", "RefurbishmentServiceStep"),
        part_keywords=("water_system", "thermoblock", "pump", "flowmeter", "hose"),
        source="seed_dpp_multilevel.py",
        note="Limescale examples are linked to water-system cleaning and weak-flow or steam symptoms.",
    ),
    ServiceRelationEvidence(
        evidence_id="legacy_burr_replacement",
        diagnosis_concept="dull_burrs",
        symptom_concepts=("grinder_not_working", "no_coffee_output"),
        service_types=("ReplaceServiceStep", "RepairServiceStep", "RefurbishmentServiceStep"),
        part_keywords=("burr", "burrs", "grinder"),
        source="seed_jura.py; seed_dpp_multilevel.py",
        note="Dull burr examples are linked to burr replacement and grinder/extraction symptoms.",
        support_level="legacy_seed_review_candidate",
    ),
    ServiceRelationEvidence(
        evidence_id="legacy_brew_group_cleaning",
        diagnosis_concept="brew_group_residue_or_friction",
        symptom_concepts=("grinder_not_working",),
        service_types=("CleaningServiceStep", "RefurbishmentServiceStep"),
        part_keywords=("brew_group", "brew", "piston", "chamber"),
        source="seed_jura.py; seed_dpp_multilevel.py",
        note="Brew-group residue/friction appears in cleaning service examples.",
        support_level="legacy_seed_review_candidate",
    ),
    ServiceRelationEvidence(
        evidence_id="legacy_motor_brush_repair",
        diagnosis_concept="motor_brush_wear",
        symptom_concepts=("grinder_not_working",),
        service_types=("RepairServiceStep", "ReplaceServiceStep"),
        part_keywords=("motor", "grinder"),
        source="seed_dpp_multilevel.py",
        note="Motor brush wear is linked to grinder symptoms and motor repair.",
        support_level="legacy_seed_review_candidate",
    ),
    ServiceRelationEvidence(
        evidence_id="legacy_check_valve_pump_replacement",
        diagnosis_concept="check_valve_fatigue",
        symptom_concepts=("reduced_water_flow_or_low_pressure",),
        service_types=("RepairServiceStep", "ReplaceServiceStep"),
        part_keywords=("pump", "valve", "water_system"),
        source="seed_dpp_multilevel.py",
        note="Check-valve fatigue is linked to pump replacement and pressure symptoms.",
        support_level="legacy_seed_review_candidate",
    ),
    ServiceRelationEvidence(
        evidence_id="legacy_hose_clamp_leakage_repair",
        diagnosis_concept="loose_hose_or_clamp_issue",
        symptom_concepts=("water_leakage",),
        service_types=("RepairServiceStep",),
        part_keywords=("hose", "hoses", "clamp", "water_system"),
        source="seed_dpp_multilevel.py",
        note="Loose hose clamp appears with water leakage and hose repair.",
        support_level="legacy_seed_review_candidate",
    ),
    ServiceRelationEvidence(
        evidence_id="legacy_ui_button_replacement",
        diagnosis_concept="switch_or_button_fault",
        symptom_concepts=("power_on_but_no_operation",),
        service_types=("RepairServiceStep", "ReplaceServiceStep", "RefurbishmentServiceStep"),
        part_keywords=("ui", "pcb", "electronics", "button", "display", "switch"),
        source="seed_dpp_multilevel.py",
        note="Button matrix faults are linked to UI PCB replacement.",
    ),
    ServiceRelationEvidence(
        evidence_id="ords_pump_fault_flow_context",
        diagnosis_concept="pump_fault",
        symptom_concepts=("not_pumping_water", "no_water_flow", "reduced_water_flow_or_low_pressure"),
        service_types=("RepairServiceStep", "ReplaceServiceStep", "CleaningServiceStep"),
        part_keywords=("pump", "water_system", "hose", "valve"),
        source="ORDS concept inventory + legacy pump/pressure seed context",
        note="Pump faults are expected around pump and water-flow components.",
        support_level="ords_plus_legacy_context",
    ),
)


SERVICE_CONCEPT_RELATION_HINTS: tuple[ServiceConceptRelationHint, ...] = (
    ServiceConceptRelationHint(
        hint_id="llm_minimal_air_in_pump_or_pipe",
        concept_id="air_in_pump_or_pipe",
        concept_kind="diagnosis",
        service_types=("RepairServiceStep",),
        part_keywords=("pump", "pipe", "hose"),
        source="llm_vocabulary_enrichment_minimal_output_2026-06-27.json",
        support_level="minimal_evidence_llm_candidate",
    ),
    ServiceConceptRelationHint(
        hint_id="llm_minimal_blocked_or_disconnected_flow_path",
        concept_id="blocked_or_disconnected_flow_path",
        concept_kind="diagnosis",
        service_types=("RepairServiceStep",),
        part_keywords=("tubing", "hose", "clamp", "pump", "pipe"),
        source="llm_vocabulary_enrichment_minimal_output_2026-06-27.json",
        support_level="minimal_evidence_llm_candidate",
    ),
    ServiceConceptRelationHint(
        hint_id="llm_minimal_blocked_steam_nozzle",
        concept_id="blocked_steam_nozzle",
        concept_kind="diagnosis",
        service_types=("CleaningServiceStep", "RepairServiceStep"),
        part_keywords=("nozzle", "steam", "steamer"),
        source="llm_vocabulary_enrichment_minimal_output_2026-06-27.json",
        support_level="minimal_evidence_llm_candidate",
    ),
    ServiceConceptRelationHint(
        hint_id="llm_minimal_dirty_or_corroded_contacts",
        concept_id="dirty_or_corroded_contacts",
        concept_kind="diagnosis",
        service_types=("CleaningServiceStep", "RepairServiceStep"),
        part_keywords=("switch", "button", "contacts", "ui"),
        source="llm_vocabulary_enrichment_minimal_output_2026-06-27.json",
        support_level="minimal_evidence_llm_candidate",
    ),
    ServiceConceptRelationHint(
        hint_id="llm_minimal_fuse_or_thermal_fuse_fault",
        concept_id="fuse_or_thermal_fuse_fault",
        concept_kind="diagnosis",
        service_types=("RepairServiceStep", "ReplaceServiceStep"),
        part_keywords=("fuse", "thermal_fuse", "plug"),
        source="llm_vocabulary_enrichment_minimal_output_2026-06-27.json",
        support_level="minimal_evidence_llm_candidate",
    ),
    ServiceConceptRelationHint(
        hint_id="llm_minimal_heating_element_failure",
        concept_id="heating_element_failure",
        concept_kind="diagnosis",
        service_types=("RepairServiceStep",),
        part_keywords=("heating_element", "element", "boiler"),
        source="llm_vocabulary_enrichment_minimal_output_2026-06-27.json",
        support_level="minimal_evidence_llm_candidate",
    ),
    ServiceConceptRelationHint(
        hint_id="llm_minimal_limescale_or_scale_build_up",
        concept_id="limescale_or_scale_build_up",
        concept_kind="diagnosis",
        service_types=("CleaningServiceStep",),
        part_keywords=("water_circuit", "pipe", "hose", "boiler", "nozzle", "pump"),
        source="llm_vocabulary_enrichment_minimal_output_2026-06-27.json",
        support_level="minimal_evidence_llm_candidate",
    ),
    ServiceConceptRelationHint(
        hint_id="llm_minimal_pod_mechanism_or_lid_fault",
        concept_id="pod_mechanism_or_lid_fault",
        concept_kind="diagnosis",
        service_types=("RepairServiceStep", "ReplaceServiceStep"),
        part_keywords=("pod", "lid", "handle", "plunger", "capsule"),
        source="llm_vocabulary_enrichment_minimal_output_2026-06-27.json",
        support_level="minimal_evidence_llm_candidate",
    ),
    ServiceConceptRelationHint(
        hint_id="llm_minimal_pump_fault",
        concept_id="pump_fault",
        concept_kind="diagnosis",
        service_types=("RepairServiceStep",),
        part_keywords=("pump", "motor", "valve"),
        source="llm_vocabulary_enrichment_minimal_output_2026-06-27.json",
        support_level="minimal_evidence_llm_candidate",
    ),
    ServiceConceptRelationHint(
        hint_id="llm_minimal_seal_issue",
        concept_id="seal_issue",
        concept_kind="diagnosis",
        service_types=("CleaningServiceStep", "RepairServiceStep", "ReplaceServiceStep"),
        part_keywords=("seal", "gasket", "valve", "hose", "clamp"),
        source="llm_vocabulary_enrichment_minimal_output_2026-06-27.json",
        support_level="minimal_evidence_llm_candidate",
    ),
    ServiceConceptRelationHint(
        hint_id="llm_minimal_switch_or_button_fault",
        concept_id="switch_or_button_fault",
        concept_kind="diagnosis",
        service_types=("RepairServiceStep",),
        part_keywords=("switch", "button", "ui", "pcb"),
        source="llm_vocabulary_enrichment_minimal_output_2026-06-27.json",
        support_level="minimal_evidence_llm_candidate",
    ),
    ServiceConceptRelationHint(
        hint_id="llm_minimal_valve_or_solenoid_fault",
        concept_id="valve_or_solenoid_fault",
        concept_kind="diagnosis",
        service_types=("RepairServiceStep",),
        part_keywords=("valve", "solenoid", "steam", "check_valve", "seal"),
        source="llm_vocabulary_enrichment_minimal_output_2026-06-27.json",
        support_level="minimal_evidence_llm_candidate",
    ),
    ServiceConceptRelationHint(
        hint_id="llm_minimal_thermostat_or_rheostat_fault",
        concept_id="thermostat_or_rheostat_fault",
        concept_kind="diagnosis",
        service_types=("RepairServiceStep", "ReplaceServiceStep"),
        part_keywords=("thermostat", "rheostat", "heating"),
        source="llm_vocabulary_enrichment_minimal_output_2026-06-27.json",
        support_level="minimal_evidence_llm_review_candidate",
    ),
    ServiceConceptRelationHint(
        hint_id="llm_minimal_brew_group_residue_or_friction",
        concept_id="brew_group_residue_or_friction",
        concept_kind="diagnosis",
        service_types=("CleaningServiceStep", "RepairServiceStep"),
        part_keywords=("brew_group", "brew", "group"),
        source="llm_vocabulary_enrichment_minimal_output_2026-06-27.json",
        support_level="minimal_evidence_llm_review_candidate",
    ),
    ServiceConceptRelationHint(
        hint_id="llm_minimal_check_valve_fatigue",
        concept_id="check_valve_fatigue",
        concept_kind="diagnosis",
        service_types=("RepairServiceStep",),
        part_keywords=("check_valve", "valve"),
        source="llm_vocabulary_enrichment_minimal_output_2026-06-27.json",
        support_level="minimal_evidence_llm_review_candidate",
    ),
    ServiceConceptRelationHint(
        hint_id="llm_minimal_dull_burrs",
        concept_id="dull_burrs",
        concept_kind="diagnosis",
        service_types=("RepairServiceStep", "ReplaceServiceStep"),
        part_keywords=("burr", "grinder"),
        source="llm_vocabulary_enrichment_minimal_output_2026-06-27.json",
        support_level="minimal_evidence_llm_review_candidate",
    ),
    ServiceConceptRelationHint(
        hint_id="llm_minimal_loose_hose_or_clamp_issue",
        concept_id="loose_hose_or_clamp_issue",
        concept_kind="diagnosis",
        service_types=("RepairServiceStep",),
        part_keywords=("hose", "clamp", "silicone"),
        source="llm_vocabulary_enrichment_minimal_output_2026-06-27.json",
        support_level="minimal_evidence_llm_review_candidate",
    ),
    ServiceConceptRelationHint(
        hint_id="llm_minimal_motor_brush_wear",
        concept_id="motor_brush_wear",
        concept_kind="diagnosis",
        service_types=("RepairServiceStep", "ReplaceServiceStep"),
        part_keywords=("motor", "brush", "grinder"),
        source="llm_vocabulary_enrichment_minimal_output_2026-06-27.json",
        support_level="minimal_evidence_llm_review_candidate",
    ),
)


def evidence_for_diagnosis(diagnosis_concept: str) -> tuple[ServiceRelationEvidence, ...]:
    """Return relation evidence entries for a diagnosis concept."""
    return tuple(
        evidence
        for evidence in SERVICE_RELATION_EVIDENCE
        if evidence.diagnosis_concept == diagnosis_concept
    )


def relation_hints_for_concept(concept_id: str) -> tuple[ServiceConceptRelationHint, ...]:
    """Return soft relation hints for a service concept."""
    return tuple(
        hint
        for hint in SERVICE_CONCEPT_RELATION_HINTS
        if hint.concept_id == concept_id
    )


def part_text_matches_keywords(part_text: str, keywords: tuple[str, ...]) -> bool:
    """Return True when a part reference contains at least one evidence keyword."""
    normalized = part_text.lower().replace("-", "_").replace(" ", "_")
    return any(keyword.lower() in normalized for keyword in keywords)
