"""Power model: component estimates -> DC power -> wall power."""
from __future__ import annotations

from dataclasses import dataclass

from .config import Hardware


def cpu_power(util_pct: float, busiest_core_pct: float, hw: Hardware) -> float:
    """Blend overall and hottest-core utilisation, then interpolate.

    A single pegged core shows up as ~6% overall on a 16-thread CPU but can
    still pull 25-30W, so the busiest core gets real weight. The 0.75 exponent
    makes low overall load rise faster than linearly, which matches how modern
    packages behave between idle and full load.
    """
    overall = max(0.0, min(100.0, util_pct)) / 100.0
    hottest = max(0.0, min(100.0, busiest_core_pct)) / 100.0
    load = 0.65 * overall + 0.35 * hottest
    shaped = load**0.75
    return hw.cpu_idle_w + (hw.cpu_max_w - hw.cpu_idle_w) * shaped


def gpu_power(smi_w: float | None, hw: Hardware) -> float:
    if hw.gpu_source == "off":
        return 0.0
    if smi_w is not None and smi_w > 0 and hw.gpu_source in ("auto", "smi"):
        # The driver reports board power, which is what the PSU actually feeds.
        return max(hw.gpu_idle_w * 0.5, min(hw.gpu_max_w * 1.25, smi_w))
    return hw.gpu_idle_w


@dataclass
class PowerSample:
    cpu_w: float
    gpu_w: float
    dc_w: float
    wall_w: float
    screen_on: bool
    monitor_w: float


def estimate(
    hw: Hardware,
    util_pct: float,
    busiest_core_pct: float,
    gpu_smi_w: float | None,
    idle_s: float,
    screen_on_override: bool | None = None,
) -> PowerSample:
    cpu = cpu_power(util_pct, busiest_core_pct, hw)
    gpu = gpu_power(gpu_smi_w, hw)
    dc = cpu + gpu + hw.base_w + hw.peripherals_w

    # Monitors plug into the wall, not into the PSU, so they are added after
    # the efficiency division and are never touched by PSU losses.
    if screen_on_override is None:
        # No display API without a driver, so infer: recent input, a busy GPU
        # (video/game keeps the panel lit while GetLastInputInfo marches on),
        # or noticeable CPU load all mean the panel is probably on.
        gpu_busy = gpu_smi_w is not None and gpu_smi_w > hw.gpu_idle_w + 6.0
        cpu_busy = util_pct > 12.0
        screen_on = idle_s < hw.screen_off_after_s or gpu_busy or cpu_busy
    else:
        screen_on = screen_on_override

    monitor = hw.monitor_w * hw.monitor_count if screen_on else 0.0
    wall = dc / hw.psu_efficiency * hw.calibration + monitor
    return PowerSample(
        cpu_w=cpu,
        gpu_w=gpu,
        dc_w=dc,
        wall_w=wall,
        screen_on=screen_on,
        monitor_w=monitor,
    )
