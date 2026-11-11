"""Overview page: today at a glance, live power, plus month/year totals."""
from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from .. import analytics
from . import theme
from .context import AppContext
from .widgets import AreaChart, Card, StackedBar, StatCard


class BreakdownList(QWidget):
    """Fixed set of component rows; values are updated in place."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[tuple[QLabel, QLabel]] = []
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 6, 0, 0)
        self._layout.setSpacing(5)

    def set_items(self, items: list[tuple[str, float, str]]) -> None:
        while len(self._rows) < len(items):
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(8)
            dot = QLabel()
            dot.setFixedSize(8, 8)
            name = QLabel()
            name.setObjectName("CardHint")
            name.setStyleSheet(f"color: {theme.TEXT_DIM};")
            value = QLabel()
            value.setStyleSheet(f"color: {theme.TEXT}; font-size: 12px;")
            h.addWidget(dot)
            h.addWidget(name)
            h.addStretch(1)
            h.addWidget(value)
            self._layout.addWidget(row)
            self._rows.append((name, value))

        total = sum(v for _, v, _ in items) or 1.0
        for idx, (name, value, color) in enumerate(items):
            name_label, value_label = self._rows[idx]
            name_label.setText(items[idx][0])
            value_label.setText(f"{value:.0f} W  ·  {value / total * 100:.0f}%")
            dot = name_label.parentWidget().layout().itemAt(0).widget()
            dot.setStyleSheet(f"background: {color}; border-radius: 4px;")
        for idx in range(len(items), len(self._rows)):
            name_label, _ = self._rows[idx]
            name_label.parentWidget().hide()
        for idx in range(len(items)):
            self._rows[idx][0].parentWidget().show()


class OverviewPage(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._build()

    # ------------------------------------------------------------------ ui
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 20, 26, 20)
        root.setSpacing(14)

        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.title = QLabel("概览")
        self.title.setObjectName("PageTitle")
        self.sub = QLabel("")
        self.sub.setObjectName("PageSub")
        titles.addWidget(self.title)
        titles.addWidget(self.sub)
        head.addLayout(titles)
        head.addStretch(1)
        self.live_chip = QLabel("● 记录中")
        self.live_chip.setObjectName("ChipAccent")
        head.addWidget(self.live_chip, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(head)

        # ---- four headline numbers
        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.card_cost = StatCard("今日电费", "元", theme.ACCENT)
        self.card_kwh = StatCard("今日用电", "kWh")
        self.card_time = StatCard("今日开机", "小时")
        self.card_now = StatCard("当前功率", "W", theme.GREEN)
        for card in (self.card_cost, self.card_kwh, self.card_time, self.card_now):
            card.setMinimumHeight(118)
            cards.addWidget(card, 1)
        root.addLayout(cards)

        # ---- chart + breakdown
        middle = QHBoxLayout()
        middle.setSpacing(12)

        chart_card = Card()
        chart_layout = QVBoxLayout(chart_card)
        chart_layout.setContentsMargins(16, 14, 16, 10)
        chart_layout.setSpacing(6)
        chart_head = QHBoxLayout()
        chart_title = QLabel("今日功率曲线")
        chart_title.setObjectName("CardTitle")
        self.chart_hint = QLabel("24 小时 · 平均功率")
        self.chart_hint.setObjectName("CardHint")
        chart_head.addWidget(chart_title)
        chart_head.addStretch(1)
        chart_head.addWidget(self.chart_hint)
        chart_layout.addLayout(chart_head)
        self.chart = AreaChart()
        chart_layout.addWidget(self.chart, 1)
        middle.addWidget(chart_card, 3)

        side_card = Card()
        side_layout = QVBoxLayout(side_card)
        side_layout.setContentsMargins(16, 14, 16, 14)
        side_layout.setSpacing(6)
        side_head = QHBoxLayout()
        side_title = QLabel("实时构成")
        side_title.setObjectName("CardTitle")
        self.side_total = QLabel("—")
        self.side_total.setStyleSheet(
            f"color: {theme.ACCENT}; font-size: 15px; font-weight: 600;"
        )
        side_head.addWidget(side_title)
        side_head.addStretch(1)
        side_head.addWidget(self.side_total)
        side_layout.addLayout(side_head)
        self.breakdown_bar = StackedBar(show_legend=False)
        side_layout.addWidget(self.breakdown_bar)
        self.breakdown_list = BreakdownList()
        side_layout.addWidget(self.breakdown_list, 1)
        self.tariff_label = QLabel("")
        self.tariff_label.setObjectName("CardHint")
        self.tariff_label.setWordWrap(True)
        side_layout.addWidget(self.tariff_label)
        middle.addWidget(side_card, 2)
        root.addLayout(middle, 1)

        # ---- month / year / yesterday
        bottom = QHBoxLayout()
        bottom.setSpacing(12)
        self.card_month = StatCard("本月电费", "元")
        self.card_year = StatCard("本年电费", "元")
        self.card_yday = StatCard("昨日电费", "元")
        self.card_avg = StatCard("日均（近 7 天）", "元")
        for card in (self.card_month, self.card_year, self.card_yday, self.card_avg):
            card.setMinimumHeight(96)
            bottom.addWidget(card, 1)
        root.addLayout(bottom)

        self.sub.setText(
            f"{self.ctx.settings.hardware.device_name} · {datetime.now():%Y年%m月%d日}"
        )
        self.tariff_label.setText("电价：" + self.ctx.engine.describe())

    # --------------------------------------------------------------- update
    def on_live(self, state: dict) -> None:
        watts = state.get("wall_w", 0.0)
        app = state.get("app")
        hint = "屏幕亮" if state.get("screen_on") else "屏幕已熄"
        if app:
            from ..analytics import app_label

            hint += f" · {app_label(app)}"
        self.card_now.set_value(f"{watts:.0f}", "W", hint)
        items = analytics.breakdown(self.ctx.settings.hardware, state)
        self.breakdown_list.set_items(items)
        self.breakdown_bar.set_data(items)
        self.side_total.setText(f"{watts:.0f} W")

        if self.ctx.sampler.paused:
            self.live_chip.setText("● 已暂停")
            self.live_chip.setStyleSheet(
                f"background: rgba(255,95,109,0.12); border: 1px solid rgba(255,95,109,0.35);"
                f" border-radius: 10px; color: {theme.RED}; font-size: 11px; padding: 3px 9px;"
            )
        else:
            self.live_chip.setText("● 记录中")
            self.live_chip.setStyleSheet("")
            self.live_chip.setObjectName("ChipAccent")

    def refresh(self) -> None:
        store = self.ctx.store
        now = datetime.now()
        day = now.strftime("%Y-%m-%d")

        today = None
        for row in store.days(day, day):
            today = row
            break

        if today is None:
            self.card_cost.set_value("0.00", "元", "等待数据")
            self.card_kwh.set_value("0.00", "kWh")
            self.card_time.set_value("0", "小时", "活跃 0分")
        else:
            monthly = today.cost * 30
            if monthly > 0:
                digits = 0 if monthly >= 10 else 1
                hint = f"按今天推算每月约 {monthly:.{digits}f} 元"
            else:
                hint = "刚开始记录"
            self.card_cost.set_value(f"{today.cost:.2f}", "元", hint)
            self.card_kwh.set_value(
                f"{today.kwh:.2f}",
                "kWh",
                f"含睡眠待机 {today.standby_kwh:.3f} kWh" if today.standby_kwh > 0.0005 else None,
            )
            if today.on_s >= 3600:
                self.card_time.set_value(
                    f"{today.on_s / 3600:.1f}",
                    "小时",
                    f"活跃 {analytics.hours_text(today.active_s)}",
                )
            else:
                self.card_time.set_value(
                    f"{today.on_s / 60:.0f}",
                    "分钟",
                    f"活跃 {analytics.hours_text(today.active_s)}",
                )

        values = analytics.hourly_watts(store, day)
        labels = [f"{h}点" for h in range(24)]
        self.chart.set_data(values, labels, "W", theme.ACCENT)

        month_start, _ = analytics.month_range(day)
        month_rows = store.days(month_start, day)
        month_kwh = sum(r.kwh for r in month_rows)
        self.card_month.set_value(
            f"{sum(r.cost for r in month_rows):.2f}",
            "元",
            f"本月 {month_kwh:.2f} kWh" if month_kwh < 10 else f"本月 {month_kwh:.1f} kWh",
        )

        year_start, year_end = analytics.year_range(day)
        year_rows = store.days(year_start, year_end)
        self.card_year.set_value(
            f"{sum(r.cost for r in year_rows):.2f}", "元", f"{len(year_rows)} 天有记录"
        )

        yday = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
        yday_str = yday.strftime("%Y-%m-%d")
        yrow = store.days(yday_str, yday_str)
        self.card_yday.set_value(
            f"{yrow[0].cost:.2f}" if yrow else "0.00",
            "元",
            f"{yrow[0].kwh:.2f} kWh" if yrow else "无记录",
        )

        week = analytics.series_days(store, day, 7)
        active_days = [d for d in week if d.kwh > 0]
        avg = sum(d.cost for d in active_days) / len(active_days) if active_days else 0.0
        self.card_avg.set_value(f"{avg:.2f}", "元", f"{len(active_days)}/7 天有记录")

        self.tariff_label.setText("电价：" + self.ctx.engine.describe())
        self.chart_hint.setText(
            "24 小时 · 平均功率" if any(v is not None for v in values) else "24 小时 · 等待采样"
        )
