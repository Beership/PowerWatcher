"""System tray icon and its menu."""
from __future__ import annotations

import time

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from ..storage import day_key
from . import icons
from .context import AppContext


def _tray_icon(paused: bool) -> QIcon:
    icon = QIcon()
    for size in (16, 20, 24, 32, 48, 64):
        icon.addPixmap(icons.tray_pixmap(size, paused=paused))
    return icon


class Tray(QObject):
    quit_requested = Signal()

    def __init__(self, ctx: AppContext, window, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.window = window
        self._cost_text = "今日 ¥0.00"
        self._idle_notified = False

        self.icon = QSystemTrayIcon(_tray_icon(False), self)
        self.menu = QMenu()

        show_action = QAction("打开主界面", self.menu)
        show_action.triggered.connect(self.window.show_from_tray)
        self.menu.addAction(show_action)

        self.today_action = QAction(self._cost_text, self.menu)
        self.today_action.setEnabled(False)
        self.menu.addAction(self.today_action)
        self.menu.addSeparator()

        self.pause_action = QAction("暂停记录", self.menu)
        self.pause_action.setCheckable(True)
        self.pause_action.toggled.connect(self._on_pause)
        self.menu.addAction(self.pause_action)
        self.menu.addSeparator()

        quit_action = QAction("退出", self.menu)
        quit_action.triggered.connect(self.quit_requested.emit)
        self.menu.addAction(quit_action)

        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self._on_activated)
        self.refresh()
        self.icon.show()

    # ---------------------------------------------------------------- events
    def _on_activated(self, reason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.DoubleClick,
            QSystemTrayIcon.ActivationReason.Trigger,
        ):
            self.window.show_from_tray()

    def _on_pause(self, checked: bool) -> None:
        self.ctx.sampler.set_paused(checked)
        self.icon.setIcon(_tray_icon(checked))
        self.refresh()

    def on_tick(self, state: dict) -> None:
        self._update_tooltip(float(state.get("wall_w", 0.0)))
        self._maybe_idle_nudge(state)

    def _maybe_idle_nudge(self, state: dict) -> None:
        """One toast per idle stretch when the user opted in."""
        threshold_min = self.ctx.settings.idle_notify_min
        if threshold_min <= 0 or self.ctx.sampler.paused:
            return
        idle_s = float(state.get("idle_s", 0.0))
        if idle_s < 60:
            self._idle_notified = False
            return
        if self._idle_notified or idle_s < threshold_min * 60:
            return
        watts = float(state.get("wall_w", 0.0))
        price, _name = self.ctx.engine.price_at(int(time.time()))
        per_hour = watts / 1000.0 * price
        if per_hour > 0:
            self.notify(
                "电脑空闲中",
                f"已无人使用 {idle_s / 60:.0f} 分钟，当前 {watts:.0f} W，"
                f"挂机一小时约 ¥{per_hour:.2f}。不用的话可以睡眠。",
            )
        self._idle_notified = True

    def notify(self, title: str, body: str) -> None:
        self.icon.showMessage(
            title, body, QSystemTrayIcon.MessageInformation, 6000
        )

    def refresh(self) -> None:
        today = day_key(int(time.time()))
        rows = self.ctx.store.days(today, today)
        cost = rows[0].cost if rows else 0.0
        self._cost_text = f"今日 ¥{cost:.2f}"
        self.today_action.setText(self._cost_text)
        self._update_tooltip(None)

    def _update_tooltip(self, watts: float | None) -> None:
        if self.ctx.sampler.paused:
            status = "已暂停记录"
        elif watts is None:
            status = "正在记录"
        else:
            status = f"当前 {watts:.0f} W"
        self.icon.setToolTip(f"电费管家 · {status}\n{self._cost_text}")

    def hide(self) -> None:
        self.icon.hide()
