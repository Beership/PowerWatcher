"""Per-day rollups. Cost is recomputed whenever the tariff changes."""
from __future__ import annotations

from . import model
from .config import Hardware
from .storage import Day, Store, day_key
from .tariff import TariffEngine


def _month_of(day: str) -> str:
    return day[:7]


def recompute_minutes(store: Store, hw: Hardware) -> int:
    """Re-derive every minute's power from stored raw signals.

    Rows written before the raw-signal columns existed keep their original
    wall_w; everything recorded since can follow the model wherever the
    settings take it (new PSU efficiency, calibration factor, wattages).
    """
    updates: list[tuple[float, float, float, int]] = []
    for row in store.all_minutes():
        if row.cpu_busy_pct is None or row.gpu_smi_w is None or row.screen_on_s is None:
            continue
        cpu_w = model.cpu_power(row.cpu_pct, row.cpu_busy_pct, hw)
        gpu_w = model.gpu_power(row.gpu_smi_w if row.gpu_smi_w > 0 else None, hw)
        dc = cpu_w + gpu_w + hw.base_w + hw.peripherals_w
        frac = min(1.0, row.screen_on_s / row.on_s) if row.on_s > 0 else 0.0
        monitor = hw.monitor_w * hw.monitor_count * frac
        wall = dc / hw.psu_efficiency * hw.calibration + monitor
        updates.append((dc, wall, gpu_w, row.ts))
    store.update_power_many(updates)
    return len(updates)


def compute_day(
    store: Store, engine: TariffEngine, day: str, month_kwh_before: float, hw: Hardware
) -> Day:
    rows = store.day_minutes(day)
    on_s = active_s = asleep_s = 0.0
    kwh = 0.0
    standby_kwh = 0.0
    cost = 0.0
    for row in rows:
        # The PSU keeps drawing a little while the machine sleeps. The sleep
        # gap is booked on the minute that observed the wake, so that minute's
        # tariff window is a reasonable price for it.
        standby = row.asleep_s * hw.sleep_w / 3_600_000.0
        standby_kwh += standby
        cost += engine.cost(row.ts, row.kwh + standby, month_kwh_before + kwh)
        kwh += row.kwh + standby
        on_s += row.on_s
        active_s += row.active_s
        asleep_s += row.asleep_s
    return Day(
        day=day,
        on_s=on_s,
        active_s=active_s,
        asleep_s=asleep_s,
        kwh=kwh,
        cost=cost,
        standby_kwh=standby_kwh,
    )


def rebuild_day(store: Store, engine: TariffEngine, day: str, hw: Hardware) -> Day:
    """Recompute one day, using already-stored days for the month total."""
    month_days = [d for d in store.days(_month_of(day) + "-01", day) if d.day < day]
    month_before = sum(d.kwh for d in month_days)
    result = compute_day(store, engine, day, month_before, hw)
    store.save_day(result, engine.signature())
    return result


def rebuild_all(store: Store, engine: TariffEngine, hw: Hardware) -> int:
    """Recompute every day. Used after a tariff or model edit."""
    days = store.distinct_days()
    if not days:
        store.clear_daily()
        return 0
    signature = engine.signature()
    month_key = ""
    month_kwh = 0.0
    for day in days:
        current_month = _month_of(day)
        if current_month != month_key:
            month_key = current_month
            month_kwh = 0.0
        row = compute_day(store, engine, day, month_kwh, hw)
        month_kwh += row.kwh
        store.save_day(row, signature)
    return len(days)


def today_totals(store: Store) -> Day | None:
    from datetime import datetime

    key = datetime.now().strftime("%Y-%m-%d")
    for row in store.days(key, key):
        return row
    return None


__all__ = [
    "compute_day",
    "rebuild_day",
    "rebuild_all",
    "recompute_minutes",
    "today_totals",
    "day_key",
]
