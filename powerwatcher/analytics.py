"""Aggregations the UI needs that are cheaper to compute here than in SQL."""
from __future__ import annotations

from datetime import datetime, timedelta

from .config import Hardware
from .storage import Day, Store, day_start_ts
from .tariff import TariffEngine

# Friendly labels for the executables that dominate most people's day.
APP_LABELS = {
    "chrome.exe": "Chrome",
    "msedge.exe": "Edge",
    "firefox.exe": "Firefox",
    "explorer.exe": "桌面",
    "dwm.exe": "桌面",
    "wechat.exe": "微信",
    "weixin.exe": "微信",
    "wechatappex.exe": "微信",
    "qq.exe": "QQ",
    "code.exe": "VS Code",
    "pycharm64.exe": "PyCharm",
    "idea64.exe": "IntelliJ",
    "steam.exe": "Steam",
    "steamwebhelper.exe": "Steam",
    "spotify.exe": "Spotify",
    "potplayermini64.exe": "PotPlayer",
    "powerpnt.exe": "PowerPoint",
    "winword.exe": "Word",
    "excel.exe": "Excel",
    "typora.exe": "Typora",
}


def app_label(exe: str | None) -> str:
    if exe is None:
        return "挂机（无人使用）"
    return APP_LABELS.get(exe.lower(), exe[:-4] if exe.lower().endswith(".exe") else exe)


def app_ranking(
    store: Store, engine: TariffEngine, day: str, top: int = 5
) -> list[tuple[str, float, float]]:
    """(label, kWh, cost) per foreground app for a day, biggest first."""
    rows = store.day_minutes(day)
    kwh_by: dict[str | None, float] = {}
    cost_by: dict[str | None, float] = {}
    for row in rows:
        if row.kwh <= 0:
            continue
        kwh_by[row.app] = kwh_by.get(row.app, 0.0) + row.kwh
        cost_by[row.app] = cost_by.get(row.app, 0.0) + engine.cost(row.ts, row.kwh, 0.0)
    ranked = [
        (app_label(app), kwh_by[app], cost_by.get(app, 0.0)) for app in kwh_by
    ]
    ranked.sort(key=lambda item: -item[1])
    if len(ranked) <= top:
        return ranked
    rest_kwh = sum(k for _, k, _ in ranked[top:])
    rest_cost = sum(c for _, _, c in ranked[top:])
    out = ranked[:top]
    if rest_kwh > 0:
        out.append((f"其他 {len(ranked) - top} 项", rest_kwh, rest_cost))
    return out


def idle_summary(store: Store, day: str) -> dict[str, float]:
    """Idle ("on but nobody at the keys") numbers for the insight text."""
    rows = store.day_minutes(day)
    idle_s = 0.0
    idle_kwh = 0.0
    idle_w_weighted = 0.0
    weight = 0.0
    for row in rows:
        gap = row.on_s - row.active_s
        if gap <= 0:
            continue
        idle_s += gap
        if row.active_s < row.on_s * 0.5:  # mostly-idle minute
            idle_kwh += row.kwh
            idle_w_weighted += row.wall_w * row.on_s
            weight += row.on_s
    return {
        "idle_s": idle_s,
        "idle_kwh": idle_kwh,
        "idle_w": idle_w_weighted / weight if weight > 0 else 0.0,
    }


def hourly_watts(store: Store, day: str) -> list[float | None]:
    """Average wall power for each hour of a day; None where there is no data."""
    rows = store.day_minutes(day)
    sums = [0.0] * 24
    weights = [0.0] * 24
    for row in rows:
        hour = datetime.fromtimestamp(row.ts).hour
        weight = max(row.on_s, 0.0)
        if weight <= 0:
            continue
        sums[hour] += row.wall_w * weight
        weights[hour] += weight
    return [sums[h] / weights[h] if weights[h] > 0 else None for h in range(24)]


def hourly_kwh(store: Store, day: str) -> list[float]:
    rows = store.day_minutes(day)
    out = [0.0] * 24
    for row in rows:
        out[datetime.fromtimestamp(row.ts).hour] += row.kwh
    return out


def series_days(store: Store, end_day: str, count: int) -> list[Day]:
    end = datetime.strptime(end_day, "%Y-%m-%d")
    start = end - timedelta(days=count - 1)
    rows = store.days(start.strftime("%Y-%m-%d"), end_day)
    by_day = {d.day: d for d in rows}
    out: list[Day] = []
    for i in range(count):
        key = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        out.append(by_day.get(key) or Day(key, 0.0, 0.0, 0.0, 0.0, 0.0))
    return out


def period_split(
    store: Store, engine: TariffEngine, start_ts: int, end_ts: int
) -> dict[str, dict[str, float]]:
    """kWh and money per tariff window over a range."""
    buckets: dict[str, dict[str, float]] = {}
    for row in store.minutes(start_ts, end_ts):
        if row.kwh <= 0:
            continue
        price, name = engine.price_at(row.ts)
        slot = buckets.setdefault(name, {"kwh": 0.0, "cost": 0.0, "price": price})
        slot["kwh"] += row.kwh
        slot["cost"] += row.kwh * price
    return buckets


def day_bounds(day: str) -> tuple[int, int]:
    start = day_start_ts(day)
    return start, start + 86400


def breakdown(hw: Hardware, state: dict) -> list[tuple[str, float, str]]:
    """Current draw split into labelled components, for the stacked bar."""
    cpu = float(state.get("cpu_w", 0.0))
    gpu = float(state.get("gpu_w", 0.0))
    monitor = hw.monitor_w * hw.monitor_count if state.get("screen_on", True) else 0.0
    base = hw.base_w
    periph = hw.peripherals_w
    psu_loss = max(0.0, (cpu + gpu + base + periph) * (1.0 / hw.psu_efficiency - 1.0))
    return [
        ("CPU", cpu, "#ffb02e"),
        ("显卡", gpu, "#4c8dff"),
        ("主板/内存/硬盘", base, "#a06bff"),
        ("显示器", monitor, "#3ddc84"),
        ("外设", periph, "#ff8fab"),
        ("电源损耗", psu_loss, "#5f6879"),
    ]


def hours_text(seconds: float) -> str:
    minutes = int(round(seconds / 60.0))
    return f"{minutes // 60}小时{minutes % 60:02d}分" if minutes >= 60 else f"{minutes}分"


def month_range(day: str) -> tuple[str, str]:
    year, month = int(day[:4]), int(day[5:7])
    first = f"{year:04d}-{month:02d}-01"
    nxt_year = year + (month == 12)
    nxt_month = month % 12 + 1
    last = (datetime(nxt_year, nxt_month, 1) - timedelta(days=1)).strftime("%Y-%m-%d")
    return first, last


def year_range(day: str) -> tuple[str, str]:
    year = int(day[:4])
    return f"{year:04d}-01-01", f"{year:04d}-12-31"
