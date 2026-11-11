"""Custom lightweight widgets: cards and hand-drawn charts.

Charts are painted with QPainter on purpose — no QtCharts dependency, full
control over the dark theme, and they stay crisp at any DPI.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout, QWidget

from . import theme


class Card(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")


class StatCard(Card):
    """Label on top, big number, unit and an optional hint line."""

    def __init__(
        self,
        title: str,
        unit: str = "",
        accent: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._accent = accent
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 13, 16, 13)
        layout.setSpacing(2)

        self.title = QLabel(title)
        self.title.setObjectName("CardTitle")

        row = QWidget()
        row_layout = QVBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)

        self.value = QLabel("—")
        self.value.setObjectName("CardValue")
        self.unit = QLabel(unit)
        self.unit.setObjectName("CardUnit")

        self.hint = QLabel("")
        self.hint.setObjectName("CardHint")

        layout.addWidget(self.title)
        layout.addWidget(self.value)
        layout.addWidget(self.unit)
        layout.addWidget(self.hint)
        layout.addStretch(1)

        if accent:
            self.value.setStyleSheet(f"color: {accent};")

    def set_value(self, value: str, unit: str | None = None, hint: str | None = None) -> None:
        self.value.setText(value)
        if unit is not None:
            self.unit.setText(unit)
        if hint is not None:
            self.hint.setText(hint)


def _nice_ceiling(value: float) -> float:
    if value <= 0:
        return 10.0
    exponent = math.floor(math.log10(value))
    base = 10.0**exponent
    for step in (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if value <= step * base:
            return step * base
    return 10 * base


def _nice_scale(value: float, levels: int = 4) -> float:
    """Axis maximum whose intermediate grid lines land on round numbers."""
    return _nice_ceiling(value / levels) * levels


class _ChartBase(QWidget):
    PAD_L = 44
    PAD_R = 16
    PAD_T = 14
    PAD_B = 24

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(150)
        self._empty_text = "还没有数据"

    def _plot_rect(self) -> QRectF:
        return QRectF(
            self.PAD_L,
            self.PAD_T,
            max(1.0, self.width() - self.PAD_L - self.PAD_R),
            max(1.0, self.height() - self.PAD_T - self.PAD_B),
        )

    def _paint_empty(self, painter: QPainter) -> None:
        painter.setPen(QPen(theme.qcolor(theme.TEXT_FAINT)))
        painter.setFont(theme.ui_font(9))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._empty_text)

    def _draw_y_grid(
        self, painter: QPainter, rect: QRectF, top: float, levels: int = 4, suffix: str = ""
    ) -> None:
        painter.setFont(theme.ui_font(8))
        decimals = 0 if top >= 10 else (1 if top >= 1 else 2)
        for i in range(levels + 1):
            ratio = i / levels
            y = rect.bottom() - rect.height() * ratio
            painter.setPen(QPen(theme.qcolor(theme.BORDER, 150), 1))
            if i > 0:
                painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            painter.setPen(QPen(theme.qcolor(theme.TEXT_FAINT)))
            label = f"{top * ratio:.{decimals}f}{suffix}"
            painter.drawText(
                QRectF(0, y - 8, self.PAD_L - 8, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                label,
            )


class AreaChart(_ChartBase):
    """Smooth filled line, used for the 24-hour power curve."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._values: list[float | None] = []
        self._labels: list[str] = []
        self._unit = "W"
        self._color = theme.ACCENT
        self._hover = -1
        self.setMouseTracking(True)

    def set_data(
        self,
        values: list[float | None],
        labels: list[str] | None = None,
        unit: str = "W",
        color: str = theme.ACCENT,
    ) -> None:
        self._values = values
        self._labels = labels or [str(i) for i in range(len(values))]
        self._unit = unit
        self._color = color
        self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        rect = self._plot_rect()
        if not self._values:
            return
        n = len(self._values)
        step = rect.width() / max(1, n - 1)
        idx = round((event.position().x() - rect.left()) / step) if step else 0
        idx = max(0, min(n - 1, idx))
        if idx != self._hover:
            self._hover = idx
            self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._hover = -1
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self._plot_rect()

        valid = [v for v in self._values if v is not None]
        if not valid:
            self._paint_empty(painter)
            return

        top = _nice_scale(max(valid) * 1.15)
        self._draw_y_grid(painter, rect, top, 4, self._unit)

        n = len(self._values)
        step = rect.width() / max(1, n - 1)

        def point(i: int, value: float) -> QPointF:
            return QPointF(
                rect.left() + step * i,
                rect.bottom() - rect.height() * min(1.0, value / top),
            )

        # Build a path over the contiguous run(s) of real data.
        segments: list[list[QPointF]] = []
        current: list[QPointF] = []
        for i, value in enumerate(self._values):
            if value is None:
                if current:
                    segments.append(current)
                current = []
            else:
                current.append(point(i, value))
        if current:
            segments.append(current)

        for seg in segments:
            if len(seg) == 1:
                # A single hour of data still deserves a marker.
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(theme.qcolor(self._color)))
                painter.drawEllipse(seg[0], 3.0, 3.0)
                continue
            area = QPainterPath()
            area.moveTo(QPointF(seg[0].x(), rect.bottom()))
            for pt in seg:
                area.lineTo(pt)
            area.lineTo(QPointF(seg[-1].x(), rect.bottom()))
            area.closeSubpath()

            gradient = QLinearGradient(0, rect.top(), 0, rect.bottom())
            gradient.setColorAt(0.0, theme.qcolor(self._color, 90))
            gradient.setColorAt(1.0, theme.qcolor(self._color, 6))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(gradient))
            painter.drawPath(area)

            # Midpoint-quadratic smoothing: control point is the previous
            # sample, endpoint the midpoint, so the curve never overshoots.
            line = QPainterPath()
            line.moveTo(seg[0])
            for i in range(1, len(seg)):
                prev, cur = seg[i - 1], seg[i]
                mid = QPointF((prev.x() + cur.x()) / 2, (prev.y() + cur.y()) / 2)
                line.quadTo(prev, mid)
            line.lineTo(seg[-1])
            painter.setPen(QPen(theme.qcolor(self._color), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(line)

        # x labels
        painter.setFont(theme.ui_font(8))
        painter.setPen(QPen(theme.qcolor(theme.TEXT_FAINT)))
        stride = max(1, n // 6)
        for i in range(0, n, stride):
            x = rect.left() + step * i
            painter.drawText(
                QRectF(x - 20, rect.bottom() + 5, 40, 16),
                Qt.AlignmentFlag.AlignCenter,
                self._labels[i] if i < len(self._labels) else "",
            )

        # hover crosshair
        if 0 <= self._hover < n and self._values[self._hover] is not None:
            idx = self._hover
            pt = point(idx, float(self._values[idx]))
            painter.setPen(QPen(theme.qcolor(theme.TEXT_FAINT, 130), 1, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(pt.x(), rect.top()), QPointF(pt.x(), rect.bottom()))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(theme.qcolor(self._color)))
            painter.drawEllipse(pt, 3.5, 3.5)
            painter.setBrush(QBrush(theme.qcolor(theme.CARD_ALT, 240)))
            painter.setPen(QPen(theme.qcolor(theme.BORDER)))
            label = f"{self._labels[idx]}  {self._values[idx]:.0f}{self._unit}"
            fm = QFontMetrics(theme.ui_font(9))
            w = fm.horizontalAdvance(label) + 16
            h = 22
            x = min(max(rect.left(), pt.x() - w / 2), rect.right() - w)
            y = max(rect.top(), pt.y() - h - 10)
            painter.drawRoundedRect(QRectF(x, y, w, h), 5, 5)
            painter.setPen(QPen(theme.qcolor(theme.TEXT)))
            painter.setFont(theme.ui_font(9))
            painter.drawText(QRectF(x, y, w, h), Qt.AlignmentFlag.AlignCenter, label)


class BarChart(_ChartBase):
    """Vertical bars with rounded tops, used for daily cost."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._values: list[float] = []
        self._labels: list[str] = []
        self._unit = "元"
        self._color = theme.ACCENT
        self._highlight = -1

    def set_data(
        self,
        values: list[float],
        labels: list[str],
        unit: str = "元",
        color: str = theme.ACCENT,
        highlight: int = -1,
    ) -> None:
        self._values = values
        self._labels = labels
        self._unit = unit
        self._color = color
        self._highlight = highlight if highlight >= 0 else len(values) - 1
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self._plot_rect()

        if not self._values or max(self._values) <= 0:
            self._paint_empty(painter)
            return

        top = _nice_scale(max(self._values) * 1.2)
        self._draw_y_grid(painter, rect, top, 4, "")

        n = len(self._values)
        slot = rect.width() / n
        bar_w = min(46.0, slot * 0.58)

        for i, value in enumerate(self._values):
            cx = rect.left() + slot * (i + 0.5)
            h = rect.height() * min(1.0, value / top) if value > 0 else 0.0
            if h < 1.5:
                continue
            bar = QRectF(cx - bar_w / 2, rect.bottom() - h, bar_w, h)
            is_last = i == self._highlight
            if is_last:
                gradient = QLinearGradient(0, bar.top(), 0, bar.bottom())
                gradient.setColorAt(0.0, theme.qcolor(self._color))
                gradient.setColorAt(1.0, theme.qcolor(self._color, 70))
                painter.setBrush(QBrush(gradient))
            else:
                painter.setBrush(QBrush(theme.qcolor(self._color, 120)))
            painter.setPen(Qt.PenStyle.NoPen)
            path = QPainterPath()
            radius = min(4.0, bar_w / 2, h / 2)
            path.addRoundedRect(bar, radius, radius)
            painter.drawPath(path)

            painter.setFont(theme.ui_font(8))
            painter.setPen(QPen(theme.qcolor(theme.TEXT if is_last else theme.TEXT_FAINT)))
            painter.drawText(
                QRectF(cx - slot / 2, rect.bottom() + 4, slot, 16),
                Qt.AlignmentFlag.AlignCenter,
                self._labels[i] if i < len(self._labels) else "",
            )
            if is_last and h > 18:
                painter.setPen(QPen(theme.qcolor(theme.TEXT)))
                painter.drawText(
                    QRectF(cx - slot / 2, bar.top() - 16, slot, 14),
                    Qt.AlignmentFlag.AlignCenter,
                    f"{value:.2f}",
                )


class AppRankList(QWidget):
    """Rows of "app · kWh · ¥" with a share bar, for the cost-per-app card."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[tuple[str, str, float, str]] = []
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

    def set_data(self, rows: list[tuple[str, str, float, str]]) -> None:
        """rows: (label, value_text, share 0..1, color)."""
        self._rows = rows
        height = 8 + len(rows) * 26 if rows else 40
        self.setMinimumHeight(height)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self._rows:
            painter.setPen(QPen(theme.qcolor(theme.TEXT_FAINT)))
            painter.setFont(theme.ui_font(9))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "今天还没记录")
            return
        width = self.width()
        y = 2.0
        for label, value, share, color in self._rows:
            painter.setFont(theme.ui_font(9))
            painter.setPen(QPen(theme.qcolor(theme.TEXT_DIM)))
            painter.drawText(QPointF(0, y + 12), label)
            painter.setPen(QPen(theme.qcolor(theme.TEXT)))
            painter.drawText(
                QRectF(0, y, width, 16),
                Qt.AlignmentFlag.AlignRight,
                value,
            )
            bar_y = y + 18
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(theme.qcolor(theme.BORDER, 130)))
            painter.drawRoundedRect(QRectF(0, bar_y, width - 2, 4), 2, 2)
            if share > 0:
                painter.setBrush(QBrush(theme.qcolor(color)))
                painter.drawRoundedRect(
                    QRectF(0, bar_y, max(3.0, (width - 2) * share), 4), 2, 2
                )
            y += 26


class StackedBar(QWidget):
    """One horizontal 100% bar, optionally with a legend underneath."""

    def __init__(self, parent: QWidget | None = None, show_legend: bool = True) -> None:
        super().__init__(parent)
        self._items: list[tuple[str, float, str]] = []
        self._show_legend = show_legend
        self.setMinimumHeight(58 if show_legend else 16)
        self.setMaximumHeight(64 if show_legend else 18)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_data(self, items: list[tuple[str, float, str]]) -> None:
        self._items = [(label, max(0.0, value), color) for label, value, color in items]
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        total = sum(v for _, v, _ in self._items)
        width = self.width()
        bar_h = 12.0
        top = 2.0 if self._show_legend else (self.height() - bar_h) / 2
        if total <= 0:
            painter.setPen(QPen(theme.qcolor(theme.TEXT_FAINT)))
            painter.setFont(theme.ui_font(9))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "还没有数据")
            return

        x = 0.0
        for _, value, color in self._items:
            seg = width * value / total
            if seg <= 0:
                continue
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(theme.qcolor(color)))
            painter.drawRoundedRect(QRectF(x, top, max(2.0, seg - 2), bar_h), 3, 3)
            x += seg

        if not self._show_legend:
            return

        painter.setFont(theme.ui_font(8))
        x = 0.0
        for label, value, color in self._items:
            if value <= 0:
                continue
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(theme.qcolor(color)))
            painter.drawEllipse(QPointF(x + 4, 30), 3, 3)
            painter.setPen(QPen(theme.qcolor(theme.TEXT_DIM)))
            text = f"{label} {value / total * 100:.0f}%"
            if x + painter.fontMetrics().horizontalAdvance(text) + 12 > width:
                break
            painter.drawText(QPointF(x + 12, 34), text)
            x += painter.fontMetrics().horizontalAdvance(text) + 26
