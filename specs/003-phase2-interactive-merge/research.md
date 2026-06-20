# Phase 2 Research: Interactive Merge

This document resolves the technical unknowns identified in [plan.md](plan.md) before design (data-model + contracts) begins. Decisions are recorded with rationale + alternatives so future maintainers can audit why each path was taken.

---

## R1. Where in the plan/execute pipeline does conflict detection live?

**Decision**: Conflict detection runs in `Lib/preview.py.build_run_plan()`, inside each per-category overwrite branch, immediately after `tgt_pre_props` and `src_props` are both available. The detected `ConflictPrompt` instances attach to `RunPlan.conflicts` (new tuple field). The actual user prompt happens in `gramtrans.py.MainFunction` between Preview and Move, mediated by a `ConflictResolver` protocol that defaults to PyQt's `ConflictDialog` but can be swapped for a test double.

**Rationale**:
- Aligns with Constitution Principle III (Preview-Before-Mutate): a Preview run already has both prop dicts; conflict detection is pure-Python, no LCM mutation.
- Keeps `transfer.py` write-side code free of UI dispatch — it consumes a `MergeDecisionLog` as data.
- The `ConflictResolver` protocol enables unit testing without spinning up Qt.

**Alternatives considered**:
- *Detect in `transfer.py` just-in-time* — rejected: violates Preview-Before-Mutate (the user would discover conflicts mid-write, with partial state).
- *Detect outside the planner via a separate diff utility* — rejected: would require re-fetching both objects, doubling LCM round-trips.

---

## R2. Where do "left value" and "right value" come from?

**Decision**:
- **Left (target's pre-overwrite value)**: read from `tgt_pre_props` in the same overwrite branch where Phase 1 already captures it for `tag.with_snapshot(tgt_pre_props)` (FR-106). No new LCM read required.
- **Right (source's value)**: read from `src_props` returned by `source.<Ops>.GetSyncableProperties(src_obj)` — already in scope.

**Rationale**:
- Reuses the Phase 1 snapshot capture; zero new LCM round-trips for the common path.
- The snapshot dict is the canonical pre-overwrite truth — same source as the audit trail.

**Alternatives considered**:
- *Re-read target value at prompt time* — rejected: LCM read between Preview and Move could race against concurrent edits in another FlexTools session (rare but possible).

---

## R3. How is the user's resolution applied to `src_props` before `ApplySyncableProperties`?

**Decision**: A new filter `_apply_merge_decisions(src_props, decisions, tgt_pre_props)` runs in `transfer.py` immediately before each `ApplySyncableProperties` call, parallel to the existing `_dedupe_custom_fields()` from FR-107. The filter:

- For `TAKE_SOURCE` decisions: leave the key in `src_props` (default; equivalent to FR-109).
- For `KEEP_TARGET` decisions: drop the key from `src_props` (target's value remains).
- For `MERGE` decisions: replace the key's value with `_deterministic_merge(left, right)` and keep in `src_props`.
- For `SKIP` decisions: drop the key AND emit a `Skip(reason=INTERACTIVE_SKIP)` into the run report.
- For `EDIT_CUSTOM` decisions: replace the key's value with the user's typed value and keep in `src_props`.

**Rationale**:
- Mirrors the existing `_dedupe_custom_fields()` shape; reviewers already know the pattern.
- Decisions are a data structure; the filter is pure-Python; no UI knowledge in `transfer.py`.
- The five-resolution model collapses to "filter the dict and optionally replace values" — no special-case branches per category.

**Alternatives considered**:
- *Apply decisions inside `ApplySyncableProperties` itself (in flexlibs2 fork)* — rejected: would couple flexlibs2 to GramTrans-specific resolution semantics. The fork stays generic.
- *Per-category resolution methods (e.g., `_resolve_entry_conflicts`)* — rejected: every Carrier-A class has the same conflict shape; one filter covers all.

---

## R4. Deterministic merge semantics

**Decision**:
- **String / Unicode fields**: `<left>\n--- merged GT-<run_id> ---\n<right>` (left first, separator with run_id, right second).
- **Multistring (ITsMultiString) fields**: per writing system, apply the string-merge rule to each populated WS slot independently.
- **Int / Bool / GUID-reference fields**: merge is not offered — these fields collapse to a take-source/keep-target binary at prompt time (the UI omits the merge button for them).
- **List / collection fields (e.g., SlotsRC)**: merge is the set-union of left and right.

**Rationale**:
- Deterministic re-runnable result is FR-203's hard requirement; the separator line embeds the run_id so a re-merge of an already-merged value produces a different output (preventing infinite re-merging confusion).
- The take-source/keep-target collapse for scalar fields matches user expectation — there's no meaningful "merge" of two booleans.
- Set-union for collections preserves Referential Completeness (Principle V): nothing dropped.

**Alternatives considered**:
- *Three-way merge using a common ancestor* — rejected per spec Out-of-Scope (deferred to a future phase).
- *Right-first merge order* — rejected: convention is "target left, source right" in every other merge tool the linguist might be familiar with (git, diff3, KDiff3).

---

## R5. Residue tag wire-format extension for `merge=` segment

**Decision**: Extend `ImportResidueTag` with an optional `merge_b64: Optional[str]` field carrying base64(json) of the `MergeDecisionLog` for that object. Wire format widens from:

```
GT|<run_id>|<source>|<iso_ts>[|snap=<b64>]
```

to:

```
GT|<run_id>|<source>|<iso_ts>[|snap=<b64>][|merge=<b64>]
```

`serialize()` emits segments in `snap`, `merge` order if present. `parse()` accepts 4, 5, or 6 segments; positional ordering of `snap=` / `merge=` is enforced by the segment prefix, not column position. New `with_merge_log(decisions)` method clones the tag and sets `merge_b64`; `decode_merge_log()` recovers the dict.

**Rationale**:
- Backward-compatible: existing 4- and 5-segment tags parse unchanged.
- A re-run reading a target object's residue can recover BOTH the pre-overwrite snapshot AND the prior interactive resolutions in one pass.
- Base64+JSON matches Phase 1's `snap=` encoding — one parser, one mental model.

**Alternatives considered**:
- *Separate residue carrier entirely* — rejected: doubles the LCM property read/write cost.
- *Embed decisions inside `snap=` JSON* — rejected: snapshot and merge log have different lifetimes (snapshot is point-in-time pre-overwrite; merge log is editable across runs).

---

## R6. WS-mapping wizard data flow

**Decision**:
1. `Lib/ws_mapping.py.detect_ws_mismatches(source, target) -> tuple[WSMismatch, ...]` runs at the very top of `MainFunction`, before any planning.
2. Each `WSMismatch` carries `source_ws_id`, `source_ws_kind`, and a list of `target_ws_candidates` (sorted by similarity heuristic — exact-tag matches first, then language-script matches, then all remaining target WSes).
3. The PyQt5 `WSWizard` widget renders one page per mismatch with the three choice buttons {map, create, skip} + a dropdown when "map" is chosen.
4. Wizard output is a tuple of `WSMappingChoice` entries that the caller folds into the existing `WSMapping(entries=(...))` Phase 0 entity.
5. `Selection.ws_mapping_choices` (new field) is wired through to `build_run_plan`, which respects user-chose-skip by emitting `Skip(UNMAPPED_WS_USER_CHOSE_SKIP)` for objects whose only string-bearing slot is in the skipped WS.

**Rationale**:
- Detection is one-shot at the wizard entry point; no per-object WS lookup during planning.
- Reuses the existing `WSMapping` entity from Phase 0 — Phase 2 only enriches each entry with the new `user_choice` field.
- `create new WS` creates the WS BEFORE planning, so downstream `ApplySyncableProperties` sees a complete target WS list (FR-212).

**Alternatives considered**:
- *WS wizard after category selection* — rejected: a user might select a category whose every transferable item depends on an unmapped WS, leaving them at the end with an empty preview.
- *Auto-create new WS without user confirmation* — rejected: silent WS creation is exactly the "silent skip" anti-pattern from Phase 0 that Phase 2 is fixing.

---

## R7. Prior-run decision recall (US3)

**Decision**: Before each conflict prompt fires, `Lib/conflict.py.load_prior_decision(tgt_object) -> Optional[MergeDecision]`:

1. Reads the target object's residue tag via the existing `apply_residue` inverse path (parse LiftResidue or Description).
2. Calls `tag.decode_merge_log()` to recover a dict keyed by field name.
3. Returns the prior decision for the current field name, or None if the tag is absent / unparseable / has no entry for this field.

The UI dialog uses the prior decision (if any) as the pre-selected radio button and displays a "from run GT-YYYYMMDD-HHMMSS" annotation.

**Rationale**:
- Reads no extra LCM properties — the residue tag is already being read for the snapshot.
- A corrupted tag falls back to fresh-prompt behavior (FR-215) — no transfer-blocking error.

**Alternatives considered**:
- *Cache prior decisions in a session-side log file* — rejected: the residue tag is the canonical truth and survives across machines, sessions, project copies. A file cache could drift.

---

## R8. PyQt widget testing strategy

**Decision**: The PyQt widget classes (`ConflictDialog`, `WSWizard`) are NOT exercised by unit tests. Instead, both expose a `resolve()` entry point that returns a `MergeDecisionLog` (or `tuple[WSMappingChoice]`), and the protocol is satisfied by a `FakeConflictResolver` / `FakeWSResolver` in `tests/unit/conftest.py` for unit tests. Live MCP verification covers the widget glue.

**Rationale**:
- Phase 1 set the precedent of "live-MCP verifies UI; pytest verifies logic." Phase 2 inherits.
- Qt's headless `QApplication` is brittle on Windows CI; the cost of stabilizing it outweighs the coverage gained for two dialogs.

**Alternatives considered**:
- *pytest-qt full coverage* — rejected: pytest-qt adds a dependency and a flaky Windows test path for marginal coverage.

---

## R9. Cancellation safety (FR-213)

**Decision**: The `ConflictResolver.resolve()` and `WSResolver.resolve()` protocol methods raise `UserCancelled` on dialog cancel. `MainFunction` catches this at the outermost level and returns before any `transfer.execute()` call. The FlexTools host's UndoableUnitOfWork rolls back the (empty) transaction; the target project is bit-identical.

**Rationale**:
- The single-UoW wrap from research.md R10 (Phase 0) already covers this case — cancelling before any write means the UoW has nothing to undo. No new infrastructure required.
- Explicit `UserCancelled` (vs returning None) makes the intent unambiguous in code review.

**Alternatives considered**:
- *Boolean return + None-means-cancel* — rejected: easy to forget the None check in a callsite; the exception path is harder to silently mishandle.

---

## R10. No new flexlibs2 fork patches needed

**Decision**: Phase 2 introduces zero new flexlibs2 fork patches. All conflict detection, WS-mapping wizardry, and residue extension live in the GramTrans tree.

**Rationale**: The existing `GetSyncableProperties` / `ApplySyncableProperties` surface already returns and accepts plain Python dicts; Phase 2's filter operates entirely on those dicts. The WS wizard reads `project.WritingSystems.GetAll()` which the fork already exposes correctly post the Phase-0 WS-enumeration fix.

**Alternatives considered**:
- *Push merge semantics into the fork* — rejected (see R3): keeps the fork generic.
