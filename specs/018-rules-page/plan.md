# Implementation Plan: Rules Page — Ad Hoc & Compound Rules (Model-B Block + Engine)

**Branch**: `018-rules-page` | **Date**: 2026-07-05 | **Spec**: [spec.md](./spec.md)

## Summary

Deliver BOTH halves of roadmap build-sequence step 3: (a) the **transfer engine**
for the `ADHOC_COMPOUND_RULES` category — the five `adhoc_compound_rules_*`
callbacks in [Lib/categories.py](../../src/gramtrans/Lib/categories.py) that today
`raise NotImplementedError("Phase 3c T056-T060")` — and (b) the **Model-B wizard
page** that surfaces the two rule inventories (Ad Hoc Rules, Compound Rules),
all-preselected, with whole-block toggle, per-item trim, and NEW/IN TARGET/SIMILAR
status, consistent with 010 (Phonology) and 021 (Lexical-entry types).

The engine reuses the **`phonological_rules` pattern** already in `categories.py`:
`_phonology_simple_enumerate` (GetAll + per-item pick filter), `_phonology_simple_plan`
(GUID-first Skip/Add), `_create_with_guid` (factory `Create(Guid)` + owner `Add`),
`ApplySyncableProperties` for scalar/text props, then **manual reference wiring by
GUID** — exactly as `phonological_rules_execute_action` hand-wires `StratumRA`. The
key departure from the simple phonology categories is **per-concrete-subclass
dispatch** (FR-341): five LCM subclasses, each with distinct factory + reference
fields, plus recursion into `IMoAdhocProhibGr.MembersOC` grouping nodes.

All LCM facts in this plan are grounded in
[probe-results.md](./probe-results.md) (FLExTools MCP probes, 2026-07-05) — **not
guessed**. That probe also flags that the flexicon `AdhocProhibition` wrapper's
docstrings name non-existent properties; the engine uses the concrete LCM
interfaces directly (constitution II sanctions direct LCM/flexicon imports).

## Technical Context

**Language/Version**: Python 3 (FlexTools host). **Primary deps**: PyQt6, flexicon
(pyflexicon>=4.1), SIL.LCModel via pythonnet. **Testing**: pytest (fake handles) +
live FLExTools MCP against Ejagham Mini → Ejagham Full GT-Test. **Project type**:
FLExTrans-style flat `Lib/`. **Constraints**: the wizard page is a pure builder
(fake-handle testable); the engine touches LCM only through the established
cast/`getattr` guards and `_create_with_guid`; enumerate-filter is guarded so an
absent pick-subset preserves transfer-all. **Scale/Scope**: rule inventories are
tiny (single-digit to low-double-digit objects); the builder walks two `GetAll()`
collections once, recursing into grouping nodes.

**Pre-wired plumbing** (no work needed): `GrammarCategory.ADHOC_COMPOUND_RULES`
exists ([models.py:35](../../src/gramtrans/Lib/models.py)) and is already registered
in the leaf-category dispatch ([categories.py:2614](../../src/gramtrans/Lib/categories.py)),
`preview.py`, `transfer.py`, `main_window.py`, and `selection_wizard.py`. Only the
five callbacks and the UI page/builder are missing.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

- **I. FLEx Domain Fidelity** — PASS. GUID-first identity (`_create_with_guid`
  pins the source GUID; `_phonology_simple_plan` skips ALREADY_PRESENT_BY_GUID).
  Correct LCM anchors: adhoc → `MorphologicalDataOA.AdhocCoProhibitionsOS` (children
  in `IMoAdhocProhibGr.MembersOC`); compound → `MorphologicalDataOA.CompoundRulesOS`.
  Reference wiring resolves allomorphs/morphemes (adhoc) and member/result POS via
  owned MSAs (compound) to target objects by GUID, or the item fails loudly
  (FR-006, unhandled subclass = loud error; missing reference = warning, never
  silent drop).
- **II. flexicon-Direct** — PASS. Direct `from SIL.LCModel import IMo…Factory` and
  `project.MorphRules.*` calls; no adapter. The flexicon `AdhocProhibition` wrapper
  is NOT trusted for member access (its docstrings are wrong — see probe-results);
  concrete LCM interfaces are used instead.
- **III. Preview-Before-Mutate** — PASS. The page builds a `Selection` only; the sole
  write stays at Move (`transfer.py` execute path). `plan_action` is read-only
  planning; `execute_action` runs only in Move mode.
- **IV. Phased Merge Discipline** — PASS. No conflict-mode UI (FR-016); per-category
  Layer-1 default applied automatically. This is additive/overwrite-by-GUID only.
- **V. Referential Completeness** — PASS (central). Whole block preselected
  (closure-by-default); `adhoc_compound_rules_dependencies` yields member refs so
  closure pulls them when a rule is kept; per-item trim allowed; a kept rule whose
  member ref is deselected AND target-absent raises one aggregated missing-reference
  warning into the shared Move gate (FR-014/FR-015) — never silent.

No violations. Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/018-rules-page/
├── spec.md              # feature spec (input)
├── probe-results.md     # FLExTools MCP ground-truth API (authoritative)
├── plan.md              # this file
├── research.md          # Phase 0 — R1..R7 (subclass dispatch, wiring, grouping, warnings)
├── data-model.md        # Phase 1 — rule inventory dataclasses + reuse of leaf_item_picks
├── contracts/
│   └── rules-page.md     # Phase 1 — page↔engine selection contract + callback contracts
├── quickstart.md        # Phase 1 — live validation scenarios (Ejagham)
└── tasks.md             # Phase 2 — /speckit-tasks (NOT created here)
```

### Source Code (repository root)

```text
src/gramtrans/Lib/
├── categories.py                # IMPLEMENT the 5 adhoc_compound_rules_* callbacks:
│                                #   enumerate_source  -> _phonology_simple_enumerate("MorphRules"?) —
│                                #     actually a dedicated walker over AdhocCoProhibitionsOS (recurse
│                                #     MembersOC) + CompoundRulesOS, filtered by leaf_item_picks
│                                #   dependencies      -> per-subclass ref GUIDs (allos/morphs; member+result POS)
│                                #   required_writing_systems -> () (rules carry Name/Desc; ws via ApplySyncable)
│                                #   plan_action        -> _phonology_simple_plan (GUID-first skip/add)
│                                #   execute_action     -> per-subclass factory create + ApplySyncableProperties
│                                #                         + manual reference wiring + apply_carrier_b
├── selection.py                 # ADD build_rules_inventory(source, target=None) -> RulesInventory
│                                #   + rule dataclasses; REUSE target-status + missing-ref warning shape
├── preview.py                   # missing-reference: kept rule with deselected+absent member ->
│                                #   aggregated entry-centric warning into shared Move gate
└── ui/selection_wizard.py       # ADD _PageRules before _page_finish; register in addPage sequence;
                                 #   named accessor page_rules(); merge picks into _PagePreview selection;
                                 #   feed missing-ref warnings into _PageFinish Move gate

tests/
├── unit/
│   ├── test_rules_inventory.py          # derivation: 2 categories, counts, preselect-all, target status,
│   │                                    #   empty category, grouping-node structure represented
│   ├── test_rules_leaf_item_picks.py    # enumerate filter: subset present => subset; absent => all;
│   │                                    #   GUID normalized both sides (_guid_str_from); grouping recursion
│   ├── test_rules_plan_dispatch.py      # plan_action GUID-first skip/add; idempotency on re-plan
│   ├── test_rules_missing_ref.py        # kept rule + deselected/absent member -> one aggregated warning;
│   │                                    #   no warning when ref resolves; unknown subclass -> loud error
│   └── test_wizard_page_order.py        # EXTEND: page_rules() returns _PageRules in post-insertion order
└── integration/
    └── test_rules_live.py               # MCP: Ejagham source->fresh target; all 5 subclasses created,
                                         #   GUID-preserved, refs wired; re-run idempotent (SC-001/002)
```

**Structure Decision**: Implement the engine callbacks inline in `categories.py`
beside the phonology engines (they share `_create_with_guid`, `_guid_str_from`,
`_phonology_simple_plan`, `apply_carrier_b`). Add one builder in `selection.py`
beside the 010/021 builders (shared target-status + warning helpers) and one wizard
page. No new module files — matches the FLExTrans flat-`Lib/` convention and the
010/021 precedent.

### Page placement (FR-007)

Spec asks for Rules "after Lexical-entry types (021), before Preview". 021 and 019
are not yet in the wizard (out of scope here). The current live sequence ends
ProjectWS → CustomFields → Phonology → Items → Skeleton → GramDeps → **Finish**
([selection_wizard.py:3309-3315](../../src/gramtrans/Lib/ui/selection_wizard.py)).
Insert `_PageRules` immediately **before** `_page_finish` (the last slot). When
021/019 land they insert ahead of Rules; closure is computed at Preview so ordering
does not affect correctness (spec Assumptions). Use the P-1 named-accessor pattern —
no literal page indices.

## Complexity Tracking

*No constitution violations. No deviations requiring justification.*
