---
description: "Task list for feature 012 — Merge-Preview Diff Engine & HTML Rendering"
---

# Tasks: Merge-Preview Diff Engine & HTML Rendering

**Input**: Design documents from `specs/012-merge-preview-diff-engine/`

**Prerequisites**: plan.md, spec.md (US1–US4), research.md (R1–R7, R4a, R6a), data-model.md,
contracts/merge_preview.md

**Tests**: This feature ships **pure unit tests only** (spec Assumptions). Test tasks are
included and are REQUIRED for this feature — the test matrix (SC-002) is the core acceptance
surface. All tests run with **no Qt and no LCM** (fabricated dicts + a fake `WsFontRegistry`).

**Organization**: Tasks are grouped by user story. This feature is a single new file
`src/gramtrans/Lib/merge_preview.py`, so many tasks touch that one file and are therefore
**sequential (not [P])** within a story unless they add distinct symbols with no shared edit
region. Test files are separate per story and parallelizable.

**Review provenance**: This task list folds in the LEX crew cycle-1 review (lex-domain,
lex-author, lex-qc, lex-simplify) and lex-lead's cycle-2 consolidated directive. Directive
IDs (A1–A3, B1–B6, test cells 1–15) are cited inline for traceability.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 (diff core), US2 (HTML render), US3 (props fetch), US4 (caching service)
- Exact file paths are given in every task.

## Path Conventions

- Module: `src/gramtrans/Lib/merge_preview.py` (single new file, flat `Lib/` per constitution II)
- Tests: `tests/unit/test_merge_preview_*.py`
- Reused: `src/gramtrans/Lib/ws_fonts.py` (`WsRole`/`WsFont`/`WsFontRegistry`)
- Mirrored (never imported): `src/gramtrans/Lib/conflict.py` (`_deterministic_merge`)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm the workspace can build/test the new module headlessly.

- [ ] T001 Confirm dev deps are installed and unit tests run: `pip install -e ".[dev]"` then
      `python -m pytest tests/unit -m "not integration" -q` (baseline green before adding 012).
- [ ] T002 [P] Create the empty test modules with a module docstring citing feature 012 and the
      user story each covers: `tests/unit/test_merge_preview_diff.py`,
      `tests/unit/test_merge_preview_html.py`, `tests/unit/test_merge_preview_props.py`,
      `tests/unit/test_merge_preview_service.py`, `tests/unit/test_merge_preview_qt_free.py`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Gates that MUST complete before ANY user-story code. Per lex-lead ordering (d):
the Qt-free audit is a **gate, not a chore**, and the module skeleton/types must exist before
diff/render/props/service code lands.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T003 **[B6 — Qt-free audit gate]** Audit `src/gramtrans/Lib/models.py` (011
      `SimilarResolution` vocabulary) and every module `merge_preview.py` will import for a
      transitive Qt import. `ws_fonts.py` is already confirmed Qt-free. If a Qt import is found on
      the diff path, breaking it is a prerequisite task here — NOT a follow-up. Record the audit
      result as a comment in `tests/unit/test_merge_preview_qt_free.py`. (SC-007, lex-qc)
- [ ] T004 Create `src/gramtrans/Lib/merge_preview.py` with `from __future__ import annotations`,
      the module docstring (three layers; Qt-free; mirrors-not-imports `conflict.py`), and
      `typing` imports only (`Dict`, `Tuple`, `Optional`, `Callable`, `Any`; py38 target — no
      3.9+ syntax). MUST NOT import Qt; keep any flexlibs2 import lazy/guarded inside functions.
- [ ] T005 Define the pure value types in `src/gramtrans/Lib/merge_preview.py` (FR-001,
      data-model.md): `SegmentKind` (added/unchanged/removed/note), frozen
      `DiffSegment(text, kind, ws_role=None)` — **no `rtl` field** (A2, lex-simplify: direction
      resolved at render), frozen `FieldDiff(field_name, segments, indent=0)`, frozen
      `MergePreview(status, fields, notes=())`, and the four mode constants
      `NEW`, `LINK_ONLY`, `OVERWRITE`, `MERGE_KEEP` (R2; all four kept per lex-simplify).

**Checkpoint**: Module imports cleanly with no Qt; types and mode constants exist. User stories
can now begin.

---

## Phase 3: User Story 1 — See exactly what a merge would change, field by field (Priority: P1) 🎯 MVP

**Goal**: `diff_props(src_props, tgt_props, mode, ws_role_of)` produces an alphabetically
ordered `MergePreview` whose segments are tagged added/unchanged/removed/note per the four
modes and the value-shape dispatch, mirroring (never importing) `_deterministic_merge`.

**Independent Test**: Call `diff_props` with fabricated source/target dicts across each mode and
value shape; assert segment kinds and field ordering — no Qt, no LCM.

### Implementation for User Story 1

- [ ] T006 [US1] Implement the private value-shape helper
      `_segments_for_value(src_val, tgt_val, ws_role_of)` in
      `src/gramtrans/Lib/merge_preview.py` (**B4**, lex-simplify). Dispatch (FR-005): multistring
      dict keyed by ws id (recurse per ws — equal→unchanged, source-only→added,
      target-only→unchanged, differing→removed+added); plain `str` (removed+added); `list/tuple/
      set` (union: common unchanged, source-only added, target-only unchanged); scalar
      `int/bool/None` (removed+added); other object (`repr()` then treat as `str`). Mirror the
      `conflict._deterministic_merge` taxonomy (`_NON_MERGEABLE_TYPES = (int, bool, NoneType)`;
      one-sided dict keys pass through WITHOUT recursion — conflict.py L188-190). Private; not in
      the contract.
- [ ] T007 [US1] Implement `diff_props(src_props, tgt_props, mode, ws_role_of) -> MergePreview`
      in `src/gramtrans/Lib/merge_preview.py` as a thin mode-router over `_segments_for_value`
      (depends on T006):
      - NEW / `tgt_props is None` → every field/value `added` (FR-002, SC-001).
      - LINK-ONLY → target fields `unchanged`; source-only fields get a `note`
        ("not transferred — links without field update"), regardless of value shape (FR-003).
      - OVERWRITE → per union key: equal `unchanged`, source-only `added`, target-only
        `unchanged`, differing → `_segments_for_value` (source wins) (FR-004).
      - MERGE-KEEP → per union key: equal `unchanged`; source-only OR empty-target `added`;
        target-only `unchanged`; differing-with-nonempty-target → target `unchanged` + `note`
        (source value not applied) (FR-004a). Per-ws emptiness evaluated INSIDE the multistring
        dispatch; **"empty target ws" = ws key absent OR value is empty string** (lex-domain
        constraint 1).
- [ ] T008 [US1] Ensure `MergePreview.fields` is always sorted **alphabetically** by
      `field_name` (FR-006, SC-003) and that keys absent on both sides are not emitted (edge
      case). Verify no import of `conflict._deterministic_merge` exists anywhere in the module
      (mirror-not-import boundary, R1).

### Tests for User Story 1 — `tests/unit/test_merge_preview_diff.py`

- [ ] T009 [P] [US1] **NEW mode**: `diff_props(src, None, NEW, role_of)` across every value shape
      → 0 non-`added` segments (SC-001).
- [ ] T010 [P] [US1] **Multistring dispatch — 3 distinct assertions** (test cells 3–5, FR-005):
      (a) source-only ws → `added`; (b) target-only ws → `unchanged` (one-sided-key pass-through,
      conflict.py L188-190); (c) both-differing ws → `removed`+`added` with **no run-id marker**
      in the preview.
- [ ] T011 [P] [US1] **MERGE-KEEP × multistring, mixed empty/non-empty target ws** (test cell 1,
      FR-004a): fixture target `{"en":"text","koh":""}`, source `{"en":"other","koh":"fill"}` →
      `en` target-wins `unchanged`+note, `koh` `added`.
- [ ] T012 [P] [US1] **FR-004a empty-check both forms** (test cell 2): assert absent-ws-key AND
      empty-string value (e.g. `{"en":"","koh":""}`) are both treated as "empty target."
- [ ] T013 [P] [US1] **LINK-ONLY × multistring source-only field** (test cell 6): a source-only
      field emits a `note` even when its value is a multistring (not just a scalar) (FR-003).
- [ ] T014 [P] [US1] **Target-only key invariant** (test cell 7): parametrized across OVERWRITE,
      MERGE-KEEP, LINK-ONLY → target-only key renders `unchanged`, never implies deletion. Plus
      **both-absent → not emitted** (test cell 8).
- [ ] T015 [P] [US1] **Scalar + other-object** (test cells 9–10, FR-005): differing scalar
      (int/bool/None) → `removed`+`added`; an arbitrary object value exercises the `repr()`
      fallback branch.
- [ ] T015a [P] [US1] **Plain-string + list/tuple/set shapes** (completes the SC-002 matrix,
      FR-005): (a) a differing plain-`str` field → `removed`+`added` (no run-id marker); (b) a
      `list`/`tuple`/`set` field union → common members `unchanged`, source-only `added`,
      target-only `unchanged`. Exercise both OVERWRITE and MERGE-KEEP so every mode × shape cell
      of SC-002 has an assertion (closes analyze finding C1).
- [ ] T016 [P] [US1] **Field ordering** (SC-003): assert `fields` alphabetical by `field_name`
      for a multi-field fixture in every mode.

**Checkpoint**: US1 is the MVP — `diff_props` is fully functional and testable with no Qt/LCM.

---

## Phase 4: User Story 2 — Diffs are legible: color, font, and script direction (Priority: P1)

**Goal**: `to_html(preview, registry)` renders a computed preview to escaped, colorized,
font/direction-aware HTML, resolving `rtl` from the registry at render time.

**Independent Test**: Feed a computed preview + a fabricated `WsFontRegistry` to `to_html`;
assert escaping, per-role font family/size, RTL direction, strike-through, indentation.

### Implementation for User Story 2

- [ ] T017 [US2] Implement `to_html(preview, registry) -> str` in
      `src/gramtrans/Lib/merge_preview.py` (FR-010, SC-004, depends on T005): `html.escape` all
      text; `added` green; `removed` red + strike-through; `note` gray italic; per-`WsRole`
      font-family + point size from `registry.font_for(role)`; **`dir="rtl"` resolved from the
      role's `WsFont.rtl` at render** (A2 — direction is NOT on `DiffSegment`); indent by
      `FieldDiff.indent`; bold field names. A `ws_role is None` segment renders in the default
      font (no font span). Pure; `registry: WsFontRegistry` is the only I/O-ish dependency.

### Tests for User Story 2 — `tests/unit/test_merge_preview_html.py`

- [ ] T018 [P] [US2] **Escaping**: text with HTML metacharacters is escaped; and assert
      `repr()`-fallback output (test cell 9 tie-in) is not mangled — no stray `<`/`>` survive.
- [ ] T019 [P] [US2] **Per-role font + RTL**: a segment with an RTL role uses the registry's
      font family/size and carries a right-to-left direction; an LTR role does not (SC-004).
      Use a fabricated `WsFontRegistry` with a known RTL `WsFont`.
- [ ] T020 [P] [US2] **Color + strike + indent**: added green, removed red + strike-through,
      note gray italic; `FieldDiff.indent > 0` produces a concrete, asserted indentation (test
      cell 12); field names bold.
- [ ] T021 [P] [US2] **Chrome path** (test cell 11): a segment with `ws_role=None` (registry
      returns `None`) renders in the default font with no font span. Covers the "ws id in value
      dict but absent from `ws_role_map`" case end-to-end with US3's classifier returning `None`.

**Checkpoint**: US1 + US2 together render a legible diff from fabricated data with no Qt.

---

## Phase 5: User Story 3 — Fetch comparable properties for any category, with fallbacks (Priority: P2)

**Goal**: `props_for(...)` returns a comparable `{field: value}` dict per category via the right
ops wrapper (building the GUID index once), with direct-read fallbacks for the 3 fork-gap
categories; `ws_role_map(project)` classifies ws ids. Coverage is 4 covered / 8 finder-needed /
3 gaps (A3, lex-author).

**Independent Test**: Call `props_for` against fakes for a covered category (ENTRY/LexEntry) and
a gap category (Slots); assert the covered path returns the syncable-props dict and the gap path
returns the `{field: {ws_id: text}}` shape (or `None` + note on failure).

### Implementation for User Story 3

- [ ] T022 [US3] Define the per-category props table in `src/gramtrans/Lib/merge_preview.py`
      per the **enumerated rows in data-model.md** ("Enumerated rows (concrete starting point for
      T022)"): columns category key → ops accessor → finder → needs_owner → fallback. Populate
      the **4 fully-covered** rows reusing the existing `conflict._OW_OPS` finders (POS, LexEntry,
      Senses, Allomorphs). **Confirm the accessor names flagged "confirm" in that table**
      (`Environments`, `PhonRules`, `Strata`, `GramCat`) against `categories.py` / the flexlibs2
      Operations class before wiring — do not assume them. Add a comment that the other 8 finders
      are net-new (T023/T024) — the table MUST NOT imply they already exist (A3, lex-author; U1).
- [ ] T023 [P] [US3] **[B1]** Implement the **7 one-arg** finders
      `_find_target_<cat>_by_guid(target, guid)` (linear `GetAll()` GUID scans) for the
      simple FINDER-NEEDED categories: Phonemes, NaturalClasses, Environments, PhonRules, Strata,
      GramCat, and InflectionFeatures (→ `IMoInflClass` inflection **classes**, NOT
      `IFsClosedFeature` — footnote per lex-author). Wire each into the props table. (The 8th
      finder-needed category, **MorphRules = templates**, is owner-dependent and handled in T024 —
      there is no separate non-template MorphRule finder.)
- [ ] T024 [US3] **[B2]** Implement the **two-level, owner-required** template finder
      `_find_target_template_by_guid(target, guid, owner_pos_guid)` (R4a) — the **8th**
      finder-needed category (MorphRules/templates): locate the owner POS by GUID via
      `target.POS.GetAll(recursive=True)`, then scan its `AffixTemplatesOS` for the template
      GUID. This is the ONLY finder taking a required owner arg — do NOT collapse it into the
      T023 one-arg signature. Wire it into the props table with `needs_owner=True`.
- [ ] T025 [US3] **[B5 — ops-table seam]** Make the per-category ops table injectable so the
      covered path is testable without LCM (R6a, lex-qc): add a parameter to
      `props_for(handle, category, guid, *, index=None, owner_guid="", ops_table=<module const>)`
      (or make the table a monkeypatchable module constant — pick one and document it in the
      docstring). Build the GUID index once and reuse it (FR-007). Template/slot requests use
      `owner_guid` = the owning POS's GUID (R4a).
- [ ] T026 [US3] **[B3]** Implement the **3 direct-read fallback** paths for the GAP categories
      (Slots, Phonological Features, Stem Names) (FR-008): guarded per-ws reads of
      Name/Abbreviation/Description via `get_String` (+ optional slot bool `IMoAffixSlot.Optional`)
      into the **`{field: {ws_id: text}}`** shape — field-name keyed, NOT flat `{ws_id: text}`.
      Return `None` + a note on hard failure; **never raise to the caller** (SC-005).
- [ ] T027 [US3] Implement `ws_role_map(project) -> dict[str, WsRole]` (FR-009, R5): classify
      each ws id as `VERNACULAR` (in the vernacular list), `IPA` (`"fonipa"` in the ws tag),
      `ANALYSIS` (otherwise); every accessor guarded so a missing/edge ws does not crash. Reuse
      the `ws_fonts._find_ipa_ws` `"fonipa" in wid.split("-")` heuristic.

### Tests for User Story 3 — `tests/unit/test_merge_preview_props.py`

- [ ] T028 [P] [US3] **Covered path** (via the T025 seam): a fake ops table returns a syncable
      dict for a covered category (ENTRY/LexEntry); assert the dict is returned and the GUID index
      is built once and reused (FR-007, SC-005).
- [ ] T029 [P] [US3] **Fork-gap fallback shape** (test cell 14, FR-008): a Slots/Stem-Names fake
      returns the direct-read shape; assert **field-name keying** `{"Name": {"en": ...}}` (NOT
      flat `{"en": ...}`); assert the optional slot bool appears for Slots.
- [ ] T030 [P] [US3] **Fallback hard failure**: a fake whose direct read raises → `props_for`
      returns `None` + a note, never an exception (SC-005).
- [ ] T031 [P] [US3] **Template owner path**: a template request resolves via `owner_guid`
      (owning POS GUID) through the two-level finder (T024).
- [ ] T032 [P] [US3] **`ws_role_map`**: classifies VERNACULAR / IPA (`fonipa` tag) / ANALYSIS;
      a missing/edge ws does not crash; a ws id absent from the map yields `None` when the
      resulting `ws_role_of` callable is queried (feeds test cell 11 in US2).

**Checkpoint**: All non-affix categories can be diffed; fork gaps degrade to a note, never a crash.

---

## Phase 6: User Story 4 — Recompute is cheap and re-link is a distinct result (Priority: P2)

**Goal**: `MergePreviewService` memoizes previews on the **4-tuple**
`(category, source_guid, target_guid, mode)`, caches dicts (never LCM handles), and exposes
`invalidate()`.

**Independent Test**: Call `preview_for` twice identical → one computation; different
`target_guid` OR different `mode` → distinct result; `invalidate()` → recompute.

### Implementation for User Story 4

- [ ] T033 [US4] Implement `MergePreviewService` in `src/gramtrans/Lib/merge_preview.py`
      (FR-011, FR-012, depends on T007/T017/T025/T027): Qt-free; holds source/target handles, the
      ws-role classifier (from `ws_role_map`), a lazy target-GUID index, a props-dict cache, and a
      preview cache. Caches property **dicts, never live LCM objects**; re-fetches by GUID on
      first click (FR-012, constitution I).
- [ ] T034 [US4] Implement `preview_for(category, source_guid, target_guid, status, mode,
      owner_guid="") -> MergePreview` (**A1** — 4-tuple key): compute lazily; memoize on
      `(category, source_guid, target_guid, mode)`; re-link (different `target_guid`) AND a
      resolution change (different `mode`) are each distinct keys. `status` is computed into the
      value, not the key. Implement `invalidate() -> None` to clear the cache for page re-entry.

### Tests for User Story 4 — `tests/unit/test_merge_preview_service.py`

- [ ] T035 [P] [US4] **Memoization**: `preview_for` twice with identical 4-tuple args → the
      second call recomputes zero times (spy/count the compute path) (SC-006).
- [ ] T036 [P] [US4] **Re-link**: same source, different `target_guid` → distinct cached entry,
      exactly one new computation (SC-006).
- [ ] T037 [P] [US4] **[A1 regression guard]** (test cell 13): same `(category, source_guid,
      target_guid)` but different `mode` → **cache MISS**, a distinct computed result. Assert the
      old 3-tuple key would have returned the stale entry (prove the fix).
- [ ] T038 [P] [US4] **Invalidate**: after `invalidate()`, the next `preview_for` recomputes
      (SC-006).
- [ ] T039 [P] [US4] **No retained handles**: assert the cache holds dicts/`MergePreview` values,
      never LCM objects (FR-012).

**Checkpoint**: All four user stories independently functional and testable headlessly.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T040 [P] **[SC-007]** Implement the Qt-free guarantee test in
      `tests/unit/test_merge_preview_qt_free.py` (test cell 15, lex-domain constraint 5): import
      `gramtrans.Lib.merge_preview` in a **standalone subprocess with Qt forcibly absent**
      (e.g. inject a `sys.modules` sentinel that raises on `PyQt6`, or `subprocess` with a stub
      path) and assert the import succeeds and `diff_props`/`to_html` run. Covers the `models.py`
      + 011 transitive-import audit from T003.
- [ ] T041 [P] Run `ruff check` and `black --check` on `src/gramtrans/Lib/merge_preview.py` and
      the five test modules (line-length 100, target py38); fix findings.
- [ ] T042 Run the full quickstart validation:
      `python -m pytest tests/unit/test_merge_preview_*.py -m "not integration" -v` and confirm
      all 7 quickstart scenarios (quickstart.md) pass.
- [ ] T043 [P] Update module/API docs: ensure `merge_preview.py` docstrings match
      contracts/merge_preview.md (4-tuple cache key; `rtl` render-resolved; coverage
      4/8/3). No `docs/` change required beyond docstrings for this internal module.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: depends on Setup. **T003 (Qt audit gate) and T005 (types) BLOCK all
  user stories.**
- **User Stories (Phases 3–6)**: all depend on Phase 2.
  - US1 (P1) → US2 (P1) → US3 (P2) → US4 (P2) is the recommended order, but see below.
- **Polish (Phase 7)**: depends on all targeted stories.

### User Story Dependencies

- **US1 (diff core)**: after Phase 2. No dependency on other stories. **MVP.**
- **US2 (HTML render)**: needs the types (T005) and benefits from a real `MergePreview` from US1
  for fixtures, but `to_html` can be built/tested against hand-built `MergePreview` literals — so
  US2 can proceed in parallel with US1 once T005 lands.
- **US3 (props fetch)**: after Phase 2. Independent of US1/US2. **T025 (B5 seam) must land before
  the US3 covered-path tests** (T028) — the seam is what makes them runnable without LCM (ordering
  note d.3).
- **US4 (service)**: depends on `diff_props` (T007), `to_html` (T017), `props_for`/seam (T025),
  and `ws_role_map` (T027) — so US4 is last.

### Within Each User Story

- **US1**: T006 (`_segments_for_value`) before T007 (`diff_props` router) before T008 (ordering +
  boundary check). Helper lands before its tests (T009–T016) per ordering note d.5.
- **US3**: T022 (table) → T023/T024 (finders) → T025 (seam) → T026 (fallback) → T027
  (`ws_role_map`). T023 and T024 are independent per-category work but T024 must be reviewed
  against T023's signature so the two-level finder is not collapsed (ordering note d.4).

### Parallel Opportunities

- T002 (test stubs) is [P] with any Phase-2 code-reading.
- Within a story, all test tasks (T009–T016, T018–T021, T028–T032, T035–T039) are [P] — separate
  test files / independent assertions.
- **T023's 7 finders** are mutually independent and can be authored in parallel (different
  functions, one shared table edit — coordinate the table wiring); T024's template finder is the
  8th finder-needed category.
- US1 and US2 can overlap after T005; US3 is fully independent of US1/US2.

---

## Parallel Example: User Story 1 tests

```bash
# After T006–T008 land, run all US1 test cells together:
pytest tests/unit/test_merge_preview_diff.py -k "new_mode"          # T009
pytest tests/unit/test_merge_preview_diff.py -k "multistring"       # T010
pytest tests/unit/test_merge_preview_diff.py -k "merge_keep_empty"  # T011,T012
pytest tests/unit/test_merge_preview_diff.py -k "link_only"         # T013
pytest tests/unit/test_merge_preview_diff.py -k "target_only"       # T014
pytest tests/unit/test_merge_preview_diff.py -k "scalar or repr"    # T015
pytest tests/unit/test_merge_preview_diff.py -k "ordering"          # T016
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 Setup → 2. Phase 2 Foundational (Qt-audit gate T003 + types T005) →
3. Phase 3 US1 (`_segments_for_value` + `diff_props`) → 4. **STOP and VALIDATE**: the mode ×
value-shape matrix (SC-002) passes headlessly. This is the highest-value, independently-testable
slice.

### Incremental Delivery

1. Setup + Foundational → foundation ready.
2. US1 → diff core (MVP) → validate.
3. US2 → legible HTML → validate.
4. US3 → any-category props + fallbacks → validate.
5. US4 → caching service (4-tuple key) → validate.
6. Polish → Qt-free guarantee test + lint + quickstart.

### Ordering gates (from lex-lead directive d)

- **B6 Qt audit (T003) is a gate**, sequenced before any diff code.
- **B5 seam (T025) before US3 covered-path tests (T028).**
- **B4 `_segments_for_value` (T006) before its consumers' tests.**
- After A1 landed in the artifacts, the mode-in-key cross-ref was added to specs/014 and
  specs/015 so the pane and wizard dry-run inherit the 4-tuple key.

---

## Notes

- [P] = different files or independent assertions, no dependencies.
- The whole feature is **read-only** (constitution III): it writes nothing to any project.
- **Mirror-not-import**: `merge_preview.py` MUST NOT import `conflict._deterministic_merge`
  (R1); it reproduces the taxonomy independently (verified in T008).
- Only **4** finders exist today (`conflict._OW_OPS`); T023 (7 simple) + T024 (1 template) add
  the **8** net-new finder-needed categories — do not assume the others exist. MorphRules ==
  templates (one owner-dependent category), not a separate non-template finder.
- Cache key is the **4-tuple** `(category, source_guid, target_guid, mode)` (A1) — a resolution
  flip in-page is a distinct key, not an `invalidate()`.
- `rtl` is **render-resolved** in `to_html`, never stored on `DiffSegment` (A2).
- Commit after each task or logical group; stop at any checkpoint to validate a story.
