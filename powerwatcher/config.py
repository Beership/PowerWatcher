"""Configuration model, load/save as JSON."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from .paths import config_path


def _num(value: Any, default: float) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if out == out else default  # reject NaN


def _int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


@dataclass
class TariffPeriod:
    """One time-of-use window, e.g. 08:00-22:00 at 0.5583 yuan/kWh."""

    name: str = "峰"
    start: str = "08:00"
    end: str = "22:00"
    price: float = 0.5583

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "TariffPeriod":
        return cls(
            name=str(raw.get("name", "峰")),
            start=str(raw.get("start", "08:00")),
            end=str(raw.get("end", "22:00")),
            price=_num(raw.get("price"), 0.5583),
        )


@dataclass
class Tariff:
    """Electricity pricing.

    mode="flat"  -> flat_price for every hour
    mode="tou"   -> look up periods by time of day (wraps past midnight)
    tier         -> optional monthly tier surcharge on top of the above
    """

    mode: str = "tou"
    flat_price: float = 0.5583
    periods: list[TariffPeriod] = field(
        default_factory=lambda: [
            TariffPeriod(name="峰", start="08:00", end="22:00", price=0.5583),
            TariffPeriod(name="谷", start="22:00", end="08:00", price=0.3583),
        ]
    )
    tier_enabled: bool = False
    # (monthly cumulative kWh upper bound, surcharge per kWh)
    tiers: list[tuple[float, float]] = field(
        default_factory=lambda: [(240.0, 0.0), (400.0, 0.05), (10**9, 0.30)]
    )

    def to_dict_signature(self) -> dict[str, Any]:
        """Stable, hashable view used to detect pricing changes."""
        return {
            "mode": self.mode,
            "flat_price": round(self.flat_price, 6),
            "periods": [
                [p.name, p.start, p.end, round(p.price, 6)] for p in self.periods
            ],
            "tier_enabled": self.tier_enabled,
            "tiers": [[lim, round(sur, 6)] for lim, sur in self.tiers],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Tariff":
        periods = [TariffPeriod.from_dict(p) for p in raw.get("periods", []) if isinstance(p, dict)]
        tiers: list[tuple[float, float]] = []
        for item in raw.get("tiers", []):
            if isinstance(item, (list, tuple)) and len(item) == 2:
                tiers.append((_num(item[0], 1e9), _num(item[1], 0.0)))
        data = cls(
            mode=str(raw.get("mode", "tou")),
            flat_price=_num(raw.get("flat_price"), 0.5583),
            periods=periods or cls().periods,
            tier_enabled=bool(raw.get("tier_enabled", False)),
            tiers=tiers or cls().tiers,
        )
        return data


@dataclass
class Hardware:
    """Power model parameters. Defaults are tuned for the sample machine,
    every value is editable in the settings page."""

    device_name: str = "这台台式机"
    cpu_name: str = "AMD Ryzen 7 9700X"
    cpu_idle_w: float = 16.0
    cpu_max_w: float = 88.0
    gpu_name: str = "NVIDIA GeForce RTX 5060"
    gpu_idle_w: float = 16.0
    gpu_max_w: float = 145.0
    gpu_source: str = "auto"  # auto | smi | model | off
    base_w: float = 28.0  # motherboard + RAM + SSDs + fans
    monitor_w: float = 22.0
    monitor_count: int = 1
    peripherals_w: float = 5.0  # USB peripherals, powered through the PSU
    psu_efficiency: float = 0.87
    sleep_w: float = 2.5  # PSU + board draw while the PC sleeps
    calibration: float = 1.0  # wall truth / model estimate
    active_after_s: int = 120  # no input for this long -> not "active"
    screen_off_after_s: int = 600  # no input for this long -> monitor assumed off

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Hardware":
        base = cls()
        return cls(
            device_name=str(raw.get("device_name", base.device_name)),
            cpu_name=str(raw.get("cpu_name", base.cpu_name)),
            cpu_idle_w=_num(raw.get("cpu_idle_w"), base.cpu_idle_w),
            cpu_max_w=_num(raw.get("cpu_max_w"), base.cpu_max_w),
            gpu_name=str(raw.get("gpu_name", base.gpu_name)),
            gpu_idle_w=_num(raw.get("gpu_idle_w"), base.gpu_idle_w),
            gpu_max_w=_num(raw.get("gpu_max_w"), base.gpu_max_w),
            gpu_source=str(raw.get("gpu_source", base.gpu_source)),
            base_w=_num(raw.get("base_w"), base.base_w),
            monitor_w=_num(raw.get("monitor_w"), base.monitor_w),
            monitor_count=max(1, _int(raw.get("monitor_count"), base.monitor_count)),
            peripherals_w=_num(raw.get("peripherals_w"), base.peripherals_w),
            psu_efficiency=min(0.99, max(0.5, _num(raw.get("psu_efficiency"), base.psu_efficiency))),
            sleep_w=max(0.0, _num(raw.get("sleep_w"), base.sleep_w)),
            calibration=min(5.0, max(0.2, _num(raw.get("calibration"), base.calibration))),
            active_after_s=max(10, _int(raw.get("active_after_s"), base.active_after_s)),
            screen_off_after_s=max(60, _int(raw.get("screen_off_after_s"), base.screen_off_after_s)),
        )


@dataclass
class Settings:
    hardware: Hardware = field(default_factory=Hardware)
    tariff: Tariff = field(default_factory=Tariff)
    # Off until the user ticks the box: we do not touch HKCU\...\Run unasked.
    autostart: bool = False
    sampling_interval_s: int = 5
    idle_notify_min: int = 0  # 0 = off; tray nudge after this many idle minutes
    region: str = ""  # province code (e.g. "SC" for 四川), empty = custom
    region_verified: bool = False  # True when user confirmed numbers match their bill
    onboarded: bool = False  # False only on a brand-new install

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Settings":
        return cls(
            hardware=Hardware.from_dict(raw.get("hardware", {}) or {}),
            tariff=Tariff.from_dict(raw.get("tariff", {}) or {}),
            autostart=bool(raw.get("autostart", False)),
            sampling_interval_s=max(2, _int(raw.get("sampling_interval_s"), 5)),
            idle_notify_min=max(0, _int(raw.get("idle_notify_min"), 0)),
            region=str(raw.get("region", "")),
            region_verified=bool(raw.get("region_verified", False)),
            # Configs written before this field existed belong to users who
            # already went through setup: never nag them with onboarding.
            onboarded=bool(raw.get("onboarded", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["tariff"]["tiers"] = [[lim, sur] for lim, sur in self.tariff.tiers]
        return data


def load_settings() -> Settings:
    path = config_path()
    if not path.exists():
        settings = Settings()
        save_settings(settings)
        return settings
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("config root is not an object")
        return Settings.from_dict(raw)
    except (OSError, ValueError, json.JSONDecodeError):
        # Keep the broken file around for inspection instead of silently eating it.
        try:
            path.replace(path.with_suffix(".broken.json"))
        except OSError:
            pass
        settings = Settings()
        save_settings(settings)
        return settings


def save_settings(settings: Settings) -> None:
    path = config_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(settings.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    tmp.replace(path)
