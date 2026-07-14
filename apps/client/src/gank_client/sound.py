from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QSoundEffect

ASSETS = Path(__file__).parent / "assets" / "sounds"

_TIER_FILES = {
    "IMMINENT": "imminent.wav",
    "RECENT": "recent.wav",
    "STAY WARY": "wary.wav",
}


class SoundPlayer:
    """One QSoundEffect per tier, kept alive for the app's lifetime --
    QSoundEffect is unreliable if constructed and immediately discarded."""

    def __init__(self) -> None:
        self._effects: dict[str, QSoundEffect] = {}
        for tier, filename in _TIER_FILES.items():
            effect = QSoundEffect()
            effect.setSource(QUrl.fromLocalFile(str(ASSETS / filename)))
            effect.setVolume(0.6)
            self._effects[tier] = effect

    def play(self, tier: str) -> None:
        effect = self._effects.get(tier)
        if effect is not None:
            effect.play()
