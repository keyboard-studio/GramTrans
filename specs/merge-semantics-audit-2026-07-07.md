# Audit: Merge/Update/Overwrite Semantics & Object Matching

**Date**: 2026-07-07
**Scope**: `Lib/models.py`, `Lib/conflict.py`, `Lib/matcher.py`, `Lib/selection.py`,
`Lib/transfer.py`, `Lib/fingerprints.py`, flexicon `BaseOperations`, specs 020/022.
**Status of underlying features**: spec 020 superseded by spec 022 (disposition model),
which is 32/33 tasks done and merged.

## 1. What the modes actually are (post-022)

The live enum is `ADD_NEW / LINK / UPDATE / OVERWRITE` (`models.py:75-97`; persisted
`"merge"` is shimmed to LINK at one read point, `models.py:467`). Dispatch is in
`transfer.py:165-193`:

- **LINK** — GUID-link only, zero field writes. Default for GOLD_RESERVED,
  SINGLETON_NONDELETABLE, CUSTOM_FIELDS.
- **UPDATE** — `apply_update_semantic` (`conflict.py:635`): iterates the
  *intersection* of syncable keys, skips identical values, skips empty-source values
  (including the `"***"` sentinel and all-empty multistrings), writes the rest.
  Genuinely non-destructive. Default for MULTI_INSTANCE.
- **OVERWRITE** — `_execute_overwrite` (`transfer.py:1589`): full
  `ApplySyncableProperties` of source props onto the matched target.
- Per-item disposition (IGNORE/SKIP/ADD/UPDATE/OVERWRITE) is computed at preview
  time with a 2-way diff, upgradeable to 3-way when a prior baseline exists
  (`conflict.py:562`).

### The biggest honesty gap: OVERWRITE is not actually overwrite

In flexicon's `_apply_props_loop` (`BaseOperations.py:282-355`), empty source values
are skipped (`if not text: continue`), target WS alternatives absent from the source
dict are untouched, and nothing is ever cleared or deleted. So OVERWRITE is really
"source wins wherever source is non-empty." It cannot propagate a deletion, cannot
blank a field, and cannot remove a target-only WS alternative.

The `ItemDisposition` docstring says OVERWRITE "may blank target" (`conflict.py:509`)
— documentation and code disagree. In practice UPDATE and OVERWRITE differ only in
subtle respects (UPDATE's empty-source guard vs. the base loop's `if not text` guard,
plus bool/int handling), so the user-facing distinction is much thinner than the UI
implies.

### Other mode facts

- A third semantic hides under OVERWRITE: `PlannedOverwrite.write_mode="merge"` →
  `fill_gaps=True` (fill-empty-slots-only), used by the merge-into path for
  SIMILAR-resolved entries and GOLD-reserved merges (`models.py:633-646`,
  `transfer.py:993`, `transfer.py:1941`). The executor actually has three write
  semantics — fill-gaps / update / source-wins — spread across two switches
  (ConflictMode x write_mode) rather than one model.
- Field-level interactive resolution (ConflictDialog, TAKE_SOURCE / KEEP_TARGET /
  MERGE / EDIT_CUSTOM, prior-decision recall from residue) exists and fires
  OVERWRITE-only per the 020 clarification — but `collect_overwrite_conflicts`
  covers only **pos / entry / sense / allomorph** (`conflict.py:233`). Templates,
  slots, MSAs, and environments get no conflict prompts at all.
- The deterministic string merge is
  `left + "--- merged GT-<run_id> ---" + right` (`conflict.py:182`) — a
  concatenation stamp, not a real merge. Fine as a placeholder; will look odd to
  users in a Definition field.
- Phoneme/PhEnvironment field-diff is **gated off** behind a flexicon version check
  with placeholder `999.0.0` (`conflict.py:684`) — those categories stay
  selector-only until the ITsString fix ships.

## 2. How related objects are identified before merging

Three distinct matching layers, in decreasing rigor:

1. **Move path** (`matcher.lookup_target`, `matcher.py:240`): GUID-first →
   prior-run `identity_remap` dict → per-category fingerprint. Good design, but the
   fingerprint registry contains **only MSA and Allomorph** (`matcher.py:227` — the
   comment admits POS/slots/templates/features "will be added").
   - MSA fingerprint = (owner entry GUID, POS GUID, slot GUID set).
   - Allomorph fingerprint = (owner entry GUID, form text in one vernacular WS,
     morphtype GUID).
   - First equality wins; no ambiguity detection — if two targets share a
     fingerprint, iteration order decides.
2. **Preview status classification** (`selection.py:490-498`): GUID membership →
   IN TARGET; else `form.strip().casefold()` exact match → SIMILAR; else NEW.
   Candidate suggestion = first match by HVO ascending. Only **entries** get
   user-resolvable SIMILAR (merge-into with overwrite/fill-gaps choice, specs
   011/013); for other categories SIMILAR/label matching is informational.
3. **Apply-time cross-reference resolution**: per-executor linear GUID scans
   (`_find_target_pos_by_guid` etc., `conflict.py:248-285`) — O(N) full iterations
   repeated per object, no shared identity index.

## 3. Blind spots, ranked

1. **No mode can delete anything, and nothing tells the user that.** A curator who
   removes a bad gloss in the source and runs OVERWRITE will not see it removed in
   the target. If that is the intended additive-transfer constitution stance, the
   mode should not be named/documented "destructive... may blank target."
2. **No Unicode normalization in matching.** `casefold()` does not unify NFC/NFD,
   and FLEx vernacular data is exactly where composed-vs-combining-diacritic
   mismatches live. Two projects storing the same form with different normalization
   silently classify as NEW → duplicate entry. There is no `unicodedata.normalize`
   anywhere in the matching path. Single most likely real-data failure.
3. **Fingerprint coverage gap = duplicate risk for hand-built targets.** POS,
   features, templates, slots, natural classes match by GUID only on the Move path.
   Anything the target linguist created by hand (different GUID, same content) never
   GUID-matches and has no fingerprint fallback — you get a duplicate, and for POS
   that then skews every MSA that references it. The SIMILAR name-check catches some
   of this at preview, for entries only.
4. **3-way comparison is built but starved.** `compute_disposition` accepts a
   `prior_baseline`, but pre-overwrite snapshots into residue are still "TODO Phase
   1.1" (`transfer.py:154`). All runs are effectively 2-way: UPDATE cannot
   distinguish "target drifted deliberately" from "target is stale," and will
   overwrite deliberate target edits with source values.
5. **Silent partial applies.** Object-reference properties are skipped silently in
   the base apply loop (`BaseOperations.py:349-353`); WS values whose target WS does
   not exist are skipped silently unless a ws_map is pre-validated;
   `apply_update_semantic` swallows `AttributeError`/`TypeError` per field with
   `pass` (`conflict.py:671`). None of these surface in the run report, so
   "transfer succeeded" can mean "some fields quietly didn't."
6. **Key-intersection diffing hides one-sided fields.** Both `detect_conflicts` and
   `compute_field_diff` compare only keys present on both sides; a syncable field
   one side emits and the other does not (e.g. across flexicon versions) is
   invisible to both conflict prompts and disposition.
7. **Single-WS fingerprints.** Allomorph fingerprints use one vernacular WS handle;
   the docstring itself flags the precision degradation. Multi-vernacular projects
   get weaker matching than they could.

## 4. Recommended follow-ups

- Decide the OVERWRITE contract explicitly — either true mirror (clear target-only
  alternatives, with Preview showing the deletions) or rename/redocument it as
  "source-wins" and make the UI copy match. Right now it is the latter behavior
  wearing the former's label.
- Add `unicodedata.normalize("NFC", ...)` in the one place forms are casefolded —
  cheap, high payoff.
- Extend `FINGERPRINT_FNS` to POS (name + parent path), slots (name + owner
  template), and features — the registry design already anticipates it.
- Land the residue baseline snapshot so the 3-way path actually activates; without
  it UPDATE's "non-destructive" claim protects only empty fields, not edited ones.
- Promote the silent skips to report-sink warnings so partial applies are auditable.
