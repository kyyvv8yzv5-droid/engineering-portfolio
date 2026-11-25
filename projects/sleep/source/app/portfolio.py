from __future__ import annotations

from datetime import date, datetime

from .domain import EquityPoint, Position, Side, Trade, SUPPORTED_SYMBOLS


class PortfolioError(ValueError):
    pass


class Portfolio:
    def __init__(self, starting_cash: float, symbols: tuple[str, ...] | list[str] | None = None):
        if starting_cash <= 0:
            raise PortfolioError("Starting cash must be positive")
        self.starting_cash = starting_cash
        self.cash = starting_cash
        universe = tuple(symbols or SUPPORTED_SYMBOLS)
        if not universe or len(set(universe)) != len(universe):
            raise PortfolioError("Portfolio symbols must be unique and non-empty")
        self.positions = {symbol: Position() for symbol in universe}
        self.trades: list[Trade] = []
        self.equity_curve: list[EquityPoint] = []
        self.peak_equity = starting_cash
        self.last_loss_at: datetime | None = None

    def apply_trade(self, trade: Trade) -> None:
        if trade.symbol not in self.positions:
            raise PortfolioError("Unsupported asset")
        if trade.quantity <= 0 or trade.price <= 0 or trade.fee < 0:
            raise PortfolioError("Invalid trade values")
        position = self.positions[trade.symbol]
        if trade.side is Side.BUY:
            total_cost = trade.notional + trade.fee
            if total_cost > self.cash + 1e-8:
                raise PortfolioError("Insufficient cash")
            old_cost = position.quantity * position.average_cost
            position.quantity += trade.quantity
            position.average_cost = (old_cost + total_cost) / position.quantity
            self.cash -= total_cost
        elif trade.side is Side.SELL:
            if trade.quantity > position.quantity + 1e-10:
                raise PortfolioError("Insufficient position")
            proceeds = trade.notional - trade.fee
            realized = proceeds - (position.average_cost * trade.quantity)
            position.quantity -= trade.quantity
            position.realized_pnl += realized
            if position.quantity < 1e-10:
                position.quantity = 0.0
                position.average_cost = 0.0
            self.cash += proceeds
            if realized < 0:
                self.last_loss_at = trade.timestamp
            trade = Trade(**{**trade.__dict__, "realized_pnl": realized})
        else:
            raise PortfolioError("HOLD is not executable")
        self.trades.append(trade)

    def equity(self, prices: dict[str, float]) -> float:
        return self.cash + sum(position.quantity * prices.get(symbol, 0.0) for symbol, position in self.positions.items())

    def mark(self, timestamp: datetime, prices: dict[str, float]) -> EquityPoint:
        equity = self.equity(prices)
        self.peak_equity = max(self.peak_equity, equity)
        drawdown = 0.0 if self.peak_equity == 0 else (self.peak_equity - equity) / self.peak_equity
        point = EquityPoint(timestamp, equity, self.cash, drawdown)
        self.equity_curve.append(point)
        return point

    def daily_realized_pnl(self, day: date) -> float:
        return sum(t.realized_pnl for t in self.trades if t.timestamp.date() == day)

    def snapshot(self, prices: dict[str, float]) -> dict:
        total = self.equity(prices)
        assets = {
            symbol: {
                "quantity": round(pos.quantity, 8),
                "value": round(pos.quantity * prices.get(symbol, 0.0), 2),
                "average_cost": round(pos.average_cost, 2),
                "realized_pnl": round(pos.realized_pnl, 2),
            }
            for symbol, pos in self.positions.items()
        }
        allocations = {symbol: (data["value"] / total if total else 0.0) for symbol, data in assets.items()}
        allocations["cash"] = self.cash / total if total else 0.0
        return {"total_equity": round(total, 2), "cash": round(self.cash, 2), "assets": assets, "allocations": allocations}

