"""Per-surface render modules.

Each module renders one navigation surface from a snapshot. The shell in
``render.py`` composes them all into a single document so client-side hash
routing can switch between them without a network round-trip.
"""

from __future__ import annotations
