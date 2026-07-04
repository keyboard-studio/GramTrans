# Implementation Plan: Similar-Resolution Transfer (Merge Write-Mode)

**Branch**: `013-similar-resolution-transfer` | **Date**: 2026-07-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/013-similar-resolution-transfer/spec.md`

## Summary

Feature 013 makes the transfer engine **honor** the per-item `SimilarResolution` that
feature 011 placed on `Selection`. When a user has resolved affix X into existing target
entry Y (with action `overwrite` or `merge`), the planner emits a `PlannedOverwrite` with
`match_via="identity_remap"` and target GUID Y; the executor creates X's children under Y
and applies X's entry-level fields using the appropriate write mode.

The two link actions differ only in how entry-level fields are written:

- **`overwrite`** — source wins on every field (existing source-wins path, no code change
  other than routing the new ENTRY action into the existing branch).
- **`merge`** — fill-the-gaps: per-WS alt is applied only if the target alt is empty
  (after strip); plain str only if target is None/empty; bool/int skipped entirely. This
  is a new write mode requiring a new `fill_gaps` kwarg on the flexlibs2 fork's
  `ApplySyncableProperties`.

Child creation (senses / MSAs / allomorphs, with fingerprint de-duplication) is identical
for both link actions and is factored into a single shared helper.

This is the third of five chunks: 011 data model -> 012 diff engine -> **013 transfer
threading** -> 014 preview pane -> 015 wizard flow. It is a headless, engine-only change:
no Qt, no wizard page, no diff rendering.

## Technical Context

**Language/Version**: Python 3, `requires-python >=3.8`. No 3.9+ syntax; use
`from __future__ import annotations` and `typing` generics.

**Primary Files**:

- `src/gramtrans/Lib/preview.py` — planner (build_run_plan, _plan_layer3_for_pos,
  _plan_layer3_verb_affixes_inner)
- `src/gramtrans/Lib/transfer.py` — executor (_execute_overwrite ENTRY branch,
  _execute_layer3, new _populate_entry_children helper)
- `src/gramtrans/Lib/models.py` — PlannedOverwrite (add write_mode field)
- `src/gramtrans/Lib/matcher.py` — fingerprint helpers (add fingerprint_with_owner)
- **[fork]** `flexlibs2/code/BaseOperations.py` and 8 Grammar/*Operations.py — add
  fill_gaps kwarg to ApplySyncableProperties

**Cross-repo boundary**: Tasks touching flexlibs2 require edits in the separate
`D:/Github/_Projects/_LEX/flexlibs2` repository and must be installed with
`pip install -e D:/Github/_Projects/_LEX/flexlibs2` before GramTrans tests run.

**Upstream dependency**: Feature 011 merged — `Selection.similar_resolutions` and
`similar_resolution_for` exist.

**Testing**: pytest (`tests/unit/`); headless (no Qt, no live LCM required for unit
tests). Integration verification runs against the Ejagham Mini -> Ejagham Full GT-Test
pair.

## Design Rulings (Decided — Do Not Re-Derive)

### R1 — Fill-Gaps Semantics (FR-007a)

Emptiness is **per-WS-alternative**, not whole-field:

- **multistring (dict[str,str] branch)**: for each WS alt, skip `set_String` if
  `(prop_obj.get_String(tgt_handle).Text or "").strip()` is non-empty (target wins).
  Note: `get_String(handle)` always returns an ITsString (never None) in LCM 9.x;
  `.Text` returns Python None on an empty ITsString, so the `or ""` coercion is
  required to prevent AttributeError. Accepted alternative: `.RunCount > 0`.
  S1 to confirm the exact call form in-runtime.
- **plain str attr**: apply source only if `getattr(item, prop_name, None)` is
  `None` or empty string after strip.
- **bool/int (setattr branch)**: do NOT apply in fill_gaps mode at all — stored
  `False` is a real choice, not an absence. Skip the `setattr` call entirely when
  `fill_gaps=True`.

Live-verify gate: **S1** (see Risks section).

### R2 — Mechanism (FR-007a)

Add `fill_gaps=False` as a kwarg to `ApplySyncableProperties` — NOT a sibling method.
Add `fill_gaps=False` to all 8 Grammar Operations subclass overrides and BaseOperations,
threading via `super().ApplySyncableProperties(..., fill_gaps=fill_gaps)`.

Files (all in the flexlibs2 fork):

| File | Location |
|------|----------|
| `BaseOperations.py` | `flexlibs2/code/BaseOperations.py:1028` |
| `POSOperations.py` | `flexlibs2/code/Grammar/POSOperations.py:1159` |
| `MorphRuleOperations.py` | `flexlibs2/code/Grammar/MorphRuleOperations.py:914` |
| `GramCatOperations.py` | `flexlibs2/code/Grammar/GramCatOperations.py:640` |
| `InflectionFeatureOperations.py` | `flexlibs2/code/Grammar/InflectionFeatureOperations.py:1693` |
| `NaturalClassOperations.py` | `flexlibs2/code/Grammar/NaturalClassOperations.py:1074` |
| `EnvironmentOperations.py` | `flexlibs2/code/Grammar/EnvironmentOperations.py:707` |
| `PhonologicalRuleOperations.py` | `flexlibs2/code/Grammar/PhonologicalRuleOperations.py:1448` |
| `PhonemeOperations.py` | `flexlibs2/code/Grammar/PhonemeOperations.py:1328` |

The GramTrans executor passes `fill_gaps=True` iff `overwrite.write_mode == "merge"`.

### R3 — Fingerprint Owner Override

Do NOT mutate `fingerprint_for_msa` / `fingerprint_for_allomorph` in place. Add a pure
helper in `matcher.py`:

```
fingerprint_with_owner(fn, obj, owner_guid_override, ws_handle=None) -> tuple
```

which calls `fn(obj, ws_handle)` and replaces tuple index 1 (the owner guid) with
`owner_guid_override`. The merge-into call site passes the **target** entry GUID as the
override so source and resolved-target fingerprints compare equal.

Live-verify gate: **S2** (see Risks section).

### R4 — Write-Mode Carrier

Add field `write_mode: str = "overwrite"` to the frozen `PlannedOverwrite` dataclass
(class at `models.py:553`; insert after `owner_guid` at line 572, the current last field).
Valid values: `"overwrite"` | `"merge"`. Plain str, no enum (keeps
the existing serialisation surface simple). The planner sets it from
`SimilarResolution.action`; the executor selects `fill_gaps=True` iff
`write_mode == "merge"`.

## Feature Requirements — File & Anchor Map

### FR-001 — Planner Resolution Hook

**File**: `preview.py`
**Hook location**: after line 587 (Phase-1 overwrite check for `entry_is_overwrite`)
inside `_plan_layer3_verb_affixes_inner` (line 466).

After confirming `not entry_is_overwrite`, read:
```
resolution = selection.similar_resolution_for(entry_guid)
```
Branch:

- `resolution` is `None` or `action == "create_new"` → existing Phase-0 add path
  (lines 706-791), unchanged.
- `action in ("overwrite", "merge")` and target lacks the entry GUID → emit
  `PlannedOverwrite(match_via="identity_remap", write_mode=resolution.action, ...)` and
  record `identity_remap[entry_guid] = resolution.target_guid`, then plan children
  against the resolved target entry (FR-003).

### FR-006 — identity_remap Threading

**File**: `preview.py`
**Current state**: `identity_remap: dict = {}` initialized at line 75 in
`build_run_plan`, returned via `RunPlan(..., identity_remap=...)` at line 175. It is NOT
currently threaded into `_plan_layer3_for_pos` (call at line 83).

**Change**: Add `identity_remap` to the signature chain:
- `build_run_plan` -> `_plan_layer3_for_pos` (line 83 call-site + `def` at line 286)
- `_plan_layer3_for_pos` -> `_plan_layer3_verb_affixes_inner` (line 298 call-site +
  line 466 signature)
- Walker body: `identity_remap[src_guid] = tgt_guid` when a resolution is applied.

This pre-seeds the map at plan-build time so downstream consumers (executor, report,
stats panel) see it with no additional wiring.

### FR-007a — Fill-Gaps Write Mode

**Files**: flexlibs2 fork (see R2 table above) + `transfer.py`

The `BaseOperations.ApplySyncableProperties` implementation loop (lines 1102-1172)
gains fill-gaps guards per R1. The executor at `transfer.py:1331`:
```python
target.LexEntry.ApplySyncableProperties(tgt_entry, src_props)
```
becomes:
```python
target.LexEntry.ApplySyncableProperties(
    tgt_entry, src_props,
    fill_gaps=(overwrite.write_mode == "merge"),
)
```

### FR-008 — Executor match_via Branch (ENTRY)

**File**: `transfer.py`
**Location**: `_execute_overwrite` ENTRY sub-branch, lines 1303-1335.

The current ENTRY branch locates target by `tgt_guid` (line 1307) and source by
`src_guid` (line 1316), then calls `ApplySyncableProperties` at line 1331. The branch
does not currently read `overwrite.match_via`.

**Change**: After locating target and source entries, read `match_via`. For
`match_via == "identity_remap"`, after applying entry-level fields, call the new shared
helper `_populate_entry_children(tgt_entry, src_entry, identity_remap, ...)` to create
senses / MSAs / allomorphs under the resolved target. Pass `fill_gaps` to
`ApplySyncableProperties` based on `write_mode` (R4 / FR-007a).

### FR-009 — Child-Creation Helper Extraction

**File**: `transfer.py`
**Source block**: `_execute_layer3`, lines 816-846 (the per-entry child-creation block:
sense+MSA loop 820-836, allomorph+env loop 840-846).

Extract into:
```
_populate_entry_children(new_entry, src_entry, identity_remap,
                         source, target, target_verb, target_slot_by_guid,
                         env_guid_to_target, tag, report_sink)
```

Existing factored helpers called from within: `_create_lexsense_with_guid` (line 935),
`_create_inflaff_msa_with_guid` (lines 1012-1015), `_create_allomorph_with_guid`
(lines 1065-1068). These remain unchanged; the extraction lifts only the loop body.

Used by both the normal add path (replaces the inline block in `_execute_layer3:816-846`)
and the new identity-remap branch in `_execute_overwrite` (FR-008).

## Project Structure

### Documentation (this feature)

```
specs/013-similar-resolution-transfer/
├── spec.md              # Feature specification (pre-existing)
├── plan.md              # This file
└── tasks.md             # Ordered implementation tasks
```

### Source Code Modified

```
src/gramtrans/
└── Lib/
    ├── models.py         # ADD write_mode field to PlannedOverwrite (R4)
    ├── matcher.py        # ADD fingerprint_with_owner helper (R3)
    ├── preview.py        # ADD identity_remap threading + resolution hook (FR-001, FR-006)
    └── transfer.py       # ADD _populate_entry_children helper (FR-009)
                          # MODIFY _execute_overwrite ENTRY branch (FR-008)
                          # MODIFY _execute_layer3 to call helper (FR-009)

[fork] flexlibs2/code/
    ├── BaseOperations.py               # ADD fill_gaps kwarg (R2)
    └── Grammar/
        ├── POSOperations.py            # ADD fill_gaps kwarg (R2)
        ├── MorphRuleOperations.py      # ADD fill_gaps kwarg (R2)
        ├── GramCatOperations.py        # ADD fill_gaps kwarg (R2)
        ├── InflectionFeatureOperations.py  # ADD fill_gaps kwarg (R2)
        ├── NaturalClassOperations.py   # ADD fill_gaps kwarg (R2)
        ├── EnvironmentOperations.py    # ADD fill_gaps kwarg (R2)
        ├── PhonologicalRuleOperations.py   # ADD fill_gaps kwarg (R2)
        └── PhonemeOperations.py        # ADD fill_gaps kwarg (R2)

tests/
└── unit/
    ├── test_013_fill_gaps.py           # NEW — S3 fill-gaps unit tests
    ├── test_013_planner_resolution.py  # NEW — US1/US2/US3 planner tests
    └── test_013_executor_merge.py      # NEW — US4 executor / child-creation tests
```

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| **I. FLEx Domain Fidelity** | PASS | GUID-first identity preserved: identity_remap keys are entry GUIDs; fingerprint_with_owner overrides index 1 to the resolved target GUID so cross-entry fingerprint comparison is sound. Fill-gaps per-WS-alt semantics respects the LCM multistring ownership model. |
| **II. FlexTools-Compatible, flexlibs2-Direct** | PASS | All transfer code imports flexlibs2 directly. The fill_gaps kwarg is a backward-compatible additive change (default False). No flavors/ adapter introduced. |
| **III. Preview-Before-Mutate** | PASS | Planner (preview.py) emits PlannedOverwrite with write_mode before any mutation. Executor reads the plan verbatim. No mutation in the preview pass. |
| **IV. Phased Merge Discipline** | PASS | Additive to Phase 1 overwrite surface. Does not reorder phases. The "merge" write mode is an executor-side apply variant, not a Phase 2 interactive step. |
| **V. Referential Completeness** | PASS | identity_remap is pre-seeded in build_run_plan; downstream blocks (report, stats) see it without additional wiring (SC-005). |

**Gate result: PASS.**

## Risks

### S1 (LIVE-VERIFY GATE — blocks R1 multistring branch)

Confirm the exact LCM 9.x API call to read a target multistring WS slot for the
fill-gaps predicate. The candidate is:

```python
prop_obj.get_String(tgt_handle).Text  # .strip() non-empty -> target wins
```

Alternative: `.RunCount > 0`. Must be verified against a real FLEx project (Ejagham
Mini -> Ejagham Full GT-Test pair) before the multistring branch of
`ApplySyncableProperties` (fill_gaps path) is considered correct.

**Unblocks**: R2 implementation in BaseOperations.py (multistring guard).

### S2 (LIVE-VERIFY GATE — blocks R3)

Confirm that `MSA.Owner` and `Allomorph.Owner` always resolve to the `ILexEntry` (not
an intermediate `MoForm`) in real Ejagham data before treating fingerprint tuple index 1
as the entry GUID. If Owner is an intermediate object, `fingerprint_with_owner` must
navigate an additional `.Owner` hop.

**Unblocks**: R3 implementation of `fingerprint_with_owner` and its merge-into call site.

### S3 (TEST GATE — verification tasks)

The test suite must include:

1. A parametrized test confirming fill-gaps never overwrites a non-empty target alt
   across all three value shapes (multistring, str, bool/int).
2. A regression test confirming `write_mode="overwrite"` behavior is byte-for-byte
   unchanged relative to the pre-feature baseline (no fill-gaps guard fires).

Both must pass before feature 013 is marked complete.

## Complexity Tracking

The flexlibs2 cross-repo boundary is the primary complexity source: 9 files across two
repositories must be coordinated; the `pip install -e` reinstall step is required after
each flexlibs2 edit before GramTrans tests reflect the change. No Constitution violations.
