from __future__ import annotations

from .domain import Order, Side, Trade
from .portfolio import Portfolio


class PaperBroker:
    def __init__(self, portfolio: Portfolio, fee_bps: float = 10, slippage_bps: float = 5):
        if fee_bps < 0 or slippage_bps < 0:
            raise ValueError("Fees and slippage cannot be negative")
        self.portfolio = portfolio
        self.fee_rate = fee_bps / 10_000
        self.slippage_rate = slippage_bps / 10_000

    def execute(self, order: Order) -> Trade:
        if order.side not in (Side.BUY, Side.SELL):
            raise ValueError("Only BUY and SELL orders can execute")
        multiplier = 1 + self.slippage_rate if order.side is Side.BUY else 1 - self.slippage_rate
        fill_price = order.reference_price * multiplier
        notional = fill_price * order.quantity
        fee = notional * self.fee_rate
        slippage_cost = abs(fill_price - order.reference_price) * order.quantity
        trade = Trade(
            order.symbol, order.side, order.quantity, fill_price, notional, fee,
            order.timestamp, reason=order.reason, reference_price=order.reference_price,
            slippage_cost=slippage_cost,
        )
        self.portfolio.apply_trade(trade)
        return self.portfolio.trades[-1]


class LiveBrokerDisabled:
    def execute(self, _order: Order) -> None:
        raise RuntimeError("Live trading is disabled. This application supports paper execution only.")
