import json
from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.opportunities import OpportunityState
from app.platform_service import PlatformService
from app.risk_supervisor import RiskReservation, SharedRiskSupervisor


class NoMarketService:
    last_sources = {}

    def status(self, _profile):
        return {"market": {}, "generated_at": "2026-10-05T00:00:00+00:00"}


def test_restore_rebuilds_stale_reservations_from_actual_open_spot_holding(tmp_path):
    state = tmp_path / "user"
    service = PlatformService(NoMarketService(), state_dir=state, user_id="tester")
    service.portfolio.cash = 94_800
    service.portfolio.positions["ETH/USD"].quantity = 2
    service.portfolio.positions["ETH/USD"].average_cost = 2_600
    opportunity = service.opportunity_engine.create(
        agent="Spot Directional Agent", strategy="swing", strategy_family="Spot Directional",
        asset_or_pair="ETH/USD", current_price=2_600, target_notional=5_200, target_allocation=.052,
        thesis="test", signals=["BUY"], invalidation_conditions=["reverse"], stop_price=2_400,
    )
    opportunity.execution_status = OpportunityState.EXITING
    opportunity.entry_trade = {"quantity": 2, "price": 2_600}
    snapshot = service.portfolio.snapshot({"BTC/USD": 0, "ETH/USD": 2_600, "SOL/USD": 0, "XRP/USD": 0, "ADA/USD": 0})
    payload = service.runtime_checkpoint_payload({"portfolio": snapshot})
    payload["risk_reservations"] = [
        {"opportunity_id": key, "family": "Spot Directional", "capital": 60_000,
         "notional": 60_000, "estimated_loss": 3_600, "gross": 60_000, "net": 60_000,
         "margin": 0, "pair_exposure": 0, "correlated_exposure": 60_000, "edge": 10, "costs": 1}
        for key in (opportunity.opportunity_id, "terminal-one", "terminal-two", "terminal-three")
    ]
    service.checkpoint_path.write_text(json.dumps(payload), encoding="utf-8")

    restored = PlatformService(NoMarketService(), state_dir=state, user_id="tester")
    rows = list(restored.risk_supervisor.reservations.values())
    assert len(rows) == 1
    assert rows[0].opportunity_id == opportunity.opportunity_id
    assert rows[0].capital == pytest.approx(5_200)
    assert rows[0].estimated_loss == pytest.approx(400)
    assert any(event["event_type"] == "risk_reservations_reconciled" for event in restored.audit.list())


def test_repeated_reserve_replaces_same_opportunity_instead_of_double_counting():
    supervisor = SharedRiskSupervisor(100_000)
    reservation = RiskReservation("same", "Spot Directional", 20_000, 20_000, 500, 20_000, 20_000, edge=100, costs=10)
    supervisor.reserve(reservation, 100_000)
    supervisor.reserve(reservation, 100_000)
    assert supervisor.utilization(100_000)["capital_committed"] == 20_000


def test_setup_deduplication_records_suppression_and_allows_material_change(tmp_path):
    service = PlatformService(NoMarketService(), state_dir=tmp_path / "user", user_id="tester")
    state = {
        "asset": "SOL/ETH", "strategy": "Cointegration spread reversion",
        "direction": "LONG_FIRST_SHORT_SECOND", "price": .045, "z": -1.7,
        "correlation": .82, "hedge": 1.1, "relationship": True,
        "risk": service._risk_availability_signature(100_000),
    }
    options = dict(ttl=timedelta(hours=2), cooldown=timedelta(minutes=5),
                   price_threshold=.005, diagnostic_thresholds={"z": .25, "correlation": .05, "hedge": .10})
    assert service._duplicate_setup_suppressed("pairs:SOL/ETH", state, **options) is False
    assert service._duplicate_setup_suppressed("pairs:SOL/ETH", state, **options) is True
    assert service.audit.list()[-1]["event_type"] == "duplicate_setup_suppressed"
    moved = dict(state, z=-2.0)
    assert service._duplicate_setup_suppressed("pairs:SOL/ETH", moved, **options) is False


def test_activity_ui_translates_states_and_preserves_expandable_audit_detail():
    source = open("static/test.js", encoding="utf-8").read()
    for phrase in ("Pair opportunity discovered", "Risk Supervisor declined this opportunity", "Planned: Long", "Technical / audit details"):
        assert phrase in source
    assert "<details class=\"activity-technical\">" in source

