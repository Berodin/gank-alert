from __future__ import annotations


def format_isk(value: float | None) -> str:
    if not value:
        return "unknown"
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B ISK"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M ISK"
    return f"{value:,.0f} ISK"
