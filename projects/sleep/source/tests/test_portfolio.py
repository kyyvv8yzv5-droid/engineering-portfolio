from datetime import datetime, timezone

import pytest

from app.domain import Side, Trade
from app.portfolio import Portfolio, PortfolioError

NOW = datetime(2025, 1, 1, tzinfo=timezone.utc)


def trade(side, quantity, price, fee=0):
    return Trade("BTC/USD", side, quantity, price, quantity * price, fee, NOW)


def test_buy_updates_cash_quantity_and_fee_adjusted_cost_basis():
    portfolio = Portfolio(10_000)
    portfolio.apply_trade(trade(Side.BUY, 1, 1_000, 10))
    assert portfolio.cash == pytest.approx(8_990)
    assert portfolio.positions["BTC/USD"].quantity == 1
    assert portfolio.positions["BTC/USD"].average_cost == pytest.approx(1_010)


def test_partial_sell_realizes_net_profit_and_keeps_cost_basis():
    portfolio = Portfolio(10_000)
    portfolio.apply_trade(trade(Side.BUY, 2, 1_000, 20))
    portfolio.apply_trade(trade(Side.SELL, 1, 1_200, 12))
    assert portfolio.cash == pytest.approx(9_168)
    assert portfolio.positions["BTC/USD"].quantity == 1
    assert portfolio.positions["BTC/USD"].average_cost == pytest.approx(1_010)
    assert portfolio.trades[-1].realized_pnl == pytest.approx(178)


def test_rejects_oversell_and_overspend():
    portfolio = Portfolio(100)
    with pytest.raises(PortfolioError):
        portfolio.apply_trade(trade(Side.BUY, 1, 101))
    with pytest.raises(PortfolioError):
        portfolio.apply_trade(trade(Side.SELL, 1, 10))


def test_equity_and_drawdown_marking():
    portfolio = Portfolio(10_000)
    portfolio.apply_trade(trade(Side.BUY, 1, 1_000))
    assert portfolio.mark(NOW, {"BTC/USD": 1_200, "ETH/USD": 0}).equity == 10_200
    point = portfolio.mark(NOW, {"BTC/USD": 900, "ETH/USD": 0})
    assert point.drawdown == pytest.approx((10_200 - 9_900) / 10_200)

