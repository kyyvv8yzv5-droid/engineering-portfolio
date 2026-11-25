from __future__ import annotations

import csv
import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .assets import PLATFORM_SYMBOLS
from .domain import Candle, SUPPORTED_SYMBOLS


class MarketDataError(RuntimeError):
    pass


class KrakenMarketData:
    """Public, keyless Kraken OHLC source. It can be replaced without touching strategy code."""

    pairs = {"BTC/USD": "XBTUSD", "ETH/USD": "ETHUSD", "SOL/USD": "SOLUSD", "XRP/USD": "XRPUSD", "ADA/USD": "ADAUSD"}
    intervals = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}

    def fetch(self, symbol: str, timeframe: str = "1h", limit: int = 500) -> list[Candle]:
        if symbol not in PLATFORM_SYMBOLS:
            raise MarketDataError(f"Unsupported symbol: {symbol}")
        if timeframe not in self.intervals:
            raise MarketDataError(f"Unsupported timeframe: {timeframe}")
        query = urlencode({"pair": self.pairs[symbol], "interval": self.intervals[timeframe]})
        request = Request(
            f"https://api.kraken.com/0/public/OHLC?{query}",
            headers={"User-Agent": "btc-eth-paper-trader/1.0"},
        )
        try:
            with urlopen(request, timeout=12) as response:
                payload = json.load(response)
        except Exception as exc:
            raise MarketDataError(f"Kraken data request failed: {exc}") from exc
        if payload.get("error"):
            raise MarketDataError(f"Kraken returned: {payload['error']}")
        rows = next(value for key, value in payload["result"].items() if key != "last")
        candles = [
            Candle(
                timestamp=datetime.fromtimestamp(float(row[0]), tz=timezone.utc),
                open=float(row[1]), high=float(row[2]), low=float(row[3]),
                close=float(row[4]), volume=float(row[6]),
            )
            for row in rows[-limit:]
        ]
        if len(candles) < min(limit, 80):
            raise MarketDataError("Not enough historical candles returned")
        return candles


class CsvMarketData:
    def __init__(self, directory: Path):
        self.directory = directory

    def fetch(self, symbol: str, timeframe: str = "1h", limit: int = 500) -> list[Candle]:
        filename = f"{symbol.replace('/', '_')}_{timeframe}.csv"
        path = self.directory / filename
        if not path.exists():
            raise MarketDataError(f"No cached candles at {path}")
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))[-limit:]
        return [
            Candle(
                timestamp=datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")),
                open=float(row["open"]), high=float(row["high"]), low=float(row["low"]),
                close=float(row["close"]), volume=float(row["volume"]),
            )
            for row in rows
        ]


class DemoMarketData:
    """Deterministic offline candles for demos/tests; responses disclose this source."""

    def fetch(self, symbol: str, timeframe: str = "1h", limit: int = 500) -> list[Candle]:
        if symbol not in PLATFORM_SYMBOLS:
            raise MarketDataError(f"Unsupported symbol: {symbol}")
        minutes = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}.get(timeframe)
        if not minutes:
            raise MarketDataError(f"Unsupported timeframe: {timeframe}")
        seeds = {"BTC/USD": 21021, "ETH/USD": 17017, "SOL/USD": 33031, "XRP/USD": 44041, "ADA/USD": 55051}
        starts = {"BTC/USD": 42000.0, "ETH/USD": 2300.0, "SOL/USD": 110.0, "XRP/USD": .55, "ADA/USD": .45}
        seed = seeds[symbol]
        rng = random.Random(seed)
        price = starts[symbol]
        end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        start = end - timedelta(minutes=minutes * (limit - 1))
        candles: list[Candle] = []
        for i in range(limit):
            regime = 0.00045 * math.sin(i / 31) + 0.00018
            shock = rng.gauss(regime, 0.009 * math.sqrt(minutes / 60))
            opened = price
            price = max(100, price * (1 + shock))
            spread = abs(rng.gauss(0.004, 0.002))
            candles.append(Candle(
                timestamp=start + timedelta(minutes=minutes * i), open=opened,
                high=max(opened, price) * (1 + spread), low=min(opened, price) * (1 - spread),
                close=price, volume=abs(rng.gauss(1200 if symbol == "BTC/USD" else 9000, 250)),
            ))
        return candles

    def fetch_range(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> list[Candle]:
        minutes = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}.get(timeframe)
        if not minutes:
            raise MarketDataError(f"Unsupported timeframe: {timeframe}")
        count = int((end - start).total_seconds() // (minutes * 60)) + 1
        if count < 2:
            raise MarketDataError("Date range is too short")
        seeds = {"BTC/USD": 21021, "ETH/USD": 17017, "SOL/USD": 33031, "XRP/USD": 44041, "ADA/USD": 55051}
        starts = {"BTC/USD": 42000.0, "ETH/USD": 2300.0, "SOL/USD": 110.0, "XRP/USD": .55, "ADA/USD": .45}
        if symbol not in seeds:
            raise MarketDataError(f"Unsupported symbol: {symbol}")
        seed = seeds[symbol]
        rng = random.Random(seed + int(start.timestamp()) // 86400)
        price = starts[symbol]
        candles: list[Candle] = []
        for i in range(count):
            timestamp = start + timedelta(minutes=minutes * i)
            if timestamp > end:
                break
            scale = math.sqrt(minutes / 60)
            regime = 0.0003 * math.sin(i / 41) + 0.00008 * scale
            shock = rng.gauss(regime, 0.008 * scale)
            opened = price
            price = max(10, price * (1 + shock))
            spread = abs(rng.gauss(0.003 * scale, 0.0015 * scale))
            candles.append(Candle(timestamp, opened, max(opened, price) * (1 + spread), min(opened, price) * (1 - spread), price, abs(rng.gauss(1500, 300))))
        return candles


class YahooMarketData:
    """Date-ranged public crypto candles; 4h bars are aggregated from 1h bars."""

    tickers = {"BTC/USD": "BTC-USD", "ETH/USD": "ETH-USD", "SOL/USD": "SOL-USD", "XRP/USD": "XRP-USD", "ADA/USD": "ADA-USD"}

    def fetch_range(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> list[Candle]:
        if symbol not in self.tickers:
            raise MarketDataError(f"Unsupported symbol: {symbol}")
        interval = "1h" if timeframe == "4h" else timeframe
        if interval not in {"15m", "1h", "1d"}:
            raise MarketDataError(f"Unsupported timeframe: {timeframe}")
        query = urlencode({
            "period1": int(start.timestamp()), "period2": int(end.timestamp()) + 86400,
            "interval": interval, "events": "history", "includeAdjustedClose": "true",
        })
        request = Request(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{self.tickers[symbol]}?{query}",
            headers={"User-Agent": "Mozilla/5.0 btc-eth-research/2.0"},
        )
        try:
            with urlopen(request, timeout=25) as response:
                payload = json.load(response)["chart"]["result"][0]
            timestamps = payload["timestamp"]
            quote = payload["indicators"]["quote"][0]
            rows = []
            for i, stamp in enumerate(timestamps):
                values = [quote[key][i] for key in ("open", "high", "low", "close", "volume")]
                if any(value is None for value in values):
                    continue
                timestamp = datetime.fromtimestamp(stamp, tz=timezone.utc)
                if start <= timestamp <= end + timedelta(days=1):
                    rows.append(Candle(timestamp, *map(float, values)))
        except Exception as exc:
            raise MarketDataError(f"Yahoo data request failed: {exc}") from exc
        if timeframe == "4h":
            rows = _aggregate(rows, 4)
        if len(rows) < 100:
            raise MarketDataError("Not enough historical candles returned for this range")
        return rows


def _aggregate(candles: list[Candle], hours: int) -> list[Candle]:
    buckets: dict[datetime, list[Candle]] = {}
    for candle in candles:
        bucket = candle.timestamp.replace(hour=(candle.timestamp.hour // hours) * hours, minute=0, second=0, microsecond=0)
        buckets.setdefault(bucket, []).append(candle)
    return [
        Candle(timestamp, rows[0].open, max(c.high for c in rows), min(c.low for c in rows), rows[-1].close, sum(c.volume for c in rows))
        for timestamp, rows in sorted(buckets.items()) if len(rows) == hours
    ]


class ResilientMarketData:
    def __init__(self, cache_dir: Path):
        self.remote = KrakenMarketData()
        self.ranged = YahooMarketData()
        self.cache = CsvMarketData(cache_dir)
        self.demo = DemoMarketData()

    def fetch(self, symbol: str, timeframe: str = "1h", limit: int = 500) -> tuple[list[Candle], str]:
        try:
            return self.remote.fetch(symbol, timeframe, limit), "kraken"
        except MarketDataError:
            try:
                return self.cache.fetch(symbol, timeframe, limit), "cache"
            except MarketDataError:
                return self.demo.fetch(symbol, timeframe, limit), "demo"

    def fetch_range(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> tuple[list[Candle], str]:
        try:
            return self.ranged.fetch_range(symbol, timeframe, start, end), "yahoo"
        except MarketDataError:
            return self.demo.fetch_range(symbol, timeframe, start, end), "demo"
