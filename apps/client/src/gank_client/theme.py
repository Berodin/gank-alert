"""EVE-inspired HUD theme: near-black panels, cyan glow, angular brackets."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFontDatabase

ASSETS = Path(__file__).parent / "assets"

# -- palette -----------------------------------------------------------
BG_VOID = "#04080b"
BG_PANEL = "#0b141c"
BG_PANEL_RAISED = "#10202c"
BG_ROW_ALT = "#0e1922"

BORDER = "#1d4a5c"
BORDER_BRIGHT = "#2ee6ff"

TEXT_PRIMARY = "#cdeefc"
TEXT_DIM = "#5f8998"
TEXT_HEADER = "#7fe8ff"

ACCENT_CYAN = "#22d3ee"
ACCENT_AMBER = "#ffb020"
ACCENT_RED = "#ff3b4e"
ACCENT_GREEN = "#35e28a"

FONT_DISPLAY = "Orbitron"
FONT_MONO = "Share Tech Mono"


def load_fonts() -> None:
    for filename in ("Orbitron-Regular.ttf", "ShareTechMono-Regular.ttf"):
        QFontDatabase.addApplicationFont(str(ASSETS / "fonts" / filename))


STYLESHEET = f"""
QWidget {{
    background-color: transparent;
    color: {TEXT_PRIMARY};
    font-family: "{FONT_MONO}";
    font-size: 13px;
}}

QMainWindow {{
    background-color: {BG_VOID};
}}

QLabel {{
    background-color: transparent;
    border: none;
}}

QLabel#wordmark {{
    font-family: "{FONT_DISPLAY}";
    font-size: 22px;
    color: {TEXT_HEADER};
    letter-spacing: 6px;
}}

QLabel#wordmarkSub {{
    font-family: "{FONT_MONO}";
    font-size: 11px;
    color: {TEXT_DIM};
    letter-spacing: 3px;
}}

QLabel[role="sectionTitle"] {{
    font-family: "{FONT_DISPLAY}";
    font-size: 12px;
    color: {ACCENT_CYAN};
    letter-spacing: 3px;
    padding-bottom: 2px;
}}

QLabel[role="statValue"] {{
    font-family: "{FONT_DISPLAY}";
    font-size: 26px;
    color: {ACCENT_CYAN};
}}

QLabel[role="statUnit"] {{
    font-family: "{FONT_MONO}";
    font-size: 11px;
    color: {TEXT_DIM};
    letter-spacing: 2px;
}}

QLabel[role="dim"] {{
    color: {TEXT_DIM};
    font-size: 11px;
}}

QPushButton {{
    background-color: {BG_PANEL_RAISED};
    border: 1px solid {BORDER};
    color: {ACCENT_CYAN};
    font-family: "{FONT_DISPLAY}";
    font-size: 11px;
    letter-spacing: 2px;
    padding: 8px 18px;
}}

QPushButton:hover {{
    border-color: {BORDER_BRIGHT};
    color: {TEXT_HEADER};
    background-color: #142835;
}}

QPushButton:pressed {{
    background-color: #0a1620;
}}

QScrollArea {{
    border: none;
}}

QScrollBar:vertical {{
    background: {BG_VOID};
    width: 8px;
}}

QScrollBar::handle:vertical {{
    background: {BORDER};
    min-height: 24px;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
"""
