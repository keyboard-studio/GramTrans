# Phase 0 Research — 020 Conflict-Mode Field Merge

All API facts sourced from [probe-results.md](./probe-results.md) (live FLExTools
MCP, 2026-07-05, Ejagham Full + Esperanto) and the existing conflict/merge
machinery in `conflict.py`, `models.py`, `protection.py`, `ui/conflict_dialog.py`.
The spec frames 020 as "surface & wire existing machinery"; the crew review
(lex-domain / lex-programmer / lex-author, cycles 1–2) found that framing is
**mostly** true for the model/dialog layer but has five substantive gaps. Each R
below records the decision that closes a gap.

## R1 — MERGE stays link-only; field-level resolution is OVERWRITE-only (closes GAP1 / D1)

**Decision**: 020 does **not** add field-level merge to `ConflictMode.MERGE`.
Field-level conflict resolution fires only for categories running in `OVERWRITE`.
Strike the "(or MERGE with divergent fields)" parenthetical from spec US2 / FR-003
and mark MERGE-field-resolution as **post-020**.

**Rationale**: (a) `models.py:81-82` documents MERGE as "link-if-present-by-GUID
else ADD — no field-level update — interim, Option b", and FR-011 forbids
redefining `ConflictMode`. (b) Structurally, MERGE-mode items emit
`Skip(ALREADY_PRESENT_BY_GUID)` (`categories.py:203-213`) *before* any overwrite
is planned, and `collect_overwrite_conflicts` only walks `plan.overwrites`
(`conflict.py:315-317`) — so MERGE items never reach conflict detection. Wiring
MERGE-field-merge is a new code path, not a surfacing task; out of scope.

**User consequence**: MERGE remains a safe, non-mutating fallback. A user who
wants per-field resolution consciously selects `OVERWRITE`.

**Alternatives**: extend MERGE to fill-gaps per field — rejected (FR-011
violation; silently elevates a safe mode into a mutating one).

## R2 — Uniform mode-SELECTOR everywhere; field-DETECTION conditional per tier (closes GAP2 / D2 / FR-012)

**Decision**: FR-012 is satisfied by presenting the per-category **mode selector**
uniformly on every category page. Field-level **detection** is present only where
the category has a working syncable-scalar surface. Three tiers (probe-grounded):

- **Tier A — real field-diff now** (GetSyncableProperties works, scalar/text +
  atomic RA): POS, InflectionFeature, NaturalClass, LexEntry, Sense, Allomorph;
  MorphRule (018-probe-sourced, mark not-re-probed).
- **Tier B — mode-selector only now, field-diff a documented no-op**: templates,
  slots, MSAs, strata, inflection classes, stem names, exception features,
  variant types, complex-form types, adhoc/compound rules, semantic domains,
  gram categories (reference-heavy or no confirmed syncable scalar surface).
- **Tier C — BLOCKED by flexicon bug** (mode-selector only): PHONEMES,
  PH_ENVIRONMENT — `GetSyncableProperties` throws (R6 / probe §5).

`_OW_OPS` (`conflict.py:233-238`) covers pos/entry/sense/allomorph today; wiring
the remaining Tier A categories (InflectionFeature, NaturalClass, MorphRule) is
the field-detection deliverable. Tier B/C get the selector but no `_OW_OPS` entry.

**Rationale**: uniform *field-diff* is not meaningful where a category has no
user-visible mergeable scalar fields; forcing a no-op dialog there is misleading.
The selector (what happens on collision) is meaningful everywhere; the diff is
not. Matches lex-author D2 and lex-domain's live key sets.

## R3 — `allowed_modes_for(category)` is surfacing, not redefinition (closes GAP3 / D3)

**Decision**: Add `allowed_modes_for(category) -> frozenset[ConflictMode]` as a
read-only companion to `conflict_mode_for()` on `Selection` (or module-level in
`models.py`). Promote the kind-sets currently discarded as locals inside
`_build_default_conflict_modes` (`models.py:102-157` — `multi_instance`,
`gold_reserved`, `singleton`, `custom_fields`) to module-level frozensets so both
the default-builder and the new query read one source.

Permitted-mode rule (unchanged Layer-1 semantics, merely exposed):
- MULTI_INSTANCE → `{ADD_NEW, MERGE, OVERWRITE}`
- SINGLETON_NONDELETABLE → `{MERGE, OVERWRITE}` (ADD_NEW hidden)
- GOLD_RESERVED → `{MERGE}` (ADD_NEW hidden, OVERWRITE forbidden)
- CUSTOM_FIELDS → `{MERGE}` (ADD_NEW hidden, OVERWRITE forbidden, conservative)

**Rationale**: This reads existing `_DEFAULT_CONFLICT_MODES` gating and returns
the permitted set as a typed query — the exact encapsulation `conflict_mode_for()`
already applies for the resolution path. It does not change which modes are
allowed, so it is **surfacing**, FR-011-safe (lex-author D3).

**Alternatives**: duplicate the kind logic in the wizard — rejected (drift risk,
FR-011-adjacent).

## R4 — `_is_protected` fails CLOSED + casts to ICmPossibility (closes GAP4 / D4)

**Decision**: Invert `protection.py._is_protected` to **fail closed** — an
indeterminate/failed-cast protection state returns `True` (treat as protected)
and emits a diagnostic log entry. Access `IsProtected` through an explicit
`ICmPossibility(x).IsProtected` cast (guarded), not bare attribute access.

**Rationale**: A GOLD/`IsProtected` veto (US4) is a safety rail; fail-open means
the rail silently disappears on a malformed/uncast object, risking an OVERWRITE
of protected data — the worst FLEx-integrity outcome (lex-author D4). The live
probe (probe §3) shows bare access rarely raises at runtime (flexicon returns
concrete `IPartOfSpeech`), so the correctness cost of failing closed is low, but
the MCP **static validator still rejects bare `.IsProtected`** and requires the
cast — so the cast is required for validator-cleanliness regardless. Two-part fix:
fail-closed on the exception path AND cast on the read path.

**Alternatives**: keep permissive fallback — rejected (US4 veto could be bypassed
for bare `ICmObject` inputs; fails the static validator).

## R5 — Field-diff scope = scalar/text + atomic RA; RS/OC excluded (corrects GAP5 / D5)

**Decision**: 020 field-diff scope is **scalar/text fields PLUS atomic `*RA`
GUID references**, minus `*RS` / `*OC` sequence & collection references. The spec
must NOT claim a flat "references out of scope."

**Rationale (live-probe correction)**: probe §4 proves atomic RA refs are in the
`GetSyncableProperties` dict — `Sense.MorphoSyntaxAnalysisRA`, `Sense.SenseTypeRA`,
`Sense.StatusRA`, `Allomorph.MorphTypeRA` — so `detect_conflicts` already surfaces
them as GUID-valued conflicts. Only RS/OC multi-valued refs are excluded upstream
by flexicon's enumeration. `_is_merge_eligible` (`conflict.py:83-88`) additionally
excludes `int`/`bool`/`None` (e.g. `HomographNumber`, `IsAbstract`) from the
MERGE option but still surfaces them as TAKE_SOURCE/KEEP_TARGET conflicts.

**User-facing note (D5 future scope)**: allomorph phonological environments
(`PhoneEnvRC`, an RC) and POS template slot-lists are reference-*category*
collections users may expect to merge; they are excluded in 020 and flagged as
future scope in the spec.

## R6 — Phoneme/Environment field-diff is blocked by a flexicon bug (finding B)

**Decision**: PHONEMES and PH_ENVIRONMENT ship **mode-selector only** in 020.
No `_OW_OPS` entry, no field-diff. File the flexicon defect separately and
reference the bug id in probe-results.md Tier C.

**Rationale**: `GetSyncableProperties` **raises**
`AttributeError("'ITsString' object has no attribute 'get_String'")` for both,
reproduced on Ejagham Full and Esperanto (probe §5). This is upstream in
flexicon, not a GramTrans wiring gap; 020 must not carry a fix. Constitution II
(direct flexicon dependency) means the fix lands in flexicon, not here.

## R7 — Prior-decision recall reuses spec-003 machinery unchanged (US3)

**Decision**: US3 wires the existing `load_prior_log` / `load_prior_decision`
(`conflict.py:385-448`) + `ConflictDialog` preselection (`conflict_dialog.py:162-166,
182-183`). No new recall mechanism. Cross-run source-changed policy (spec edge
case): surface the recalled decision but flag it for re-evaluation rather than
blindly reapply — the dialog already shows the prior run id; add a "source changed
since" annotation when `src_props[field]` differs from the prior `right_value`.

**Rationale**: pure surfacing of shipped Phase-2 machinery; matches spec
Assumptions and the safe-default the spec calls out.

## R8 — Mode-change invalidates stale field decisions (US-edge / FR-009)

**Decision**: When a category's mode changes (e.g. OVERWRITE→ADD_NEW), drop any
captured field-level decisions for that category's items. Field decisions live in
`InteractiveSession.merge_decisions_by_guid`; the wizard clears the affected
guids when `category_conflict_modes[cat]` changes. No model change — the wizard
owns session state.

**Rationale**: FR-009 — the user must never be left with silently-applied stale
decisions. ADD_NEW/plain-create collapses field conflicts to none (spec edge
case: NEW item ⇒ no field conflict).

## GUID-normalization invariant (carried from 010/018)

Every target-lookup in `collect_overwrite_conflicts` already normalizes via
`str(ICmObject(concrete).Guid).lower()` (`conflict.py:248-285`). Any new Tier-A
finder added for InflectionFeature/NaturalClass/MorphRule MUST use the same
lowercase-normalized GUID match on both sides.

## R9 — Future disposition model (IGNORE / SKIP / UPDATE / OVERWRITE) — POST-020

**Not in 020 scope** (redefines `ConflictMode` ⇒ FR-011 / constitution
Principle IV territory). Recorded here so the follow-up is not lost. Full
proposal: [amendment-disposition-model.md](./amendment-disposition-model.md).

**Observation**: in a *cross-project* transfer the current enum
(`ADD_NEW / MERGE / OVERWRITE`) conflates *whether we act* with *how
destructively we write*, and the word "merge" is misleading — today's
`ConflictMode.MERGE` writes nothing (link-if-present). A cleaner model
separates a per-item **disposition** into four outcomes:

| Disposition | Meaning | Today |
|---|---|---|
| **IGNORE** | item/category unchecked — never transferred | ✓ selection (never enters plan) |
| **SKIP** (true) | would transfer, but all user-editable fields already in sync → no write | ⚠ today skips on GUID presence, not field-identity |
| **UPDATE** | write divergent fields from source; **never blank** a target field from an empty source | ✗ new semantic (see below) |
| **OVERWRITE** | source wins on everything, incl. blanking from empty source | ✓ `fill_gaps=False` |

**Three write semantics (only two exist today)**:
- `fill_gaps=True` (current "merge" write_mode): write source→target **only where
  target is empty** (conservative; never changes an existing value).
- **UPDATE (new)**: write source→target **wherever source is non-empty** (divergent
  fields update) but keep target where source is empty — source-preferring AND
  non-destructive. This is the semantic most users expect and it is unbuilt. It can
  be realised as a default per-field policy over the existing `MergeResolution`
  machinery (auto `TAKE_SOURCE` on a divergent field; auto `KEEP_TARGET` where
  source empty).
- `fill_gaps=False` (OVERWRITE): write every key; empty source blanks target.

**true-SKIP refinement** (cheap, could even be pulled into 020 as an additive
improvement): `detect_conflicts` already returns the (identical-suppressed) field
diff; when it is empty, emit `Skip(reason=in-sync)` instead of a no-op overwrite so
the run report is honest ("unchanged" vs. a phantom overwrite count).

**3-way baseline caveat**: "untouched *since the projects diverged*" is a
three-way merge notion — it needs the common ancestor. At transfer time we hold
current-source and current-target only, so we can prove **identical vs. different**
but not **who** changed a field. The only baseline available is the prior-run
residue log (`load_prior_log`), which exists for previously-transferred items. So a
true "untouched" test is possible on re-runs; a first transfer is limited to
"in-sync vs. diverged."

**Data-migration note**: the enum value `"merge"` is persisted in
`Selection.category_conflict_modes` and serialized in residue `merge=` tags —
adopting this model is a data-migration, not a rename. See the amendment.

## Open items for implementation-time MCP confirmation

- **R2a** — live re-probe MorphRule `GetSyncableProperties` against a rule-bearing
  project before wiring it into Tier A (018-probe key set not re-confirmed in 020).
- **R6a** — confirm the flexicon bug id once filed; update probe-results.md Tier C.
- **R3a** — confirm no existing caller depends on the kind-sets being function-local
  before promoting them to module scope (grep `_build_default_conflict_modes`).
