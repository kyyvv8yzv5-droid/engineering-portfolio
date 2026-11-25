"""Stable typed contracts shared by fusion adapters and consumers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


VALID_STATUSES = {
    "success", "unavailable", "disabled", "unsupported", "failed",
    "inconclusive", "uncalibrated",
}
VALID_PREDICTIONS = {"supports_ai", "supports_authentic", "neutral", "unknown"}


def clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


@dataclass
class EvidenceContribution:
    detector_id: str
    detector_name: str
    detector_version: str
    evidence_family: str
    availability: bool
    enabled: bool
    status: str
    raw_score: Any = None
    normalized_ai_probability: float | None = None
    calibration_status: str = "unknown"
    reliability_score: float = 0.0
    effective_weight: float = 0.0
    prediction: str = "unknown"
    confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    timing_ms: float = 0.0
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.status not in VALID_STATUSES:
            raise ValueError(f"invalid contribution status: {self.status}")
        if self.prediction not in VALID_PREDICTIONS:
            raise ValueError(f"invalid contribution prediction: {self.prediction}")
        if self.normalized_ai_probability is not None:
            self.normalized_ai_probability = clamp(self.normalized_ai_probability)
        self.reliability_score = clamp(self.reliability_score)
        self.confidence = clamp(self.confidence)
        self.effective_weight = max(0.0, float(self.effective_weight))
        self.timing_ms = max(0.0, float(self.timing_ms or 0.0))

    @property
    def usable(self) -> bool:
        return (
            self.availability
            and self.enabled
            and self.status in {"success", "uncalibrated"}
            and self.normalized_ai_probability is not None
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FusionResult:
    verdict: str
    ai_score: float
    authentic_score: float
    confidence: float
    confidence_label: str
    coverage: float
    conflict_score: float
    weighted_ai_evidence: float
    weighted_authentic_evidence: float
    neutral_unresolved_evidence: float
    primary_reasons: list[str]
    supporting_evidence: list[str]
    conflicting_evidence: list[str]
    limitations: list[str]
    detector_contributions: list[dict[str, Any]]
    conflicting_detectors: list[str]
    conflicting_families: list[str]
    conflict_explanation: str
    policy_version: int = 1
    schema_version: int = 1
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
