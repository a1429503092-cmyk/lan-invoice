---
target: src/invoice_tool.py
total_score: 26
p0_count: 0
p1_count: 2
timestamp: 2026-06-03T01-53-38Z
slug: src-invoice-tool-py
---
## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Progress bar, status bar, filter hints. No silent operations |
| 2 | Match System / Real World | 3 | Accurate financial terminology, verb+object button labels |
| 3 | User Control and Freedom | 3 | Filter reset, delete double-confirmation, dialogs cancelable. No undo |
| 4 | Consistency and Standards | 2 | Theme tokens defined but ~40% of styles use hardcoded color values |
| 5 | Error Prevention | 3 | Delete has dual confirmation. Low form-input surface reduces need |
| 6 | Recognition Rather Than Recall | 3 | All buttons icon+text. Filters visible. Right-click menu complete |
| 7 | Flexibility and Efficiency | 3 | Drag-drop, Ctrl+V, context menu. No keyboard shortcuts for power users |
| 8 | Aesthetic and Minimalist Design | 2 | Clean overall but filter bar 11 elements in one row, inline style fragmentation |
| 9 | Error Recovery | 2 | Parse failures shown in remark column. No "undo delete" mechanism |
| 10 | Help and Documentation | 2 | Status bar tips, button tooltips. No searchable help or first-run guidance |
| **Total** | | **26/40** | **Acceptable** |

## Anti-Patterns Verdict

**LLM assessment**: PyQt5 desktop app, does not fall into AI-generated web UI traps. No cream backgrounds, gradient text, glassmorphism, decorative shadows. The risk is not "AI slop" but "DIY inconsistency" — a design token system exists (ui/theme.py) but execution is incomplete. ~40% of styles use hardcoded color values, creating subtle cross-component color mismatches.

**Deterministic scan**: detector returned empty array on Python sources — expected, as detect.mjs targets HTML/CSS/JSX markup.

## Overall Impression

A solid, functional desktop tool. The visual architecture is correct at the top level: centralized tokens, cold palette, single-font hierarchy, flat layering. The single biggest issue is incomplete token execution — ui/theme.py defines 15 color constants, but ~30 hardcoded color values (#333, #555, #aaa, #CC0000, #1E6FBF, etc.) exist throughout the codebase with subtle deviations from DESIGN.md.

## What's Working

1. Data table design is excellent: blue header + white bold text + alternating rows + selected blue bg + hover gray bg. Four visual states fully covered. Stretch column algorithm (largest remainder method) is thoughtful.
2. Operation safety net: three-layer delete protection (select row → right-click → checkbox confirmation dialog). High-cost errors have appropriate friction.
3. Multi-path interaction: same operation via button click, drag-drop, Ctrl+V paste, or right-click menu. Correct design for efficiency-oriented users.

## Priority Issues

**[P1] Incomplete color token execution.** ~40% of styles use hardcoded values with deviations from DESIGN.md:
- #333 → should be #1A2130 (TEXT)
- #555 → should be #5C6778 (TEXT_SEC)
- #888/#aaa → should be #8F99A8 (TEXT_DIM)
- #CC0000 → should be #DC2626 (RED)
- #1E6FBF → should be #2879D0 (ACCENT)
- #2E8B57 → should be #16A34A (GREEN)

**[P1] Filter bar cognitive overload.** 11 visible elements (4 dropdowns + 2 inputs + 2 buttons + labels) in one row. Fails cognitive load checklist on "minimal choices" and "one thing at a time".

**[P2] Settings dialog bypasses tokens entirely.** settings.py uses 100% hardcoded values, no references to ui/theme.py color constants.

**[P2] Image viewer button colors deviate from theme.** Uses #1E6FBF and #2E8B57 instead of ACCENT #2879D0 and GREEN #16A34A.

**[P3] No keyboard shortcut system.** Delete, Ctrl+F (focus filter), Ctrl+E (export) are natural mappings that don't exist.

## Persona Red Flags

**Alex (Power User)**: No keyboard shortcuts for core operations. Import-then-apply-company is a two-step process with no batch preset. 11-element filter bar makes rapid targeting hard.
**Jordan (First-Timer)**: No first-run guidance. Filter bar has no priority distinction. "Apply to selected rows" semantics assume table selection understanding.
**Riley (Stress Tester)**: Empty state shows blank table with no guidance. Error messages in remark column are developer-facing technical strings.

## Minor Observations

- Table header font size (13px) equals body (13px) — compensated by blue bg + white + bold
- Contract manager selected color #BDD7EE differs from table selected #E3EDF7 — "selected" should be one blue
- Version mismatch: settings shows "v5.1" but main window title says "v4.0"
- Summary stat values at 17px bold accent color is a good design choice
- Export button is the only accent-solid-bg button — good visual hierarchy marking "recommended action"

## Questions to Consider

- Could high-frequency filters (year/month) stay visible while low-frequency ones collapse into "advanced filters"?
- At 500+ invoices, does table performance hold?
- Could the empty table state become a drag-drop guide area instead of blank?
- Could export also benefit from a confirmation step showing row count / amount summary?
