"""
OpenRepairData-derived service concept registry for free-text harmonization.

This module contains the canonical diagnosis and symptom concepts used by the
service free-text harmonizer. Concept descriptions, surface forms, example
phrases, and soft context metadata are generated from the documented LLM API
workflow in docs/thesis_context/notebooks/llm_alias_and_service_description_generation_2026-06-29.ipynb.
Matching logic stays in free_text.py, so the registry can be reviewed and
extended without changing the normalization algorithm.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


TextConceptKind = Literal["symptom", "diagnosis"]
TextConceptInventoryStatus = Literal["core", "review_candidate"]


@dataclass(frozen=True)
class TextConcept:
    """
    Canonical free-text concept used for service-text harmonization.

    Attributes:
        concept_id: Stable machine-readable identifier.
        label: Human-readable canonical label.
        kind: Concept registry kind, e.g. symptom or diagnosis.
        description: Short semantic description used for embedding matching.
        examples: Surface forms and example phrases from the documented service concept generation workflow.
        applicable_service_types: Optional service-step types where the concept is especially plausible.
        related_part_keywords: Optional part-name keywords kept as soft context metadata.
        inventory_status: Whether the concept is part of the OpenRepairData-derived core vocabulary or a review candidate.
    """

    concept_id: str
    label: str
    kind: TextConceptKind
    description: str
    examples: tuple[str, ...] = ()
    applicable_service_types: tuple[str, ...] = ()
    related_part_keywords: tuple[str, ...] = ()
    inventory_status: TextConceptInventoryStatus = "core"


SYMPTOM_CONCEPTS: tuple[TextConcept, ...] = (
    TextConcept(
        concept_id='does_not_turn_on',
        label='Does not turn on',
        kind='symptom',
        description='Coffee machine will not start, switch on, or turn on when attempted.',
        examples=(
            'does not turn on',
            "won't turn on",
            'does not switch on',
            "can't start",
            'not turning on',
            "Doesn't turn on",
        ),
        applicable_service_types=(
            'RepairServiceStep',
            'ReplaceServiceStep',
            'RefurbishmentServiceStep',
            'RemanufacturingServiceStep',
            'SecondaryValueStep',
        ),
        related_part_keywords=(
            'power switch',
            'button',
            'plug',
            'fuse',
            'control board',
        ),
    ),
    TextConcept(
        concept_id='generic_not_working',
        label='Generic not working',
        kind='symptom',
        description='Generic report that the coffee machine does not work, without a specific failure mode.',
        examples=(
            'not working',
            "doesn't work",
            'coffee machine not working',
            'coffee maker not working',
            'nothing happens',
            'Coffee maker - not working',
            'nothing happens when its turned on',
        ),
        applicable_service_types=(
            'RepairServiceStep',
            'ReplaceServiceStep',
            'RefurbishmentServiceStep',
            'RemanufacturingServiceStep',
            'SecondaryValueStep',
        ),
        related_part_keywords=(
            'machine',
            'coffee maker',
            'coffee machine',
            'unknown part',
        ),
    ),
    TextConcept(
        concept_id='grinder_not_working',
        label='Grinder not working',
        kind='symptom',
        description='Coffee grinder does not grind, has stopped grinding, or will not grind coffee.',
        examples=(
            'grinder not working',
            'will not grind',
            "won't grind coffee",
            'stopped grinding',
            'not grinding',
            'COFFEE GRINDER NOT GRINDING',
            'Stopped grinding coffee',
        ),
        applicable_service_types=(
            'RepairServiceStep',
            'ReplaceServiceStep',
            'RefurbishmentServiceStep',
            'RemanufacturingServiceStep',
        ),
        related_part_keywords=(
            'grinder',
            'coffee grinder',
            'grinding motor',
            'grind mechanism',
        ),
    ),
    TextConcept(
        concept_id='no_coffee_output',
        label='No coffee output',
        kind='symptom',
        description='Machine brews poorly or produces no coffee output even if some functions may work.',
        examples=(
            'no coffee output',
            'no coffee coming out',
            'did not brew',
            'will not brew',
            'not brewing',
            'Not frothing milk but makes coffee okay',
        ),
        applicable_service_types=(
            'RepairServiceStep',
            'CleaningServiceStep',
            'RefurbishmentServiceStep',
            'RemanufacturingServiceStep',
        ),
        related_part_keywords=(
            'brew group',
            'coffee outlet',
            'filter',
            'pump',
            'water line',
        ),
    ),
    TextConcept(
        concept_id='no_power_or_no_lights',
        label='No power or no lights',
        kind='symptom',
        description='No electrical power, no display power, or no indicator lights are present.',
        examples=(
            'no power',
            'no lights',
            'no electrical power',
            'display has no power',
            'light not coming on',
            'No power to the display',
            'No lights on operation panel',
        ),
        applicable_service_types=(
            'RepairServiceStep',
            'ReplaceServiceStep',
            'RefurbishmentServiceStep',
            'RemanufacturingServiceStep',
            'SecondaryValueStep',
        ),
        related_part_keywords=(
            'plug',
            'fuse',
            'power cord',
            'display',
            'operation panel',
        ),
    ),
    TextConcept(
        concept_id='no_water_flow',
        label='No water flow',
        kind='symptom',
        description='Water or coffee does not come through the machine during brewing.',
        examples=(
            'no water flow',
            'water not coming through',
            'coffee not coming through',
            'not percolating',
            'will not pour coffee',
            'water not getting through to the coffee',
            'No water coming through',
            'No water coming out to make coffee',
        ),
        applicable_service_types=(
            'RepairServiceStep',
            'CleaningServiceStep',
            'RefurbishmentServiceStep',
            'RemanufacturingServiceStep',
        ),
        related_part_keywords=(
            'pump',
            'water line',
            'tube',
            'brew group',
            'coffee outlet',
        ),
    ),
    TextConcept(
        concept_id='not_pumping_water',
        label='Not pumping water',
        kind='symptom',
        description='Water is not being pumped or moved through the coffee machine as expected.',
        examples=(
            'not pumping water',
            'water not pumping',
            "won't pump water",
            'water not moving',
            "water's not moving",
        ),
        applicable_service_types=(
            'RepairServiceStep',
            'ReplaceServiceStep',
            'CleaningServiceStep',
            'RefurbishmentServiceStep',
            'RemanufacturingServiceStep',
        ),
        related_part_keywords=(
            'pump',
            'water pump',
            'water reservoir',
            'tube',
            'water line',
        ),
    ),
    TextConcept(
        concept_id='pod_jam_or_lid_not_closing',
        label='Pod jam or lid not closing',
        kind='symptom',
        description='Pod is jammed, pod cavity will not close, or lid cannot close around capsules.',
        examples=(
            'pod jam',
            'jammed pod',
            "lid won't close",
            'pod cavity not closing',
            'stuck coffee pod',
            'Two jammed pods inside',
            'Not closing pod cavity',
            'pod jams',
        ),
        applicable_service_types=(
            'RepairServiceStep',
            'CleaningServiceStep',
            'RefurbishmentServiceStep',
            'RemanufacturingServiceStep',
        ),
        related_part_keywords=(
            'pod',
            'capsule',
            'lid',
            'pod cavity',
            'handle',
        ),
    ),
    TextConcept(
        concept_id='pod_not_pierced',
        label='Pod not pierced',
        kind='symptom',
        description='Machine fails to pierce coffee pods or capsules properly during operation.',
        examples=(
            'pod not pierced',
            'not piercing pods',
            'capsules not pierced',
            'does not pierce pods',
            'pod not punching',
            'Stopped punching holes in the pods',
            'Pods were not pierced properly',
            'Machine does not pierce pods',
            'Not piercing coffee capsules',
        ),
        applicable_service_types=(
            'RepairServiceStep',
            'ReplaceServiceStep',
            'RefurbishmentServiceStep',
            'RemanufacturingServiceStep',
        ),
        related_part_keywords=(
            'pod',
            'capsule',
            'piercer',
            'plunger',
            'pod mechanism',
        ),
    ),
    TextConcept(
        concept_id='power_on_but_no_operation',
        label='Power on but no operation',
        kind='symptom',
        description='Machine powers or lights up but does not perform the expected operation.',
        examples=(
            'power on but no operation',
            'powers up but nothing happens',
            'light on but nothing happens',
            'power is on but not working',
            'Light comes on when plugged in , but nothing happens',
            'Power is on - but nothing happening',
            'Powers up but something wrong',
        ),
        applicable_service_types=(
            'RepairServiceStep',
            'ReplaceServiceStep',
            'RefurbishmentServiceStep',
            'RemanufacturingServiceStep',
            'SecondaryValueStep',
        ),
        related_part_keywords=(
            'control board',
            'display',
            'switch',
            'pump',
            'motor',
        ),
    ),
    TextConcept(
        concept_id='reduced_water_flow_or_low_pressure',
        label='Reduced water flow or low pressure',
        kind='symptom',
        description='Water flow is weak, slow, insufficient, blocked, or has low pressure.',
        examples=(
            'low water flow',
            'low water pressure',
            'reduced water flow',
            'pumps slowly',
            'not dispensing enough water',
            'No pressure through system',
        ),
        applicable_service_types=(
            'RepairServiceStep',
            'CleaningServiceStep',
            'RefurbishmentServiceStep',
            'RemanufacturingServiceStep',
        ),
        related_part_keywords=(
            'pump',
            'water line',
            'boiler',
            'nozzle',
            'filter',
        ),
    ),
    TextConcept(
        concept_id='steam_leak',
        label='Steam leak',
        kind='symptom',
        description='Steam leaks from the steam wand, control area, or machine during use.',
        examples=(
            'steam leak',
            'steam leaking',
            'steam wand leaking',
            'steam leaking from control',
            'water and steam leaking',
            'some water and steam out but nothing more',
        ),
        applicable_service_types=(
            'RepairServiceStep',
            'ReplaceServiceStep',
            'CleaningServiceStep',
            'RefurbishmentServiceStep',
        ),
        related_part_keywords=(
            'steam wand',
            'steam control',
            'valve',
            'seal',
            'nozzle',
        ),
    ),
    TextConcept(
        concept_id='steam_wand_not_working',
        label='Steam wand not working',
        kind='symptom',
        description='Steam wand or steamer function has low power or does not work correctly.',
        examples=(
            'steam wand not working',
            'steamer not working',
            'not steaming properly',
            'steam wand losing power',
            'steamer malfunction',
            'Steamer wand no longer fundtions',
            'Not steam properly',
        ),
        applicable_service_types=(
            'RepairServiceStep',
            'CleaningServiceStep',
            'RefurbishmentServiceStep',
            'RemanufacturingServiceStep',
        ),
        related_part_keywords=(
            'steam wand',
            'steamer',
            'steam nozzle',
            'valve',
            'boiler',
        ),
    ),
    TextConcept(
        concept_id='water_leakage',
        label='Water leakage',
        kind='symptom',
        description='Water leaks from the machine, base, inside, or during operation.',
        examples=(
            'water leakage',
            'water leak',
            'leaking water',
            'machine leaking',
            'leaking from base',
            'leaking inside',
            'Leaking',
            'Leaking water when operational',
            'Water leaking from the machine',
            'leaking from the base',
        ),
        applicable_service_types=(
            'RepairServiceStep',
            'ReplaceServiceStep',
            'CleaningServiceStep',
            'RefurbishmentServiceStep',
            'RemanufacturingServiceStep',
        ),
        related_part_keywords=(
            'seal',
            'gasket',
            'hose',
            'base',
            'water tank',
        ),
    ),
    TextConcept(
        concept_id='water_not_heating',
        label='Water not heating',
        kind='symptom',
        description='Water does not heat up or boiler fails to heat water for brewing.',
        examples=(
            'water not heating',
            'not heating water',
            "won't heat water",
            "doesn't heat up",
            "boiler doesn't heat",
            "water don't heat",
            "boiler doesn't heat the water",
        ),
        applicable_service_types=(
            'RepairServiceStep',
            'ReplaceServiceStep',
            'RefurbishmentServiceStep',
            'RemanufacturingServiceStep',
        ),
        related_part_keywords=(
            'heating element',
            'boiler',
            'thermostat',
            'thermal fuse',
            'heater',
        ),
    ),
    TextConcept(
        concept_id='grinder_not_switching_on',
        label='Grinder not switching on',
        kind='symptom',
        description='Coffee grinder specifically does not switch on or start.',
        examples=(
            'grinder not switching on',
            "grinder doesn't turn on",
            'grinder will not start',
            'grinder not starting',
            'not switching on',
            'doesn’t turn on',
        ),
        applicable_service_types=(
            'RepairServiceStep',
            'ReplaceServiceStep',
            'RefurbishmentServiceStep',
            'RemanufacturingServiceStep',
        ),
        related_part_keywords=(
            'grinder',
            'coffee grinder',
            'grinder motor',
            'switch',
        ),
        inventory_status='review_candidate',
    ),
    TextConcept(
        concept_id='indicator_light_error',
        label='Indicator light error',
        kind='symptom',
        description='Indicator light shows an error state, such as red or flashing light, instead of normal operation.',
        examples=(
            'indicator light error',
            'red light error',
            'flashing red light',
            "red light won't change",
            'warning light',
            "instantly turns red and doesn't work",
            'Red light still comes on',
            'flashing light. red light flashing',
            "Red light won't change to green",
        ),
        applicable_service_types=(
            'RepairServiceStep',
            'CleaningServiceStep',
            'RefurbishmentServiceStep',
            'RemanufacturingServiceStep',
            'SecondaryValueStep',
        ),
        related_part_keywords=(
            'indicator light',
            'red light',
            'green light',
            'display',
            'operation panel',
        ),
        inventory_status='review_candidate',
    ),
    TextConcept(
        concept_id='pod_area_leakage',
        label='Pod area leakage',
        kind='symptom',
        description='Water leaks from the pod insertion area or pod cavity of the machine.',
        examples=(
            'pod area leakage',
            'leaks from pod area',
            'water leaking from pod',
            'pod cavity leak',
            'leak near capsules',
            'Leaks water from pod',
            'leaks water onto the bench',
            'leak is coming from the area where the pods are inserted',
            'Leaking',
        ),
        applicable_service_types=(
            'RepairServiceStep',
            'ReplaceServiceStep',
            'CleaningServiceStep',
            'RefurbishmentServiceStep',
        ),
        related_part_keywords=(
            'pod area',
            'pod cavity',
            'capsule holder',
            'seal',
            'lid',
        ),
        inventory_status='review_candidate',
    ),
)


DIAGNOSIS_CONCEPTS: tuple[TextConcept, ...] = (
    TextConcept(
        concept_id='air_in_pump_or_pipe',
        label='Air in pump or pipe',
        kind='diagnosis',
        description='Air trapped in the coffee machine pump or pipework causing flow or pump issues.',
        examples=(
            'air in pump',
            'air in pipe',
            'air lock in pump',
            'air in water line',
            'Pump had air in the pipe',
            'air trapped in pump line',
        ),
        applicable_service_types=(
            'RepairServiceStep',
            'CleaningServiceStep',
            'RefurbishmentServiceStep',
            'RemanufacturingServiceStep',
        ),
        related_part_keywords=(
            'pump',
            'pipe',
            'tube',
            'water line',
        ),
    ),
    TextConcept(
        concept_id='blocked_or_disconnected_flow_path',
        label='Blocked or disconnected flow path',
        kind='diagnosis',
        description='Blocked, plugged, or disconnected tubing or flow path preventing water movement.',
        examples=(
            'blocked flow path',
            'plugged tubing',
            'blocked pipe',
            'disconnected water line',
            'or is blocked',
            'Connection to water pump had come off',
        ),
        applicable_service_types=(
            'RepairServiceStep',
            'CleaningServiceStep',
            'RefurbishmentServiceStep',
            'RemanufacturingServiceStep',
        ),
        related_part_keywords=(
            'tubing',
            'pipe',
            'hose',
            'water pump',
            'connector',
        ),
    ),
    TextConcept(
        concept_id='blocked_steam_nozzle',
        label='Blocked steam nozzle',
        kind='diagnosis',
        description='Steam nozzle or steamer outlet is blocked and needs cleaning or unblocking.',
        examples=(
            'blocked nozzle',
            'blocked steam nozzle',
            'clogged steamer nozzle',
            'unblock nozzle',
            'cleaned steamer nozzle',
            'Cleaned and unblocked the nozzle',
        ),
        applicable_service_types=(
            'CleaningServiceStep',
            'RepairServiceStep',
            'RefurbishmentServiceStep',
        ),
        related_part_keywords=(
            'steam nozzle',
            'steamer nozzle',
            'steam wand',
            'nozzle',
        ),
    ),
    TextConcept(
        concept_id='dirty_or_corroded_contacts',
        label='Dirty or corroded contacts',
        kind='diagnosis',
        description='Dirty, worn, carbonized, or corroded electrical contacts affecting switches or buttons.',
        examples=(
            'dirty contacts',
            'corroded contacts',
            'worn contact',
            'dirty switch contacts',
            'button contact worn off',
            'Switch dirty contacts',
            'switch corroded',
            'dirty on/off button',
        ),
        applicable_service_types=(
            'CleaningServiceStep',
            'RepairServiceStep',
            'RefurbishmentServiceStep',
            'RemanufacturingServiceStep',
        ),
        related_part_keywords=(
            'contacts',
            'switch',
            'button',
            'on off button',
            'tact switch',
        ),
    ),
    TextConcept(
        concept_id='fuse_or_thermal_fuse_fault',
        label='Fuse or thermal fuse fault',
        kind='diagnosis',
        description='Blown plug fuse or thermal fuse fault preventing safe electrical operation.',
        examples=(
            'blown fuse',
            'thermal fuse fault',
            'plug fuse blown',
            'thermal fuse blown',
            'Need thermal fuse',
        ),
        applicable_service_types=(
            'RepairServiceStep',
            'ReplaceServiceStep',
            'RefurbishmentServiceStep',
            'RemanufacturingServiceStep',
        ),
        related_part_keywords=(
            'fuse',
            'thermal fuse',
            'plug fuse',
            'power circuit',
        ),
    ),
    TextConcept(
        concept_id='heating_element_failure',
        label='Heating element failure',
        kind='diagnosis',
        description='Heating element is broken, failed, open circuit, or not receiving power.',
        examples=(
            'heating element failure',
            'broken heating element',
            'heater failed',
            'heating element open circuit',
            'heating element failed',
            'no power to heating element',
        ),
        applicable_service_types=(
            'RepairServiceStep',
            'ReplaceServiceStep',
            'RefurbishmentServiceStep',
            'RemanufacturingServiceStep',
        ),
        related_part_keywords=(
            'heating element',
            'heater',
            'boiler',
            'thermal circuit',
        ),
    ),
    TextConcept(
        concept_id='limescale_or_scale_build_up',
        label='Limescale or scale build-up',
        kind='diagnosis',
        description='Limescale, limestone, or scale build-up clogging or degrading coffee machine performance.',
        examples=(
            'limescale build up',
            'scale build-up',
            'clogged with limescale',
            'requires descaling',
            'Probably lime scale build up',
            'scale light on',
        ),
        applicable_service_types=(
            'CleaningServiceStep',
            'RepairServiceStep',
            'RefurbishmentServiceStep',
            'RemanufacturingServiceStep',
        ),
        related_part_keywords=(
            'boiler',
            'water line',
            'pump',
            'nozzle',
            'scale light',
        ),
    ),
    TextConcept(
        concept_id='pod_mechanism_or_lid_fault',
        label='Pod mechanism or lid fault',
        kind='diagnosis',
        description='Fault in pod mechanism, lid, handle, or plunger used to close or pierce capsules.',
        examples=(
            'pod mechanism fault',
            'lid fault',
            'broken handle',
            'plunger fault',
            'capsule piercer fault',
            'handle/lid of the machine was loose/broken',
            'Plunger not able to pierce capsuls',
            'replaced pod mechanism',
        ),
        applicable_service_types=(
            'RepairServiceStep',
            'ReplaceServiceStep',
            'RefurbishmentServiceStep',
            'RemanufacturingServiceStep',
        ),
        related_part_keywords=(
            'pod mechanism',
            'lid',
            'handle',
            'plunger',
            'capsule piercer',
        ),
    ),
    TextConcept(
        concept_id='pump_fault',
        label='Pump fault',
        kind='diagnosis',
        description='Pump or small pump motor is faulty, seized, dead, or not operating.',
        examples=(
            'pump fault',
            'faulty pump',
            'pump not working',
            'pump seized',
            'dead pump',
            'Could be faulty pump',
            'Pump is dead',
            'small motor not operating',
        ),
        applicable_service_types=(
            'RepairServiceStep',
            'ReplaceServiceStep',
            'RefurbishmentServiceStep',
            'RemanufacturingServiceStep',
        ),
        related_part_keywords=(
            'pump',
            'water pump',
            'pump motor',
            'small motor',
        ),
    ),
    TextConcept(
        concept_id='seal_issue',
        label='Seal issue',
        kind='diagnosis',
        description='Seal is dirty, misfitting, worn, or needs replacement, often causing leakage.',
        examples=(
            'seal issue',
            'seal needs replacing',
            'seal not fitting',
            'dirty seal',
            'bad seal',
            'seal needs cleaning /replaced',
            'Seal not fitting right',
        ),
        applicable_service_types=(
            'CleaningServiceStep',
            'RepairServiceStep',
            'ReplaceServiceStep',
            'RefurbishmentServiceStep',
        ),
        related_part_keywords=(
            'seal',
            'gasket',
            'o-ring',
            'water seal',
        ),
    ),
    TextConcept(
        concept_id='switch_or_button_fault',
        label='Switch or button fault',
        kind='diagnosis',
        description='Switch, on/off button, or tact switch is broken, defective, faulty, or unstable.',
        examples=(
            'broken switch',
            'faulty switch',
            'defective button',
            'tact switch fault',
            'wonky switch',
            'broken on switch',
            'Switch faulty',
        ),
        applicable_service_types=(
            'RepairServiceStep',
            'ReplaceServiceStep',
            'RefurbishmentServiceStep',
            'RemanufacturingServiceStep',
        ),
        related_part_keywords=(
            'switch',
            'button',
            'on switch',
            'on off button',
            'tact switch',
        ),
    ),
    TextConcept(
        concept_id='valve_or_solenoid_fault',
        label='Valve or solenoid fault',
        kind='diagnosis',
        description='Steam valve, water valve, or solenoid is faulty, stripped, or not directing steam correctly.',
        examples=(
            'valve fault',
            'solenoid fault',
            'steam valve fault',
            'faulty solenoid',
            'stripped steam valve',
            'Valve not directing steam',
            'Probably one of the solenoids is faulty',
            'Steam valve stripped - turns but no effect',
        ),
        applicable_service_types=(
            'RepairServiceStep',
            'ReplaceServiceStep',
            'RefurbishmentServiceStep',
            'RemanufacturingServiceStep',
        ),
        related_part_keywords=(
            'valve',
            'steam valve',
            'solenoid',
            'steam control',
        ),
    ),
    TextConcept(
        concept_id='thermostat_or_rheostat_fault',
        label='Thermostat or rheostat fault',
        kind='diagnosis',
        description='Thermostat or rheostat fault affecting temperature or heating control.',
        examples=(
            'thermostat fault',
            'rheostat fault',
            'thermostat not working',
            'new rheostat needed',
            'change thermostat',
            'Changer le thermostat',
            'needs a new rheostat',
        ),
        applicable_service_types=(
            'RepairServiceStep',
            'ReplaceServiceStep',
            'RefurbishmentServiceStep',
            'RemanufacturingServiceStep',
        ),
        related_part_keywords=(
            'thermostat',
            'rheostat',
            'temperature control',
            'heater control',
        ),
        inventory_status='review_candidate',
    ),
)


TEXT_CONCEPTS_BY_KIND: dict[TextConceptKind, tuple[TextConcept, ...]] = {
    "symptom": SYMPTOM_CONCEPTS,
    "diagnosis": DIAGNOSIS_CONCEPTS,
}


TEXT_CONCEPTS_BY_ID: dict[str, TextConcept] = {
    concept.concept_id: concept
    for concepts in TEXT_CONCEPTS_BY_KIND.values()
    for concept in concepts
}
