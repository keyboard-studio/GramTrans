# Implementation Plan: Skeleton + Grammatical-Deps Selectors

**Branch**: `feature/007-selection-ui` | **Date**: 2026-07-01 | **Spec**: [spec.md](./spec.md)

## Summary

Two new Model-A wizard pages after the affix picker, plus preselect-all in the picker.
A pure builder derives the **skeleton** (POS → Slots → Templates) from the affix picks and
a pure builder derives the **grammatical deps** (inflection features/classes/stem-names/
exception-features) from the picked affixes' POSes; both preselect at AS-NEEDED, reuse the
008 target-status logic, and feed the existing plan/closure engine. Deselecting a needed,
target-absent item raises an aggregated EXCLUDED-LOSSY warning gated once at Move. Conflict
UI deferred (Layer-1 defaults). Validated live on Ejagham + Esperanto.

## Technical Context

**Language/Version**: Python 3 (FlexTools host). **Primary deps**: PyQt6, MattGyverLee/
flexicon fork, SIL.LCModel via pythonnet. **Testing**: pytest (fake handles) + live
FlexTools MCP. **Project type**: FLExTrans-style flat `Lib/`. **Constraints**: pure
builders (fake-handle testable); all LCM access via the existing `_cast` helper (pythonnet
resolves against declared base interface). **Scale**: builders reuse the 008 enumeration;
skeleton/deps are tiny in practice (Ejagham ≤4 slots, 1 template/POS).

## Constitution Check

- **I. FLEx Domain Fidelity** — PASS. Read-only derivation; GUID identity; correct LCM
  anchors (AffixSlotsOC, AffixTemplatesOS, IMoInflAffMsa.SlotsRC, InflectableFeatsRC,
  InflectionClassesOC, StemNamesOC, ExceptionFeaturesOC). Casts guarded.
- **II. flexicon-Direct** — PASS. Direct imports; `_cast` pattern; no adapter.
- **III. Preview-Before-Mutate** — PASS. Pages build a Selection only; single write at Move.
- **IV. Phased Merge Discipline** — PASS. Conflict UI deferred; no later-phase merge here.
- **V. Referential Completeness** — PASS (central). Closure derived + preselected; per-item
  deselect; deliberate omissions reported (EXCLUDED-LOSSY), aggregated at Move; not silent.

No violations.

## Project Structure

```text
src/gramtrans/Lib/
├── selection.py                 # ADD build_skeleton_inventory(source, affix_picks, target=None)
│                                #     + build_deps_inventory(source, affix_picks, target=None)
│                                #     + skeleton/deps dataclasses + collapse helpers.
│                                #     REUSE _cast, AffixRow.status logic, POS enumeration.
│   ui/selection_wizard.py       # ADD _PageSkeleton, _PageGramDeps; wire sequence
│                                #     (Affixes -> Skeleton -> Deps -> Preview); remove old
│                                #     _PageScopeConflict from the flow; preselect-all affixes.
├── preview.py                   # EXCLUDED-LOSSY: skeleton/dep deselection -> grouped warning.
└── models.py                    # extend Selection with skeleton/deps picks if needed.

tests/
├── unit/
│   ├── test_skeleton_inventory.py     # derivation, slot counts, template-forces-slots, preselect
│   ├── test_deps_inventory.py         # deps derivation, empty sections, target status
│   └── test_excluded_lossy_grouping.py# aggregation: N omissions -> one gated summary
└── integration/
    └── test_skeleton_deps_live.py     # MCP: Ejagham (v/4slots/1tmpl, n,num/1) + Esperanto
```

**Structure Decision**: Extend `selection.py` (beside the 008 POS-grouped builder — shared
`_cast`, status, POS-walk) and add two wizard pages. Keep changes additive; the 008 picker
gains only the preselect-all default.

## Complexity Tracking

No violations; section empty.
