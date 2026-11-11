"""Background sampler: turns sensors into per-minute rows."""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, Signal

from . import model, sensors
from .config import Settings
from .rollup import rebuild_day
from .storage import Minute, Store, day_key
from .tariff import TariffEngine

log = logging.getLogger(__name__)

# A resume after sleep can report a huge tick delta; anything beyond this is
# treated as "the clock jumped" rather than real powered-on time.
_MAX_AWAKE_STEP_S = 30.0


@dataclass
class _Bucket:
    ts: int
    on_s: float = 0.0
    active_s: float = 0.0
    asleep_s: float = 0.0
    wall_sum: float = 0.0
    wall_weight: float = 0.0
    dc_sum: float = 0.0
    cpu_sum: float = 0.0
    cpu_busy_sum: float = 0.0
    gpu_pct_sum: float = 0.0
    gpu_w_sum: float = 0.0
    gpu_smi_sum: float = 0.0
    gpu_smi_weight: float = 0.0
    screen_on_s: float = 0.0
    app_seconds: dict[str, float] = field(default_factory=dict)
    samples: int = 0

    def add(
        self,
        dt: float,
        active: bool,
        screen_on: bool,
        wall_w: float,
        dc_w: float,
        cpu_pct: float,
        cpu_busy_pct: float,
        gpu_pct: float,
        gpu_w: float,
        gpu_smi_w: float | None,
        app: str | None,
    ) -> None:
        if dt <= 0:
            return
        self.on_s += dt
        if active:
            self.active_s += dt
            if app:
                self.app_seconds[app] = self.app_seconds.get(app, 0.0) + dt
        if screen_on:
            self.screen_on_s += dt
        weight = max(dt, 0.001)
        self.wall_sum += wall_w * weight
        self.wall_weight += weight
        self.dc_sum += dc_w * weight
        self.cpu_sum += cpu_pct * weight
        self.cpu_busy_sum += cpu_busy_pct * weight
        self.gpu_pct_sum += gpu_pct * weight
        self.gpu_w_sum += gpu_w * weight
        if gpu_smi_w is not None and gpu_smi_w > 0:
            self.gpu_smi_sum += gpu_smi_w * weight
            self.gpu_smi_weight += weight
        self.samples += 1

    def dominant_app(self) -> str | None:
        if not self.app_seconds:
            return None
        return max(self.app_seconds.items(), key=lambda kv: kv[1])[0]

    def to_minute(self) -> Minute:
        w = self.wall_weight or 1.0
        gpu_smi = self.gpu_smi_sum / self.gpu_smi_weight if self.gpu_smi_weight > 0 else 0.0
        return Minute(
            ts=self.ts,
            on_s=self.on_s,
            active_s=self.active_s,
            asleep_s=self.asleep_s,
            dc_w=self.dc_sum / w,
            wall_w=self.wall_sum / w,
            cpu_pct=self.cpu_sum / w,
            gpu_pct=self.gpu_pct_sum / w,
            gpu_w=self.gpu_w_sum / w,
            cpu_busy_pct=self.cpu_busy_sum / w,
            gpu_smi_w=gpu_smi,
            screen_on_s=self.screen_on_s,
            app=self.dominant_app(),
        )


class Sampler(QObject):
    """Runs a sampling thread; emits `ticked` for the UI and writes to SQLite."""

    ticked = Signal(dict)
    flushed = Signal(str)  # day key whose rollup was refreshed

    def __init__(
        self, store: Store, settings: Settings, engine: TariffEngine, parent=None
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._settings = settings
        self._engine = engine
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._paused = False
        self._bucket: _Bucket | None = None
        self._last_wall: float | None = None
        self._last_tick: float | None = None
        self._cpu = sensors.CpuProbe()
        self._gpu = sensors.GpuProbe()
        self.state: dict = {
            "wall_w": 0.0,
            "cpu_w": 0.0,
            "gpu_w": 0.0,
            "cpu_pct": 0.0,
            "gpu_pct": 0.0,
            "screen_on": True,
            "idle_s": 0.0,
            "uptime_s": 0.0,
            "paused": False,
            "app": None,
            "gpu_source": self._gpu.available and "NVML" or "无",
            "gpu_error": None,
        }

    # ------------------------------------------------------------- lifecycle
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._cpu.read()  # prime the utilisation counter
        self._thread = threading.Thread(target=self._run, name="sampler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3.0)
        self._flush(force=True)

    def set_paused(self, paused: bool) -> None:
        with self._lock:
            self._paused = paused
        self.state["paused"] = paused

    @property
    def paused(self) -> bool:
        return self._paused

    def update_settings(self, settings: Settings, engine: TariffEngine) -> None:
        with self._lock:
            self._settings = settings
            self._engine = engine

    # ------------------------------------------------------------------ loop
    def _run(self) -> None:
        log.info("sampler started")
        while not self._stop.is_set():
            interval = max(2, self._settings.sampling_interval_s)
            if self._stop.wait(interval):
                break
            try:
                self._sample()
            except Exception:  # keep the monitor alive no matter what
                log.exception("sample failed")
        log.info("sampler stopped")

    def _sample(self) -> None:
        with self._lock:
            settings = self._settings
            paused = self._paused

        now_wall = time.time()
        now_tick = sensors.tick_seconds()
        if self._last_wall is None or self._last_tick is None:
            self._last_wall, self._last_tick = now_wall, now_tick
            return

        dt_wall = now_wall - self._last_wall
        dt_tick = now_tick - self._last_tick
        asleep_s = max(0.0, dt_wall - dt_tick - 2.0)
        self._last_wall, self._last_tick = now_wall, now_tick

        idle_s = sensors.idle_seconds()
        util, busiest = self._cpu.read()
        gpu = self._gpu.read()
        app = sensors.foreground_process()
        smi_w = gpu.power_w if gpu.source in ("nvml", "nvidia-smi") else None

        sample = model.estimate(
            settings.hardware,
            util,
            busiest,
            smi_w,
            idle_s,
        )

        dt = max(0.0, min(dt_tick, _MAX_AWAKE_STEP_S))
        active = idle_s < settings.hardware.active_after_s

        with self._lock:
            if self._bucket is None:
                self._bucket = _Bucket(ts=int(now_wall // 60) * 60)
            bucket = self._bucket
            if bucket.ts != int(now_wall // 60) * 60:
                self._flush(force=True)
                bucket = self._bucket = _Bucket(ts=int(now_wall // 60) * 60)
            if not paused:
                bucket.add(
                    dt,
                    active,
                    sample.screen_on,
                    sample.wall_w,
                    sample.dc_w,
                    util,
                    busiest,
                    gpu.util_pct or 0.0,
                    sample.gpu_w,
                    smi_w,
                    app,
                )
                if asleep_s > 5.0:
                    bucket.asleep_s += asleep_s

        self.state.update(
            {
                "wall_w": sample.wall_w,
                "cpu_w": sample.cpu_w,
                "gpu_w": sample.gpu_w,
                "cpu_pct": util,
                "gpu_pct": gpu.util_pct or 0.0,
                "screen_on": sample.screen_on,
                "idle_s": idle_s,
                "uptime_s": sensors.tick_seconds(),
                "app": app,
                "gpu_error": self._gpu.error,
                "gpu_source": "NVML" if gpu.source == "nvml"
                else "nvidia-smi" if gpu.source == "nvidia-smi"
                else "模型估算",
            }
        )
        self.ticked.emit(dict(self.state))

    # ----------------------------------------------------------------- flush
    def _flush(self, force: bool = False) -> None:
        with self._lock:
            bucket = self._bucket
            self._bucket = None
            engine = self._engine
            hw = self._settings.hardware
        if bucket is None or (bucket.samples == 0 and bucket.on_s <= 0):
            return
        minute = bucket.to_minute()
        self._store.upsert_minute(minute)
        day = day_key(minute.ts)
        try:
            rebuild_day(self._store, engine, day, hw)
            self.flushed.emit(day)
        except Exception:
            log.exception("rollup failed for %s", day)
