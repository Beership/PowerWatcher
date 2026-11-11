"""Main window: sidebar navigation plus the three pages."""
from __future__ import annotations

import ctypes
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..autostart import set_enabled as set_autostart
from ..config import save_settings
from ..rollup import rebuild_all, recompute_minutes
from ..tariff import TariffEngine
from . import icons
from .analysis import AnalysisPage
from .context import AppContext
from .overview import OverviewPage
from .settings import SettingsPage


def enable_dark_title_bar(window: QWidget) -> None:
    """Windows 10/11: ask DWM to paint the native frame dark."""
    try:
        hwnd = int(window.winId())
        value = ctypes.c_int(1)
        # 20 = DWMWA_USE_IMMERSIVE_DARK_MODE (19 on older Win10 builds)
        for attribute in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
            ) == 0:
                break
    except (OSError, AttributeError):
        pass


class MainWindow(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self._force_close = False
        self.setObjectName("Root")
        self.setWindowTitle("电费管家 · PowerWatcher")
        self.setWindowIcon(icons.app_icon())
        self.resize(1080, 730)
        self.setMinimumSize(950, 640)
        self._build()

        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self.refresh_all)
        self._timer.start()

    # ------------------------------------------------------------------ ui
    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(198)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(14, 18, 14, 16)
        side.setSpacing(6)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(icons.app_pixmap(30))
        logo.setFixedSize(30, 30)
        names = QVBoxLayout()
        names.setSpacing(0)
        name = QLabel("电费管家")
        name.setObjectName("Brand")
        sub = QLabel("PowerWatcher")
        sub.setObjectName("BrandSub")
        names.addWidget(name)
        names.addWidget(sub)
        brand.addWidget(logo)
        brand.addLayout(names)
        brand.addStretch(1)
        side.addLayout(brand)
        side.addSpacing(18)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self._nav_buttons: list[QPushButton] = []
        for index, label in enumerate(("概览", "分析", "设置")):
            button = QPushButton(f"  {label}")
            button.setObjectName("Nav")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setChecked(index == 0)
            button.clicked.connect(lambda _=False, i=index: self.stack.setCurrentIndex(i))
            self.nav_group.addButton(button, index)
            self._nav_buttons.append(button)
            side.addWidget(button)

        side.addStretch(1)

        self.side_status = QLabel("")
        self.side_status.setObjectName("BrandSub")
        self.side_status.setWordWrap(True)
        side.addWidget(self.side_status)
        version = QLabel(f"v{__version__}")
        version.setObjectName("BrandSub")
        side.addWidget(version)
        root.addWidget(sidebar)

        self.stack = QStackedWidget()
        self.overview = OverviewPage(self.ctx)
        self.analysis = AnalysisPage(self.ctx)
        self.settings = SettingsPage(self.ctx, self.apply_settings)
        self.stack.addWidget(self.overview)
        self.stack.addWidget(self.analysis)
        self.stack.addWidget(self.settings)
        root.addWidget(self.stack, 1)

    # -------------------------------------------------------------- runtime
    def showEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().showEvent(event)
        enable_dark_title_bar(self)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if self._force_close:
            event.accept()
            return
        if not QSystemTrayIcon.isSystemTrayAvailable():
            # No tray to hide in: closing the window must actually quit,
            # otherwise the app becomes unreachable.
            event.accept()
            QApplication.quit()
            return
        event.ignore()
        self.hide()

    def show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_now(self) -> None:
        self._force_close = True
        self.close()

    def apply_settings(self, settings) -> None:
        old = self.ctx.settings
        save_settings(settings)
        self.ctx.settings = settings
        self.ctx.engine = TariffEngine(settings.tariff)
        self.ctx.sampler.update_settings(settings, self.ctx.engine)
        set_autostart(settings.autostart)
        if settings.hardware != old.hardware:
            # Model inputs changed: re-run the power model over history, not
            # just the tariff, so a calibration or efficiency fix is retroactive.
            recompute_minutes(self.ctx.store, settings.hardware)
        rebuild_all(self.ctx.store, self.ctx.engine, settings.hardware)
        self.refresh_all()

    def refresh_all(self) -> None:
        self.overview.refresh()
        if self.stack.currentIndex() == 1:
            self.analysis.refresh()
        days = len(self.ctx.store.all_days())
        self.side_status.setText(
            f"已记录 {days} 天\n今日 {datetime.now():%H:%M} 更新"
            if days
            else "还没有记录\n保持运行即可"
        )

    def on_tick(self, state: dict) -> None:
        self.overview.on_live(state)
