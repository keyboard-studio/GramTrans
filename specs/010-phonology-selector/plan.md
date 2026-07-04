# Implementation Plan: Phonology Selector (Model-B Independent Block)

**Branch**: `feature/007-selection-ui` | **Date**: 2026-07-02 | **Spec**: [spec.md](./spec.md)

## Summary

Add the **Phonology** wizard page — the first Model-B (independent-block) selector — at
position 2 (Project+WS → **Phonology** → Affixes → Skeleton → Grammatical deps → Preview →
Finish). A pure builder enumerates the five user-facing phonology categories (features,
phonemes, natural classes, environments, rules) from the source, all preselected (ALL by
default), each with 008/009 target-status. The user toggles the whole block off or trims
individual items. Strata travel automatically iff a phonological **rule** is kept. Deselecting
an item a kept item needs (and the target lacks) raises an aggregated EXCLUDED-LOSSY warning
into the existing single Move gate.

Delivering per-item trim (FR-005/US2, P1) requires **one contained engine touch**: the
spec-005 leaf-dispatch transfers whole categories, so a new `Selection.leaf_item_picks`
subset field is added and the six phonology `enumerate_source` helpers filter by it
(absent key ⇒ transfer all — every existing caller unchanged). Category on/off and
strata-gating are pure wiring. Validated live on Ejagham Mini → Ejagham Full GT-Test.

## Technical Context

**Language/Version**: Python 3 (FlexTools host). **Primary deps**: PyQt6, MattGyverLee/
flexicon fork, SIL.LCModel via pythonnet. **Testing**: pytest (fake handles) + live
FlexTools MCP. **Project type**: FLExTrans-style flat `Lib/`. **Constraints**: pure builder
(fake-handle testable); LCM access via the existing cast/`getattr` guards; the engine
enumerate-filter is guarded so absent-subset preserves all-items behavior. **Scale/Scope**:
Ejagham Mini phonology = 32 phonemes, 5 natural classes, 2+ environments, phon features + a
handful of rules — tiny; the builder walks five `GetAll()` collections once.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

- **I. FLEx Domain Fidelity** — PASS. Read-only derivation; GUID identity; correct LCM anchors
  (`PhFeatureSystemOA`, `PhonemeSetsOS`, `NaturalClassesOS`, `EnvironmentsOS`, `PhonRulesOS`;
  strata `MorphologicalDataOA.StrataOS` via rule `StratumRA`). Reference chain corrected in
  cycle-1 domain review (rules→NC/phoneme; environments are allomorph-side, excluded).
- **II. flexicon-Direct** — PASS. Direct imports; no adapter; enumerate helpers already call
  `project.<Ops>.GetAll()`.
- **III. Preview-Before-Mutate** — PASS. The page builds a `Selection` only; the sole write
  stays in the page-Finish Move handler. The engine enumerate-filter is read-only planning.
- **IV. Phased Merge Discipline** — PASS. No conflict-mode UI; Layer-1 defaults applied
  automatically (FR-012).
- **V. Referential Completeness** — PASS (central). Whole block preselected (closure-by-
  default); per-item trim allowed; deselecting a needed, target-absent item raises an
  aggregated EXCLUDED-LOSSY warning gated once at Move — never silent.

**One deviation from the spec's original framing** (tracked in Complexity Tracking): the spec
first assumed zero engine change; the shipped engine transfers whole leaf categories, so
per-item trim needs a contained `Selection` + enumerate-filter extension. The spec (Context,
FR-008, Assumptions) has been corrected to acknowledge this. No new categories; no behavior
change for existing callers.

## Project Structure

### Documentation (this feature)

```text
specs/010-phonology-selector/
├── plan.md              # this file
├── research.md          # Phase 0 — R1..R7 (engine granularity, chain, strata, index coupling)
├── data-model.md        # Phase 1 — phonology inventory dataclasses + Selection.leaf_item_picks
├── contracts/
│   └── phonology-page.md # Phase 1 — page↔engine selection contract + builder signature
├── quickstart.md        # Phase 1 — live validation scenarios (Ejagham)
└── tasks.md             # Phase 2 — /speckit-tasks (NOT created here)
```

### Source Code (repository root)

```text
src/gramtrans/Lib/
├── models.py                    # ADD Selection.leaf_item_picks: dict[GrammarCategory, frozenset[str]]
│                                #   (absent key ⇒ transfer all; __post_init__ validation optional)
├── categories.py                # EXTEND _phonology_simple_enumerate (+ strata enumerate) to
│                                #   filter GetAll() by selection.leaf_item_picks.get(cat) when present
├── selection.py                 # ADD build_phonology_inventory(source, target=None) → PhonologyInventory
│                                #   + phonology dataclasses + collapse/into-Selection helper;
│                                #   REUSE target-status logic + build_excluded_lossy_warnings shape
├── preview.py                   # EXCLUDED-LOSSY: phonology intra-block deselection → grouped warning
│                                #   (rules→NC/phoneme, NC→phoneme, phoneme→feature)
└── ui/selection_wizard.py       # ADD _PagePhonology at index 1; wire sequence;
                                 #   REPLACE hardcoded wizard.page(N) lookups with named accessors;
                                 #   merge phonology picks into _PagePreview selection build;
                                 #   feed phonology EXCLUDED-LOSSY into _PageFinish Move gate

tests/
├── unit/
│   ├── test_phonology_inventory.py       # derivation, 5 categories, counts, preselect-all, target status, empty category
│   ├── test_leaf_item_picks.py           # enumerate filter: subset present ⇒ subset; absent ⇒ all; GUID normalized both sides (_guid_str_from); stale key for off category is inert (P2/A-1)
│   ├── test_strata_gating.py             # strata iff ≥1 rule kept; none when rules off / block off
│   ├── test_phonology_excluded_lossy.py  # per-rule attribution: rules→NC/phoneme + NC→phoneme stranding → one entry-centric warning each; aggregated
│   └── test_wizard_page_order.py         # P-2: each named accessor returns the expected page TYPE in post-insertion order
└── integration/
    └── test_phonology_live.py            # MCP: Ejagham Mini→Full GT-Test (32 phonemes, 5 NCs, 2 envs); whole-block, trim, strata
```

**Structure Decision**: Extend `selection.py` beside the 008/009 builders (shared status +
EXCLUDED-LOSSY helpers) and add one wizard page. The engine touch is confined to one enumerate
helper in `categories.py` + one `Selection` field in `models.py`; everything else is additive
UI. The `wizard.page(N)` → named-accessor refactor is a prerequisite so page insertion is safe.

### Ordered prerequisites (cycle-2 QC — must land BEFORE the Phonology page is inserted)

- **P-1 — Named-accessor refactor.** Replace every literal `wizard.page(N)` / `w.page(N)` with
  a named accessor backed by the existing stored attributes (`self._page_items`,
  `_page_skeleton`, `_page_gram_deps`, `_page_preview`, `_page_finish`, and new
  `_page_phonology`). Call sites to convert (current line numbers):
  `selection_wizard.py` 1363, 1575, 1689, 1711, 1780, 1787, 1798. Inserting Phonology at index
  1 shifts items 1→2 / skeleton 2→3 / gramdeps 3→4 / preview 4→5 / finish 5→6, so every literal
  index would silently resolve to the wrong page (no crash — a functional break).
- **P-2 — Wizard-order regression test** (`tests/unit/test_wizard_page_order.py`, NEW): assert
  each named accessor returns the expected page *type* in post-insertion order
  (`isinstance(wizard.page_items(), _PageItemPicker)`, … for all 6 pages). The four planned
  engine/builder unit tests do NOT cover ordering; a mis-index passes all four and still breaks
  the live wizard. P-2 is additive, not a substitute.

### GUID normalization (cycle-2 QC, P0)

The item-pick trim filter and the builder MUST normalize GUIDs through the **same**
`_guid_str_from` helper (categories.py:94-104; lowercase, braces stripped) on both sides —
raw `str(it.Guid)` is uppercase-with-braces and would make every trim lookup miss. See
data-model.md "GUID-normalization invariant".

### Known limitation

- **KL-010-1** — the EXCLUDED-LOSSY reference traversal covers `PhRegularRule` only
  (`StrucDescOS` + `rhs.Left/RightContextOA`); it does NOT traverse `PhMetathesisRule`
  (`Left/RightPartOfMetathesisOS`) or `PhReduplicationRule` (`Left/RightPartOfReduplicationOS`)
  part-sequences. A kept metathesis/reduplication rule stranded against a deselected
  NC/phoneme raises no warning. Safe for the current Ejagham corpus (PhRegularRule only);
  the fix is a mechanical extension of the same traversal + metathesis/reduplication fixtures,
  deferred to a post-010 follow-up task.

## Complexity Tracking

| Deviation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|--------------------------------------|
| Engine touch: `Selection.leaf_item_picks` + phonology enumerate filter | Spec-005 leaf-dispatch transfers whole categories; per-item trim (FR-005/US2, P1) is impossible without it | Whole-block-only (no engine change) rejected by user — per-item trim is the defining Model-B affordance |
| `wizard.page(N)` → named-accessor refactor | Pages cross-reference by literal index; inserting Phonology at index 1 shifts Affixes/Skeleton/Deps/Preview and breaks every lookup | Bumping each literal index by one is brittle and silently breaks on the next insertion |
