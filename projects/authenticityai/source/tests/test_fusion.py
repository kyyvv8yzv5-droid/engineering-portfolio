import json
import tempfile
import unittest
from pathlib import Path

from fusion import EvidenceContribution, FusionEngine, FusionPolicyError, load_policy
import web_ui


def learned(probability=None, *, available=True, enabled=True, confidence=0.9):
    return {
        "universal_fake_detect": {
            "enabled": enabled,
            "available": available,
            "ai_probability": probability,
            "raw_score": None if probability is None else probability * 4 - 2,
            "confidence": confidence,
            "calibration_status": "uncalibrated",
            "warnings": [],
        }
    }


def forensic(detector_id, probability, *, confidence=0.9, reliability=0.8, warnings=None):
    return {
        detector_id: {
            "applicable": True,
            "ai_probability": probability,
            "confidence": confidence,
            "reliability": reliability,
            "warnings": list(warnings or []),
            "explanation": "Synthetic test signal.",
        }
    }


class FusionTests(unittest.TestCase):
    def setUp(self):
        self.engine = FusionEngine()
        self.context = {
            "metadata": {},
            "compression": {"applicable": True},
            "noise": {"applicable": True, "noise_warnings": []},
            "quality": {"sharpness": 500, "brightness": 128, "contrast": 50},
            "quality_warnings": [],
            "face_count": 0,
            "resolution": {"width": 1024, "height": 1024},
            "media_type": "image",
        }

    def run_fusion(self, learned_detectors=None, forensic_detectors=None, **changes):
        context = dict(self.context)
        context.update(changes)
        return self.engine.analyze(
            learned_detectors=learned_detectors or {},
            forensic_detectors=forensic_detectors or {},
            **context,
        )

    def test_policy_loads_and_is_versioned(self):
        policy = load_policy()
        self.assertEqual(policy["schema_version"], 1)
        self.assertIn("strong_min_coverage", policy["gates"])

    def test_contribution_contract_rejects_unknown_status(self):
        with self.assertRaises(ValueError):
            EvidenceContribution("x", "X", "1", "test", True, True, "negative")

    def test_disabled_detector_is_not_negative_evidence(self):
        result = self.run_fusion(learned(False, available=False, enabled=False))
        row = next(item for item in result["detector_contributions"] if item["detector_id"] == "universal_fake_detect")
        self.assertEqual(row["status"], "disabled")
        self.assertEqual(row["effective_weight"], 0.0)
        self.assertEqual(result["verdict"], "inconclusive")
        self.assertEqual(result["ai_score"], 0.5)

    def test_failed_detector_has_zero_weight(self):
        source = forensic("future_failed", 0.99)
        source["future_failed"]["error"] = "inference failed"
        result = self.run_fusion(forensic_detectors=source)
        row = next(item for item in result["contributions"] if item["detector_id"] == "future_failed")
        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["effective_weight"], 0.0)

    def test_unsupported_detector_has_zero_weight(self):
        source = {"future_video_only": {"applicable": False, "ai_probability": 0.99}}
        result = self.run_fusion(forensic_detectors=source)
        row = next(item for item in result["contributions"] if item["detector_id"] == "future_video_only")
        self.assertEqual(row["status"], "unsupported")
        self.assertEqual(row["effective_weight"], 0.0)

    def test_all_learned_unavailable_cannot_produce_strong_verdict(self):
        result = self.run_fusion(learned(None, available=False), forensic("diffusion_edge_artifacts", 0.99))
        self.assertNotIn(result["verdict"], {"likely_ai_generated", "likely_authentic"})
        self.assertIn("No learned image detector contributed", result["limitations"][0])

    def test_one_uncalibrated_learned_detector_never_produces_strong_verdict(self):
        result = self.run_fusion(learned(0.99))
        self.assertNotIn(result["verdict"], {"likely_ai_generated", "likely_authentic"})
        row = next(item for item in result["detector_contributions"] if item["detector_id"] == "universal_fake_detect")
        self.assertEqual(row["status"], "uncalibrated")
        self.assertEqual(row["calibration_status"], "uncalibrated")

    def test_strong_multifamily_ai_agreement(self):
        result = self.run_fusion(learned(0.96), forensic("diffusion_edge_artifacts", 0.91))
        self.assertEqual(result["verdict"], "likely_ai_generated")
        self.assertGreater(result["weighted_ai_evidence"], 0)

    def test_strong_multifamily_authentic_agreement(self):
        result = self.run_fusion(learned(0.04), forensic("prnu_approximation", 0.08))
        self.assertEqual(result["verdict"], "likely_authentic")
        self.assertGreater(result["weighted_authentic_evidence"], 0)

    def test_conflicting_models_are_named_and_reduce_confidence(self):
        agreeing = self.run_fusion(learned(0.92), forensic("diffusion_edge_artifacts", 0.88))
        conflict = self.run_fusion(learned(0.92), forensic("diffusion_edge_artifacts", 0.08))
        self.assertGreater(conflict["conflict_score"], 0)
        self.assertIn("universal_fake_detect", conflict["conflicting_detectors"])
        self.assertIn("diffusion_edge_artifacts", conflict["conflicting_detectors"])
        self.assertLess(conflict["confidence"], agreeing["confidence"])

    def test_high_conflict_forces_inconclusive(self):
        opposing = {}
        for detector_id in ("diffusion_edge_artifacts", "prnu_approximation", "gan_checkerboard_artifacts", "lighting_consistency"):
            opposing.update(forensic(detector_id, 0.02, confidence=1.0, reliability=1.0))
        result = self.run_fusion(learned(0.98, confidence=1.0), opposing)
        self.assertGreater(result["conflict_score"], 0.70)
        self.assertEqual(result["verdict"], "inconclusive")

    def test_poor_media_quality_blocks_strong_verdict(self):
        result = self.run_fusion(
            learned(0.98), forensic("diffusion_edge_artifacts", 0.95),
            resolution={"width": 64, "height": 64}, quality_warnings=["Blurry", "Very dark"],
            compression={"applicable": True, "estimated_jpeg_quality": 20},
        )
        self.assertNotIn(result["verdict"], {"likely_ai_generated", "likely_authentic"})
        self.assertTrue(any("resolution" in item.lower() for item in result["limitations"]))

    def test_low_resolution_reduces_weight(self):
        high = self.run_fusion(learned(0.9), forensic("diffusion_edge_artifacts", 0.9))
        low = self.run_fusion(learned(0.9), forensic("diffusion_edge_artifacts", 0.9), resolution={"width": 120, "height": 120})
        def weight(result):
            return next(item["effective_weight"] for item in result["contributions"] if item["detector_id"] == "universal_fake_detect")
        self.assertLess(weight(low), weight(high))

    def test_low_coverage_forces_inconclusive(self):
        result = self.run_fusion(forensic_detectors=forensic("future_detector", 0.99, confidence=0.01, reliability=0.01))
        self.assertEqual(result["verdict"], "inconclusive")

    def test_missing_metadata_is_neutral(self):
        result = self.run_fusion()
        row = next(item for item in result["detector_contributions"] if item["detector_id"] == "metadata_provenance")
        self.assertEqual(row["status"], "inconclusive")
        self.assertIsNone(row["normalized_ai_probability"])
        self.assertEqual(row["effective_weight"], 0.0)

    def test_generator_metadata_is_directional_but_not_sufficient_for_strong_verdict(self):
        result = self.run_fusion(metadata={"metadata_warnings": ["generator_or_ai_software_detected"]})
        row = next(item for item in result["detector_contributions"] if item["detector_id"] == "metadata_provenance")
        self.assertGreater(row["normalized_ai_probability"], 0.5)
        self.assertNotIn(result["verdict"], {"likely_ai_generated", "likely_authentic"})

    def test_warnings_reduce_effective_weight(self):
        clear = self.run_fusion(forensic_detectors=forensic("diffusion_edge_artifacts", 0.9))
        warned = self.run_fusion(forensic_detectors=forensic("diffusion_edge_artifacts", 0.9, warnings=["a", "b"]))
        def weight(result):
            return next(item["effective_weight"] for item in result["detector_contributions"] if item["detector_id"] == "diffusion_edge_artifacts")
        self.assertLess(weight(warned), weight(clear))

    def test_false_negative_learned_signal_is_exposed_as_conflict(self):
        others = forensic("diffusion_edge_artifacts", 0.94)
        others.update(forensic("gan_checkerboard_artifacts", 0.90))
        result = self.run_fusion(learned(0.194), others)
        self.assertGreater(result["conflict_score"], 0)
        self.assertIn("universal_fake_detect", result["conflicting_detectors"])

    def test_universal_fake_strong_positive_requires_independent_support(self):
        result = self.run_fusion(learned(0.99), forensic("diffusion_edge_artifacts", 0.95))
        self.assertEqual(result["verdict"], "likely_ai_generated")

    def test_future_detector_uses_generic_adapter(self):
        result = self.run_fusion(forensic_detectors=forensic("future_detector_v2", 0.8))
        row = next(item for item in result["contributions"] if item["detector_id"] == "future_detector_v2")
        self.assertEqual(row["evidence_family"], "forensic")
        self.assertEqual(row["normalized_ai_probability"], 0.8)
        self.assertIn("timing_ms", row)

    def test_deterministic_repeated_results_except_timing(self):
        first = self.run_fusion(learned(0.8), forensic("prnu_approximation", 0.7))
        second = self.run_fusion(learned(0.8), forensic("prnu_approximation", 0.7))
        first.pop("processing_time_ms")
        second.pop("processing_time_ms")
        self.assertEqual(first, second)

    def test_invalid_policy_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps({"schema_version": 99}), encoding="utf-8")
            result = FusionEngine(policy_path=path).analyze()
        self.assertEqual(result["verdict"], "inconclusive")
        self.assertEqual(result["confidence"], 0.0)
        self.assertIsNotNone(result["error"])

    def test_video_is_inconclusive_when_image_detectors_are_unsupported(self):
        result = self.run_fusion(learned(None, available=False), media_type="video")
        self.assertEqual(result["verdict"], "inconclusive")

    def test_ui_contains_dedicated_fusion_card_and_disclaimer(self):
        rendered = web_ui.render_analyze_page()
        self.assertIn("Evidence fusion summary", rendered)
        self.assertIn("Probabilistic evidence summary", rendered)
        self.assertIn("renderFusion(fields,body.fusion)", rendered)

    def test_explanation_and_requested_alias_contract(self):
        result = self.run_fusion(learned(0.9), forensic("diffusion_edge_artifacts", 0.85))
        for field in ("primary_reasons", "supporting_reasons", "counter_evidence", "limitations", "warnings", "contributions"):
            self.assertIn(field, result)
            self.assertIsInstance(result[field], list)


if __name__ == "__main__":
    unittest.main()
