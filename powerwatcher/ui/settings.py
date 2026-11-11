"""Settings page: hardware model, tariff, startup and data tools."""
from __future__ import annotations

import csv
import subprocess
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..config import Hardware, Settings, Tariff, TariffPeriod
from ..paths import data_dir
from .context import AppContext
from .widgets import Card


def _spin(
    minimum: float,
    maximum: float,
    value: float,
    step: float = 1.0,
    decimals: int = 0,
    suffix: str = "",
) -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setRange(minimum, maximum)
    box.setSingleStep(step)
    box.setDecimals(decimals)
    box.setValue(value)
    box.setSuffix(suffix)
    box.setFixedWidth(128)
    box.setAlignment(Qt.AlignmentFlag.AlignRight)
    return box


def _line(text: str = "", width: int = 84) -> QLineEdit:
    edit = QLineEdit(text)
    edit.setFixedWidth(width)
    return edit


class FormSection(Card):
    def __init__(self, title: str, subtitle: str = "") -> None:
        super().__init__()
        self._row = 0
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(18, 14, 18, 16)
        self._grid.setHorizontalSpacing(12)
        self._grid.setVerticalSpacing(9)
        self._grid.setColumnStretch(2, 1)

        heading = QLabel(title)
        heading.setObjectName("SectionTitle")
        self._grid.addWidget(heading, 0, 0, 1, 3)
        self._row = 1
        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("Hint")
            sub.setWordWrap(True)
            self._grid.addWidget(sub, self._row, 0, 1, 3)
            self._row += 1

    def add_row(self, label: str, widget: QWidget, hint: str | QWidget = "") -> None:
        name = QLabel(label)
        name.setObjectName("FieldLabel")
        name.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._grid.addWidget(name, self._row, 0, Qt.AlignmentFlag.AlignTop)
        self._grid.addWidget(widget, self._row, 1, Qt.AlignmentFlag.AlignTop)
        if hint:
            tip = QLabel(hint) if isinstance(hint, str) else hint
            tip.setObjectName("Hint")
            tip.setWordWrap(True)
            self._grid.addWidget(tip, self._row, 2)
        self._row += 1

    def add_full(self, widget: QWidget) -> None:
        self._grid.addWidget(widget, self._row, 0, 1, 3)
        self._row += 1


class SettingsPage(QWidget):
    """Settings page: hardware model, region, tariff, startup, data tools."""

    location_found = Signal(object)  # (province, city) tuple or None

    def __init__(self, ctx: AppContext, on_saved, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._on_saved = on_saved
        self._pending_calibration: float | None = None
        self.location_found.connect(self._on_locate_result)
        self._build()
        self._load(self.ctx.settings)

    # ------------------------------------------------------------------ ui
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 20, 26, 0)
        outer.setSpacing(12)

        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        title = QLabel("设置")
        title.setObjectName("PageTitle")
        sub = QLabel("改完点右下角保存。电价改动会重算全部历史账单。")
        sub.setObjectName("PageSub")
        titles.addWidget(title)
        titles.addWidget(sub)
        head.addLayout(titles)
        head.addStretch(1)
        outer.addLayout(head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        self._stack = QVBoxLayout(inner)
        self._stack.setContentsMargins(0, 0, 14, 8)
        self._stack.setSpacing(12)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

        # ---------------- device
        hw = self.ctx.settings.hardware
        sec = FormSection("设备", "这个软件只统计这一台机器。")
        self.device_name = QLineEdit(hw.device_name)
        self.device_name.setFixedWidth(260)
        sec.add_row("名称", self.device_name, "显示在概览页")
        self.cpu_name = QLabel(hw.cpu_name)
        self.cpu_name.setObjectName("Hint")
        self.gpu_name = QLabel(hw.gpu_name)
        self.gpu_name.setObjectName("Hint")
        sec.add_row("CPU", self.cpu_name, "自动识别，用于对照参数")
        sec.add_row("显卡", self.gpu_name, "自动识别")
        self._stack.addWidget(sec)

        # ---------------- power model
        sec = FormSection(
            "功耗参数",
            "这些是估算的核心。不确定就保持默认，之后用「实测校准」一键修正。",
        )
        self.cpu_idle = _spin(0, 200, hw.cpu_idle_w, 1, 0, " W")
        self.cpu_max = _spin(10, 500, hw.cpu_max_w, 1, 0, " W")
        sec.add_row("CPU 空闲 / 满载", self._pair(self.cpu_idle, self.cpu_max), "9700X 约 16 / 88 W")
        self.gpu_idle = _spin(0, 300, hw.gpu_idle_w, 1, 0, " W")
        self.gpu_max = _spin(10, 800, hw.gpu_max_w, 1, 0, " W")
        sec.add_row("显卡 空闲 / 满载", self._pair(self.gpu_idle, self.gpu_max), "RTX 5060 约 16 / 145 W")
        self.base_w = _spin(0, 200, hw.base_w, 1, 0, " W")
        sec.add_row("主板/内存/硬盘", self.base_w, "B850M + 24G + 双 NVMe 约 24 W")
        self.monitor_w = _spin(0, 200, hw.monitor_w, 1, 0, " W")
        self.monitor_count = _spin(1, 6, hw.monitor_count, 1, 0, " 台")
        sec.add_row("显示器", self._pair(self.monitor_w, self.monitor_count), "24 寸约 22 W/台，直接走墙插")
        self.peripherals_w = _spin(0, 100, hw.peripherals_w, 1, 0, " W")
        sec.add_row("键鼠/音箱等", self.peripherals_w, "USB 外设，走电源")
        self.psu_eff = _spin(0.5, 0.99, hw.psu_efficiency, 0.01, 2, "")
        sec.add_row("电源效率", self.psu_eff, "白牌 0.82 / 铜牌 0.86 / 金牌 0.90")
        self.sleep_w = _spin(0, 30, hw.sleep_w, 0.5, 1, " W")
        sec.add_row("睡眠待机功率", self.sleep_w, "睡眠中电源仍在耗电，典型 2~3 W")

        calib_row = QWidget()
        calib_layout = QHBoxLayout(calib_row)
        calib_layout.setContentsMargins(0, 0, 0, 0)
        calib_layout.setSpacing(8)
        self.measured = _spin(1, 2000, 100, 1, 0, " W")
        self.calib_btn = QPushButton("按实测校准")
        self.calib_btn.setObjectName("Ghost")
        self.calib_btn.clicked.connect(self._calibrate)
        self.calib_label = QLabel(f"当前系数 ×{hw.calibration:.3f}")
        self.calib_label.setObjectName("Hint")
        self.calib_label.setWordWrap(True)
        calib_layout.addWidget(self.measured)
        calib_layout.addWidget(self.calib_btn)
        calib_layout.addStretch(1)
        sec.add_row("实测墙插功率", calib_row, self.calib_label)
        self._stack.addWidget(sec)

        # ---------------- region / location
        from ..regions import all_names

        sec = FormSection("地区", "选择你所在的省份，自动套用该省的参考电价。")
        region_row = QWidget()
        region_layout = QHBoxLayout(region_row)
        region_layout.setContentsMargins(0, 0, 0, 0)
        region_layout.setSpacing(8)

        self.region_combo = QComboBox()
        self.region_combo.addItem("自定义（手动填写）")
        for name in all_names():
            self.region_combo.addItem(name)
        self.region_combo.setFixedWidth(200)
        self.region_combo.currentTextChanged.connect(self._on_region_changed)
        region_layout.addWidget(self.region_combo)

        self.locate_btn = QPushButton("自动定位")
        self.locate_btn.setObjectName("Ghost")
        self.locate_btn.clicked.connect(self._auto_locate)
        region_layout.addWidget(self.locate_btn)

        self.apply_region_btn = QPushButton("套用参考电价")
        self.apply_region_btn.setObjectName("Ghost")
        self.apply_region_btn.clicked.connect(self._apply_region)
        region_layout.addWidget(self.apply_region_btn)

        region_layout.addStretch(1)
        sec.add_row("省份", region_row, "")

        self.region_badge = QLabel("")
        self.region_badge.setObjectName("Hint")
        self.region_badge.setWordWrap(True)
        sec.add_full(self.region_badge)

        self._stack.addWidget(sec)

        # ---------------- tariff
        sec = FormSection("电价", "按你家电费单填。谷电占比越高，这个软件省下的钱越明显。")
        self.mode = QComboBox()
        self.mode.addItems(["峰谷分时", "单一电价"])
        self.mode.setFixedWidth(128)
        self.mode.currentIndexChanged.connect(self._sync_mode)
        sec.add_row("计费方式", self.mode, "")
        self.flat_price = _spin(0, 3, self.ctx.settings.tariff.flat_price, 0.0001, 4, " 元")
        self.flat_row_widget = self.flat_price
        sec.add_row("统一电价", self.flat_price, "元/kWh")

        self.period_rows: list[tuple[QLineEdit, QLineEdit, QLineEdit, QDoubleSpinBox]] = []
        for idx in range(2):
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(6)
            name = _line("", 44)
            start = _line("", 52)
            end = _line("", 52)
            price = _spin(0, 3, 0.5, 0.0001, 4, "")
            price.setFixedWidth(96)
            arrow = QLabel("→")
            arrow.setObjectName("Hint")
            layout.addWidget(name)
            layout.addWidget(start)
            layout.addWidget(arrow)
            layout.addWidget(end)
            layout.addWidget(price)
            layout.addStretch(1)
            sec.add_row(f"时段 {idx + 1}", row, "名称 / 起 / 止 / 元每度")
            self.period_rows.append((name, start, end, price))

        tiers = self.ctx.settings.tariff.tiers
        self.tier_enabled = QCheckBox("启用月度阶梯加价")
        self.tier_enabled.setChecked(self.ctx.settings.tariff.tier_enabled)
        sec.add_full(self.tier_enabled)
        self.tier_limits: list[QDoubleSpinBox] = []
        self.tier_sur: list[QDoubleSpinBox] = []
        for idx, (limit, surcharge) in enumerate(tiers[:3]):
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(6)
            lim = _spin(1, 100000, limit if limit < 1e8 else 9999, 10, 0, " kWh/月")
            sur = _spin(0, 2, surcharge, 0.01, 2, " 元/kWh")
            layout.addWidget(lim)
            layout.addWidget(sur)
            layout.addStretch(1)
            sec.add_row(f"第 {idx + 1} 档", row, "月累计超过该值后加价")
            self.tier_limits.append(lim)
            self.tier_sur.append(sur)
        self._stack.addWidget(sec)

        # ---------------- runtime
        sec = FormSection("运行", "")
        self.autostart = QCheckBox("开机自动启动（登录后最小化到托盘）")
        self.autostart.setChecked(self.ctx.settings.autostart)
        sec.add_full(self.autostart)
        self.interval = _spin(2, 60, self.ctx.settings.sampling_interval_s, 1, 0, " 秒")
        sec.add_row("采样间隔", self.interval, "越小越准，也越费一点点 CPU")
        self.idle_notify = _spin(0, 240, self.ctx.settings.idle_notify_min, 5, 0, " 分钟")
        sec.add_row("空闲提醒", self.idle_notify, "挂机超过该时长弹托盘提醒；0 = 关闭")
        self._stack.addWidget(sec)

        # ---------------- data
        sec = FormSection("数据", f"记录保存在 {data_dir()}")
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        open_btn = QPushButton("打开数据文件夹")
        open_btn.setObjectName("Ghost")
        open_btn.clicked.connect(self._open_folder)
        export_btn = QPushButton("导出 CSV")
        export_btn.setObjectName("Ghost")
        export_btn.clicked.connect(self._export_csv)
        clear_btn = QPushButton("清空记录")
        clear_btn.setObjectName("Ghost")
        clear_btn.clicked.connect(self._clear)
        layout.addWidget(open_btn)
        layout.addWidget(export_btn)
        layout.addWidget(clear_btn)
        layout.addStretch(1)
        sec.add_row("操作", row, "")
        self._stack.addWidget(sec)
        self._stack.addStretch(1)

        # ---------------- save bar
        bar = QHBoxLayout()
        self.status = QLabel("")
        self.status.setObjectName("Hint")
        bar.addWidget(self.status)
        bar.addStretch(1)
        reset_btn = QPushButton("恢复默认")
        reset_btn.setObjectName("Ghost")
        reset_btn.clicked.connect(self._reset)
        save_btn = QPushButton("保存设置")
        save_btn.setObjectName("Primary")
        save_btn.clicked.connect(self._save)
        bar.addWidget(reset_btn)
        bar.addWidget(save_btn)
        outer.addLayout(bar)

    @staticmethod
    def _pair(a: QWidget, b: QWidget) -> QWidget:
        holder = QWidget()
        layout = QHBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(a)
        layout.addWidget(b)
        layout.addStretch(1)
        return holder

    # --------------------------------------------------------------- state
    def _sync_mode(self) -> None:
        tou = self.mode.currentIndex() == 0
        self.flat_price.setEnabled(not tou)
        for name, start, end, price in self.period_rows:
            for widget in (name, start, end, price):
                widget.setEnabled(tou)

    def _load(self, settings: Settings) -> None:
        hw = settings.hardware
        self.device_name.setText(hw.device_name)
        self.cpu_name.setText(hw.cpu_name)
        self.gpu_name.setText(hw.gpu_name)
        self.cpu_idle.setValue(hw.cpu_idle_w)
        self.cpu_max.setValue(hw.cpu_max_w)
        self.gpu_idle.setValue(hw.gpu_idle_w)
        self.gpu_max.setValue(hw.gpu_max_w)
        self.base_w.setValue(hw.base_w)
        self.monitor_w.setValue(hw.monitor_w)
        self.monitor_count.setValue(hw.monitor_count)
        self.peripherals_w.setValue(hw.peripherals_w)
        self.psu_eff.setValue(hw.psu_efficiency)
        self.calib_label.setText(f"当前系数 ×{hw.calibration:.3f}")

        tariff = settings.tariff
        self.mode.setCurrentIndex(0 if tariff.mode == "tou" else 1)
        self.flat_price.setValue(tariff.flat_price)
        for idx, (name, start, end, price) in enumerate(self.period_rows):
            if idx < len(tariff.periods):
                period = tariff.periods[idx]
                name.setText(period.name)
                start.setText(period.start)
                end.setText(period.end)
                price.setValue(period.price)
            else:
                name.setText("")
                start.setText("")
                end.setText("")
        self.tier_enabled.setChecked(tariff.tier_enabled)
        for idx in range(min(3, len(tariff.tiers))):
            limit, surcharge = tariff.tiers[idx]
            self.tier_limits[idx].setValue(limit if limit < 1e8 else 9999)
            self.tier_sur[idx].setValue(surcharge)

        self.autostart.setChecked(settings.autostart)
        self.interval.setValue(settings.sampling_interval_s)
        self.idle_notify.setValue(settings.idle_notify_min)
        self.sleep_w.setValue(hw.sleep_w)

        # Region combo and badge
        if settings.region:
            for i in range(self.region_combo.count()):
                if self.region_combo.itemText(i) == self._region_code_to_name(settings.region):
                    self.region_combo.setCurrentIndex(i)
                    break
        else:
            self.region_combo.setCurrentIndex(0)
        self._update_region_badge(settings)
        self._sync_mode()

    @staticmethod
    def _region_code_to_name(code: str) -> str:
        from ..regions import by_code

        r = by_code(code)
        return r.name if r else ""

    def _update_region_badge(self, settings: Settings) -> None:
        from ..regions import by_name

        name = self.region_combo.currentText()
        if name == "自定义（手动填写）":
            self.region_badge.setText("当前为自定义电价。如果你在某个省，选好后点「套用参考电价」。")
            return
        region = by_name(name)
        if region is None:
            self.region_badge.setText("")
            return
        verified_text = "已核实" if settings.region_verified else "未核实"
        self.region_badge.setText(
            f"{region.name}（{region.grid}）· {region.note} · 状态：{verified_text}。"
            "这些数字是参考值，请按你家电费单核对后保存。"
        )

    def collect(self) -> Settings:
        old = self.ctx.settings
        hw = Hardware(
            device_name=self.device_name.text().strip() or old.hardware.device_name,
            cpu_name=old.hardware.cpu_name,
            cpu_idle_w=self.cpu_idle.value(),
            cpu_max_w=self.cpu_max.value(),
            gpu_name=old.hardware.gpu_name,
            gpu_idle_w=self.gpu_idle.value(),
            gpu_max_w=self.gpu_max.value(),
            gpu_source=old.hardware.gpu_source,
            base_w=self.base_w.value(),
            monitor_w=self.monitor_w.value(),
            monitor_count=int(self.monitor_count.value()),
            peripherals_w=self.peripherals_w.value(),
            psu_efficiency=self.psu_eff.value(),
            sleep_w=self.sleep_w.value(),
            calibration=self._calibration_value(old.hardware.calibration),
            active_after_s=old.hardware.active_after_s,
            screen_off_after_s=old.hardware.screen_off_after_s,
        )

        periods = []
        for name, start, end, price in self.period_rows:
            if not start.text().strip() or not end.text().strip():
                continue
            periods.append(
                TariffPeriod(
                    name=name.text().strip() or "段",
                    start=start.text().strip(),
                    end=end.text().strip(),
                    price=price.value(),
                )
            )
        tiers = []
        for limit_box, sur_box in zip(self.tier_limits, self.tier_sur):
            tiers.append((limit_box.value(), sur_box.value()))
        tariff = Tariff(
            mode="tou" if self.mode.currentIndex() == 0 else "flat",
            flat_price=self.flat_price.value(),
            periods=periods or old.tariff.periods,
            tier_enabled=self.tier_enabled.isChecked(),
            tiers=tiers,
        )
        # Region code from the combo selection
        selected = self.region_combo.currentText()
        from ..regions import by_name

        region = by_name(selected) if selected != "自定义（手动填写）" else None
        region_code = region.code if region else ""
        region_verified = region is not None and self.ctx.settings.region_verified

        return Settings(
            hardware=hw,
            tariff=tariff,
            autostart=self.autostart.isChecked(),
            sampling_interval_s=int(self.interval.value()),
            idle_notify_min=int(self.idle_notify.value()),
            region=region_code,
            region_verified=region_verified,
        )

    def _calibration_value(self, fallback: float) -> float:
        if self._pending_calibration is None:
            return fallback
        value = self._pending_calibration
        self._pending_calibration = None
        return value

    # -------------------------------------------------------------- actions
    def _on_region_changed(self, text: str) -> None:
        """Badge refresh when the user picks a different province."""
        from ..regions import by_name

        if text == "自定义（手动填写）":
            self.region_badge.setText("当前为自定义电价。如果你在某个省，选好后点「套用参考电价」。")
            return
        region = by_name(text)
        if region is None:
            self.region_badge.setText("")
            return
        self.region_badge.setText(
            f"{region.name}（{region.grid}）· {region.note} · 状态：未核实。"
            "点「套用参考电价」把参考值填进下方，核对后保存。"
        )

    def _auto_locate(self) -> None:
        """Detect province from public IP and suggest it in the combo."""
        self.locate_btn.setEnabled(False)
        self.locate_btn.setText("检测中…")
        self.region_badge.setText("正在通过网络定位你的省份…")

        def _worker():
            from ..regions import detect_province_name

            result = detect_province_name(timeout=3)
            # Signal emission is thread-safe; the slot runs on the UI thread.
            self.location_found.emit(result)

        import threading

        threading.Thread(target=_worker, daemon=True).start()

    def _on_locate_result(self, result) -> None:
        """Runs on the UI thread via the location_found signal."""
        self.locate_btn.setEnabled(True)
        self.locate_btn.setText("自动定位")
        if result is None:
            self.region_badge.setText("定位失败，请手动选择省份。")
            return
        prov, city = result
        for i in range(self.region_combo.count()):
            if self.region_combo.itemText(i) == prov:
                self.region_combo.setCurrentIndex(i)
                break
        self.region_badge.setText(
            f"检测到：{prov}{city}。点「套用参考电价」加载该省参考值，然后按电费单核对。"
        )

    def _apply_region(self) -> None:
        """Load the selected province's reference tariff into the fields."""
        from ..regions import by_name

        name = self.region_combo.currentText()
        if name == "自定义（手动填写）":
            return
        region = by_name(name)
        if region is None:
            return

        # Fill the tariff widgets from the region's reference data
        if region.mode == "tou":
            self.mode.setCurrentIndex(0)
            for idx, (name_w, start_w, end_w, price_w) in enumerate(self.period_rows):
                if idx < len(region.periods):
                    p = region.periods[idx]
                    name_w.setText(p["name"])
                    start_w.setText(p["start"])
                    end_w.setText(p["end"])
                    price_w.setValue(p["price"])
                else:
                    name_w.setText("")
                    start_w.setText("")
                    end_w.setText("")
        else:
            self.mode.setCurrentIndex(1)
            self.flat_price.setValue(region.flat_price)

        self.tier_enabled.setChecked(bool(region.tiers))
        for idx, (limit, surcharge) in enumerate(region.tiers[:3]):
            if idx < len(self.tier_limits):
                self.tier_limits[idx].setValue(limit if limit < 1e8 else 9999)
                self.tier_sur[idx].setValue(surcharge)

        self._sync_mode()
        self.region_badge.setText(
            f"已套用 {region.name} 参考电价（{region.note}）。"
            f"这些是参考值，请务必按你家电费单核对后再保存。"
        )

    def _calibrate(self) -> None:
        state = self.ctx.sampler.state
        current = float(state.get("wall_w", 0.0))
        calib = self.ctx.settings.hardware.calibration
        if current <= 1:
            QMessageBox.information(self, "还没有数据", "先让它在后台记录几秒，再回来校准。")
            return
        uncalibrated = current / max(calib, 1e-6)
        measured = self.measured.value()
        new_calib = measured / uncalibrated
        new_calib = min(5.0, max(0.2, new_calib))
        self._pending_calibration = new_calib
        self.calib_label.setText(f"保存后系数 → ×{new_calib:.3f}（当前模型 {uncalibrated:.0f} W）")

    def _save(self) -> None:
        settings = self.collect()
        try:
            self._on_saved(settings)
        except Exception as exc:  # surface, don't crash the app
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        self._load(settings)
        self.status.setText(f"已保存 · {datetime.now():%H:%M:%S}")

    def _reset(self) -> None:
        if QMessageBox.question(self, "恢复默认", "把所有设置恢复成默认值？") != QMessageBox.StandardButton.Yes:
            return
        self._load(Settings())

    def _open_folder(self) -> None:
        subprocess.Popen(["explorer", str(data_dir())])

    def _export_csv(self) -> None:
        default = Path.home() / f"电费记录_{datetime.now():%Y%m%d}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "导出 CSV", str(default), "CSV (*.csv)")
        if not path:
            return
        rows = self.ctx.store.all_days()
        with open(path, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(["日期", "开机秒", "活跃秒", "睡眠秒", "用电kWh", "电费元"])
            for row in rows:
                writer.writerow(
                    [
                        row.day,
                        round(row.on_s, 1),
                        round(row.active_s, 1),
                        round(row.asleep_s, 1),
                        round(row.kwh, 4),
                        round(row.cost, 4),
                    ]
                )
        self.status.setText(f"已导出 {len(rows)} 天 → {path}")

    def _clear(self) -> None:
        answer = QMessageBox.question(
            self,
            "清空记录",
            "会删除所有采样数据，不可恢复。确定？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.ctx.store.clear_all()
        self.status.setText("已清空")
