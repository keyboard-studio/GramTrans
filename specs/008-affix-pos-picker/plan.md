# Implementation Plan: Affixes-by-POS Item Picker

**Branch**: `feature/007-selection-ui` | **Date**: 2026-07-01 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/008-affix-pos-picker/spec.md`

## Summary

Fix the empty affix picker on wizard page 2 by building the missing source-inventory
feed and reorganizing the tree to group affixes by the part of speech they attach to
(inflectional + unclassified via `PartOfSpeechRA`; derivational via
`FromPartOfSpeechRA`/`ToPartOfSpeechRA`). A new pure-Python builder
`build_pos_grouped_inventory(source)` produces a `PosGroupedAffixInventory`; the wizard
renders it as a nested POS hierarchy with per-POS subgroups and per-`(entry, group)`
rows, mirrors selection state across an affix's multiple appearances, and collapses the
checked leaves into `Selection.affix_picks` — with no change to the dependency-closure
engine. Validated live against Ejagham (inflectional-only) and Esperanto
(derivational/unclassified/multi-POS) via the FlexTools MCP.

## Technical Context

**Language/Version**: Python 3 (FlexTools host runtime)

**Primary Dependencies**: PyQt6 (wizard UI); MattGyverLee/flexicon fork (runtime LCM
access, imported directly per Constitution II); SIL.LCModel interfaces via pythonnet.

**Storage**: N/A (reads live FLEx projects; writes only at Move, unchanged by this feature)

**Testing**: pytest with duck-typed fake handles (unit); FlexTools MCP live runs against
Ejagham Full GT-Test and Esperanto (integration).

**Target Platform**: Windows FlexTools desktop host.

**Project Type**: Desktop-app module (FLExTrans-style flat entry + `Lib/` helpers).

**Performance Goals**: Interactive; builder runs once on page-2 entry over the source
lexicon (Esperanto: 15,318 entries scanned, 68 affixes — sub-second acceptable).

**Constraints**: No optional runtime deps beyond flexicon fork + PyQt; builder must be
pure-Python-testable without a live LCM (duck-typed fakes); polymorphic property access
requires pythonnet casts (guarded).

**Scale/Scope**: Two files touched in `src/gramtrans/Lib/` (selection.py model+builder,
ui/selection_wizard.py page 2); one legacy file assessed (ui/affix_tree_picker.py).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. FLEx Domain Fidelity** — PASS. Read-only enumeration; GUIDs are the selection
  identity (dedup/mirror by entry GUID). No GOLD/WS/reference mutation. Attachment
  semantics read the correct MSA fields per FLEx model (validated live). Note: the
  derivational *closure* completeness gap is tracked separately (issue #1) and does not
  regress here — this feature only reads From/To for grouping, it does not change what
  closure pulls.
- **II. FlexTools-Compatible Output, flexicon-Direct** — PASS. Builder imports
  flexicon/SIL.LCModel directly; no adapter layer; casts via the documented pattern.
- **III. Preview-Before-Mutate** — PASS. The picker builds a `Selection` only; nothing
  here writes. The single write remains at Move (page 5), untouched.
- **IV. Phased Merge Discipline** — PASS. This is Phase-3c selection-UI work on the
  existing wizard; it does not implement a later merge phase early.
- **V. Referential Completeness** — PASS (respected, not modified). Closure is computed
  downstream from `affix_picks`; this feature changes only *how affixes are picked*, not
  the closure engine. Per-item deselection remains available.

No violations. Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/008-affix-pos-picker/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── pos-grouped-inventory.md   # builder + model + collapse contract
├── checklists/
│   └── requirements.md  # from /speckit-specify
└── tasks.md             # /speckit-tasks output (not created here)
```

### Source Code (repository root)

```text
src/gramtrans/Lib/
├── selection.py                 # ADD PosGroupedAffixInventory + AffixRow + PosNode
│                                #     + build_pos_grouped_inventory(source)
│                                #     + collapse_pos_grouped(...) helper
│                                # KEEP SourceAffixInventory + existing helpers intact
├── ui/
│   ├── selection_wizard.py      # REWORK _PageItemPicker: POS-hierarchy tree,
│   │                            #     subgroups, 4 columns, initializePage wiring,
│   │                            #     GUID-mirroring itemChanged handler, collapse
│   └── affix_tree_picker.py     # ASSESS: mark legacy/unused OR align (see research)
└── models.py                    # (unchanged; Selection/PickerState reused as-is)

tests/
├── unit/
│   ├── test_pos_grouped_inventory.py   # NEW: builder grouping/dedup/junk/multi-POS/deriv
│   └── test_affix_pos_collapse.py      # NEW: collapse + mirroring pure helpers
└── integration/
    └── test_affix_pos_picker_live.py   # NEW: MCP live counts (Ejagham + Esperanto)
```

**Structure Decision**: Follows the FLExTrans-style flat `Lib/` layout mandated by
Constitution II. The builder and its pure helpers live in `selection.py` beside the
existing selection machinery so they share the fake-handle test pattern; UI changes are
confined to the page-2 class in `selection_wizard.py`.

## Complexity Tracking

No constitution violations; section intentionally empty.
