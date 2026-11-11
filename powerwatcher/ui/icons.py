"""Drawn-in-code icons so the app ships without binary assets."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from . import theme

# Lightning bolt in a 24x24 design space.
_BOLT = [
    (13.2, 2.0),
    (4.4, 13.6),
    (10.6, 13.6),
    (9.6, 22.0),
    (19.6, 10.2),
    (13.0, 10.2),
]


def _scaled(points: list[tuple[float, float]], size: int, inset: float) -> list[QPointF]:
    span = size - inset * 2
    return [QPointF(inset + x / 24 * span, inset + y / 24 * span) for x, y in points]


def app_pixmap(size: int = 64, rounded: bool = True) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    if rounded:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#171b22"))
        painter.drawRoundedRect(QRectF(0.5, 0.5, size - 1, size - 1), size * 0.24, size * 0.24)

    path = QPainterPath()
    pts = _scaled(_BOLT, size, size * 0.22)
    path.moveTo(pts[0])
    for pt in pts[1:]:
        path.lineTo(pt)
    path.closeSubpath()

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(theme.ACCENT))
    painter.drawPath(path)
    painter.end()
    return pixmap


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(app_pixmap(size))
    return icon


def tray_pixmap(size: int = 32, paused: bool = False) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor(theme.TEXT_FAINT) if paused else QColor(theme.ACCENT)
    painter.setPen(QPen(color, max(1.0, size * 0.045)))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    radius = size * 0.42
    painter.drawEllipse(QPointF(size / 2, size / 2), radius, radius)
    path = QPainterPath()
    pts = _scaled(_BOLT, size, size * 0.26)
    path.moveTo(pts[0])
    for pt in pts[1:]:
        path.lineTo(pt)
    path.closeSubpath()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawPath(path)
    painter.end()
    return pixmap
