# DRAFT Amendment — Per-Item Disposition Model (IGNORE / SKIP / UPDATE / OVERWRITE)

**Status**: PROPOSAL (not ratified). Post-020. Requires a constitution amendment
(Principle IV) + a `ConflictMode` redefinition + a data migration.

**Origin**: surfaced during `/speckit-plan` of 020-conflict-mode-field-merge
(see [research.md](./research.md) R9). 020 itself is deliberately scoped to
OVERWRITE-only field resolution over the *existing* enum and does NOT depend on
this amendment.

**Author prompt**: in a cross-project transfer, the current
`ADD_NEW / MERGE / OVERWRITE` enum conflates *whether we act* with *how
destructively we write*, and "merge" is a misnomer — today's `ConflictMode.MERGE`
writes nothing (link-if-present). This amendment replaces the collision-policy
enum with a clearer disposition model.

---

## 1. Problem statement

Three defects in the current model:

1. **"MERGE" writes nothing.** `ConflictMode.MERGE` = link-if-present-by-GUID,
   else ADD (`models.py:81-82`). It is really **LINK / dedup**, not a merge. The
   name misleads users and authors alike.
2. **No non-destructive update.** The only "overwrite" is wholesale source-wins
   (`fill_gaps=False`), which silently **blanks** a target field when the source
   field is empty. The conservative alternative (`fill_gaps=True`) only fills
   *empty* target fields and never updates a divergent non-empty one. Neither is
   the "update the fields that changed, keep the rest" behaviour users expect.
3. **SKIP is by GUID-presence, not field-identity.** An item present in the target
   is skipped (under LINK) or produces a no-op overwrite (under OVERWRITE) even
   when nothing actually differs — the run report cannot honestly say "unchanged."

## 2. Proposed model

Separate two layers explicitly:

**Category-level MODE (user intent):**

| Mode | Replaces | Meaning |
|---|---|---|
| `ADD_NEW` | `ADD_NEW` (unchanged) | always create a new copy |
| `LINK` | `MERGE` (renamed) | if present by GUID, reference the existing target object; write nothing. Else ADD. |
| `UPDATE` | *new* | write divergent fields from source; **never blank** a target field from an empty source (non-destructive, source-preferring) |
| `OVERWRITE` | `OVERWRITE` (unchanged) | source wins on every field, including blanking from an empty source |

**Per-item DISPOSITION (computed outcome at plan time):**

| Disposition | When |
|---|---|
| `IGNORE` | item/category unchecked — never enters the plan |
| `SKIP` | selected + present, but all user-editable fields already in sync |
| `UPDATE` | selected + present + diverges, mode is UPDATE → selective non-destructive write |
| `OVERWRITE` | selected + present + diverges, mode is OVERWRITE → wholesale write |
| `ADD` | selected + not present (or mode ADD_NEW) → create |

Note `IGNORE` (never transferred) and `SKIP` (transferred-but-unchanged) become
distinct report outcomes, ending the current conflation.

## 3. The three write semantics (name them)

| Semantic | Rule | Status |
|---|---|---|
| fill-gaps | write source→target only where **target** is empty | exists (`fill_gaps=True`) |
| **update** | write source→target wherever **source** is non-empty; keep target where source empty | **NEW** |
| overwrite | write every key; empty source blanks target | exists (`fill_gaps=False`) |

`UPDATE` is buildable as a default per-field policy over the existing
`MergeResolution` machinery: auto `TAKE_SOURCE` on a divergent field, auto
`KEEP_TARGET` where the source value is empty — no new low-level writer required,
only a new default-resolution pass and (optionally) an `ApplySyncableProperties`
mode flag.

## 4. The 3-way baseline limitation (must be documented, not hidden)

"Untouched **since the projects diverged**" is a three-way-merge notion requiring
the common ancestor. At transfer time only *current source* and *current target*
are held, so the engine can prove **identical vs. different**, never **who**
changed a field. The only baseline available is the prior-run residue log
(`load_prior_log`), which exists solely for previously-transferred items.
Therefore:

- **Re-run**: a genuine "untouched" (3-way) test is possible using the residue
  baseline.
- **First transfer**: limited to "in-sync vs. diverged" (2-way). `SKIP` on a first
  transfer means "identical now," not "provably untouched."

The report and UI copy MUST NOT claim more certainty than the available baseline
supports.

## 5. Data migration (blocking — this is why it is not a rename)

`ConflictMode` values are **persisted**:

- `Selection.category_conflict_modes: dict[GrammarCategory, ConflictMode]`
  (serialized selections / saved runs).
- Residue tags serialize a `merge=` segment (`MergeDecisionLog.to_json`,
  `models.py:702`).

Migration mapping:

| Old value | New value | Notes |
|---|---|---|
| `"add_new"` | `"add_new"` | unchanged |
| `"merge"` | `"link"` | pure rename of the collision policy |
| `"overwrite"` | `"overwrite"` | unchanged; **UPDATE is new**, no old value maps to it |

A one-time reader shim MUST accept `"merge"` as an alias for `"link"` for at least
one release (mirror the `flexlibs2`→`flexicon` deprecation-shim precedent in the
constitution). No existing selection maps to `UPDATE`; it is opt-in only.

## 6. Constitution impact (Principle IV)

Principle IV (Phased Merge Discipline) currently defines:
- Phase 1 — Overwrite (GUID/fingerprint match, overwrite matched items).
- Phase 2 — Interactive Merge (per-conflict prompt).

This amendment redefines the **mode vocabulary** those phases operate on
(LINK/UPDATE/OVERWRITE + computed IGNORE/SKIP dispositions). Per the constitution
versioning policy, redefining a principle's normative content is a **MAJOR** bump.

### Proposed Sync Impact Report (for constitution.md when ratified)

```
Version change: 5.1.0 → 6.0.0
Bump rationale: MAJOR — Principle IV mode vocabulary redefined. ConflictMode
  {ADD_NEW, MERGE, OVERWRITE} → mode {ADD_NEW, LINK, UPDATE, OVERWRITE} with a
  computed per-item disposition {IGNORE, SKIP, ADD, UPDATE, OVERWRITE}. Adds the
  non-destructive UPDATE write semantic and field-identity-based true-SKIP.
  "MERGE" renamed to "LINK" (it never merged — it linked). Data migration: reader
  shim aliases persisted "merge" → "link" for ≥1 release; no value maps to UPDATE.
Principles modified: IV (Phased Merge Discipline) — mode vocabulary + dispositions.
Templates requiring updates:
  ⚠ models.py ConflictMode enum + _DEFAULT_CONFLICT_MODES + allowed_modes_for
  ⚠ conflict.py write-semantic dispatch (add UPDATE policy; true-SKIP downgrade)
  ⚠ protection.py apply_isprotected_layer2 (LINK is the safe downgrade target)
  ⚠ specs referencing ConflictMode.MERGE (008/009/010/016/018/019/020/021)
  ⚠ residue tag reader (merge= alias shim)
```

## 7. Suggested rollout

1. **In 020 (additive, no enum change)**: adopt the honest **UI labels** only —
   *Add new* / *Link to existing (no changes)* / *Update* /(where offered) *Overwrite* —
   and optionally the **true-SKIP** report refinement (both are within FR-011
   because they do not change enum values or mode semantics).
2. **New feature spec (post-020)**: `/speckit-specify` a "disposition model"
   feature that (a) ratifies this constitution amendment, (b) renames `MERGE`→`LINK`
   with the reader shim, (c) adds the `UPDATE` mode + non-destructive write
   semantic, (d) adds field-identity SKIP, (e) adds the 3-way residue-baseline
   test for re-runs.
3. **Migration test**: round-trip a saved selection and a residue tag written with
   `"merge"` through the shim; assert it reads back as `LINK`.

## 8. Open questions

- Should `UPDATE` be the new default for MULTI_INSTANCE categories (safer than
  OVERWRITE, more useful than LINK), demoting OVERWRITE to an explicit opt-in?
- Does `LINK` need a "re-point stale reference" variant, or is pure link-if-present
  sufficient?
- For the 3-way test, is the residue baseline trustworthy enough to auto-SKIP on
  re-run, or should it only *inform* (annotate) and still prompt?
