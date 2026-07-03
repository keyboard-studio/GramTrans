# Phase 0 Research: Merge-Preview Diff Engine (012)

All decisions below resolve the Technical Context of [plan.md](plan.md). The spec is
plan-complete (it names the module, types, and signatures), so research here is about
*grounding each decision in existing code paths* and pinning the few genuinely open choices.

## R1 — Mirror, don't import, `_deterministic_merge`

**Decision**: `merge_preview.py` reimplements the value-shape dispatch (multistring dict,
str, list/tuple/set, scalar, other) itself, rather than importing
`conflict._deterministic_merge`.

**Rationale**: `_deterministic_merge` produces a *merged value* (with a run-id string-concat
marker: `<left>\n--- merged <run_id> ---\n<right>`). The preview needs *diff segments*
(added/removed/unchanged/note), not a merged string, and the run-id marker is a Move-time
artifact that must not leak into a preview (spec Edge Cases; constitution III/IV). Mirroring
keeps the Move-time semantics authoritative in `conflict.py` while letting the preview show
replace-with-note semantics. The two share the same *shape taxonomy* (`_NON_MERGEABLE_TYPES
= (int, bool, NoneType)`; dict = multistring keyed by ws id; list/tuple/set = union) so they
stay consistent.

**Alternatives considered**: (a) Import and post-process the merged value into segments —
rejected: the merged string is lossy (can't recover which ws differed) and carries the
run-id marker. (b) Refactor `_deterministic_merge` to emit segments — rejected: that couples
Move-time to preview and risks Phase 2 regressions; out of scope for a read-only feature.

## R2 — Four conflict modes and their mapping to 011 resolutions

**Decision**: The engine exposes four modes:

| Engine mode | Origin | Semantics |
|-------------|--------|-----------|
| **NEW** | `SimilarResolution.action == "create_new"` / `tgt_props is None` | Every value `added`. |
| **LINK-ONLY** | engine's category-default link-by-id (formerly "MERGE") | Target fields `unchanged`; source-only fields get a `note` ("not transferred — links without field update"). |
| **OVERWRITE** | `SimilarResolution.action == "overwrite"` (source wins) | Per-key value-shape dispatch, source winning on every differing value. |
| **MERGE-KEEP** | `SimilarResolution.action == "merge"` (target-preserving fill-gaps) | Equal → `unchanged`; source-only/empty-target → `added`; target-only → `unchanged`; differing-with-nonempty-target → target `unchanged` + `note`. Mirrors 013 FR-007a apply. |

**Rationale**: The 011 [data-model](../011-similar-resolution-datamodel/data-model.md) fixes
`SimilarResolution.action ∈ {"overwrite","merge","create_new"}`. The historical engine
"MERGE" (link-by-id, no field write) collides with the SIMILAR `merge` resolution, so it is
renamed **LINK-ONLY** and the SIMILAR `merge` becomes **MERGE-KEEP** (spec FR-003/FR-004a).

**Alternatives considered**: Keep one "MERGE" name — rejected: the collision is exactly the
bug the rename prevents; a reviewer or 014 author would wire the wrong semantics.

## R3 — Per-writing-system emptiness inside MERGE-KEEP

**Decision**: In MERGE-KEEP, emptiness is evaluated **within** the multistring value-shape
dispatch, per ws id: a ws present/non-empty on the source but empty/absent on the target is
`added`; a ws where the target already holds a differing value renders target `unchanged` +
`note` (FR-004a).

**Rationale**: `GetSyncableProperties` multistrings are `{ws_id: text}` dicts (per
`LexEntryOperations`; ids like `"en"`, `"koh"`, `"koh-fonipa"`). Fill-gaps is a per-ws
notion, not a whole-field notion — a field can be present on the target in `en` but empty in
`koh`, and MERGE-KEEP fills only the `koh` gap.

## R4 — Props fetch table and fork-gap fallback

**Decision**: `props_for(handle, category, guid, *, index=None, owner_guid="")` dispatches on
a per-category ops/finder table. Covered categories call `<ops>.GetSyncableProperties(obj)`.
The three fork-gap categories fall back to **direct guarded multistring reads** of
Name/Abbreviation/Description per ws (plus optional bool for slots) into the same
`{field: {ws_id: text}}` shape; a hard failure returns `None` + a note (never raises).

**Coverage (CORRECTED cycle 1 by lex-author; supersedes the earlier "12 covered" reading)**.
The distinction that matters for tasks is not just "has `GetSyncableProperties`" but "has a
GUID **finder** to locate the target object." Only 4 categories have both today:

- **FULLY COVERED — 4** (have `GetSyncableProperties` AND an existing `conflict._OW_OPS`
  finder): **POS, LexEntry, Senses, Allomorphs**.
- **FINDER-NEEDED — 8** (have `GetSyncableProperties` but NO target finder — the finder is
  net-new work for this feature): **Phonemes, NaturalClasses, Environments, PhonRules, Strata,
  GramCat, InflectionFeatures, MorphRules (templates)**.
  - *Footnote:* **InflectionFeatures** targets `IMoInflClass` (inflection **classes**), NOT
    `IFsClosedFeature`. Closed-feature sync is out of scope for 012 (use `categories.py`
    direct reads if ever needed).
  - *Footnote:* **MorphRules/templates** needs a **two-level, owner-POS-dependent** finder —
    see R4a.
- **FORK GAPS — 3** (no `GetSyncableProperties` at all — direct-read fallback required):
  **Slots, Phonological Features** (`PhonFeatureOperations` has no `GetSyncableProperties`,
  grep-confirmed), **Stem Names**.

The fallback field set is verified: **Name / Abbreviation / Description + optional slot bool**
(Stem Names read Name/Abbrev/Desc via `get_String` at `categories.py` ~L854-870; the slot bool
is `IMoAffixSlot.Optional`). FR-008 shape MUST be `{field: {ws_id: text}}` (field-name keyed),
NOT flat `{ws_id: text}`.

**Rationale**: Grounded in [categories.py](../../src/gramtrans/Lib/categories.py) precedents
(`source.POS.GetSyncableProperties`, `source.InflectionFeatures.GetSyncableProperties`,
`source.Phonemes.GetSyncableProperties`, `source.NaturalClasses.GetSyncableProperties`) and
in [conflict.py](../../src/gramtrans/Lib/conflict.py) `_OW_OPS` (the source/target/finder
triple pattern). Template/slot requests need the **owner POS GUID** to resolve the wrapper,
so `owner_guid` is a keyword arg (FR-007). The GUID index is built **once** and reused
(mirrors `preview.py` indexing; the `_find_target_*_by_guid` linear-scan precedent).

**Alternatives considered**: Adding wrappers to the fork for the three gap categories —
rejected: out of scope for GramTrans (fork work tracked separately in CLAUDE.md); direct
guarded reads are enough for a read-only preview.

## R4a — Two-level owner-POS finder for templates

**Decision**: `_find_target_template_by_guid(target, guid, owner_pos_guid)` is a distinct,
**owner-required** finder: it locates the owning POS by GUID (`target.POS.GetAll(recursive=
True)`) then scans that POS's `AffixTemplatesOS` for the template GUID. `props_for`'s
`owner_guid` for a template/slot request is therefore the **owning POS's GUID**, not the
template's own GUID (lex-author, cycle 1).

**Rationale**: There is no template finder in `conflict._OW_OPS`; templates are owned by a POS
in LCM (`IPartOfSpeech.AffixTemplatesOS`), so a flat GUID scan cannot find them. This is the
only finder that takes a *required* owner argument — it must not be collapsed into the one-arg
`_find_target_<cat>_by_guid` signature the other 8 finders share.

## R5 — WS role classification

**Decision**: `ws_role_map(project)` returns `{ws_id: WsRole}` classifying each ws id as
`VERNACULAR` (in the project's vernacular list), `IPA` (`"fonipa"` in the ws tag), or
`ANALYSIS` (otherwise), every accessor guarded so a missing/edge ws does not crash.

**Rationale**: Reuses the existing [ws_fonts.py](../../src/gramtrans/Lib/ws_fonts.py)
`WsRole` enum and the `"fonipa" in wid.split("-")` heuristic already proven in
`_find_ipa_ws`. `to_html` then asks the `WsFontRegistry` for a `WsFont` per role — no new
font machinery. A ws id present in a value dict but not in the project map renders as chrome
(role `None`) and falls back to the default font (spec Edge Cases).

**Alternatives considered**: Per-ws-id fonts (not per-role) — rejected: `WsFontRegistry` is
role-keyed and IPA falls back to the vernacular font; matching that contract keeps rendering
consistent with the rest of the wizard.

## R6 — Qt-free HTML rendering and the caching service

**Decision**: `to_html(preview, registry)` returns an HTML string: all text `html.escape`d,
`added` green, `removed` red + strike-through, `note` gray italic, per-`WsRole` font-family
and point size from the registry, `dir="rtl"` where the role's `WsFont.rtl`, indent by field
nesting depth, bold field names. `MergePreviewService` holds source/target handles + the
ws-role classifier + a lazy target-GUID index, memoizes on `(category, source_guid,
target_guid)`, caches property **dicts** (never LCM objects), and exposes `invalidate()`.

**Rationale**: The viewer runs no scripts, so escaping is purely anti-corruption (SC-004).
Caching dicts (not handles) honors the "no retained LCM handles" invariant (FR-012,
constitution I); re-fetch by GUID on first click keeps handles valid within the wizard's
target-locked lifetime (spec Assumptions). Re-link (different `target_guid`) and a resolution
change (different `mode`) are each distinct cache keys so each computes exactly one new entry
(SC-006).

**Cache key — DECIDED (cycle 1, lex-qc + lex-domain concurring):** the key is the **4-tuple
`(category, source_guid, target_guid, mode)`**, NOT the GUID triple. A user can flip a SIMILAR
resolution (OVERWRITE → MERGE-KEEP) on the same source/target *in-page*; `invalidate()` fires
only on page re-entry (SC-006/US4), so a 3-tuple key would silently serve a stale diff — a
correctness defect. `status` is computed into the value, not the key.

## R6a — `props_for` ops-table seam (testability)

**Decision**: the per-category ops-dispatch table is **injectable** — either a `props_for`
parameter defaulting to the module-level constant, or a monkeypatchable module constant. Pick
one and state it in the implementing task.

**Rationale** (lex-qc, cycle 1): `props_for` takes a live project `handle` to drive
`GetSyncableProperties`. Without an injection seam, the *covered-category* path cannot be
tested without a live LCM. The fork-gap fallback path is already testable via a fake handle
that raises/returns `None`, but the covered path needs the seam.

## R7 — Testing strategy

**Decision**: Pure unit tests only, one file per user story:
`test_merge_preview_diff.py` (US1 mode × shape matrix), `test_merge_preview_html.py` (US2
escaping/font/rtl/strike/indent), `test_merge_preview_props.py` (US3 covered + fork-gap +
`ws_role_map`), `test_merge_preview_service.py` (US4 caching/re-link/invalidate). All use
fabricated dicts and a fake `WsFontRegistry`; a module-import-with-no-Qt test asserts SC-007.

**Rationale**: Spec Assumptions: "ships with pure unit tests only." Matches the repo's
`tests/unit/` layout and the `-m "not integration"` default.
