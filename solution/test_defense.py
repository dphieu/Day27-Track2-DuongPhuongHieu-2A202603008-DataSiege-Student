"""Behavior checks with synthetic measurements; no phase data or keys needed."""
import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness" / "child_env"))
from api import SiegeContext, Verdict
import defense

BASELINE = json.loads((ROOT / "data" / "baselines.json").read_text())
CASES = {
    "data_batch": (
        "batch_profile", "checks", {"batch_id": "batch-example"},
        {"row_count": 498, "null_rate": {"customer_id": 0.003},
         "mean_amount": 81.5, "std_amount": 12, "staleness_min": 4}),
    "contract_checkpoint": (
        "contract_diff", "contracts",
        {"contract_id": "orders", "checkpoint_batch_id": "checkpoint-example",
         "declared_sla": {"freshness_min": 15}},
        {"freshness_delay_min": 5, "violations": []}),
    "lineage_run": (
        "lineage_graph_slice", "lineage", {"run_id": "run-example"},
        {"actual_upstream": ["raw.orders", "raw.customers"],
         "actual_downstream_count": 2, "duration_ms": 3000}),
    "feature_materialization": (
        "feature_drift", "ai_infra",
        {"feature_view": "customer_ltv_features", "batch_id": "feature-example"},
        {"serve_mean": 104.72, "train_mean": 100, "train_std": 10,
         "mean_shift_sigma": 0.472}),
    "embedding_batch": (
        "embedding_drift", "ai_infra",
        {"corpus": "support_docs", "chunk_batch_id": "embedding-example"},
        {"centroid_shift": 0.039, "avg_doc_age_days": 41}),
}


class DefenseTests(unittest.TestCase):
    def evaluate(self, event_type, changes=None, payload_changes=None, error=False):
        method, pillar, payload, measurement = copy.deepcopy(CASES[event_type])
        measurement.update(changes or {})
        payload.update(payload_changes or {})
        tool = Mock(return_value={"error": "not available"} if error else measurement)
        ctx = SiegeContext(SimpleNamespace(**{method: tool}), dict(BASELINE))
        defense.register(ctx)
        event = {"type": event_type, "payload": payload}
        verdict = ctx.dispatch(event)
        self.assertIsInstance(verdict, Verdict)
        self.assertEqual(verdict.pillar, pillar)
        self.assertEqual(tool.call_count, 1)
        return verdict, ctx, event, tool

    def test_all_handlers_accept_clean_measurements(self):
        for event_type in CASES:
            with self.subTest(event_type=event_type):
                verdict, ctx, _, _ = self.evaluate(event_type)
                self.assertFalse(verdict.alert)
                self.assertEqual(set(ctx._handlers), set(CASES))

    def test_batch_individual_faults(self):
        for changes in (
            {"row_count": 400}, {"row_count": 600},
            {"mean_amount": 70}, {"mean_amount": 95},
            {"null_rate": {"customer_id": 0.02}}, {"staleness_min": 12},
        ):
            with self.subTest(changes=changes):
                self.assertTrue(self.evaluate("data_batch", changes)[0].alert)

    def test_batch_joint_fault_inside_individual_bounds(self):
        verdict = self.evaluate("data_batch", {
            "row_count": 550, "mean_amount": 89,
            "null_rate": {"customer_id": 0.007}, "staleness_min": 7,
        })[0]
        self.assertTrue(verdict.alert)
        self.assertIn("combined", verdict.reason)

    def test_contract_violations_and_freshness(self):
        for changes in (
            {"violations": ["schema_hash_mismatch"]},
            {"violations": ["type_violation"]}, {"freshness_delay_min": 12},
        ):
            with self.subTest(changes=changes):
                self.assertTrue(self.evaluate("contract_checkpoint", changes)[0].alert)

    def test_contract_uses_stricter_declared_sla(self):
        verdict = self.evaluate("contract_checkpoint", {"freshness_delay_min": 7},
                                {"declared_sla": {"freshness_min": 6}})[0]
        self.assertTrue(verdict.alert)

    def test_contract_without_declared_sla_uses_baseline(self):
        self.assertTrue(self.evaluate("contract_checkpoint", {"freshness_delay_min": 12},
                                      {"declared_sla": None})[0].alert)

    def test_lineage_structural_and_runtime_faults(self):
        for changes in (
            {"actual_downstream_count": 0}, {"actual_upstream": ["raw.orders"]},
            {"actual_upstream": ["raw.customers"]}, {"duration_ms": 6000},
        ):
            with self.subTest(changes=changes):
                self.assertTrue(self.evaluate("lineage_run", changes)[0].alert)

    def test_feature_calibration_gap(self):
        for shift, expected in ((0.472, False), (0.65, False), (0.970, True)):
            with self.subTest(shift=shift):
                verdict = self.evaluate("feature_materialization", {"mean_shift_sigma": shift})[0]
                self.assertEqual(verdict.alert, expected)

    def test_embedding_drift_and_age(self):
        for changes in ({"centroid_shift": 0.041}, {"avg_doc_age_days": 48}):
            with self.subTest(changes=changes):
                self.assertTrue(self.evaluate("embedding_batch", changes)[0].alert)

    def test_tool_errors_are_explicit_and_do_not_crash(self):
        for event_type in CASES:
            with self.subTest(event_type=event_type):
                verdict = self.evaluate(event_type, error=True)[0]
                self.assertFalse(verdict.alert)
                self.assertEqual(verdict.confidence, 0.0)
                self.assertIn("measurement unavailable", verdict.reason)

    def test_repeated_references_do_not_spend_again(self):
        for event_type in CASES:
            with self.subTest(event_type=event_type):
                first, ctx, event, tool = self.evaluate(event_type)
                self.assertEqual(ctx.dispatch(event), first)
                self.assertEqual(tool.call_count, 1)

    def test_new_reference_gets_its_own_measurement(self):
        _, ctx, event, tool = self.evaluate("data_batch")
        event["payload"]["batch_id"] = "another-batch"
        ctx.dispatch(event)
        self.assertEqual(tool.call_count, 2)


if __name__ == "__main__":
    unittest.main()
