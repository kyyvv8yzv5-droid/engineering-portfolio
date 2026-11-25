from collections import OrderedDict
import time

from detectors.learned.aide import AIDEDetector
from detectors.learned.clip_sid import CLIPSIDDetector
from detectors.learned.ssp import SSPDetector
from detectors.learned.trufor import TruForDetector
from detectors.learned.universal_fake import UniversalFakeDetector


class LearnedDetectorRegistry:
    """Ordered, fail-isolated collection of independent learned detectors."""

    def __init__(self, detectors=None):
        if detectors is None:
            detectors = [
                UniversalFakeDetector(),
                AIDEDetector(),
                CLIPSIDDetector(),
                SSPDetector(),
                TruForDetector(),
            ]
        self._detectors = OrderedDict((detector.key, detector) for detector in detectors)

    @classmethod
    def default(cls, universal_fake_detector=None):
        return cls([
            universal_fake_detector or UniversalFakeDetector(),
            AIDEDetector(),
            CLIPSIDDetector(),
            SSPDetector(),
            TruForDetector(),
        ])

    def get(self, key):
        return self._detectors[key]

    def keys(self):
        return self._detectors.keys()

    def analyze_image(self, image, cached=None):
        cached = cached or {}
        results = OrderedDict()
        for key, detector in self._detectors.items():
            if key in cached:
                results[key] = cached[key]
                continue
            started = time.perf_counter()
            try:
                value = detector.analyze_image(image).to_dict()
            except Exception as error:
                result = detector._result(
                    warnings=["experimental_model", "detector_internal_failure"],
                    error=f"{type(error).__name__}: {error}",
                )
                value = result.to_dict()
            results[key] = self._evidence_contract(
                key, value, (time.perf_counter() - started) * 1000.0
            )
        return dict(results)

    def analyze_video(self, cached=None):
        cached = cached or {}
        results = OrderedDict()
        for key, detector in self._detectors.items():
            if key in cached:
                results[key] = cached[key]
                continue
            started = time.perf_counter()
            try:
                value = detector.video_result().to_dict()
            except Exception as error:
                result = detector._result(
                    applicable=False,
                    warnings=["experimental_model", "detector_internal_failure"],
                    error=f"{type(error).__name__}: {error}",
                )
                value = result.to_dict()
            results[key] = self._evidence_contract(
                key, value, (time.perf_counter() - started) * 1000.0
            )
        return dict(results)

    @staticmethod
    def _evidence_contract(key, value, elapsed_ms):
        value = dict(value)
        probability = value.get("ai_probability")
        available = bool(value.get("available")) and probability is not None
        confidence = min(1.0, 0.55 + abs(float(probability) - 0.5) * 0.8) if available else 0.0
        direction = (
            "supports_ai" if available and probability >= 0.58 else
            "supports_authentic" if available and probability <= 0.42 else
            "neutral"
        )
        value["confidence"] = round(confidence, 6)
        value["explanation"] = (
            "Local learned inference completed; confidence is an uncalibrated distance-from-0.5 heuristic, not empirical accuracy."
            if available else
            "The local learned detector was unavailable, disabled, or not applicable."
        )
        value["evidence"] = [] if not available else [{
            "evidence_id": f"{key}.model_probability",
            "category": "learned_detector",
            "direction": direction,
            "strength": round(abs(float(probability) - 0.5) * 2.0, 6),
            "confidence": round(confidence, 6),
            "description": "Uncalibrated sigmoid output from a locally supplied, fail-closed learned detector.",
            "metrics": {"ai_probability": round(float(probability), 6)},
        }]
        value["processing_time_ms"] = round(max(0.0, elapsed_ms), 3)
        if not value.get("inference_time_ms"):
            value["inference_time_ms"] = value["processing_time_ms"]
        return value
