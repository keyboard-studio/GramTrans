# Tasks: Phase 1 — Overwrite by Match

**Branch**: `002-phase1-overwrite` | **Date**: 2026-06-20

## Status: SHIPPED & LIVE-VERIFIED — no granular task list

This feature never received a `/speckit-tasks` breakdown, but its capability
(**FR-101..110 — overwrite-by-match** for Entry / Sense / MSA / Allomorph /
PhEnvironment) **shipped and was live-verified** during the Phase-1 session. Per
[STATUS.md](../../STATUS.md) ("Phase 1 ship state") the following commits landed and
were MCP-verified against Ejagham Mini → Ejagham Full GT-Test:

- `e6cde61` — Phase 1.1 Entry + Sense overwrite via direct GUID
- `e129b72` — Phase 1.2 MSA + Allomorph overwrite via fingerprint matching
- `e5f322c` — Phase 1.3a PhEnvironment overwrite via `enable_overwrite`
- `1097df5` — Phase 1.3b FR-106 pre-overwrite snapshot in residue tag
- `aecd565`, `50f873d` — Phase 1.3c residue carrier-write fix
- `f4cdd9c` — Phase 1.4 FR-107 custom-field deduplication

No retroactive per-task history is invented here; the commit trail above plus
STATUS.md are the authoritative record.

**Partly superseded by [feature 022 — Disposition Model](../022-disposition-model/).**
022 (constitution v6.0.0) redefined the conflict-mode vocabulary around the overwrite
path (`ConflictMode.MERGE` → `LINK`; new non-destructive `UPDATE`; computed per-item
disposition), so the *intent surface* wrapping FR-101..110 evolved. The underlying
OVERWRITE write path introduced here remains live; consult 022 for the current
LINK/UPDATE/OVERWRITE semantics.
