"""Custom-painted widgets that give the EVE HUD look: angular cut-corner
panels with glowing viewfinder-style corner brackets."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from gank_client import theme

CUT = 14
"""Diagonal corner-cut size, in px."""

BRACKET = 16
"""Corner bracket arm length, in px."""


class HudPanel(QFrame):
    """A panel with cut top-left/bottom-right corners and glowing corner
    brackets, like an EVE Online HUD window."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setContentsMargins(18, 16, 18, 16)
        self._bracket_color = QColor(theme.BORDER_BRIGHT)
        self._border_color = QColor(theme.BORDER)
        self._bg_color = QColor(theme.BG_PANEL)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        path = QPainterPath()
        path.moveTo(CUT, 0)
        path.lineTo(w, 0)
        path.lineTo(w, h - CUT)
        path.lineTo(w - CUT, h)
        path.lineTo(0, h)
        path.lineTo(0, CUT)
        path.closeSubpath()

        painter.fillPath(path, self._bg_color)
        painter.setPen(QPen(self._border_color, 1))
        painter.drawPath(path)

        pen = QPen(self._bracket_color, 2)
        pen.setCapStyle(Qt.PenCapStyle.SquareCap)
        painter.setPen(pen)

        # top-left (already cut, so bracket starts past the cut)
        painter.drawLine(QPointF(CUT + 4, 1), QPointF(CUT + 4 + BRACKET, 1))
        painter.drawLine(QPointF(0, CUT + 4), QPointF(0, CUT + 4 + BRACKET))
        # top-right
        painter.drawLine(QPointF(w - 1, 0), QPointF(w - 1, BRACKET))
        painter.drawLine(QPointF(w - BRACKET, 0), QPointF(w, 0))
        # bottom-left
        painter.drawLine(QPointF(0, h - BRACKET), QPointF(0, h))
        painter.drawLine(QPointF(0, h - 1), QPointF(BRACKET, h - 1))
        # bottom-right (cut corner)
        painter.drawLine(
            QPointF(w - CUT - 4 - BRACKET, h - 1), QPointF(w - CUT - 4, h - 1)
        )
        painter.drawLine(
            QPointF(w, h - CUT - 4 - BRACKET), QPointF(w, h - CUT - 4)
        )

        super().paintEvent(event)


def fix_transparency(root: QWidget) -> None:
    """Qt paints each child widget's own backing store opaque black by
    default when its ancestor draws a custom (non-QSS) background, as
    HudPanel does -- these attributes make children genuinely see-through
    so the panel's hand-painted background shows through instead of a
    black box. Call once after the widget tree under `root` is built."""
    for widget in [root, *root.findChildren(QWidget)]:
        widget.setAutoFillBackground(False)
        widget.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)


class SectionTitle(QLabel):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setProperty("role", "sectionTitle")


class GankFeedRow(QWidget):
    """One row in the region feed: a left threat-color strip + kill summary.

    `tier` is one of gank_shared.tiers' labels (FRESH/RECENT/STAY WARY),
    or None for anything older than that window -- shown dim/gray rather
    than excluded, since the feed is a broader history view, not just live
    alerts like the bot's."""

    def __init__(
        self,
        *,
        time_label: str,
        system_name: str,
        victim_name: str,
        victim_ship: str,
        ganker_tag: str,
        value_str: str,
        attacker_count: int,
        location_name: str | None,
        jumps: int | None,
        tier: tuple[str, str] | None,
        on_dismiss: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        color = tier[1] if tier is not None else theme.TEXT_DIM

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 6, 0, 6)
        root.setSpacing(12)

        strip = QFrame()
        strip.setFixedWidth(3)
        strip.setStyleSheet(f"background-color: {color}; border: none;")
        root.addWidget(strip)

        text_col = QVBoxLayout()
        text_col.setSpacing(1)

        top = QHBoxLayout()
        sys_label = QLabel(system_name.upper())
        sys_label.setStyleSheet(
            f"font-family: '{theme.FONT_DISPLAY}'; font-size: 12px; color: {theme.TEXT_HEADER};"
        )
        time_lbl = QLabel(time_label)
        time_lbl.setProperty("role", "dim")
        top.addWidget(sys_label)
        top.addStretch()
        top.addWidget(time_lbl)

        middle = QLabel(f"{victim_name} lost a {victim_ship} ({value_str})")
        middle.setStyleSheet(f"color: {theme.TEXT_PRIMARY}; font-size: 12px;")

        attacker_word = "attacker" if attacker_count == 1 else "attackers"
        bottom = QLabel(f"Killed by {ganker_tag} · {attacker_count} {attacker_word}")
        bottom.setProperty("role", "dim")

        text_col.addLayout(top)
        text_col.addWidget(middle)
        text_col.addWidget(bottom)

        if location_name:
            location_lbl = QLabel(location_name)
            location_lbl.setProperty("role", "dim")
            text_col.addWidget(location_lbl)

        root.addLayout(text_col, stretch=1)

        if jumps is not None:
            jump_lbl = QLabel(f"{jumps}J")
            jump_lbl.setStyleSheet(
                f"font-family: '{theme.FONT_DISPLAY}'; font-size: 16px; color: {color};"
            )
            jump_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            root.addWidget(jump_lbl)

        if on_dismiss is not None:
            dismiss_btn = QPushButton("×")
            dismiss_btn.setFixedSize(20, 20)
            dismiss_btn.setStyleSheet(
                f"QPushButton {{ color: {theme.TEXT_DIM}; border: none; font-size: 14px; }}"
                f"QPushButton:hover {{ color: {theme.ACCENT_RED}; }}"
            )
            dismiss_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            dismiss_btn.clicked.connect(on_dismiss)
            root.addWidget(dismiss_btn, alignment=Qt.AlignmentFlag.AlignTop)
