from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


SUPPORTED_SYMBOLS = ("BTC/USD", "ETH/USD")


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass(frozen=True)
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            object.__setattr__(self, "timestamp", self.timestamp.replace(tzinfo=timezone.utc))
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("Candle prices must be positive")
        if self.volume < 0:
            raise ValueError("Candle volume cannot be negative")


@dataclass(frozen=True)
class FeatureVector:
    timestamp: datetime
    close: float
    values: tuple[float, ...]
    regime: str = "range-bound"


@dataclass(frozen=True)
class ModelSignal:
    side: Side
    confidence: float
    probability_up: float
    explanation: str
    expected_return: float = 0.0
    uncertainty: float = 0.0


@dataclass(frozen=True)
class Order:
    symbol: str
    side: Side
    quantity: float
    reference_price: float
    timestamp: datetime
    reason: str = ""


@dataclass(frozen=True)
class Trade:
    symbol: str
    side: Side
    quantity: float
    price: float
    notional: float
    fee: float
    timestamp: datetime
    realized_pnl: float = 0.0
    reason: str = ""
    reference_price: float = 0.0
    slippage_cost: float = 0.0

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": round(self.quantity, 8),
            "price": round(self.price, 2),
            "notional": round(self.notional, 2),
            "fee": round(self.fee, 2),
            "timestamp": self.timestamp.isoformat(),
            "realized_pnl": round(self.realized_pnl, 2),
            "reason": self.reason,
            "reference_price": round(self.reference_price, 2),
            "slippage_cost": round(self.slippage_cost, 2),
        }


@dataclass
class Position:
    quantity: float = 0.0
    average_cost: float = 0.0
    realized_pnl: float = 0.0


@dataclass(frozen=True)
class EquityPoint:
    timestamp: datetime
    equity: float
    cash: float
    drawdown: float

    def as_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "equity": round(self.equity, 2),
            "cash": round(self.cash, 2),
            "drawdown": round(self.drawdown, 6),
        }
