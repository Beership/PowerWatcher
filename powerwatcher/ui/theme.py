"""Colours, fonts and the global stylesheet."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase

ASSETS = (Path(__file__).resolve().parent / "assets").as_posix()

BG = "#0e1013"
SIDEBAR = "#111419"
CARD = "#171b22"
CARD_ALT = "#1c212a"
BORDER = "#232a35"
TEXT = "#e8ebf2"
TEXT_DIM = "#98a1b3"
TEXT_FAINT = "#5d6678"
ACCENT = "#ffb02e"
ACCENT_DEEP = "#8a5b00"
GREEN = "#3ddc84"
BLUE = "#4c8dff"
PURPLE = "#a06bff"
PINK = "#ff8fab"
RED = "#ff5f6d"

SERIES = [ACCENT, BLUE, PURPLE, GREEN, PINK, TEXT_FAINT]


def ui_font(size: int = 10, weight: int = 400) -> QFont:
    families = QFontDatabase.families()
    for name in ("Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Segoe UI"):
        if name in families:
            font = QFont(name, size)
            break
    else:
        font = QFont("Segoe UI", size)
    font.setWeight(QFont.Weight(weight))
    return font


def qcolor(hex_str: str, alpha: int = 255) -> QColor:
    color = QColor(hex_str)
    color.setAlpha(alpha)
    return color


STYLESHEET = f"""
QWidget {{
    background: transparent;
    color: {TEXT};
    font-family: "Microsoft YaHei UI", "Segoe UI";
    font-size: 13px;
}}
#Root {{ background: {BG}; }}
#Sidebar {{ background: {SIDEBAR}; border-right: 1px solid {BORDER}; }}
#Brand {{ color: {TEXT}; font-size: 16px; font-weight: 600; }}
#BrandSub {{ color: {TEXT_FAINT}; font-size: 11px; }}
#PageTitle {{ color: {TEXT}; font-size: 21px; font-weight: 600; }}
#PageSub {{ color: {TEXT_DIM}; font-size: 12px; }}

QPushButton#Nav {{
    background: transparent;
    border: none;
    border-radius: 8px;
    color: {TEXT_DIM};
    text-align: left;
    padding: 9px 12px;
    font-size: 13px;
}}
QPushButton#Nav:hover {{ background: {CARD}; color: {TEXT}; }}
QPushButton#Nav:checked {{
    background: {CARD_ALT};
    color: {ACCENT};
    font-weight: 600;
}}

QFrame#Card {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
#CardTitle {{ color: {TEXT_DIM}; font-size: 12px; }}
#CardValue {{ color: {TEXT}; font-size: 27px; font-weight: 600; }}
#CardUnit {{ color: {TEXT_FAINT}; font-size: 12px; }}
#CardHint {{ color: {TEXT_FAINT}; font-size: 11px; }}

#Chip {{
    background: {CARD_ALT};
    border: 1px solid {BORDER};
    border-radius: 10px;
    color: {TEXT_DIM};
    font-size: 11px;
    padding: 3px 9px;
}}
#ChipAccent {{
    background: rgba(255,176,46,0.12);
    border: 1px solid rgba(255,176,46,0.35);
    border-radius: 10px;
    color: {ACCENT};
    font-size: 11px;
    padding: 3px 9px;
}}

QPushButton#Ghost {{
    background: {CARD_ALT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    color: {TEXT_DIM};
    padding: 7px 14px;
}}
QPushButton#Ghost:hover {{ color: {TEXT}; border-color: {TEXT_FAINT}; }}
QPushButton#Ghost:checked {{
    background: rgba(255,176,46,0.13);
    border-color: rgba(255,176,46,0.45);
    color: {ACCENT};
}}
QPushButton#Primary {{
    background: {ACCENT};
    border: none;
    border-radius: 8px;
    color: #17130a;
    font-weight: 600;
    padding: 9px 20px;
}}
QPushButton#Primary:hover {{ background: #ffc157; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {CARD_ALT};
    border: 1px solid {BORDER};
    border-radius: 7px;
    padding: 6px 9px;
    color: {TEXT};
    selection-background-color: {ACCENT_DEEP};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {ACCENT};
}}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{
    color: {TEXT_FAINT};
    background: #14171d;
    border-color: #1c222c;
}}
/* Hide the spin arrows instead of using NoButtons: with a stylesheet applied,
   NoButtons collapses the text field and the value disappears. */
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    width: 0px;
    border: none;
    background: transparent;
}}
QSpinBox::up-arrow, QSpinBox::down-arrow,
QDoubleSpinBox::up-arrow, QDoubleSpinBox::down-arrow {{
    width: 0px;
    height: 0px;
    image: none;
}}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background: {CARD_ALT};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT_DEEP};
    outline: none;
}}

QCheckBox {{ color: {TEXT_DIM}; spacing: 8px; }}
QCheckBox:disabled {{ color: {TEXT_FAINT}; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {BORDER};
    border-radius: 4px;
    background: {CARD_ALT};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
    image: url("{ASSETS}/check.svg");
}}

#SectionTitle {{ color: {TEXT}; font-size: 14px; font-weight: 600; }}
#FieldLabel {{ color: {TEXT_DIM}; font-size: 12px; }}
#Hint {{ color: {TEXT_FAINT}; font-size: 11px; }}
#Mono {{ font-family: "Cascadia Mono", "Consolas"; }}

QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{
    background: transparent; width: 9px; margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER}; border-radius: 4px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {TEXT_FAINT}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QMenu {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px;
}}
QMenu::item {{
    padding: 7px 22px 7px 14px;
    border-radius: 5px;
    color: {TEXT_DIM};
}}
QMenu::item:selected {{ background: {CARD_ALT}; color: {TEXT}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 5px 8px; }}

QToolTip {{
    background: {CARD_ALT};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 5px 8px;
}}
"""
