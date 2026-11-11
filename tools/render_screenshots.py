"""Render the three pages to PNG with seeded demo data, for the README.

Run from anywhere:  py tools/render_screenshots.py
Uses a throwaway demo.db under docs/_demo, never the real telemetry store.
"""
import os
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication, QScrollArea

from powerwatcher.config import load_settings
from powerwatcher.engine import Sampler
from powerwatcher.rollup import rebuild_all
from powerwatcher.storage import Minute, Store
from powerwatcher.tariff import TariffEngine
from powerwatcher.ui import theme as ui_theme
from powerwatcher.ui.context import AppContext
from powerwatcher.ui.main_window import MainWindow

OUT = Path(__file__).resolve().parent.parent / "docs" / "_demo"
OUT.mkdir(parents=True, exist_ok=True)
DB = OUT / "demo.db"
if DB.exists():
    DB.unlink()

store = Store(DB)
random.seed(7)
now = datetime.now()

APPS = ["chrome.exe", "code.exe", "explorer.exe", "steam.exe", "WeChat.exe"]


def wall_w_for(hour: float, weekday: int) -> float:
    if 0 <= hour < 8:
        return 0.0
    if 8 <= hour < 9:
        return 105.0
    if 9 <= hour < 12:
        return 128.0 + random.uniform(-12, 18)
    if 12 <= hour < 14:
        return 108.0 + random.uniform(-6, 10)
    if 14 <= hour < 18:
        return 132.0 + random.uniform(-10, 22)
    if 18 <= hour < 20:
        return 112.0 + random.uniform(-8, 14)
    if 20 <= hour < 23:
        return (300.0 if weekday >= 5 else 285.0) + random.uniform(-25, 35)
    return 106.0


for back in range(14, -1, -1):
    day = now - timedelta(days=back)
    for slot in range(0, 144):
        start = day.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
            minutes=slot * 10
        )
        if start > now:
            continue
        hour = slot / 6.0
        wall = wall_w_for(hour, day.weekday())
        if wall <= 0:
            continue
        active = 8 <= hour < 23 and (hour < 12.5 or hour > 13.5)
        app = APPS[(slot + back) % len(APPS)] if active else None
        if hour >= 20:
            app = "steam.exe"
        store.upsert_minute(
            Minute(
                ts=int(start.timestamp()),
                on_s=600.0,
                active_s=600.0 if active else 60.0,
                asleep_s=0.0,
                dc_w=wall * 0.87,
                wall_w=wall,
                cpu_pct=random.uniform(4, 22) if wall < 200 else random.uniform(35, 70),
                gpu_pct=random.uniform(1, 8) if wall < 200 else random.uniform(45, 90),
                gpu_w=22 if wall < 200 else 120,
                cpu_busy_pct=random.uniform(6, 30) if wall < 200 else 55.0,
                gpu_smi_w=22 if wall < 200 else 120,
                screen_on_s=600.0 if active else 0.0,
                app=app,
            )
        )

settings = load_settings()
engine = TariffEngine(settings.tariff)
rebuild_all(store, engine, settings.hardware)

app = QApplication(sys.argv)
app.setStyle("Fusion")
app.setStyleSheet(ui_theme.STYLESHEET)

sampler = Sampler(store, settings, engine)
hw = settings.hardware
dc = 46.0 + 118.0 + hw.base_w + hw.peripherals_w
sampler.state.update(
    {
        "wall_w": dc / hw.psu_efficiency + hw.monitor_w,
        "cpu_w": 46.0,
        "gpu_w": 118.0,
        "cpu_pct": 38.0,
        "gpu_pct": 72.0,
        "screen_on": True,
        "idle_s": 4.0,
        "app": "chrome.exe",
    }
)
ctx = AppContext(store=store, settings=settings, engine=engine, sampler=sampler)

window = MainWindow(ctx)
window.resize(1080, 730)
window.show()
app.processEvents()

window.on_tick(sampler.state)
window.refresh_all()
window.analysis.refresh()
app.processEvents()
time.sleep(0.3)


def shot(name: str, index: int, scroll: float | None = None) -> None:
    window.stack.setCurrentIndex(index)
    window._nav_buttons[index].setChecked(True)
    app.processEvents()
    if scroll is not None:
        area = window.settings.findChild(QScrollArea)
        bar = area.verticalScrollBar()
        bar.setValue(int(bar.maximum() * scroll))
    app.processEvents()
    time.sleep(0.25)
    app.processEvents()
    path = OUT / f"{name}.png"
    window.grab().save(str(path))
    print("saved", path)


shot("overview", 0)
shot("analysis", 1)
shot("settings-top", 2, 0.0)
shot("settings-tariff", 2, 0.45)
shot("settings-bottom", 2, 1.0)

print("days:", len(store.all_days()))
