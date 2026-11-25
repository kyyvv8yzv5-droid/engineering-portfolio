    def _failed_result(self, error):
        output = FusionResult(
            verdict="inconclusive", ai_score=0.5, authentic_score=0.5, confidence=0.0,
            confidence_label="low", coverage=0.0, conflict_score=0.0,
            weighted_ai_evidence=0.0, weighted_authentic_evidence=0.0,
            neutral_unresolved_evidence=1.0,
            primary_reasons=["Fusion was withheld because its policy or inputs were invalid."],
            supporting_evidence=[], conflicting_evidence=[],
            limitations=[error, "No fallback verdict was invented."], detector_contributions=[],
            conflicting_detectors=[], conflicting_families=[], conflict_explanation="No conflict calculation was possible.",
            error=error,
        ).to_dict()
        output["supporting_reasons"] = []
        output["counter_evidence"] = []
        output["warnings"] = [error]
        output["contributions"] = []
        output["processing_time_ms"] = 0.0
        return output
