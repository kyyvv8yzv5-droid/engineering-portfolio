from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.derivatives import DerivativeSpec, DerivativesResearchAccount
from app.audit_log import AuditLog
from app.main import app
from app.pairs_research import SharedPairPaperAccount
from app.platform_service import PlatformService
from app.risk_supervisor import RiskReservation, SharedRiskSupervisor


COLLECTION_FIELDS = (
    "agents", "active_pair_positions", "pair_legs", "open_spot_positions",
    "open_derivative_positions", "active_opportunities", "recent_decisions", "risk_rejections",
)
NUMERIC_SUMMARIES = (
    "portfolio_equity", "total_capital_committed", "total_notional_exposure",
    "total_gross_exposure", "total_net_exposure", "modeled_loss_at_stops",
    "derivatives_margin_used", "pair_exposure",
)


def dashboard(spot: bool = False) -> dict:
    assets = {
        symbol: {"quantity": 0.0, "value": 0.0, "average_cost": 0.0, "realized_pnl": 0.0, "unrealized_pnl": 0.0}
        for symbol in ("BTC/USD", "ETH/USD", "SOL/USD", "XRP/USD", "ADA/USD")
    }
    if spot:
        assets["BTC/USD"].update(quantity=1.0, value=10_000.0, average_cost=9_500.0, unrealized_pnl=500.0)
    return {"portfolio": {"total_equity": 100_000.0, "cash": 90_000.0 if spot else 100_000.0, "assets": assets},
            "generated_at": datetime.now(timezone.utc).isoformat()}


def telemetry_service(pair_account=None, derivative_account=None) -> PlatformService:
    service = object.__new__(PlatformService)
    from app.agent_settings import baseline
    service.agent_risk_settings = baseline()
    service.pair_account = pair_account or SharedPairPaperAccount(100_000, 0, 0)
    service.derivatives_account = derivative_account or DerivativesResearchAccount(100_000, 0, 0)
    service.risk_supervisor = SharedRiskSupervisor(100_000)
    service.opportunity_engine = SimpleNamespace(opportunities={})
    service._family_decisions = {"Pairs Agent": "Monitoring", "Leveraged Long/Short Agent": "Monitoring"}
    service.audit = AuditLog()
    service.starting_balance = 100_000
    return service


def add_pair(service: PlatformService):
    position = service.pair_account.open("SOL/ETH", "short_first", {"SOL": 100, "ETH": 2_000}, 8_000, 1.0, 2.0, .8, "stable")
    key = "pair-" + position.position_id
    service.risk_supervisor.reservations[key] = RiskReservation(key, "Pairs & Relative Strength", 8_000, 8_000, 200, 8_000, 0, pair_exposure=8_000, edge=1)


def add_derivative(service: PlatformService):
    position = service.derivatives_account.open(DerivativeSpec("BTC/USD", "perpetual", 2.0), "long", 100, 10_000)
    key = "derivative-" + position.position_id
    service.risk_supervisor.reservations[key] = RiskReservation(key, "Leveraged Long/Short", 5_000, 10_000, 250, 10_000, 10_000, margin=5_000, edge=1)


def add_spot(service: PlatformService):
    service.risk_supervisor.reservations["spot"] = RiskReservation("spot", "Spot Directional", 10_000, 10_000, 500, 10_000, 10_000, edge=1)


@pytest.mark.parametrize("scenario", ["empty", "spot", "pair", "derivative", "all"])
def test_telemetry_contract_for_every_family_combination(scenario):
    service = telemetry_service()
    spot = scenario in {"spot", "all"}
    if spot: add_spot(service)
    if scenario in {"pair", "all"}: add_pair(service)
    if scenario in {"derivative", "all"}: add_derivative(service)
    payload = service._normalized_agent_telemetry(dashboard(spot)).model_dump(mode="json")
    assert payload["schema_version"] == "3.0"
    assert all(isinstance(payload[field], list) for field in COLLECTION_FIELDS)
    assert all(isinstance(payload["risk_supervisor"][field], (int, float)) for field in NUMERIC_SUMMARIES)
    assert len(payload["agents"]) == 4
    assert payload["agent_manager"]["paper_only"] is True
    assert len(payload["performance"]["agents"]) == 4
    assert len(payload["snipe_monitoring"]["windows"]) == 3
    identity_total = (payload["performance"]["open_unrealized_change_today"]
                      + payload["performance"]["gross_realized_pnl_today"]
                      - payload["performance"]["costs_today"])
    assert payload["performance"]["today_net_pnl"] == pytest.approx(identity_total, abs=.01)
    assert payload["performance"]["reconciliation_difference"] == pytest.approx(0, abs=.01)
    for contribution in payload["performance"]["agents"]:
        assert contribution["net_contribution_today"] == pytest.approx(
            contribution["open_unrealized_change_today"] + contribution["gross_realized_pnl_today"]
            - contribution["costs_today"], abs=.001)
    assert payload["risk_supervisor"]["total_gross_exposure"] >= payload["risk_supervisor"]["pair_exposure"]
    if scenario in {"pair", "all"}:
        assert len(payload["active_pair_positions"]) == 1
        assert len(payload["pair_legs"]) == 2
        assert payload["risk_supervisor"]["total_capital_committed"] >= 8_000
        assert payload["risk_supervisor"]["total_notional_exposure"] >= 8_000
        assert payload["risk_supervisor"]["total_gross_exposure"] >= 8_000
        pair = payload["active_pair_positions"][0]
        assert pair["holding_time_seconds"] >= 0
        assert pair["estimated_entry_costs"] >= 0
        assert pair["accumulated_costs"] >= 0
        assert pair["net_pnl_after_costs"] == pytest.approx(pair["total_pair_pnl"])


def test_recovered_pair_schema_matches_live_created_schema(tmp_path):
    state = tmp_path / "pair.json"
    live_account = SharedPairPaperAccount(100_000, 0, 0, state)
    live_account.open("SOL/ETH", "short_first", {"SOL": 100, "ETH": 2_000}, 8_000, 1.0, 2.0, .8, "stable")
    recovered_account = SharedPairPaperAccount(100_000, 0, 0, state)
    live, recovered = telemetry_service(live_account), telemetry_service(recovered_account)
    add_reservation = lambda service: service.risk_supervisor.reservations.update({"pair": RiskReservation("pair", "Pairs & Relative Strength", 8_000, 8_000, 200, 8_000, 0, pair_exposure=8_000, edge=1)})
    add_reservation(live); add_reservation(recovered)
    live_payload = live._normalized_agent_telemetry(dashboard()).model_dump(mode="json")
    recovered_payload = recovered._normalized_agent_telemetry(dashboard()).model_dump(mode="json")
    assert live_payload.keys() == recovered_payload.keys()
    assert live_payload["active_pair_positions"][0].keys() == recovered_payload["active_pair_positions"][0].keys()
    assert live_payload["pair_legs"][0].keys() == recovered_payload["pair_legs"][0].keys()


def test_supervisor_totals_use_open_positions_not_larger_risk_reservations():
    service = telemetry_service()
    add_spot(service)
    add_pair(service)
    data = dashboard(spot=True)
    data["portfolio"]["assets"]["BTC/USD"]["value"] = 5_000.0
    payload = service._normalized_agent_telemetry(data).model_dump(mode="json")
    supervisor = payload["risk_supervisor"]
    assert supervisor["total_capital_committed"] == pytest.approx(13_000)
    assert supervisor["total_notional_exposure"] == pytest.approx(13_000)
    assert supervisor["total_gross_exposure"] == pytest.approx(13_000)
    assert supervisor["pair_exposure"] == pytest.approx(8_000)
    assert supervisor["modeled_loss_at_stops"] == pytest.approx(450)
    capital = payload["capital_breakdown"]
    assert capital["cash_balance"] == pytest.approx(90_000)
    assert capital["spot_invested"] == pytest.approx(5_000)
    assert capital["pair_exposure"] == pytest.approx(8_000)
    assert capital["total_capital_committed"] == pytest.approx(13_000)
    assert "do not subtract" in capital["explanation"]


def test_snipe_windows_group_candidates_without_hiding_audit_detail():
    service = telemetry_service()
    service.audit.record(event_type="snipe_candidate_evaluated", asset="ETH/USD", strategy="Snipe",
                         rule_output="STRATEGY_REJECTED", operating_mode="automated-paper",
                         outcome="No Snipe: recommendation=SELL, confidence=0.1850, required confidence>=0.5500.")
    summary = service.snipe_monitoring().model_dump(mode="json")
    assert len(summary["recent_evaluations"]) == 1
    assert [window["window"] for window in summary["windows"]] == ["Last 15 minutes", "Last hour", "Today"]
    assert all(window["candidates_evaluated"] == 1 for window in summary["windows"])
    assert all(window["sell_candidates"] == 1 for window in summary["windows"])
    assert all(window["strategy_rejected"] == 1 for window in summary["windows"])
    assert all(window["required_confidence"] == pytest.approx(.55) for window in summary["windows"])


def test_canonical_endpoint_and_frontend_collection_guards():
    response = TestClient(app).get("/api/agents/telemetry")
    assert response.status_code == 200
    payload = response.json()
    assert all(isinstance(payload[field], list) for field in COLLECTION_FIELDS)
    source = (Path(__file__).resolve().parents[1] / "static" / "agents.js").read_text(encoding="utf-8")
    assert "const list=value=>Array.isArray(value)?value:[]" in source
    assert "data.agents.map" not in source
    assert "data.trading_agents.map" not in source
    assert "position.invalidation_conditions.map" not in source
