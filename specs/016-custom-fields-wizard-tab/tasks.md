# Tasks: Custom Fields Wizard Tab (create-early, fill-later)

**Feature dir**: `specs/016-custom-fields-wizard-tab/` | **Spec**: [spec.md](./spec.md) |
**Plan**: [plan.md](./plan.md) | **Contract**: [contracts/custom-fields-page.md](./contracts/custom-fields-page.md)

TDD-ordered. Reuse from 008/009/010: `_cast` / `_guid_str_from`, target-status logic
(`_build_target_sets` / `_entry_status`), the `leaf_item_picks` enumerate filter (010 T003/T004),
named page accessors (010 T005), tristate group toggles + `_PagePhonology` grouped-tree pattern,
and the fake-handle pattern in `tests/unit/_fakes_*.py` (extend, don't fork).

**Engine reality**: `CUSTOM_FIELDS` today ships a **detect-and-skip** posture
([categories.py](../../src/gramtrans/Lib/categories.py) `custom_fields_plan_action`) because
Phase 3b found `CustomFieldOperations.CreateField` raises `FP_TransactionError` inside the UoW
and raw `AddCustomField` was cited as corrupting schema
(see [us2-blocker-memo.md](../006-inflection-prep-block/us2-blocker-memo.md)). **Resolving that
blocker empirically (T004) is the gate for this entire feature.** If creation stays unreachable,
US3's create-definition path is infeasible and 016 degrades to fill-into-preexisting — a decision
that MUST be made from probe evidence, not assumption.

**Ordering reality**: `transfer.execute` runs `_execute_verb_vertical` + `_execute_layer3`
(where entry/sense/allomorph values are written) **before** the leaf-dispatch loop (where
`CUSTOM_FIELDS` actions currently execute). So a create-definition action left in the leaf loop
would run *after* the values that need it — the wrong order. FR-010 requires a **create-definition
pre-pass** ahead of all value writes (plan.md Design Decision 3a).

**Out of scope**: conflict-mode UI (ADD_NEW/MERGE/OVERWRITE); per-category merge; possibility-list
item travel (governed by existing engine closure); owner classes beyond the four enumerated.

**MCP is source of truth**: all probe/verify tasks run against a live FLEx repo via flextools-mcp
(read-only enumeration always; write probes only against the throwaway `Ejagham Full GT-Test`).

---

## Phase 1: Setup

- [x] T001 [P] Extend `tests/unit/_fakes_custom_fields.py` (create it) with duck-typed fakes (no
  pythonnet): a fake `source_handle` exposing `CustomFields.GetAllFields(cls)` yielding
  `(field_id, name, field_type, list_root_guid)` per owner class, and `.Cache.MetaDataCacheAccessor`
  exposing `GetFieldType`/`GetFieldName`/`GetFieldListRoot`; a fake `target_handle` with a mutable
  in-memory flid registry supporting `CustomFields.FindField(cls, name)` and
  `Cache.MetaDataCacheAccessor.AddCustomField(cls, name, type, list_root)` returning a nonzero flid
  (and a switch to return `0` for the fail-loud test). Cover all four levels
  (`LexEntry`/`LexSense`/`LexExampleSentence`/`MoForm`) plus an empty level.

---

## Phase 2: Foundational (BLOCKS all user stories)

**⚠️ CRITICAL**: the creation-route probe (T004) gates US3; the record extension + classification
(T005–T007) feed every UI story. No page work until this phase is green.

### Research / probe — resolve the Phase-3b blocker (plan.md Phase A)

- [x] T002 [P] Write `specs/016-custom-fields-wizard-tab/research.md` capturing: the
  CellarPropertyType → human-label mapping to display on rows (String / MultiString / Integer /
  GenDate / Boolean / OwningAtomic / "List item" for ReferenceAtom+ReferenceCollection / …),
  the four owner-class → level names, and the identity/not-a-collision policy. Seed it with the
  probe questions T003/T004 answer.
- [x] T003 [P] MCP read-only probe against Ejagham Full GT-Test: enumerate existing custom fields
  via `CustomFields.GetAllFields` per owner class and via `Cache.MetaDataCacheAccessor` (GetFieldType,
  GetFieldName, GetFieldListRoot, IsCustom); confirm the flexicon `CustomFieldOperations` accessor
  names and return shapes. Record actual field types seen and the type→label rows in research.md.
- [x] T004 MCP **write** probe against a freshly-restored throwaway `Ejagham Full GT-Test` ONLY:
  determine whether `Cache.MetaDataCacheAccessor.AddCustomField(class, name, type, list_root)`
  succeeds **inside** the FlexTools UoW envelope (the Phase-3b `FP_TransactionError` context),
  whether it returns a nonzero flid, whether the field survives a FLEx-UI reopen without schema
  corruption, and whether `CustomFieldOperations.CreateField` is still blocked. Also probe
  help/label MDC setter availability. Record the definitive creation route (MDC-direct vs wrapper,
  reachable vs blocked) in `specs/016-custom-fields-wizard-tab/probe-results.md`. **This result is
  the go/no-go for US3's create-definition path** — attach the pre/post evidence.

### Engine — record extension + classification (plan.md Phase B, blocks all UI)

- [x] T005 [P] Unit tests in `tests/unit/test_categories_custom_fields.py` (extend if present) for:
  `_CustomFieldRecord` now carrying `field_type: int` and `list_root_guid`; NEW vs IN_TARGET
  classification by `(owner_class, name)` match; type-difference on a `(class,name)` match yields
  IN_TARGET + a `type_diff_note`, NOT a collision and NOT `IDENTITY_COLLISION`; the type→label
  renderer. All against the T001 fakes.
- [x] T006 Extend `_CustomFieldRecord` in [src/gramtrans/Lib/categories.py](../../src/gramtrans/Lib/categories.py)
  with `field_type: int` and `list_root_guid`, and update `_enumerate_custom_fields` /
  `custom_fields_enumerate_source` to populate them from `GetAllFields` / MDC. Add a
  `custom_field_type_label(field_type)` helper (CellarPropertyType → human label per research.md).
  Preserve the synthetic `guid = "cf:<owner>:<name>"` identity. Makes the T005 record/label tests pass.
- [x] T007 Add a `classify_custom_field(record, target)` helper in `categories.py` returning
  (status ∈ {NEW, IN_TARGET, blank-when-no-target}, optional `type_diff_note`) computed by
  `(owner_class, name)` match; a same-name/same-class field of differing type → IN_TARGET +
  type_diff_note, never a collision (FR-008). Makes the T005 classification tests pass.

**Checkpoint**: engine record carries type + status; creation route decided from probe evidence.

---

## Phase 3: User Story 1 — See every source custom field grouped by level (Priority: P1) 🎯 MVP

**Goal**: the Custom Fields wizard page renders every source custom field grouped by level
(Entry/Sense/Example/Allomorph) with counts, name + data-type labels, all preselected.

**Independent Test**: bind a source with custom fields on multiple levels; open the page; confirm
fields render grouped by level with correct counts + data-type labels, all checked, before any
interaction.

- [x] T008 [P] [US1] Unit test in `tests/unit/test_page_custom_fields.py`: page builds four level
  groups from the enumerated records, each header shows its count, each row shows name + type label,
  every row checked on open; empty level renders empty (not error); source with zero custom fields
  → whole-block toggle unchecked/disabled (not vacuously fully-selected) per Acceptance 1.3.
- [x] T009 [US1] Add `_PageCustomFields(QWizardPage)` to
  [src/gramtrans/Lib/ui/selection_wizard.py](../../src/gramtrans/Lib/ui/selection_wizard.py):
  grouped tree (four level parents from `_CUSTOM_FIELD_OWNER_CLASSES` → Entry/Sense/Example/
  Allomorph), per-row name + type-label + (US4) status column, counts on headers, all preselected,
  NO conflict-mode control. Reuse the `_PagePhonology` grouped-tree scaffold. Makes T008 pass.
- [x] T010 [US1] Add `page_custom_fields()` named accessor to `SelectionWizard`; insert
  `self._page_custom_fields = _PageCustomFields()` and `addPage` it **immediately after**
  `_page_project_ws` and **before** `_page_phonology` (new order: Project+WS → Custom Fields →
  Phonology → Affixes → Skeleton → Grammatical deps → Finish). Wire the page's `context()`/source
  handle from the bound project the same way `_PagePhonology` receives it.
- [x] T011 [US1] Renumber every "Step N of M" title (now M=8) and update the wizard-order regression
  test `tests/unit/test_wizard_page_order.py` to assert Custom Fields is at index 1, Phonology at 2,
  and that no page references a neighbor by literal index (P-1). Confirm all sibling pages reach
  neighbors via named accessors only.

**Checkpoint**: page renders the grouped inventory; wizard order + titles correct (SC-001, SC-007).

---

## Phase 4: User Story 2 — Toggle the whole block off, or trim individual fields (Priority: P1)

**Goal**: whole-block toggle + per-field trim with tristate group toggles; selections flow into the
plan via `custom_fields` callbacks.

**Independent Test**: toggle whole block off → plan creates/fills zero fields; toggle on, deselect
two → plan omits exactly those two.

- [x] T012 [P] [US2] Unit tests in `tests/unit/test_page_custom_fields.py`: whole-block toggle
  off → all level+field rows unchecked and selection contributes no custom-field picks; deselect a
  single field → that field omitted, others retained; all fields in a level deselected → level
  header reads fully-unchecked (tristate consistency) per Acceptance 2.1–2.3.
- [x] T013 [US2] Implement the whole-block tristate toggle (all/none/partial; empty block ⇒
  unchecked+disabled) and per-level AutoTristate headers + per-field deselect in `_PageCustomFields`,
  mirroring 010's `leaf_item_picks` contract. Full block ⇒ omit the key (transfer-all back-compat);
  partial ⇒ emit the selected GUID subset. Makes T012 pass.
- [x] T014 [US2] Fold the page's selection into the Preview `Selection` in `selection_wizard.py`:
  set `CUSTOM_FIELDS` on/off and `leaf_item_picks[CUSTOM_FIELDS]` from the checked rows (synthetic
  `cf:<owner>:<name>` guids), routing through the existing `custom_fields_enumerate_source` filter.
  Confirm `custom_fields_enumerate_source` honors `selection.leaf_item_picks` (add the 010-style
  filter if absent).

**Checkpoint**: none / bare-bones / full selection all produce correct plans (SC-002, SC-003).

---

## Phase 5: User Story 3 — Definitions created before values are filled (Priority: P1)

**Goal** (correctness core): for every selected target-absent field, the plan emits exactly one
create-definition action ordered strictly before all value-fill actions for that field; Move creates
then populates; fail-loud on flid 0; idempotent re-run.

**Independent Test**: select an Entry field absent from target + entries carrying values; Preview
shows create-definition before every fill; Move on a fresh target leaves the field present +
populated.

> **GATED ON T004.** If the probe proves creation unreachable in transaction mode, STOP and escalate:
> implement the detect-and-report degrade instead and record the decision in probe-results.md.

- [x] T015 [P] [US3] Unit tests in `tests/unit/test_categories_custom_fields.py`: selected
  target-absent field → exactly one create-definition `PlannedAction` (kind = create-custom-field);
  selected field present (same class+name) → zero create actions, values target the existing flid;
  `AddCustomField` returning 0 → `RuntimeError`, no orphan (FR-012); re-run with the field already
  present → zero new create actions (idempotency, SC-009); type-difference match → zero create
  actions + no `IDENTITY_COLLISION` (FR-008/SC-006).
- [x] T016 [US3] Rewrite `custom_fields_plan_action` in `categories.py`: for a selected field absent
  from target, emit a create-definition `PlannedAction` carrying `(class, name, field_type,
  list_root_guid)`; for a present field, emit no create action (reuse existing flid); type-diff →
  IN_TARGET note, no create, no `IDENTITY_COLLISION`. Add a `PlannedAction` kind for the non-ICmObject
  MDC write in [models.py](../../src/gramtrans/Lib/models.py) if the existing model can't express it.
- [x] T017 [US3] Rewrite `custom_fields_execute_action` to perform the MDC-direct
  `AddCustomField(class, name, type, list_root)` via the route confirmed in T004; `flid == 0` ⇒
  `RuntimeError` (fail-loud, no orphan); apply help/label via MDC setters if T004 found them exposed.
- [x] T018 [US3] Add the **create-definition pre-pass** to
  [src/gramtrans/Lib/transfer.py](../../src/gramtrans/Lib/transfer.py) `execute`: run all
  `CUSTOM_FIELDS` create-definition actions **before** `_execute_verb_vertical`/`_execute_layer3`
  and before the leaf-dispatch loop, and **remove** `CUSTOM_FIELDS` from `_LEAF_DISPATCH_CATEGORIES`
  so it isn't double-executed after values are written (FR-010 create-early, fill-later). Preserve
  fail-loud bubbling to the runner UoW.
- [x] T019 [US3] Surface the ordering in Preview: `build_run_plan` in
  [src/gramtrans/Lib/preview.py](../../src/gramtrans/Lib/preview.py) must place create-definition
  actions ahead of value-fills in `plan.actions`, and the report must list, per selected field, its
  create-vs-reuse action + count of values to fill (FR-011). Add a unit test asserting 0 ordering
  violations (SC-004).

**Checkpoint**: definitions precede content in plan + Move; fail-loud + idempotent (SC-004, SC-009).

---

## Phase 6: User Story 4 — Know what already exists in the target (Priority: P2)

**Goal**: each row shows NEW / IN TARGET; a same-name field of differing type shows an informational
type-difference note, never a blocking conflict.

**Independent Test**: source=target → all IN TARGET; fresh target → all NEW; same-name different-type
target field → IN TARGET + note, plan still proceeds.

- [x] T020 [P] [US4] Unit tests in `tests/unit/test_page_custom_fields.py`: status column renders
  NEW / IN TARGET by `(class,name)` match; blank when no target bound (degrade to treat-as-NEW for
  preview); type-difference row reads IN TARGET + note and plans no create (Acceptance 4.1–4.3).
- [x] T021 [US4] Render the target-status column + type-difference note in `_PageCustomFields` using
  the T007 `classify_custom_field` helper (mirror 008/009/010 status column). No-target-bound ⇒
  blank status; degrade classification to NEW for preview safety.

**Checkpoint**: every row shows presence status; type-diff is informational only (SC-005, SC-006).

---

## Phase 7: Polish & Cross-Cutting / Verify

- [x] T022 Confirm FR-013 / SC-008: the page presents no ADD_NEW/MERGE/OVERWRITE control and the
  `CUSTOM_FIELDS` Layer-1 default applies without user input; add/confirm an assertion in
  `test_page_custom_fields.py`.
- [ ] T023 [P] Write `specs/016-custom-fields-wizard-tab/quickstart.md` with live Scenarios
  (US1 render, US2 toggle-off, US3 create-before-fill + fresh-target Move + idempotent re-run,
  US4 status + type-diff) against Ejagham Mini → freshly-restored Ejagham Full GT-Test.
- [ ] T024 Add live integration scaffold `tests/integration/test_custom_fields_live.py`
  (skip-by-default, `@pytest.mark.integration`) covering the quickstart scenarios; collects + skips
  cleanly on bare pytest.
- [x] T025 Full regression sweep (`pytest tests/unit/`), confirm zero regressions vs the 633-baseline;
  update the `custom-field-creation.md` contract addendum note (type-diff-not-a-collision override)
  and [STATUS.md](../../STATUS.md) with the 016 handoff + the T004 creation-route verdict.
- [x] T026 **Live MCP verification** (source of truth): run the T023 quickstart against live FLEx —
  dry-run + Move on a fresh target — and attach pre/post artifacts to
  `specs/016-custom-fields-wizard-tab/verification-log.md` per the constitution's verification gate:
  create-before-fill (0 violations), fields present + populated after Move, counts of created vs
  reused + values filled, idempotent re-run (0 new creates), type-diff note non-blocking.

---

## Dependencies & Execution Order

- **Setup (T001)** → no deps.
- **Foundational (T002–T007)** → blocks all stories. **T004 (write probe) is the go/no-go gate for
  US3.** T005–T007 (record + classification) feed all UI stories.
- **US1 (T008–T011)** → after Foundational; the MVP (renders grouped inventory).
- **US2 (T012–T014)** → after US1 (extends the same page).
- **US3 (T015–T019)** → after Foundational; **gated on T004**. Engine-only; independently testable
  against fakes even before UI lands.
- **US4 (T020–T021)** → after US1 (adds a column to the same page); uses T007 classifier.
- **Polish/Verify (T022–T026)** → after all desired stories.

### Parallel opportunities

- T002 + T003 (docs/read-probe) run in parallel; T004 (write probe) is sequential after T003.
- T005 (tests) parallels T002/T003; T006/T007 sequential after T005.
- Within a story, `[P]` test tasks precede implementation and can be authored in parallel with the
  next story's tests. US3 engine work can proceed in parallel with US1/US2/US4 UI work once
  Foundational is green and T004 has resolved the creation route.

---

## Implementation Strategy

### MVP First

1. Phase 1 Setup → Phase 2 Foundational (**T004 gate resolved**) → Phase 3 US1.
2. **STOP and VALIDATE**: the page renders the grouped, preselected inventory (SC-001, SC-007).

### Incremental Delivery

US1 (render) → US2 (toggle/trim) → US3 (create-before-fill correctness core) → US4 (status column).
US3 is the correctness heart and MUST NOT ship on assumption — it ships only on T004 probe evidence.

---

## Notes

- `[P]` = different files, no dependency on an incomplete task.
- Custom fields have **no GUID**; identity is `(owner_class, name)`; synthetic key `cf:<owner>:<name>`.
- Type-difference on a `(class,name)` match is **informational, never a collision** (overrides the
  006 `IDENTITY_COLLISION` framing for this path).
- "Create early, fill later" is a **within-Move ordering** guarantee (definitions before content),
  NOT an out-of-band early write — Principle III preserved; definitions appear in the dry-run.
- Commit after each task or logical group; solo-fork direct-to-main per crew protocol.
