from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4


@dataclass(frozen=True)
class AuditEvent:
    product: str
    event_id: str
    timestamp: str
    event_type: str
    asset: str
    strategy: str
    market_data_used: str
    rule_output: str
    risk_checks: str
    operating_mode: str
    outcome: str

    def as_dict(self) -> dict:
        # All event fields are immutable scalar strings; a shallow copy preserves isolation.
        return self.__dict__.copy()


class AuditLog:
    def __init__(self) -> None:
        self._events: list[AuditEvent] = []
        self._lock = Lock()

    def record(self, *, event_type: str, asset: str = "", strategy: str = "", market_data_used: str = "", rule_output: str = "", risk_checks: str = "", operating_mode: str = "", outcome: str = "") -> AuditEvent:
        event = AuditEvent("SLEEP", str(uuid4()), datetime.now(timezone.utc).isoformat(), event_type, asset, strategy, market_data_used, rule_output, risk_checks, operating_mode, outcome)
        with self._lock:
            self._events.append(event)
        return event

    def list(self) -> list[dict]:
        with self._lock:
            return [event.as_dict() for event in self._events]

    def recent(self, limit: int = 50) -> list[dict]:
        with self._lock:
            return [event.as_dict() for event in reversed(self._events[-max(1, min(limit, 200)):])]

    def matching(self, event_type: str) -> list[dict]:
        with self._lock:
            return [event.as_dict() for event in self._events if event.event_type == event_type]

    def page(self, limit: int = 50, before: str | None = None, *, event_type: str | None = None,
             asset: str | None = None, strategy: str | None = None, search: str | None = None,
             category: str | None = None) -> dict:
        """Newest first, bounded serialization; cursor/filter before pagination."""
        limit = max(1, min(int(limit), 200))
        with self._lock:
            end = len(self._events)
            if before:
                index = next((i for i, event in enumerate(self._events) if event.event_id == before), None)
                if index is None:
                    raise ValueError("Unknown activity cursor")
                end = index
            needle = (search or '').casefold()
            selected = []
            for index in range(end - 1, -1, -1):
                event = self._events[index]
                if event_type and event.event_type != event_type:
                    continue
                if asset and event.asset != asset:
                    continue
                if strategy and event.strategy != strategy:
                    continue
                if category and category != "All" and self._category(event) != category:
                    continue
                if needle and needle not in ' '.join(event.__dict__.values()).casefold():
                    continue
                selected.append(event)
                if len(selected) > limit:
                    break
            more = len(selected) > limit
            records = [event.as_dict() for event in selected[:limit]]
            return {'events': records, 'has_more': more,
                    'next_cursor': records[-1]['event_id'] if more else None}

    @staticmethod
    def _category(event: AuditEvent) -> str:
        event_type, state = event.event_type, event.rule_output
        if "agent_" in event_type or "autopilot" in event_type:
            return "Agents"
        if any(term in event_type for term in ("settings", "policy", "restriction")):
            return "Settings"
        if any(term in event_type for term in ("learn", "quiz", "conversation", "explanation")):
            return "Learning"
        if "risk" in event_type.lower() or "RISK_" in state:
            return "Risk"
        if any(term in event_type for term in ("trade", "order", "position")) or state in {
            "OPEN", "CLOSED", "EXECUTING", "EXITING"
        }:
            return "Trades"
        return "All"

    def restore(self, rows: list[dict]) -> None:
        """Restore a previously exported local paper audit journal."""
        with self._lock:
            self._events = [AuditEvent(**row) for row in rows]

    def csv(self) -> str:
        rows = self.list()
        output = io.StringIO()
        keys = list(AuditEvent.__dataclass_fields__)
        writer = csv.DictWriter(output, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue()
