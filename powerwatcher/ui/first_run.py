"""One-time first-run setup: autostart and regional tariff."""
from __future__ import annotations

import copy
import threading

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import icons
from .context import AppContext


class FirstRunDialog(QDialog):
    """Two decisions, then never shown again.

    Deliberately not a wizard: both items are optional, and skipping is a
    first-class choice. Nothing here writes to the registry or overwrites the
    tariff unless the corresponding box is ticked.
    """

    location_found = Signal(object)  # (province, city) or None

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._region = None
        self._result = None
        self.setObjectName("Root")
        self.setWindowTitle("欢迎使用电费管家")
        self.setWindowIcon(icons.app_icon())
        self.setModal(True)
        self.setFixedWidth(520)
        self.location_found.connect(self._on_location)
        self._build()

    # ------------------------------------------------------------------ ui
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 18)
        root.setSpacing(14)

        title = QLabel("欢迎使用电费管家")
        title.setObjectName("PageTitle")
        sub = QLabel(
            "还有两件事，设好之后就能一直准确记录。两个都可以跳过，之后在设置页随时改。"
        )
        sub.setObjectName("PageSub")
        sub.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(sub)

        # ---- autostart
        box1 = self._block(
            "开机自动启动",
            "只有一直运行，账单才是完整的。现在不开，记录会从今天某一次开机才开始。",
        )
        self.autostart_cb = QCheckBox("开机后自动启动，并缩到托盘")
        self.autostart_cb.setChecked(True)
        box1.layout().addWidget(self.autostart_cb)
        root.addWidget(box1)

        # ---- region
        box2 = self._block(
            "你所在省份的电价",
            "各地电价不同。自动识别只需联网一次，套用的是参考值，之后按电费单核对。",
        )
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(10)
        self.locate_btn = QPushButton("自动识别省份")
        self.locate_btn.setObjectName("Ghost")
        self.locate_btn.clicked.connect(self._locate)
        row_layout.addWidget(self.locate_btn)
        self.region_label = QLabel("未识别")
        self.region_label.setObjectName("Hint")
        row_layout.addWidget(self.region_label)
        row_layout.addStretch(1)
        box2.layout().addWidget(row)

        self.apply_region_cb = QCheckBox("套用该省的参考电价")
        self.apply_region_cb.setChecked(True)
        self.apply_region_cb.setVisible(False)
        box2.layout().addWidget(self.apply_region_cb)

        self.region_note = QLabel("")
        self.region_note.setObjectName("Hint")
        self.region_note.setWordWrap(True)
        self.region_note.setVisible(False)
        box2.layout().addWidget(self.region_note)
        root.addWidget(box2)

        note = QLabel(
            "内置电价是公开资料整理的参考值，不是官方实时数据。核对方法：设置 → 电价，"
            "对着电费单改一次，历史账单会自动重算。"
        )
        note.setObjectName("Hint")
        note.setWordWrap(True)
        root.addWidget(note)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        skip = QPushButton("跳过")
        skip.setObjectName("Ghost")
        skip.clicked.connect(self._skip)
        start = QPushButton("开始使用")
        start.setObjectName("Primary")
        start.clicked.connect(self._start)
        buttons.addWidget(skip)
        buttons.addWidget(start)
        root.addLayout(buttons)

    def _block(self, title: str, subtitle: str) -> QWidget:
        from .widgets import Card

        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 13, 16, 14)
        layout.setSpacing(6)
        head = QLabel(title)
        head.setObjectName("SectionTitle")
        text = QLabel(subtitle)
        text.setObjectName("Hint")
        text.setWordWrap(True)
        layout.addWidget(head)
        layout.addWidget(text)
        layout.addSpacing(2)
        return card

    # --------------------------------------------------------------- region
    def _locate(self) -> None:
        self.locate_btn.setEnabled(False)
        self.locate_btn.setText("识别中…")
        self.region_label.setText("正在联网查询…")

        def worker() -> None:
            from ..regions import detect_province_name

            self.location_found.emit(detect_province_name(timeout=3))

        threading.Thread(target=worker, daemon=True).start()

    def _on_location(self, result) -> None:
        self.locate_btn.setEnabled(True)
        self.locate_btn.setText("重新识别")
        if result is None:
            self.region_label.setText("识别失败，可以在设置页手动选省份")
            self.apply_region_cb.setVisible(False)
            return
        province, city = result
        from ..regions import by_name

        region = by_name(province)
        if region is None:
            self.region_label.setText(f"识别到 {province}，但不在内置列表里")
            self.apply_region_cb.setVisible(False)
            return
        self._region = region
        self.region_label.setText(f"识别到：{province} {city}".strip())
        self.apply_region_cb.setText(f"套用{region.name}的参考电价")
        self.apply_region_cb.setChecked(True)
        self.apply_region_cb.setVisible(True)
        self.region_note.setText(region.note)
        self.region_note.setVisible(True)

    # ---------------------------------------------------------------- finish
    def _collect(self) -> None:
        settings = copy.deepcopy(self.ctx.settings)
        settings.autostart = self.autostart_cb.isChecked()
        if self._region is not None and self.apply_region_cb.isChecked():
            from ..regions import to_tariff

            settings.tariff = to_tariff(self._region)
            settings.region = self._region.code
            settings.region_verified = False
        settings.onboarded = True
        self._result = settings

    def _start(self) -> None:
        self._collect()
        self.accept()

    def _skip(self) -> None:
        settings = copy.deepcopy(self.ctx.settings)
        settings.onboarded = True
        self._result = settings
        self.accept()

    def result_settings(self):
        return self._result


def run_first_run(ctx: AppContext, parent: QWidget | None = None):
    """Show the dialog; returns the settings to apply, or None on failure."""
    dialog = FirstRunDialog(ctx, parent)
    dialog.exec()
    return dialog.result_settings()
