"""Shared command-line parsing helpers for runtime entry points."""

from __future__ import annotations


def parse_symbol_list(
    value: str | None,
    *,
    default: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Parse comma-separated symbols without normalizing their casing."""

    if not value:
        return default
    return tuple(symbol.strip() for symbol in value.split(",") if symbol.strip())
