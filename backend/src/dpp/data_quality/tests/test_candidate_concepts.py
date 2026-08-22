"""Tests for service candidate-concept evidence reporting."""

from __future__ import annotations

import unittest

from dpp.data_quality.harmonization.candidate_concepts import (
    HistoricalServiceTextRecord,
    build_candidate_concept_evidence_report,
    observations_from_learned_feedback,
    select_unresolved_historical_observations,
    unresolved_service_observation,
)
from dpp.data_quality.harmonization.feedback import LearnedServiceTextMapping


class CandidateConceptEvidenceReportTests(unittest.TestCase):
    def test_learned_feedback_and_unresolved_observations_cluster_with_provenance(self) -> None:
        learned = observations_from_learned_feedback(
            (
                LearnedServiceTextMapping(
                    feedback_id="feedback-001",
                    kind="diagnosis",
                    field_path="RepairServiceStep.diagnose",
                    original_value="pump makes hydraulic noise",
                    concept_id="pump_fault",
                    surface_form="pump makes hydraulic noise",
                ),
            )
        )
        unresolved = unresolved_service_observation(
            observation_id="unresolved-001",
            kind="diagnosis",
            text="hydraulic pump noise",
            field_path="RepairServiceStep.diagnose",
            service_type="RepairServiceStep",
            part_label="Vibration Pump",
        )

        report = build_candidate_concept_evidence_report(
            (*learned, unresolved),
            cluster_similarity_threshold=0.45,
        )
        payload = report.as_dict()

        self.assertEqual("neutral_evidence_only", payload["parameters"]["interpretation"])
        self.assertEqual(2, payload["clustering_quality"]["observations_total"])
        self.assertEqual(1, payload["clustering_quality"]["clusters_total"])
        self.assertIn("metric_note", payload["clustering_quality"])
        self.assertEqual(1, len(payload["clusters"]))

        cluster = payload["clusters"][0]
        self.assertEqual(2, cluster["n_total"])
        self.assertEqual(1, cluster["n_learned"])
        self.assertEqual(1, cluster["n_unresolved"])
        self.assertEqual({"learned_feedback": 1, "unresolved_observation": 1}, cluster["source_counts"])
        self.assertEqual({"pump_fault": 1}, cluster["learned_target_counts"])
        self.assertEqual("pump_fault", cluster["top_learned_target"])
        self.assertEqual(1.0, cluster["top_learned_target_share"])
        self.assertIn("hydraulic pump noise", cluster["candidate_surface_forms"])
        self.assertEqual("pump_fault", cluster["nearest_core_id"])
        self.assertIn("pump_fault", cluster["nearest_core_ids"])
        self.assertTrue(cluster["nearest_core_id"])
        self.assertGreaterEqual(len(cluster["core_anchors"]), 1)

        alias_candidates = payload["core_alias_candidates"]
        self.assertEqual(1, len(alias_candidates))
        self.assertEqual("pump_fault", alias_candidates[0]["concept_id"])
        self.assertEqual(("pump makes hydraulic noise",), tuple(alias_candidates[0]["surface_forms"]))
        self.assertEqual(1, alias_candidates[0]["support_count"])
        self.assertEqual(("feedback-001",), tuple(alias_candidates[0]["feedback_ids"]))

    def test_core_registry_is_not_clustered_as_an_observation_or_decision(self) -> None:
        report = build_candidate_concept_evidence_report(
            (
                unresolved_service_observation(
                    observation_id="unresolved-001",
                    kind="symptom",
                    text="water dripping under machine",
                ),
            )
        )
        cluster = report.as_dict()["clusters"][0]

        self.assertEqual(1, cluster["n_total"])
        self.assertEqual(1, len(cluster["observations"]))
        self.assertEqual("unresolved_observation", cluster["observations"][0]["source"])
        self.assertNotIn("suggested_review_action", cluster)
        self.assertIn("nearest_core_id", cluster)
        self.assertIn("core_anchors", cluster)
        self.assertEqual([], report.as_dict()["core_alias_candidates"])

    def test_clustering_quality_reports_internal_diagnostics(self) -> None:
        report = build_candidate_concept_evidence_report(
            (
                unresolved_service_observation(
                    observation_id="a",
                    kind="diagnosis",
                    text="pump makes hydraulic noise",
                ),
                unresolved_service_observation(
                    observation_id="b",
                    kind="diagnosis",
                    text="hydraulic pump noise",
                ),
                unresolved_service_observation(
                    observation_id="c",
                    kind="diagnosis",
                    text="grinder motor burned out",
                ),
            ),
            cluster_similarity_threshold=0.45,
        )
        quality = report.as_dict()["clustering_quality"]

        self.assertEqual(3, quality["observations_total"])
        self.assertEqual(2, quality["clusters_total"])
        self.assertEqual(1, quality["singleton_clusters_total"])
        self.assertIsNotNone(quality["mean_intra_cluster_similarity"])
        self.assertIsNotNone(quality["approximate_silhouette"])
        self.assertIn("not a validated performance score", quality["metric_note"])

    def test_historical_selection_rechecks_resolved_and_keeps_unresolved_with_provenance(self) -> None:
        selection = select_unresolved_historical_observations(
            (
                HistoricalServiceTextRecord(
                    observation_id="resolved-001",
                    kind="symptom",
                    text="water leak",
                    canonical_value="water_leakage",
                ),
                HistoricalServiceTextRecord(
                    observation_id="unresolved-001",
                    kind="diagnosis",
                    text="unmapped hydraulic resonance qzvx",
                    canonical_value="unmapped hydraulic resonance qzvx",
                    field_path="RepairServiceStep.diagnose",
                    service_type="RepairServiceStep",
                    instance_id="instance-001",
                    service_step_id="part-001:partProcessTracking:2",
                    part_id="part-002",
                ),
            ),
            (),
            enable_semantic=False,
        )

        self.assertEqual(2, selection.inspected_count)
        self.assertEqual(1, selection.resolved_count)
        self.assertEqual(0, selection.learned_feedback_count)
        self.assertEqual(1, len(selection.unresolved_observations))
        observation = selection.unresolved_observations[0]
        self.assertEqual("instance-001", observation.instance_id)
        self.assertEqual("part-001:partProcessTracking:2", observation.service_step_id)
        self.assertEqual("part-002", observation.part_id)

    def test_historical_selection_does_not_double_count_applied_learned_feedback(self) -> None:
        mapping = LearnedServiceTextMapping(
            feedback_id="feedback-001",
            kind="diagnosis",
            field_path="RepairServiceStep.diagnose",
            original_value="rare hydraulic pulse qzvx",
            concept_id="pump_fault",
            surface_form="rare hydraulic pulse qzvx",
        )
        selection = select_unresolved_historical_observations(
            (
                HistoricalServiceTextRecord(
                    observation_id="learned-001",
                    kind="diagnosis",
                    text="rare hydraulic pulse qzvx",
                    canonical_value="pump_fault",
                ),
                HistoricalServiceTextRecord(
                    observation_id="still-unresolved-001",
                    kind="diagnosis",
                    text="rare hydraulic pulse qzvx",
                    canonical_value="rare hydraulic pulse qzvx",
                ),
            ),
            (mapping,),
            enable_semantic=False,
        )

        self.assertEqual(2, selection.inspected_count)
        self.assertEqual(0, selection.resolved_count)
        self.assertEqual(1, selection.learned_feedback_count)
        self.assertEqual(
            ("still-unresolved-001",),
            tuple(item.observation_id for item in selection.unresolved_observations),
        )


if __name__ == "__main__":
    unittest.main()
