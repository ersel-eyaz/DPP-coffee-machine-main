"""Tests for collecting persisted service text for candidate reporting."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from dpp.models.processstep import RepairServiceStep
from dpp.routers.data_quality import _historical_service_text_records


class CandidateHistoryIntegrationTests(unittest.TestCase):
    def test_collects_original_text_and_record_provenance(self) -> None:
        step = RepairServiceStep.model_construct(
            type_="RepairServiceStep",
            repairedPartId="part-target",
            diagnose="pump_fault",
            observedSymptoms=["water_leakage", "odd hiss"],
            originalDiagnose="rare pump pulse",
            originalObservedSymptoms=["water leak", "odd hiss"],
        )
        root = SimpleNamespace(
            id="root-part",
            partProcessTracking=[step],
            compositeParts=[],
            historyOfDetachedParts=[],
        )
        instance = SimpleNamespace(id="instance-001", partInstanceLink=root)

        records = _historical_service_text_records([instance])

        self.assertEqual(3, len(records))
        diagnosis = records[0]
        self.assertEqual("rare pump pulse", diagnosis.text)
        self.assertEqual("pump_fault", diagnosis.canonical_value)
        self.assertEqual("RepairServiceStep.diagnose", diagnosis.field_path)
        self.assertEqual("instance-001", diagnosis.instance_id)
        self.assertEqual("root-part:partProcessTracking:0", diagnosis.service_step_id)
        self.assertEqual("part-target", diagnosis.part_id)

        self.assertEqual(
            ("water leak", "odd hiss"),
            tuple(record.text for record in records[1:]),
        )
        self.assertEqual(
            ("water_leakage", "odd hiss"),
            tuple(record.canonical_value for record in records[1:]),
        )


if __name__ == "__main__":
    unittest.main()
