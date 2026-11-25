from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum


class NewsCategory(str, Enum):
    CRYPTO = "crypto-specific news"
    REGULATION = "regulatory event"
    ETF = "ETF development"
    SECURITY = "exchange/security incident"
    FOMC = "FOMC"
    CPI = "CPI"
    EMPLOYMENT = "employment report"
    LIQUIDITY = "major liquidity/macro event"


@dataclass(frozen=True)
class ContextEvent:
    timestamp: datetime
    category: NewsCategory
    headline: str
    affected_assets: tuple[str, ...]
    severity: str
    source: str
    risk_context: str
    can_generate_trade: bool = False

    def as_dict(self) -> dict:
        result = asdict(self)
        result["timestamp"] = self.timestamp.isoformat()
        result["category"] = self.category.value
        result["affected_assets"] = list(self.affected_assets)
        return result


def overlay_schema() -> dict:
    return {
        "categories": [category.value for category in NewsCategory],
        "events": [],
        "trade_generation_enabled": False,
        "purpose": "Context and risk overlay only; never a standalone buy/sell trigger.",
        "status": "Data model and interface prepared; external news ingestion is scaffolded for a later phase.",
    }
