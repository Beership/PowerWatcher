"""Electricity price engine: flat / time-of-use / monthly tier surcharge."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

from .config import Tariff


def _hhmm(value: str, fallback: int) -> int:
    """'08:30' -> minutes since midnight."""
    try:
        hour, minute = value.split(":")
        return int(hour) * 60 + int(minute)
    except (AttributeError, ValueError):
        return fallback


class TariffEngine:
    def __init__(self, tariff: Tariff) -> None:
        self.tariff = tariff
        self._ranges: list[tuple[int, int, float, str]] = []
        for period in tariff.periods:
            start = _hhmm(period.start, 0)
            end = _hhmm(period.end, 0)
            self._ranges.append((start, end, float(period.price), period.name))

    # ------------------------------------------------------------------ price
    def _tou_lookup(self, minutes_of_day: int) -> tuple[float, str]:
        for start, end, price, name in self._ranges:
            if start <= end:
                if start <= minutes_of_day < end:
                    return price, name
            else:  # window wraps midnight, e.g. 22:00 -> 08:00
                if minutes_of_day >= start or minutes_of_day < end:
                    return price, name
        return self.tariff.flat_price, "平"

    def price_at(self, ts: int) -> tuple[float, str]:
        """Base energy price (yuan/kWh) and window name for a timestamp."""
        if self.tariff.mode == "flat":
            return self.tariff.flat_price, "平价"
        dt = datetime.fromtimestamp(ts)
        return self._tou_lookup(dt.hour * 60 + dt.minute)

    def surcharge(self, month_kwh_before: float) -> float:
        """Tier surcharge per kWh, based on cumulative usage this month."""
        if not self.tariff.tier_enabled:
            return 0.0
        for limit, delta in self.tariff.tiers:
            if month_kwh_before < limit:
                return delta
        return self.tariff.tiers[-1][1] if self.tariff.tiers else 0.0

    def cost(self, ts: int, kwh: float, month_kwh_before: float) -> float:
        base, _ = self.price_at(ts)
        return kwh * (base + self.surcharge(month_kwh_before))

    # --------------------------------------------------------------- summary
    def signature(self) -> str:
        payload = self.tariff.to_dict_signature()
        return hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]

    def describe(self) -> str:
        if self.tariff.mode == "flat":
            text = f"平价 {self.tariff.flat_price:.4f} 元/kWh"
        else:
            parts = [f"{p.name} {p.start}-{p.end} {p.price:.4f}" for p in self.tariff.periods]
            text = "峰谷 · " + " / ".join(parts)
        if self.tariff.tier_enabled:
            text += "（含月度阶梯）"
        return text
