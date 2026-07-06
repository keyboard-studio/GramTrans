---

description: "Task list for Nested Preview Field Gathering (feature 023)"
---

# Tasks: Nested Preview Field Gathering

**Input**: Design documents from `/specs/023-nested-preview-gather/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included — the quickstart enumerates unit-validation scenarios and this module has a
mature pytest suite (`tests/unit/test_merge_preview_service.py`). Write tests before implementation
within each story.

**Organization**: Tasks grouped by user story (US1 P1, US2 P2, US3 P3) for independent delivery.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1 / US2 / US3 (setup, foundational, polish carry no story label)

## Path Conventions

Single project. Implementation under `src/gramtrans/Lib/`, tests under `tests/`. Per the repo Git
Workflow Protocol, all code/test work happens on a **feature worktree**, not `main`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Isolate implementation on a worktree and stage test files.

- [ ] T001 Create feature worktree `../GramTrans-023-nested-preview-gather` on branch `023-nested-preview-gather` from `main` (per repo Git Workflow Protocol); do all Phase 2+ work there.
- [ ] T002 [P] Create test skeleton `tests/unit/test_fingerprints.py` (module-import stub) in the worktree.
- [ ] T003 [P] Create test skeleton `tests/integration/test_nested_preview_e2e.py` (module-import stub) in the worktree.
- [ ] T004 [P] Ensure `tests/unit/test_merge_preview_diff.py` exists (create if missing) for `diff_props` ordering tests.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared data-model + fingerprint plumbing that US1 and US3 both build on. Backward
compatible — all existing scalar categories must remain byte-identical.

**⚠️ CRITICAL**: US1 and US3 cannot begin until this phase is complete. US2 depends only on T012.

- [ ] T005 [P] Write failing tests for the `child_join_token` / `token_hash` content-token contract (allomorph form+morphtype, sense gloss, msa label; collision → ordinal disambiguation; unreadable → degraded token) in `tests/unit/test_fingerprints.py` (contract: [contracts/child-fingerprint-join.md](contracts/child-fingerprint-join.md)).
- [ ] T006 Create Qt-free `src/gramtrans/Lib/fingerprints.py` implementing `child_join_token(kind, obj, *, ws_handle=None)` and `token_hash(token)`; NO PyQt and NO Move-execution imports (research R2, R7).
- [ ] T007 Write failing tests for extended `FieldDiff` (`display_name` default "", `sort_key` default ()) and the ordering rule in `diff_props` (sort by `sort_key` when any present, else alphabetical) in `tests/unit/test_merge_preview_diff.py` (data-model §1).
- [ ] T008 Extend `FieldDiff` dataclass in `src/gramtrans/Lib/merge_preview.py` with `display_name: str = ""` and `sort_key: tuple = ()` (frozen; existing construction sites unaffected).
- [ ] T009 Add optional `meta` param to `diff_props` in `src/gramtrans/Lib/merge_preview.py` (default `None`), stamp `display_name`/`sort_key` onto emitted `FieldDiff`s and apply the ordering rule; `meta=None` path MUST be identical to today (data-model §1, §3).
- [ ] T010 Thread the `meta` map through `MergePreviewService.preview_for` / `_fetch_props` so `props_for` can return `(props, meta)` for entry category while non-entry categories keep `meta=None`; preserve the 4-tuple cache and dict-only caching (FR-013) in `src/gramtrans/Lib/merge_preview.py`.
- [ ] T011 [P] Run the full existing preview suite to confirm zero regressions on scalar categories: `python -m pytest tests/unit/test_merge_preview_service.py tests/unit/test_merge_preview_diff.py -q`.
- [ ] T012 [P] Confirm `_coerce_cf_value` (and a small shared text-coercion for standard `ITsString`/`IMultiString` child values) is available for reuse by both the gather and the CF fallback in `src/gramtrans/Lib/merge_preview.py` (research R6).

**Checkpoint**: Model + fingerprint plumbing ready; existing behavior unchanged.

---

## Phase 3: User Story 1 - See an affix's real content in the preview (Priority: P1) 🎯 MVP

**Goal**: An affix preview shows Morph Type, Sense (gloss + grammatical info), MSA slots/category, and
every allomorph (form/morph-type/environments/comment) — not just Lexeme Form — with per-field
NEW/IN TARGET/SIMILAR status when a target match exists.

**Independent Test**: Select an affix with a populated sense and two allomorphs; confirm the pane
shows the gloss, grammatical info, and both allomorphs distinctly (quickstart "Live validation").

### Tests for User Story 1

- [ ] T013 [P] [US1] Failing unit test: nested gather of a fake entry with 2 senses + 2 allomorphs emits distinct child fields (no collapse), empty children/fields suppressed, in `tests/unit/test_merge_preview_service.py` (contract: [contracts/gather-nested-entry.md](contracts/gather-nested-entry.md); SC-002, FR-008).
- [ ] T014 [P] [US1] Failing unit test: fingerprint join — source/target fakes with matching allomorph forms share a key (per-field status); source-only child → all ADDED; target-only child → target-only, in `tests/unit/test_merge_preview_service.py` (FR-011).
- [ ] T015 [P] [US1] Failing unit test: ordering + display — `display_name` = "Sense 1 ▸ Gloss" / "Allomorph 2 ▸ Form" in source order; child `indent=1`, in `tests/unit/test_merge_preview_service.py` (FR-005, data-model §3).
- [ ] T016 [P] [US1] Failing unit test: child standard string values render as text, never object repr, in `tests/unit/test_merge_preview_service.py` (SC-003, FR-006).

### Implementation for User Story 1

- [ ] T017 [US1] Implement `_gather_entry_nested(handle, obj) -> (props, meta)` in `src/gramtrans/Lib/merge_preview.py`: traverse senses (Gloss, Definition, Grammatical Info label), MSA (Slots, Category), morph type, and allomorphs (`LexemeFormOA` + `AlternateFormsOS`: Form, Morph Type, Environments, Comment); values coerced to text/`{ws:text}`/`list[str]` (research R5; data-model §3, §4).
- [ ] T018 [US1] Build fingerprint-based machine keys + ordinal `display_name`/`sort_key` for each child field using `fingerprints.child_join_token`/`token_hash`; disambiguate collisions first-unused-wins in source order (data-model §2; contract child-fingerprint-join).
- [ ] T019 [US1] Wire `_gather_entry_nested` into `props_for`/`_append_custom_fields` for the resolved `entry` category so entry-level scalars + child fields + child custom fields all land in one dict with the parallel `meta` map; apply `_filter_props` empty/exclusion rules to all new keys (FR-008, FR-009).
- [ ] T020 [US1] Add per-child and per-field containment (each read wrapped; failure logged/noted, never aborts the entry) in `src/gramtrans/Lib/merge_preview.py` (FR-012, SC-005).
- [ ] T021 [US1] Render ordered child groups in `src/gramtrans/Lib/ui/merge_preview_pane.py` using `FieldDiff.indent` + `display_name` (group headers/indentation); keep the pane the only Qt file touched (research R7).
- [ ] T022 [US1] Live validation via FLExToolsMCP against `Ejagham Full GT-Test` affix `n-1`: assert MorphType, Sense gloss `1.n`, Grammatical Info `n:NC`, both allomorph forms, allomorph comment, MSA slots present (quickstart "Live validation"; SC-001, SC-002); record evidence in `tests/integration/test_nested_preview_e2e.py` notes.

**Checkpoint**: MVP — affix preview shows full nested content. Deploy/demo-able.

---

## Phase 4: User Story 2 - Multi-string custom fields are never silently lost (Priority: P2)

**Goal**: Populated MultiString custom fields (e.g. `Plural`) appear in the preview; unrecoverable
reads show a visible note; empty ones are suppressed — never a silent omission.

**Independent Test**: Select an entry with a populated MultiString custom field; confirm its value
appears (or a read-failure note), never simply missing (quickstart; SC-004).

### Tests for User Story 2

- [ ] T023 [P] [US2] Failing unit test: fake CF ops whose `GetValue` raises the ITsMultiString `AttributeError` triggers the direct `{ws:text}` fallback → value shown; empty → suppressed; unrecoverable → read-failure note, in `tests/unit/test_merge_preview_service.py` (contract: [contracts/multistring-cf-read.md](contracts/multistring-cf-read.md); SC-004, FR-007).

### Implementation for User Story 2

- [ ] T024 [US2] Extend `_read_custom_fields` in `src/gramtrans/Lib/merge_preview.py`: on the known MultiString `GetValue` failure, fall back to a direct multi-string read across writing systems (by field flid from `GetAllFields`) returning `{ws_id: text}`; apply `_is_empty_value` suppression (contract multistring-cf-read).
- [ ] T025 [US2] Emit a visible read-failure note (`DiffSegment(kind=NOTE)` + `MergePreview.notes`) when both read paths fail, for the specific field, in `src/gramtrans/Lib/merge_preview.py` (FR-007, data-model §5).
- [ ] T026 [US2] Live validation via FLExToolsMCP against `Ejagham Full GT-Test`: the `Plural` custom field (flid 5002502) is present with a value or a read-failure note on affix entries — never absent (SC-004).

**Checkpoint**: US1 + US2 both work independently.

---

## Phase 5: User Story 3 - Stems and other entry-category items benefit identically (Priority: P3)

**Goal**: The same nested gather applies to stems; a stem preview shows its senses/allomorphs/MSA
with the same fidelity as an affix.

**Independent Test**: Select a stem with two senses; confirm both glosses appear as distinct, ordered
entries (quickstart; SC-002).

### Tests for User Story 3

- [ ] T027 [P] [US3] Failing unit test: nested gather over a fake stem entry (multiple senses) emits both senses distinctly and in source order, in `tests/unit/test_merge_preview_service.py` (US3-AS1, FR-010).

### Implementation for User Story 3

- [ ] T028 [US3] Verify the `entry`-category gather path (T017–T019) applies unchanged to `stems` (both resolve to `entry` in `_resolve_category_key`); add any stem-specific field handling only if a gap is found, in `src/gramtrans/Lib/merge_preview.py` (FR-010).
- [ ] T029 [US3] Live validation via FLExToolsMCP: a stem entry with multiple senses shows all senses/allomorphs nested, matching FLEx (SC-002); record in `tests/integration/test_nested_preview_e2e.py`.

**Checkpoint**: All user stories independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Parity verification, full validation, and merge-back.

- [ ] T030 Preview-vs-Move parity check (SC-006): for an affix present in the target, confirm the nested gather's child field set + child pairing equals what the Move plan-builder (`preview.py`) writes/pairs; document any divergence per contract child-fingerprint-join (quickstart "Preview-vs-Move parity").
- [ ] T031 [P] Run the full quickstart validation and the complete preview test suite: `python -m pytest tests/unit/test_merge_preview_service.py tests/unit/test_merge_preview_diff.py tests/unit/test_fingerprints.py tests/integration/test_nested_preview_e2e.py -q`.
- [ ] T032 [P] Sweep-pattern audit: confirm no other `GetValue`/`ITsString`-repr sibling sites regressed and the child-standard-field reads are consistent; note results in the merge commit body (repo `sweep-pattern` convention).
- [ ] T033 [P] Update module docstrings in `src/gramtrans/Lib/merge_preview.py` (and `fingerprints.py` header) to describe the nested gather, join keys, and MultiString fallback.
- [ ] T034 Merge the feature worktree branch `023-nested-preview-gather` back to `main` after validation; remove the worktree (per repo Git Workflow Protocol).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies — start immediately.
- **Foundational (Phase 2)**: after Setup — BLOCKS US1 and US3. (US2 depends only on T012.)
- **US1 (Phase 3)**: after Phase 2 (needs T006 fingerprints, T008/T009/T010 model+diff+meta).
- **US2 (Phase 4)**: after T012 (coercion helper) — otherwise independent of US1; can run in parallel with US1.
- **US3 (Phase 5)**: after US1 implementation (reuses T017–T019 gather path).
- **Polish (Phase 6)**: after all desired stories complete.

### User Story Dependencies

- **US1 (P1)**: depends on Foundational. Independently testable.
- **US2 (P2)**: depends on T012 only. Independently testable; parallelizable with US1.
- **US3 (P3)**: depends on US1's gather (T017–T019). Independently testable.

### Within Each User Story

- Tests written first and failing before implementation.
- Gather (model) before pane rendering.
- Core implementation before live validation.

### Parallel Opportunities

- Setup: T002, T003, T004 in parallel.
- Foundational: T005 (fingerprint tests) parallel with T007 (diff tests); T011/T012 parallel after their deps.
- US1 tests T013–T016 in parallel; then implementation T017→T018→T019→T020→T021 largely sequential (same file `merge_preview.py`), T021 (pane) parallel with T020.
- US2 (Phase 4) can proceed in parallel with US1 once T012 is done (different code region: `_read_custom_fields`).
- Polish: T031, T032, T033 in parallel; T030 before T034; T034 last.

---

## Parallel Example: User Story 1

```bash
# Launch US1 tests together (all in test_merge_preview_service.py — coordinate or split files):
Task: "Nested gather emits distinct child fields (T013)"
Task: "Fingerprint join per-field status (T014)"
Task: "Ordering + display_name (T015)"
Task: "Child string values render as text (T016)"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1 Setup → 2. Phase 2 Foundational (CRITICAL) → 3. Phase 3 US1 → 4. STOP & validate affix
   `n-1` shows full nested content → demo.

### Incremental Delivery

1. Setup + Foundational → foundation ready.
2. US1 → nested affix preview (MVP) → validate.
3. US2 → MultiString CF no-silent-drop → validate (parallelizable with US1).
4. US3 → stems parity → validate.
5. Polish → preview-vs-Move parity, full suite, merge to `main`.

### Notes

- `[P]` = different files / no incomplete-task dependency. Many US1 impl tasks share
  `merge_preview.py`, so they are sequential despite being one story.
- Keep `merge_preview.py` and `fingerprints.py` Qt-free (feature 012 SC-007; research R7).
- Commit after each task or logical group; final merge-back is T034.
