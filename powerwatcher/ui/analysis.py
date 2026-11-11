"""Analysis page: daily cost bars and peak/valley tariff insight."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import analytics
from . import theme
from .context import AppContext
from .widgets import AppRankList, BarChart, Card, StackedBar, StatCard


class AnalysisPage(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._range = 7
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 20, 26, 20)
        root.setSpacing(14)

        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        title = QLabel("分析")
        title.setObjectName("PageTitle")
        self.sub = QLabel("按天看花了多少，以及峰谷电价的空间")
        self.sub.setObjectName("PageSub")
        titles.addWidget(title)
        titles.addWidget(self.sub)
        head.addLayout(titles)
        head.addStretch(1)

        self.range_group = QButtonGroup(self)
        self.range_group.setExclusive(True)
        for days, label in ((7, "近 7 天"), (30, "近 30 天"), (0, "本月")):
            btn = QPushButton(label)
            btn.setObjectName("Ghost")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setChecked(days == 7)
            btn.clicked.connect(lambda _=False, d=days: self._set_range(d))
            self.range_group.addButton(btn)
            head.addWidget(btn)
        root.addLayout(head)

        stats = QHBoxLayout()
        stats.setSpacing(12)
        self.card_total = StatCard("期间电费", "元", theme.ACCENT)
        self.card_kwh = StatCard("期间用电", "kWh")
        self.card_avg = StatCard("日均", "元")
        self.card_valley = StatCard("谷电占比", "%", theme.GREEN)
        for card in (self.card_total, self.card_kwh, self.card_avg, self.card_valley):
            card.setMinimumHeight(108)
            stats.addWidget(card, 1)
        root.addLayout(stats)

        chart_card = Card()
        chart_layout = QVBoxLayout(chart_card)
        chart_layout.setContentsMargins(16, 14, 16, 10)
        chart_layout.setSpacing(4)
        chart_head = QHBoxLayout()
        chart_title = QLabel("每日电费")
        chart_title.setObjectName("CardTitle")
        self.chart_sub = QLabel("")
        self.chart_sub.setObjectName("CardHint")
        chart_head.addWidget(chart_title)
        chart_head.addStretch(1)
        chart_head.addWidget(self.chart_sub)
        chart_layout.addLayout(chart_head)
        self.bars = BarChart()
        self.bars.setMinimumHeight(170)
        chart_layout.addWidget(self.bars, 1)
        root.addWidget(chart_card, 1)

        # ---- cost per foreground app (today)
        app_card = Card()
        app_layout = QVBoxLayout(app_card)
        app_layout.setContentsMargins(16, 14, 16, 10)
        app_layout.setSpacing(4)
        app_head = QHBoxLayout()
        app_title = QLabel("钱花在哪个软件（今日）")
        app_title.setObjectName("CardTitle")
        self.app_sub = QLabel("按前台软件归因 · 仅统计你在使用的时间")
        self.app_sub.setObjectName("CardHint")
        app_head.addWidget(app_title)
        app_head.addStretch(1)
        app_head.addWidget(self.app_sub)
        app_layout.addLayout(app_head)
        self.app_rank = AppRankList()
        app_layout.addWidget(self.app_rank)
        root.addWidget(app_card)

        # ---- tariff window split + idle insight
        split_card = Card()
        split_layout = QVBoxLayout(split_card)
        split_layout.setContentsMargins(16, 14, 16, 14)
        split_layout.setSpacing(6)
        split_title = QLabel("电价时段构成")
        split_title.setObjectName("CardTitle")
        split_layout.addWidget(split_title)
        self.split_bar = StackedBar()
        split_layout.addWidget(self.split_bar)
        self.insight = QLabel("")
        self.insight.setObjectName("CardHint")
        self.insight.setWordWrap(True)
        split_layout.addWidget(self.insight)
        self.idle_insight = QLabel("")
        self.idle_insight.setObjectName("CardHint")
        self.idle_insight.setWordWrap(True)
        split_layout.addWidget(self.idle_insight)
        root.addWidget(split_card)

    def _set_range(self, days: int) -> None:
        self._range = days
        self.refresh()

    # --------------------------------------------------------------- update
    def refresh(self) -> None:
        store = self.ctx.store
        today = datetime.now().strftime("%Y-%m-%d")

        if self._range == 0:
            start_day, end_day = analytics.month_range(today)
            rows = store.days(start_day, today)
            labels = [d.day[5:] for d in rows]
            values = [d.cost for d in rows]
            window_text = "本月至今"
        else:
            rows = analytics.series_days(store, today, self._range)
            labels = [d.day[5:].replace("-", "/") for d in rows]
            values = [d.cost for d in rows]
            window_text = f"近 {self._range} 天"

        total = sum(values)
        kwh = sum(d.kwh for d in rows)
        active_days = [d for d in rows if d.kwh > 0]
        avg = total / len(active_days) if active_days else 0.0

        self.card_total.set_value(f"{total:.2f}", "元", window_text)
        self.card_kwh.set_value(f"{kwh:.2f}", "kWh", f"{len(active_days)} 天有记录")
        self.card_avg.set_value(f"{avg:.2f}", "元", "只在有记录的天上平均")
        self.bars.set_data(values, labels, "元", theme.ACCENT)
        self.chart_sub.setText(f"{window_text} · 单位 元")

        start_ts = int(datetime.strptime(rows[0].day, "%Y-%m-%d").timestamp()) if rows else 0
        end_ts = int(datetime.strptime(rows[-1].day, "%Y-%m-%d").timestamp()) + 86400 if rows else 0
        split = analytics.period_split(store, self.ctx.engine, start_ts, end_ts) if rows else {}

        palette = {"峰": theme.ACCENT, "谷": theme.GREEN, "平": theme.BLUE, "平价": theme.BLUE}
        items = [
            (name, data["kwh"], palette.get(name, theme.PURPLE))
            for name, data in sorted(split.items(), key=lambda kv: -kv[1]["kwh"])
        ]
        self.split_bar.set_data(items)

        valley_kwh = split.get("谷", {}).get("kwh", 0.0)
        ratio = valley_kwh / kwh * 100 if kwh > 0 else 0.0
        self.card_valley.set_value(f"{ratio:.0f}", "%", f"谷段 {valley_kwh:.1f} kWh")

        peak = split.get("峰", {})
        valley = split.get("谷", {})
        if peak and valley and valley["kwh"] > 0:
            delta = peak["price"] - valley["price"]
            movable = peak["kwh"] * 0.5
            saving = movable * delta
            self.insight.setText(
                f"峰段 {peak['kwh']:.1f} kWh（{peak['price']:.4f} 元）占大头。"
                f"如果把其中一半（{movable:.1f} kWh）挪到谷电时段（{valley['price']:.4f} 元），"
                f"这段时间可以少付约 {saving:.2f} 元。"
            )
        elif kwh > 0:
            prices = [d["price"] for d in split.values()]
            self.insight.setText(
                f"当前是单一电价，{prices[0]:.4f} 元/kWh。"
                "如果你所在地区有峰谷电价，改成峰谷后这里会算出可节省的金额。"
            )
        else:
            self.insight.setText("还没有足够的数据。让它在托盘里跑上一天，这里就会有内容。")

        self._refresh_apps(today)
        self._refresh_idle(today)

    def _refresh_apps(self, today: str) -> None:
        ranking = analytics.app_ranking(self.ctx.store, self.ctx.engine, today)
        total_kwh = sum(k for _, k, _ in ranking)
        rows = []
        for idx, (label, kwh, cost) in enumerate(ranking):
            share = kwh / total_kwh if total_kwh > 0 else 0.0
            rows.append((label, f"{cost:.2f} 元 · {kwh:.2f} kWh", share, theme.SERIES[idx % len(theme.SERIES)]))
        self.app_rank.set_data(rows)
        self.app_sub.setText(
            "按前台软件归因 · 仅统计你在使用的时间"
            if rows
            else "按前台软件归因 · 等待今天的记录"
        )

    def _refresh_idle(self, today: str) -> None:
        summary = analytics.idle_summary(self.ctx.store, today)
        idle_s = summary["idle_s"]
        if idle_s < 300:
            self.idle_insight.setText("")
            return
        idle_hours = idle_s / 3600
        avg_price = 0.55
        day = None
        for row in self.ctx.store.days(today, today):
            day = row
        if day and day.kwh > 0:
            avg_price = day.cost / day.kwh
        monthly = summary["idle_kwh"] * 30 * avg_price
        self.idle_insight.setText(
            f"今天挂机（开机但没人用）{idle_hours:.1f} 小时，约 {summary['idle_kwh']:.2f} kWh、"
            f"{summary['idle_kwh'] * avg_price:.2f} 元——挂机时平均功率 {summary['idle_w']:.0f} W。"
            f"离开时改睡眠，这个习惯每月能省约 {monthly:.0f} 元。"
        )
