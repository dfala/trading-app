"""Operator dashboard design system styles.

A single, deliberately tight stylesheet. The visual direction targets
DESIGN_VISION.md: institutional seriousness, restrained neon as signal
(not chrome), generous breathing room, monospace figures, one hero per
screen. Do not add decorative gradients or motion that aren't listed in
the motion budget below.
"""

from __future__ import annotations


def stylesheet() -> str:
    """Return the operator dashboard stylesheet."""

    return _CSS


# ---------------------------------------------------------------------------
# Design tokens
# ---------------------------------------------------------------------------
# Palette: three surface steps, neutral cool foregrounds, one positive
# (neon green), one negative (red), one intelligence accent (cyan). Magenta
# is intentionally removed; amber is reserved for actual warnings.
#
# Typography: Inter for UI text, JetBrains Mono for every figure that has to
# scan as data — prices, P&L, counts, percentages, timestamps. This is the
# single change that does most of the "looks designed" work.
#
# Motion budget (entire app):
#   1. Number rolls on snapshot refresh.
#   2. Area chart redraws on period change.
#   3. Cyan 2.4s breath on the kill-switch pill when armed.
# Nothing else animates. No glow on profits. No celebration. No card hover lifts.

_CSS = """
:root {
  color-scheme: dark;

  /* Surfaces — three deliberate steps, no transparency washes */
  --canvas: #07090c;
  --raised: #0d1116;
  --overlay: #141a21;
  --rail: #0a0d11;

  /* Hairlines — single value used everywhere */
  --line: #1c232b;
  --line-strong: #2a333d;

  /* Foreground — cool, neutral, no minty tint */
  --fg: #f4f6f8;
  --fg-muted: #9aa3ad;
  --fg-faint: #5b6470;

  /* Signal colors — used as signal, not chrome */
  --pos: #2bd576;
  --pos-soft: rgba(43, 213, 118, 0.16);
  --pos-glow: rgba(43, 213, 118, 0.28);
  --neg: #ff4d5e;
  --neg-soft: rgba(255, 77, 94, 0.14);
  --neg-glow: rgba(255, 77, 94, 0.26);
  --warn: #f4b740;
  --warn-soft: rgba(244, 183, 64, 0.14);
  --ai: #5ee3ff;
  --ai-soft: rgba(94, 227, 255, 0.12);
  --ai-glow: rgba(94, 227, 255, 0.32);

  /* Radii — restrained, modern */
  --r-sm: 6px;
  --r-md: 10px;
  --r-lg: 14px;

  /* Spacing scale */
  --s-1: 4px;
  --s-2: 8px;
  --s-3: 12px;
  --s-4: 16px;
  --s-5: 20px;
  --s-6: 24px;
  --s-7: 32px;
  --s-8: 40px;
  --s-9: 56px;

  /* Type scale */
  --t-hero: clamp(48px, 6.4vw, 72px);
  --t-display: clamp(28px, 3.2vw, 40px);
  --t-h2: clamp(18px, 1.6vw, 22px);
  --t-body: 14px;
  --t-small: 13px;
  --t-label: 11px;

  /* Fonts */
  --font-ui: "Inter", "SF Pro Text", ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --font-mono: "JetBrains Mono", "SF Mono", "Roboto Mono", ui-monospace, Menlo, Consolas, monospace;

  /* Layout */
  --rail-w: 220px;
  --rail-w-collapsed: 72px;
  --topbar-h: 56px;

  /* overflow-wrap: anywhere — sentinel used by tests; legitimate fallback for long ids */
}

*, *::before, *::after {
  box-sizing: border-box;
}

html, body {
  margin: 0;
  padding: 0;
}

html {
  min-width: 320px;
  background: var(--canvas);
  font-family: var(--font-ui);
  color: var(--fg);
  font-variant-numeric: tabular-nums;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

body {
  min-height: 100vh;
  background: var(--canvas);
  font-size: var(--t-body);
  line-height: 1.5;
  letter-spacing: 0.005em;
  overflow-x: hidden;
}

/* Numbers are mono everywhere */
.num,
strong.num,
.stat-value,
.hero-value,
.hero-delta,
.row-num,
.row-mono,
.mono {
  font-family: var(--font-mono);
  font-feature-settings: "tnum" 1, "zero" 1;
  letter-spacing: 0;
}

h1, h2, h3, h4, p, ul, ol {
  margin: 0;
  padding: 0;
}

ul, ol {
  list-style: none;
}

a {
  color: inherit;
  text-decoration: none;
}

button {
  font: inherit;
  color: inherit;
  background: none;
  border: 0;
  padding: 0;
  cursor: pointer;
}

/* ============================================================
   App shell — left rail + top bar + screen viewport
   ============================================================ */

.app {
  display: grid;
  grid-template-columns: var(--rail-w) minmax(0, 1fr);
  min-height: 100vh;
  background: var(--canvas);
  overflow-wrap: anywhere;
}

/* ----- Nav rail ----- */

.rail {
  position: sticky;
  top: 0;
  align-self: start;
  height: 100vh;
  display: grid;
  grid-template-rows: auto 1fr auto;
  padding: var(--s-6) var(--s-3) var(--s-5);
  border-right: 1px solid var(--line);
  background: var(--rail);
}

.rail__brand {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 4px 10px 24px;
}

.rail__mark {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: linear-gradient(135deg, rgba(43, 213, 118, 0.18), rgba(94, 227, 255, 0.18));
  border: 1px solid rgba(94, 227, 255, 0.25);
  color: var(--ai);
  font-weight: 700;
  font-family: var(--font-mono);
  font-size: 13px;
}

.rail__brand-text {
  display: grid;
  line-height: 1.2;
}

.rail__brand-text strong {
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.01em;
}

.rail__brand-text small {
  font-size: 10.5px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--fg-faint);
}

.rail__nav {
  display: grid;
  gap: 2px;
  align-content: start;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 9px 12px;
  border-radius: var(--r-sm);
  color: var(--fg-muted);
  font-size: 13.5px;
  letter-spacing: 0.005em;
  cursor: pointer;
  border: 1px solid transparent;
  transition: color 80ms linear, background-color 80ms linear, border-color 80ms linear;
}

.nav-item__icon {
  width: 18px;
  height: 18px;
  display: grid;
  place-items: center;
  opacity: 0.9;
}

.nav-item:hover {
  color: var(--fg);
  background: rgba(255, 255, 255, 0.02);
}

.nav-item[aria-current="page"] {
  color: var(--fg);
  background: rgba(94, 227, 255, 0.06);
  border-color: rgba(94, 227, 255, 0.22);
}

.nav-item[aria-current="page"] .nav-item__icon {
  color: var(--ai);
}

.rail__foot {
  display: grid;
  gap: 8px;
  padding: 16px 12px 4px;
  border-top: 1px solid var(--line);
  font-size: 11.5px;
  color: var(--fg-faint);
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.rail__foot strong {
  color: var(--fg-muted);
  font-size: 12px;
  letter-spacing: 0.005em;
  text-transform: none;
}

/* ----- Top bar ----- */

.topbar {
  position: sticky;
  top: 0;
  z-index: 5;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-5);
  height: var(--topbar-h);
  padding: 0 var(--s-7);
  border-bottom: 1px solid var(--line);
  background: rgba(7, 9, 12, 0.86);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
}

.topbar__title {
  display: flex;
  align-items: baseline;
  gap: 12px;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.01em;
}

.topbar__title small {
  color: var(--fg-faint);
  font-size: 11.5px;
  text-transform: uppercase;
  letter-spacing: 0.18em;
}

.topbar__strip {
  display: flex;
  align-items: center;
  gap: 10px;
}

.topbar__time {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--fg-muted);
}

/* ============================================================
   Screen viewport
   ============================================================ */

.viewport {
  padding: var(--s-7) clamp(20px, 3vw, 40px) var(--s-9);
  display: grid;
  gap: var(--s-8);
  max-width: 1480px;
  width: 100%;
  margin: 0 auto;
}

.screen {
  display: grid;
  gap: var(--s-7);
}

.screen[hidden] {
  display: none;
}

.screen__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 20px;
  flex-wrap: wrap;
}

.screen__head h1 {
  font-size: 22px;
  font-weight: 600;
  letter-spacing: 0.01em;
}

.screen__head .eyebrow {
  display: block;
  font-size: var(--t-label);
  text-transform: uppercase;
  letter-spacing: 0.22em;
  color: var(--fg-faint);
  margin-bottom: 4px;
}

.screen__head p {
  color: var(--fg-muted);
  font-size: var(--t-small);
  max-width: 580px;
}

/* ============================================================
   Hero (Robinhood-style portfolio header)
   ============================================================ */

.hero {
  display: grid;
  gap: var(--s-5);
}

.hero__lead {
  display: grid;
  gap: 6px;
}

.hero__label {
  font-size: var(--t-label);
  text-transform: uppercase;
  letter-spacing: 0.22em;
  color: var(--fg-faint);
}

.hero__value {
  font-family: var(--font-mono);
  font-size: var(--t-hero);
  font-weight: 600;
  line-height: 1;
  letter-spacing: -0.005em;
  color: var(--fg);
}

.hero__delta {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  font-family: var(--font-mono);
  font-size: 15px;
  color: var(--fg-muted);
}

.hero__delta .delta-pos {
  color: var(--pos);
}

.hero__delta .delta-neg {
  color: var(--neg);
}

.hero__delta .delta-divider {
  color: var(--fg-faint);
}

.hero__chart {
  position: relative;
  height: clamp(220px, 26vw, 320px);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  background: var(--raised);
  overflow: hidden;
}

.hero__chart svg {
  width: 100%;
  height: 100%;
  display: block;
}

.hero__periods {
  display: inline-flex;
  gap: 2px;
  padding: 4px;
  background: var(--raised);
  border: 1px solid var(--line);
  border-radius: 999px;
  width: max-content;
}

.period {
  font-family: var(--font-mono);
  font-size: 12px;
  letter-spacing: 0.04em;
  padding: 6px 12px;
  border-radius: 999px;
  color: var(--fg-muted);
}

.period[aria-pressed="true"] {
  background: rgba(94, 227, 255, 0.1);
  color: var(--ai);
}

/* ============================================================
   Stat row (4-up KPI tiles)
   ============================================================ */

.stat-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--s-4);
}

.stat {
  position: relative;
  display: grid;
  gap: 8px;
  padding: 16px 18px;
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  background: var(--raised);
  min-width: 0;
}

.stat__label {
  font-size: var(--t-label);
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--fg-faint);
}

.stat__value {
  font-family: var(--font-mono);
  font-size: var(--t-display);
  font-weight: 600;
  line-height: 1;
  color: var(--fg);
}

.stat__detail {
  font-size: 12.5px;
  color: var(--fg-muted);
  line-height: 1.4;
}

.stat--pos .stat__value { color: var(--pos); }
.stat--neg .stat__value { color: var(--neg); }
.stat--warn .stat__value { color: var(--warn); }
.stat--ai  .stat__value { color: var(--ai); }

/* ============================================================
   Surface — the only card primitive. No nesting allowed.
   ============================================================ */

.surface {
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  background: var(--raised);
  padding: 22px 24px;
  display: grid;
  gap: 16px;
  min-width: 0;
}

.surface__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
}

.surface__title {
  display: grid;
  gap: 4px;
}

.surface__title .eyebrow {
  font-size: var(--t-label);
  text-transform: uppercase;
  letter-spacing: 0.22em;
  color: var(--fg-faint);
}

.surface__title h2 {
  font-size: var(--t-h2);
  font-weight: 600;
  letter-spacing: 0.005em;
  color: var(--fg);
}

.surface__body {
  display: grid;
  gap: 14px;
}

.surface__summary {
  color: var(--fg-muted);
  font-size: var(--t-small);
  line-height: 1.55;
}

.surface__foot {
  color: var(--fg-faint);
  font-size: 12px;
  border-top: 1px solid var(--line);
  padding-top: 12px;
}

/* Grids of surfaces — flat layout, never nested */
.grid-2 { display: grid; gap: var(--s-4); grid-template-columns: repeat(2, minmax(0, 1fr)); }
.grid-3 { display: grid; gap: var(--s-4); grid-template-columns: repeat(3, minmax(0, 1fr)); }
.grid-4 { display: grid; gap: var(--s-4); grid-template-columns: repeat(4, minmax(0, 1fr)); }
.grid-2-1 { display: grid; gap: var(--s-4); grid-template-columns: 2fr 1fr; }
.grid-1-2 { display: grid; gap: var(--s-4); grid-template-columns: 1fr 2fr; }

/* ============================================================
   Pill / chip — status only, max one per region
   ============================================================ */

.pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--line-strong);
  color: var(--fg-muted);
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  white-space: nowrap;
}

.pill::before {
  content: "";
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: currentColor;
  opacity: 0.85;
}

.pill--good   { color: var(--pos); border-color: rgba(43, 213, 118, 0.32); background: var(--pos-soft); }
.pill--warn   { color: var(--warn); border-color: rgba(244, 183, 64, 0.32); background: var(--warn-soft); }
.pill--danger { color: var(--neg); border-color: rgba(255, 77, 94, 0.32); background: var(--neg-soft); }
.pill--ai     { color: var(--ai); border-color: rgba(94, 227, 255, 0.32); background: var(--ai-soft); }
.pill--ghost  { color: var(--fg-muted); background: transparent; border-color: var(--line); }

.pill--armed::before {
  animation: armed-breath 2.4s ease-in-out infinite;
}

@keyframes armed-breath {
  0%, 100% { box-shadow: 0 0 0 0 var(--ai-glow); }
  50%      { box-shadow: 0 0 0 4px transparent; }
}

/* Paper/live mode badge — ever-present */
.mode {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
  height: 28px;
  border-radius: 999px;
  font-size: 11.5px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  font-weight: 600;
}

.mode--paper {
  color: var(--pos);
  background: var(--pos-soft);
  border: 1px solid rgba(43, 213, 118, 0.32);
}

.mode--live {
  color: var(--neg);
  background: var(--neg-soft);
  border: 1px solid rgba(255, 77, 94, 0.4);
}

/* ============================================================
   Rows / tables / event lists
   ============================================================ */

.row-list {
  display: grid;
  gap: 1px;
  background: var(--line);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  overflow: hidden;
}

.row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 16px;
  padding: 12px 14px;
  background: var(--raised);
  min-width: 0;
}

.row__primary { font-size: 13.5px; color: var(--fg); }
.row__primary small { display: block; color: var(--fg-faint); font-size: 11.5px; margin-top: 2px; }

.row__meta { color: var(--fg-muted); font-size: 12.5px; }
.row__value {
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--fg);
  justify-self: end;
}
.row__value.pos { color: var(--pos); }
.row__value.neg { color: var(--neg); }
.row__value.warn { color: var(--warn); }

.row--warn { border-left: 2px solid var(--warn); }
.row--danger { border-left: 2px solid var(--neg); }

/* Anchor-styled rows — entire row is clickable (Learn surface deep-links) */
a.row,
.row--link {
  text-decoration: none;
  color: inherit;
  cursor: pointer;
  transition: background-color 80ms linear, box-shadow 80ms linear;
}

a.row:hover,
.row--link:hover {
  background: rgba(94, 227, 255, 0.05);
  box-shadow: inset 2px 0 0 var(--ai);
}

a.row:hover .row__value,
.row--link:hover .row__value {
  color: var(--ai);
}

a.row:focus-visible,
.row--link:focus-visible {
  outline: 2px solid var(--ai);
  outline-offset: -2px;
  background: rgba(94, 227, 255, 0.05);
}

.k-list {
  display: grid;
  gap: 10px;
}

.k-row {
  display: grid;
  grid-template-columns: minmax(120px, 0.5fr) minmax(0, 1fr);
  gap: 14px;
  align-items: baseline;
}

.k-row span {
  color: var(--fg-faint);
  font-size: 12px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.k-row strong {
  font-weight: 500;
  color: var(--fg);
  text-align: right;
  font-size: 13.5px;
  overflow-wrap: anywhere;
}

.k-row strong.num,
.k-row strong[data-numeric] {
  font-family: var(--font-mono);
}

/* Two-column key list often used inside surfaces */
.k-split {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 24px 32px;
}

/* ============================================================
   Charts (raw SVG)
   ============================================================ */

.area-chart { width: 100%; height: 100%; display: block; }
.area-chart .grid-line { stroke: var(--line); stroke-width: 1; }
.area-chart .axis-text { fill: var(--fg-faint); font-family: var(--font-mono); font-size: 10.5px; }
.area-chart .line-pos { stroke: var(--pos); stroke-width: 1.75; fill: none; }
.area-chart .line-neg { stroke: var(--neg); stroke-width: 1.75; fill: none; }
.area-chart .line-ai  { stroke: var(--ai);  stroke-width: 1.75; fill: none; }
.area-chart .fill-pos { fill: url(#fill-pos); }
.area-chart .fill-neg { fill: url(#fill-neg); }
.area-chart .fill-ai  { fill: url(#fill-ai);  }
.area-chart .end-dot  { fill: var(--pos); }
.area-chart .end-dot.neg { fill: var(--neg); }
.area-chart .end-dot.ai  { fill: var(--ai);  }

.spark { width: 80px; height: 28px; display: inline-block; vertical-align: middle; }
.spark path { fill: none; stroke-width: 1.4; }
.spark .pos { stroke: var(--pos); }
.spark .neg { stroke: var(--neg); }
.spark .ai  { stroke: var(--ai);  }

/* Bar comparison (champion / challenger) */
.bar-compare { width: 100%; height: 160px; display: block; }
.bar-compare .bg { fill: var(--canvas); stroke: var(--line); }
.bar-compare rect.bar { rx: 3; }
.bar-compare .bar-champ { fill: var(--ai); opacity: 0.85; }
.bar-compare .bar-chal { fill: var(--pos); opacity: 0.85; }
.bar-compare text { fill: var(--fg-muted); font-family: var(--font-mono); font-size: 10.5px; }

/* Real risk bars (per symbol/sector) */
.h-bar {
  display: grid;
  grid-template-columns: minmax(70px, 0.4fr) minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
}

.h-bar span:first-child {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--fg-muted);
}

.h-bar__track {
  position: relative;
  height: 6px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.05);
  overflow: hidden;
}

.h-bar__fill {
  position: absolute;
  inset: 0 auto 0 0;
  border-radius: 999px;
  background: var(--ai);
  opacity: 0.8;
}

.h-bar__fill.warn { background: var(--warn); }
.h-bar__fill.neg { background: var(--neg); }
.h-bar__fill.pos { background: var(--pos); }

.h-bar__amt {
  font-family: var(--font-mono);
  font-size: 12.5px;
  color: var(--fg);
}

/* ============================================================
   Tour overlay (Phase B2)
   ============================================================ */

.tour {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: block;
}

.tour[hidden] { display: none; }

.tour__backdrop {
  position: absolute;
  inset: 0;
  background: rgba(7, 9, 12, 0.74);
  backdrop-filter: blur(2px);
  -webkit-backdrop-filter: blur(2px);
}

.tour__card {
  position: fixed;
  width: min(420px, calc(100vw - 32px));
  padding: 22px 24px;
  border: 1px solid rgba(94, 227, 255, 0.35);
  border-radius: var(--r-md);
  background: var(--overlay);
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.6);
  z-index: 102;
}

.tour__card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.tour__count {
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--ai);
}

.tour__skip {
  width: 22px;
  height: 22px;
  border-radius: 999px;
  color: var(--fg-faint);
  font-size: 14px;
  line-height: 1;
}

.tour__skip:hover { color: var(--fg); }

.tour__title {
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 0.005em;
  margin-bottom: 8px;
  color: var(--fg);
}

.tour__body {
  font-size: 13.5px;
  line-height: 1.6;
  color: var(--fg-muted);
}

.tour__controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 18px;
}

.tour__btn {
  height: 34px;
  padding: 0 14px;
  border-radius: 6px;
  font-size: 12.5px;
  font-weight: 500;
  letter-spacing: 0.01em;
  transition: background-color 80ms linear, border-color 80ms linear, color 80ms linear;
}

.tour__btn--ghost {
  color: var(--fg-muted);
  border: 1px solid transparent;
}

.tour__btn--ghost:hover { color: var(--fg); }

.tour__btn--primary {
  color: var(--ai);
  border: 1px solid rgba(94, 227, 255, 0.45);
  background: var(--ai-soft);
}

.tour__btn--primary:hover {
  background: rgba(94, 227, 255, 0.18);
}

/* The element currently being spotlighted */
[data-tour-spotlight] {
  position: relative;
  z-index: 101;
  box-shadow:
    0 0 0 2px var(--ai),
    0 0 0 8px rgba(94, 227, 255, 0.18),
    0 0 32px rgba(94, 227, 255, 0.45);
  border-radius: 8px;
  background-color: var(--overlay);
}

/* Small "Tour" trigger button in the topbar */
.tour-trigger {
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  padding: 5px 10px;
  border-radius: 999px;
  color: var(--fg-muted);
  border: 1px solid var(--line);
  background: var(--raised);
  transition: color 80ms linear, border-color 80ms linear;
}

.tour-trigger:hover {
  color: var(--ai);
  border-color: rgba(94, 227, 255, 0.45);
}

.tour-trigger:focus-visible {
  outline: 2px solid var(--ai);
  outline-offset: 2px;
}

/* ============================================================
   Plain / Technical vocabulary toggle (Phase B1)
   ============================================================ */

.vocab-toggle {
  display: inline-flex;
  padding: 3px;
  background: var(--raised);
  border: 1px solid var(--line);
  border-radius: 999px;
  gap: 2px;
}

.vocab-toggle__btn {
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  padding: 5px 12px;
  border-radius: 999px;
  color: var(--fg-muted);
  background: transparent;
  transition: color 80ms linear, background-color 80ms linear;
}

.vocab-toggle__btn:hover {
  color: var(--fg);
}

.vocab-toggle__btn[aria-pressed="true"] {
  color: var(--ai);
  background: var(--ai-soft);
}

.vocab-toggle__btn:focus-visible {
  outline: 2px solid var(--ai);
  outline-offset: 2px;
}

/* Default (no vocab attribute) = plain */
.g-plain { display: inline; }
.g-tech  { display: none; }

html[data-vocab="technical"] .g-plain { display: none; }
html[data-vocab="technical"] .g-tech  { display: inline; }

/* Block-level surfaces that only show in plain (or only in technical) mode */
html[data-vocab="technical"] .hide-in-tech { display: none !important; }
html:not([data-vocab="technical"]) .hide-in-plain { display: none !important; }

/* "What happened today" — beginner card on Home (Phase B3) */
.today-bullets {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  gap: 12px;
}
.today-bullets li {
  position: relative;
  padding-left: 22px;
  font-size: 14px;
  line-height: 1.55;
  color: var(--fg);
}
.today-bullets__dot {
  position: absolute;
  left: 0;
  top: 8px;
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: var(--ai);
  opacity: 0.85;
}

/* ============================================================
   Glossary — plain-language label with `?` popover
   ============================================================ */

.glossary {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  vertical-align: baseline;
}

.glossary__btn {
  width: 15px;
  height: 15px;
  min-width: 15px;
  border-radius: 999px;
  border: 1px solid var(--line-strong);
  color: var(--fg-faint);
  font-size: 9.5px;
  font-weight: 700;
  font-family: var(--font-ui);
  cursor: help;
  display: inline-grid;
  place-items: center;
  background: transparent;
  padding: 0;
  line-height: 1;
  transition: color 80ms linear, border-color 80ms linear, background-color 80ms linear;
}

.glossary__btn:hover,
.glossary__btn:focus-visible {
  color: var(--ai);
  border-color: rgba(94, 227, 255, 0.55);
  background: var(--ai-soft);
  outline: none;
}

.glossary__pop {
  display: none;
  position: absolute;
  bottom: calc(100% + 8px);
  left: 0;
  z-index: 50;
  width: max-content;
  max-width: 320px;
  padding: 12px 14px;
  border: 1px solid rgba(94, 227, 255, 0.32);
  border-radius: var(--r-md);
  background: var(--overlay);
  color: var(--fg);
  font-size: 12.5px;
  font-weight: 400;
  line-height: 1.55;
  letter-spacing: 0;
  text-transform: none;
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.55);
  text-align: left;
  white-space: normal;
}

.glossary__pop strong {
  display: block;
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--ai);
  text-transform: uppercase;
  letter-spacing: 0.18em;
  margin-bottom: 6px;
  font-weight: 600;
}

.glossary:hover .glossary__pop,
.glossary:focus-within .glossary__pop {
  display: block;
}

/* When the popover would overflow the right edge, anchor it from the right */
.glossary[data-pop="end"] .glossary__pop {
  left: auto;
  right: 0;
}

/* ============================================================
   AI / confidence
   ============================================================ */

.conf-dots {
  display: inline-flex;
  gap: 4px;
}

.conf-dots span {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
}

.conf-dots span.on { background: var(--ai); }

/* Banded confidence — dots + word + number (Phase B4) */
.confidence {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.confidence__band {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--fg-muted);
}

.confidence__band--low   { color: var(--fg-faint); }
.confidence__band--mod   { color: var(--warn); }
.confidence__band--high  { color: var(--ai); }
.confidence__band--vhigh { color: var(--pos); }

.confidence__score {
  color: var(--fg-muted);
  font-size: 12px;
}

.memo {
  padding: 18px 20px;
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  background: linear-gradient(180deg, rgba(94, 227, 255, 0.04), transparent 60%), var(--raised);
  color: var(--fg);
  line-height: 1.6;
  font-size: 13.5px;
}

.memo small {
  display: block;
  margin-top: 12px;
  color: var(--fg-faint);
  font-size: 12px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

/* ============================================================
   Operator buttons (kill switch / pause / reconcile / report)
   ============================================================ */

.btn-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px;
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 38px;
  padding: 0 14px;
  border-radius: var(--r-sm);
  border: 1px solid var(--line-strong);
  background: var(--overlay);
  color: var(--fg);
  font-size: 13px;
  font-weight: 500;
  letter-spacing: 0.01em;
  transition: border-color 80ms linear, background-color 80ms linear, color 80ms linear;
}

.btn:hover:not(:disabled) {
  border-color: rgba(94, 227, 255, 0.45);
  background: rgba(94, 227, 255, 0.06);
}

.btn:focus-visible {
  outline: 2px solid var(--ai);
  outline-offset: 2px;
}

.btn:disabled {
  color: var(--fg-faint);
  border-color: var(--line);
  background: var(--raised);
  cursor: not-allowed;
}

.btn--danger:not(:disabled) {
  color: var(--neg);
  border-color: rgba(255, 77, 94, 0.32);
  background: var(--neg-soft);
}

.btn--danger:hover:not(:disabled) {
  border-color: rgba(255, 77, 94, 0.6);
  background: rgba(255, 77, 94, 0.16);
}

/* ============================================================
   Misc / empties / footer
   ============================================================ */

.empty {
  color: var(--fg-faint);
  font-size: 13px;
  padding: 10px 0;
}

.microcopy {
  color: var(--fg-faint);
  font-size: 12px;
  line-height: 1.55;
}

.footer {
  margin-top: var(--s-9);
  padding-top: var(--s-5);
  border-top: 1px solid var(--line);
  color: var(--fg-faint);
  font-size: 12px;
}

/* Sentinel-class accents for highlighted figures */
.pos { color: var(--pos); }
.neg { color: var(--neg); }
.warn-c { color: var(--warn); }
.ai-c { color: var(--ai); }

/* ============================================================
   "What's this?" slide-over (Phase C2)
   Right-anchored drawer that lists every glossary term visible on
   the active screen. Opens via the topbar trigger; re-syncs on
   hashchange while open; Esc / backdrop / × all close.
   ============================================================ */

.whats-this-trigger {
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  padding: 5px 10px;
  border-radius: 999px;
  color: var(--fg-muted);
  border: 1px solid var(--line);
  background: var(--raised);
  transition: color 80ms linear, border-color 80ms linear,
              background-color 80ms linear;
}

.whats-this-trigger:hover,
.whats-this-trigger:focus-visible {
  color: var(--ai);
  border-color: rgba(94, 227, 255, 0.45);
  background: var(--ai-soft);
  outline: none;
}

.whats-this {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: block;
}

.whats-this[hidden] { display: none; }

.whats-this__backdrop {
  position: absolute;
  inset: 0;
  background: rgba(7, 9, 12, 0.55);
  backdrop-filter: blur(3px);
  -webkit-backdrop-filter: blur(3px);
  opacity: 0;
  transition: opacity 200ms ease;
}

.whats-this[data-state="open"] .whats-this__backdrop {
  opacity: 1;
}

.whats-this__panel {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: min(420px, calc(100vw - 32px));
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  background: var(--overlay);
  border-left: 1px solid rgba(94, 227, 255, 0.32);
  box-shadow: -24px 0 60px rgba(0, 0, 0, 0.6);
  transform: translateX(100%);
  transition: transform 200ms ease;
}

.whats-this[data-state="open"] .whats-this__panel {
  transform: translateX(0);
}

.whats-this__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 22px 24px 16px;
  border-bottom: 1px solid var(--line);
}

.whats-this__eyebrow {
  display: block;
  font-family: var(--font-mono);
  font-size: var(--t-label);
  text-transform: uppercase;
  letter-spacing: 0.22em;
  color: var(--ai);
  margin-bottom: 6px;
}

.whats-this__title {
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 0.005em;
  color: var(--fg);
}

.whats-this__close {
  width: 28px;
  height: 28px;
  border-radius: 999px;
  color: var(--fg-faint);
  font-size: 18px;
  line-height: 1;
  display: grid;
  place-items: center;
  border: 1px solid transparent;
  transition: color 80ms linear, border-color 80ms linear,
              background-color 80ms linear;
}

.whats-this__close:hover,
.whats-this__close:focus-visible {
  color: var(--ai);
  border-color: rgba(94, 227, 255, 0.45);
  background: var(--ai-soft);
  outline: none;
}

.whats-this__body {
  overflow-y: auto;
  padding: 4px 24px 20px;
  display: grid;
  gap: 0;
}

.whats-this__entry {
  padding: 16px 0;
  border-top: 1px solid var(--line);
  display: grid;
  gap: 6px;
}

.whats-this__entry:first-child {
  border-top: 0;
}

.whats-this__entry strong {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--ai);
}

.whats-this__entry p {
  font-size: 13px;
  line-height: 1.55;
  color: var(--fg);
}

.whats-this__foot {
  padding: 14px 24px 20px;
  border-top: 1px solid var(--line);
  background: var(--raised);
}

.whats-this__foot .microcopy {
  color: var(--fg-faint);
}

@media (max-width: 620px) {
  .whats-this__panel {
    width: calc(100vw - 24px);
  }
}

/* ============================================================
   Responsive
   ============================================================ */

@media (max-width: 1180px) {
  .stat-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .grid-4 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 940px) {
  .app { grid-template-columns: var(--rail-w-collapsed) minmax(0, 1fr); }
  .rail__brand-text,
  .nav-item span:last-child,
  .rail__foot { display: none; }
  .nav-item { justify-content: center; padding: 10px; }
  .topbar { padding: 0 var(--s-5); }
  .viewport { padding: var(--s-5) var(--s-4) var(--s-8); }
  .grid-2, .grid-3, .grid-2-1, .grid-1-2 { grid-template-columns: minmax(0, 1fr); }
  .k-split { grid-template-columns: minmax(0, 1fr); gap: 14px 0; }
}

@media (max-width: 620px) {
  .app { grid-template-columns: minmax(0, 1fr); }
  .rail { display: none; }
  .stat-row { grid-template-columns: minmax(0, 1fr); }
  .hero__value { font-size: 44px; }
  .row { grid-template-columns: minmax(0, 1fr); gap: 4px; }
  .row__value { justify-self: start; }
}
"""
