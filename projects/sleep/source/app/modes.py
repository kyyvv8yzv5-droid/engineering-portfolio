from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum


class OperatingMode(str, Enum):
    AUTOMATED = "automated"
    APPROVAL = "approval"
    LEARN = "learn"
    IDEAS = "ideas"
    COPILOT = "copilot"
    MANUAL = "manual"
    AUTOPILOT = "autopilot"


@dataclass(frozen=True)
class ModePolicy:
    mode: OperatingMode
    description: str
    can_view_ideas: bool
    can_analyze_orders: bool
    can_prepare_paper_order: bool
    requires_approval: bool
    available: bool
    autonomous_execution: bool = False
    live_execution: bool = False

    def as_dict(self) -> dict:
        result = asdict(self)
        result["mode"] = self.mode.value
        return result


MODE_POLICIES = {
    OperatingMode.AUTOMATED: ModePolicy(OperatingMode.AUTOMATED, "Primary experience: discover, explain, risk-check, and execute validated paper opportunities automatically.", True, True, False, False, True, autonomous_execution=True),
    OperatingMode.APPROVAL: ModePolicy(OperatingMode.APPROVAL, "SLEEP proposes expiring paper opportunities and waits for explicit approval.", True, True, True, True, True),
    OperatingMode.LEARN: ModePolicy(OperatingMode.LEARN, "Education only; no execution.", False, False, False, False, True),
    OperatingMode.IDEAS: ModePolicy(OperatingMode.IDEAS, "Explained trade ideas; no execution.", True, False, False, False, True),
    OperatingMode.COPILOT: ModePolicy(OperatingMode.COPILOT, "Position and proposed-trade analysis; no execution.", True, True, False, False, True),
    OperatingMode.MANUAL: ModePolicy(OperatingMode.MANUAL, "Secondary workflow for user-initiated paper orders with explicit confirmation.", True, True, True, True, True),
    OperatingMode.AUTOPILOT: ModePolicy(OperatingMode.AUTOPILOT, "Architecture reserved for a later production-readiness phase.", True, True, False, True, False),
}


def policy_for(mode: str | OperatingMode) -> ModePolicy:
    try:
        parsed = mode if isinstance(mode, OperatingMode) else OperatingMode(mode.lower())
    except ValueError as exc:
        raise ValueError("Unknown operating mode") from exc
    return MODE_POLICIES[parsed]


def require_permission(mode: str, permission: str) -> ModePolicy:
    policy = policy_for(mode)
    if not policy.available:
        raise PermissionError(f"{policy.mode.value.title()} mode is unavailable")
    if not getattr(policy, permission, False):
        raise PermissionError(f"{policy.mode.value.title()} mode does not permit {permission.replace('_', ' ')}")
    return policy
