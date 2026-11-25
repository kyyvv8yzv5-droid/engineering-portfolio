"""Stable contracts shared by every offline Evidence Engine detector."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

import cv2
import numpy as np


def clamp(value, minimum=0.0, maximum=1.0):
    return float(max(minimum, min(maximum, float(value))))


@dataclass(frozen=True)
class EvidenceObject:
    evidence_id: str
    category: str
    direction: str
    strength: float
    confidence: float
    description: str
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        value = asdict(self)
        value["strength"] = round(clamp(value["strength"]), 6)
        value["confidence"] = round(clamp(value["confidence"]), 6)
        return value


@dataclass
class DetectorResult:
    detector_id: str
    applicable: bool
    ai_probability: float | None
    confidence: float
    explanation: str
    evidence: list[EvidenceObject] = field(default_factory=list)
    processing_time_ms: float = 0.0
    weight: float = 1.0
    reliability: float = 0.5
    false_positive_rate: float = 0.1
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self):
        return {
            "detector_id": self.detector_id,
            "applicable": bool(self.applicable),
            "ai_probability": (
                None if self.ai_probability is None
                else round(clamp(self.ai_probability), 6)
            ),
            "confidence": round(clamp(self.confidence), 6),
            "explanation": self.explanation,
            "evidence": [item.to_dict() for item in self.evidence],
            "processing_time_ms": round(max(0.0, self.processing_time_ms), 3),
            "weight": round(max(0.0, float(self.weight)), 6),
            "reliability": round(clamp(self.reliability), 6),
            "false_positive_rate": round(clamp(self.false_positive_rate), 6),
            "warnings": list(self.warnings),
            "error": self.error,
        }


@dataclass(frozen=True)
class DetectorContext:
    image: np.ndarray
    data: bytes
    extension: str
    metadata: dict[str, Any]
    compression: dict[str, Any]

    def bounded_image(self, maximum=512):
        height, width = self.image.shape[:2]
        scale = min(1.0, float(maximum) / max(height, width))
        if scale == 1.0:
            return self.image
        return cv2.resize(
            self.image,
            (max(1, round(width * scale)), max(1, round(height * scale))),
            interpolation=cv2.INTER_AREA,
        )

    def gray(self, maximum=512):
        image = self.bounded_image(maximum)
        if image.ndim == 2:
            gray = image
        else:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return gray.astype(np.float32) / 255.0


class EvidenceDetector:
    detector_id = "base"
    weight = 1.0
    reliability = 0.5
    false_positive_rate = 0.1

    def analyze(self, context: DetectorContext) -> DetectorResult:
        started = time.perf_counter()
        try:
            result = self._analyze(context)
        except Exception as error:  # one weak detector must never fail /analyze
            result = self.not_applicable(
                "Detector failed safely and did not contribute to the verdict.",
                warnings=["detector_internal_failure"],
                error=f"{type(error).__name__}: {error}",
            )
        result.processing_time_ms = (time.perf_counter() - started) * 1000.0
        result.weight = self.weight
        result.reliability = self.reliability
        result.false_positive_rate = self.false_positive_rate
        return result

    def _analyze(self, context: DetectorContext) -> DetectorResult:
        raise NotImplementedError

    def result(
        self,
        probability,
        confidence,
        explanation,
        evidence=None,
        warnings=None,
    ):
        return DetectorResult(
            detector_id=self.detector_id,
            applicable=True,
            ai_probability=clamp(probability),
            confidence=clamp(confidence),
            explanation=explanation,
            evidence=list(evidence or []),
            warnings=list(warnings or []),
        )

    def not_applicable(self, explanation, warnings=None, error=None):
        return DetectorResult(
            detector_id=self.detector_id,
            applicable=False,
            ai_probability=None,
            confidence=0.0,
            explanation=explanation,
            evidence=[],
            warnings=list(warnings or []),
            error=error,
        )

    def evidence_object(
        self,
        suffix,
        direction,
        strength,
        confidence,
        description,
        metrics=None,
        category=None,
    ):
        return EvidenceObject(
            evidence_id=f"{self.detector_id}.{suffix}",
            category=category or self.detector_id,
            direction=direction,
            strength=clamp(strength),
            confidence=clamp(confidence),
            description=description,
            metrics=dict(metrics or {}),
        )
