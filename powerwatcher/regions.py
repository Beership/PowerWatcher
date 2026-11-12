"""Province-level electricity tariff reference data and geo-location.

China's residential electricity is priced by the provincial DRC (发改委),
not nationally. Each province has its own tier thresholds and peak/valley
schedule. This module provides:

- A reference tariff table for all 31 province-level regions (省/直辖市/自治区)
- Structure notes (seasonal pricing, annual tiers, etc.)
- IP-based province detection via cip.cc

IMPORTANT: All values are REFERENCE ONLY, compiled from public sources.
They are NOT guaranteed current. Users MUST verify against their own
electricity bill. Each entry carries verified=False until a user confirms
the numbers match their bill.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RegionTariff:
    """Reference tariff for one province."""

    code: str
    name: str
    grid: str  # 国网 / 南网
    verified: bool = False
    note: str = ""
    mode: str = "flat"  # flat | tou
    flat_price: float = 0.55
    periods: list[dict[str, Any]] = field(default_factory=list)
    tiers: list[tuple[float, float]] = field(
        default_factory=lambda: [(200.0, 0.0), (350.0, 0.05), (1e9, 0.30)]
    )
    tier_period: str = "month"  # month | year


# All 31 province-level regions. Values are approximate reference points
# compiled from publicly available information, NOT official real-time data.
# verified=False means these numbers have NOT been confirmed against a bill.
REGIONS: list[RegionTariff] = [
    # --- 华北 ---
    RegionTariff("BJ", "北京", "国网", note="不分时，月度阶梯",
                 mode="flat", flat_price=0.5383,
                 tiers=[(240, 0.0), (400, 0.05), (1e9, 0.30)]),
    RegionTariff("TJ", "天津", "国网", note="不分时，月度阶梯",
                 mode="flat", flat_price=0.49,
                 tiers=[(240, 0.0), (400, 0.05), (1e9, 0.30)]),
    RegionTariff("HE", "河北", "国网", note="不分时，月度阶梯",
                 mode="flat", flat_price=0.52,
                 tiers=[(180, 0.0), (280, 0.05), (1e9, 0.30)]),
    RegionTariff("SX", "山西", "国网", note="不分时，月度阶梯",
                 mode="flat", flat_price=0.47,
                 tiers=[(180, 0.0), (280, 0.05), (1e9, 0.30)]),
    RegionTariff("NM", "内蒙古", "国网", note="不分时，月度阶梯",
                 mode="flat", flat_price=0.42,
                 tiers=[(180, 0.0), (280, 0.05), (1e9, 0.30)]),
    # --- 东北 ---
    RegionTariff("LN", "辽宁", "国网", note="不分时，月度阶梯",
                 mode="flat", flat_price=0.50,
                 tiers=[(180, 0.0), (280, 0.05), (1e9, 0.30)]),
    RegionTariff("JL", "吉林", "国网", note="不分时，月度阶梯",
                 mode="flat", flat_price=0.52,
                 tiers=[(180, 0.0), (280, 0.05), (1e9, 0.30)]),
    RegionTariff("HL", "黑龙江", "国网", note="不分时，月度阶梯",
                 mode="flat", flat_price=0.51,
                 tiers=[(180, 0.0), (280, 0.05), (1e9, 0.30)]),
    # --- 华东 ---
    RegionTariff("SH", "上海", "国网", note="峰谷可选，年度阶梯",
                 mode="tou", flat_price=0.617,
                 periods=[
                     {"name": "峰", "start": "08:00", "end": "22:00", "price": 0.617},
                     {"name": "谷", "start": "22:00", "end": "08:00", "price": 0.307},
                 ],
                 tiers=[(3120, 0.0), (4800, 0.05), (1e9, 0.30)],
                 tier_period="year"),
    RegionTariff("JS", "江苏", "国网", note="峰谷可选，月度阶梯",
                 mode="tou", flat_price=0.5583,
                 periods=[
                     {"name": "峰", "start": "08:00", "end": "21:00", "price": 0.5583},
                     {"name": "谷", "start": "21:00", "end": "08:00", "price": 0.3583},
                 ],
                 tiers=[(200, 0.0), (300, 0.05), (1e9, 0.30)]),
    RegionTariff("ZJ", "浙江", "国网", note="峰谷可选，年度阶梯，部分时段有尖峰",
                 mode="tou", flat_price=0.568,
                 periods=[
                     {"name": "峰", "start": "08:00", "end": "22:00", "price": 0.568},
                     {"name": "谷", "start": "22:00", "end": "08:00", "price": 0.268},
                 ],
                 tiers=[(2760, 0.0), (4800, 0.05), (1e9, 0.30)],
                 tier_period="year"),
    RegionTariff("AH", "安徽", "国网", note="不分时，月度阶梯",
                 mode="flat", flat_price=0.5653,
                 tiers=[(180, 0.0), (280, 0.05), (1e9, 0.30)]),
    RegionTariff("FJ", "福建", "国网", note="峰谷可选，月度阶梯",
                 mode="tou", flat_price=0.55,
                 periods=[
                     {"name": "峰", "start": "08:00", "end": "22:00", "price": 0.55},
                     {"name": "谷", "start": "22:00", "end": "08:00", "price": 0.30},
                 ],
                 tiers=[(200, 0.0), (400, 0.05), (1e9, 0.30)]),
    RegionTariff("JX", "江西", "国网", note="不分时，月度阶梯",
                 mode="flat", flat_price=0.60,
                 tiers=[(180, 0.0), (280, 0.05), (1e9, 0.30)]),
    RegionTariff("SD", "山东", "国网", note="不分时，月度阶梯",
                 mode="flat", flat_price=0.5469,
                 tiers=[(210, 0.0), (400, 0.05), (1e9, 0.30)]),
    # --- 华中 ---
    RegionTariff("HA", "河南", "国网", note="不分时，月度阶梯",
                 mode="flat", flat_price=0.56,
                 tiers=[(180, 0.0), (280, 0.05), (1e9, 0.30)]),
    RegionTariff("HB", "湖北", "国网", note="不分时，月度阶梯",
                 mode="flat", flat_price=0.558,
                 tiers=[(180, 0.0), (280, 0.05), (1e9, 0.30)]),
    RegionTariff("HN", "湖南", "国网", note="不分时，月度阶梯",
                 mode="flat", flat_price=0.588,
                 tiers=[(200, 0.0), (400, 0.05), (1e9, 0.30)]),
    # --- 华南 ---
    RegionTariff("GD", "广东", "南网", note="夏季/非夏季门槛不同，月度阶梯",
                 mode="flat", flat_price=0.64,
                 tiers=[(200, 0.0), (400, 0.05), (1e9, 0.30)]),
    RegionTariff("GX", "广西", "南网", note="不分时，月度阶梯",
                 mode="flat", flat_price=0.53,
                 tiers=[(180, 0.0), (280, 0.05), (1e9, 0.30)]),
    RegionTariff("HI", "海南", "南网", note="不分时，月度阶梯",
                 mode="flat", flat_price=0.65,
                 tiers=[(200, 0.0), (400, 0.05), (1e9, 0.30)]),
    # --- 西南 ---
    RegionTariff("CQ", "重庆", "国网", note="不分时为主，月度阶梯，峰谷可选",
                 mode="flat", flat_price=0.52,
                 tiers=[(240, 0.0), (400, 0.05), (1e9, 0.30)]),
    RegionTariff("SC", "四川", "国网",
                 note="丰水期(5-10月)谷电更低(约0.17元)，枯水期谷约0.35元，峰谷可选",
                 mode="tou", flat_price=0.55,
                 periods=[
                     {"name": "峰", "start": "08:00", "end": "22:00", "price": 0.55},
                     {"name": "谷", "start": "22:00", "end": "08:00", "price": 0.35},
                 ],
                 tiers=[(180, 0.0), (280, 0.05), (1e9, 0.30)]),
    RegionTariff("GZ", "贵州", "南网", note="不分时，月度阶梯",
                 mode="flat", flat_price=0.45,
                 tiers=[(180, 0.0), (280, 0.05), (1e9, 0.30)]),
    RegionTariff("YN", "云南", "南网", note="不分时，月度阶梯",
                 mode="flat", flat_price=0.36,
                 tiers=[(180, 0.0), (280, 0.05), (1e9, 0.30)]),
    RegionTariff("XZ", "西藏", "国网", note="不分时，月度阶梯",
                 mode="flat", flat_price=0.54,
                 tiers=[(180, 0.0), (280, 0.05), (1e9, 0.30)]),
    # --- 西北 ---
    RegionTariff("SN", "陕西", "国网", note="不分时，月度阶梯",
                 mode="flat", flat_price=0.4983,
                 tiers=[(180, 0.0), (280, 0.05), (1e9, 0.30)]),
    RegionTariff("GS", "甘肃", "国网", note="不分时，月度阶梯",
                 mode="flat", flat_price=0.51,
                 tiers=[(180, 0.0), (280, 0.05), (1e9, 0.30)]),
    RegionTariff("QH", "青海", "国网", note="不分时，月度阶梯",
                 mode="flat", flat_price=0.46,
                 tiers=[(180, 0.0), (280, 0.05), (1e9, 0.30)]),
    RegionTariff("NX", "宁夏", "国网", note="不分时，月度阶梯",
                 mode="flat", flat_price=0.49,
                 tiers=[(180, 0.0), (280, 0.05), (1e9, 0.30)]),
    RegionTariff("XJ", "新疆", "国网", note="不分时，月度阶梯",
                 mode="flat", flat_price=0.39,
                 tiers=[(180, 0.0), (280, 0.05), (1e9, 0.30)]),
]

_BY_CODE = {r.code: r for r in REGIONS}
_BY_NAME = {r.name: r for r in REGIONS}


def by_code(code: str) -> RegionTariff | None:
    return _BY_CODE.get(code)


def by_name(name: str) -> RegionTariff | None:
    return _BY_NAME.get(name)


def all_codes() -> list[str]:
    return [r.code for r in REGIONS]


def all_names() -> list[str]:
    return [r.name for r in REGIONS]


def to_tariff(region: RegionTariff):
    """Convert a region preset into a config.Tariff instance."""
    from .config import Tariff, TariffPeriod

    periods = [
        TariffPeriod(name=p["name"], start=p["start"], end=p["end"], price=float(p["price"]))
        for p in region.periods
    ]
    return Tariff(
        mode=region.mode,
        flat_price=region.flat_price,
        periods=periods or Tariff().periods,
        tier_enabled=bool(region.tiers),
        tiers=list(region.tiers),
    )


# ---------------------------------------------------------- geo-location
def detect_province_name(timeout: float = 4.0) -> tuple[str, str] | None:
    """Detect province from public IP via cip.cc (plain text, no JS).

    Returns (province_name, city) or None if detection fails.
    Example: ("四川", "成都")
    """
    import urllib.request

    for url in ("https://www.cip.cc/", "https://myip.ipip.net/"):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                text = resp.read().decode("utf-8", "ignore")
            prov = _parse_province(text)
            if prov:
                return prov
        except Exception:
            continue
    return None


def _parse_province(text: str) -> tuple[str, str] | None:
    """Parse cip.cc / myip.ipip.net response for province and city."""
    import re

    # cip.cc: "地址\t: 中国 四川 成都" or "中国 四川省 成都市"
    # myip.ipip.net: "来自于：中国 四川 成都  电信"
    for name in all_names():
        if name in text:
            # Try to extract city too
            m = re.search(rf"{name}\S*\s+(\S+?市)", text)
            city = m.group(1) if m else ""
            return (name, city)
    return None
