# GramTrans — Session Handoff

## ▶▶▶ Feature 017 — GOLD_RESERVED Edit-Copy (MERGE-per-WS fill-gaps) CREW-APPROVED (2026-07-05)

**Spec**: [specs/017-gold-reserved-edit-copy/spec.md](specs/017-gold-reserved-edit-copy/spec.md)
**LEX crew**: 4 review cycles, APPROVED (spec+domain+sweep → implement → verify/QC/domain → remediate).
**Tests**: full unit suite **964 passed / 7 skipped / 13 xfailed / 1 xpassed / 0 failed** (+53 new).

### What shipped
- **Shared helper** `_plan_gold_reserved_edit()` in `categories.py` — guard chain: GOLD_INVIOLABLE
  first, then IsProtected layer-2, then MERGE-per-WS comparison on Name/Abbreviation/Description.
  Gaps (empty-in-target) -> `PlannedOverwrite(write_mode="merge")`. All-equal -> Skip(APBG).
  All-conflict -> Skip(APBG) + detail. Mixed -> PlannedOverwrite for gap slots, conflict in summary.
- **6 plan_action functions updated** via the helper: `gram_categories`, `inflection_features`,
  `variant_types`, `complex_form_types`, `semantic_domains`, and `phonological_features` (via
  `_phonology_simple_plan` filtered to `_GOLD_RESERVED_PHONOLOGY_CATEGORIES`; other 4 phonology
  cats unchanged).
- **Executor**: `_execute_gold_reserved_merge()` in `transfer.py` — fills empty-in-target WS slots
  via direct `tgt_ms.set_String()` (not ApplySyncableProperties which overwrites non-empty slots).
  Routed from `_execute_overwrite` for GOLD_RESERVED categories with `write_mode="merge"`.
- **Defect fix**: `merge_preview._find_target_inflection_feature_by_guid` corrected from
  `InflectionClassGetAll()` (returned inflection CLASSES) to `FeatureGetAll()` (inflection FEATURES).
- **merge-preview wiring**: `variant_types`, `complex_form_types`, `semantic_domains` keep their
  `None` mapping in `_CATEGORY_VALUE_TO_KEY` (FR-E13 fallback: summary text rendered without
  per-field before/after columns). Noted as non-blocking follow-up for proper diff-key wiring.
- **Tests**: 53 new in `test_017_gold_reserved_edit_copy.py` covering all 7 cases (a-g) x 6
  categories parametrized; plus phoneme MULTI_INSTANCE guard, helper isolation, merge_preview
  defect regression. Pre-existing `TestInflectionFeatureFinderFix` updated to match corrected behavior.

## ▶▶▶ Feature 016 — Custom Fields Wizard Tab (create-early, fill-later) CREW-APPROVED (2026-07-05)

**Spec**: [specs/016-custom-fields-wizard-tab/](specs/016-custom-fields-wizard-tab/) — spec + plan
+ contract + tasks (26) + research.md + probe-results.md. LEX crew: 6 review cycles, APPROVED.
**Commits (direct-to-main)**: `c0443f7` (fakes/research/tests) · `f7e17ec` (record+helpers) ·
`2ec39ba` (tasks+probe docs) · `03171c0` (UI page US1/US2/US4) · `5193ffe` (handle-lifecycle memo) ·
`18ccd01` (US3 engine T016-T019) · `34a8484` (T026 verify docs) · `b589d6c` (test-pollution fix) ·
`81ed8a6` (list-type 7-arg fix) · `1f59da9` (QC P1/P2 remediation).
**Tests**: full unit suite **911 passed / 7 skipped / 13 xfailed / 1 xpassed / 0 failed**.

### What shipped
- **Custom Fields wizard page** at index 1 (Project+WS → **Custom Fields** → Phonology → Affixes →
  Skeleton → Gram deps → Finish; titles "of 7"), reached via `page_custom_fields()` accessor.
  Grouped by owner level (Entry/Sense/Example/Allomorph), counts, type labels, all preselected,
  whole-block tristate toggle + per-field trim, NEW/IN TARGET status column + type-diff note, NO
  conflict-mode control (Layer-1 MERGE default).
- **Engine**: `_CustomFieldRecord` carries `field_type` + `list_root_guid`; `custom_field_type_label`
  + `classify_custom_field` (type-diff ⇒ IN_TARGET note, never `IDENTITY_COLLISION`, FR-008);
  `custom_fields_plan_action` emits `CreateDefinitionAction` for NEW fields; `leaf_item_picks`
  filter on `custom_fields_enumerate_source` wires per-field trim into the plan.
- **US3 create-early/fill-later** via **PATH-CLOSE-REBIND** in `api.py._ensure_custom_fields` +
  `execute_move`: close the Phase-1 target handle → open a fresh `undoable=True` handle → create
  definitions at `CurrentDepth==0` (`AddCustomField` in `NonUndoableUnitOfWorkHelper.Do`) → close
  (persist) → reopen Phase-1 + re-bind `RunContext`/`RunPlan` → value-fill. `transfer.execute`
  internals unchanged. Fail-loud (flid==0 ⇒ RuntimeError) + idempotent (name+class match).

### Key findings (live-MCP, in probe-results.md — GT-Test restored clean each time)
- **T004 gate GO**: custom-field creation is blocked in Phase-1 mode but works + persists in
  Phase-2/**undoable** at `CurrentDepth==0` — refuted the Phase-3b NO-GO.
- **Single-owner required**: two write handles can co-open in-process, but a secondary handle's
  schema write neither persists nor updates the primary's stale MDC ⇒ PATH-CLOSE-REBIND.
- **T026 PASS**: create → close → Phase-1 reopen → SetValue → reopen persists **both** schema AND
  value (no issue-#21 corruption).
- **AddCustomField signature** (corrects the 006 contract): 4th arg is `destinationClass:Int32`
  (0 for value types), NOT list_root_guid; list root is the **7th** arg. On
  `IFwMetaDataCacheManaged` (cast from `cache.MetaDataCacheAccessor`). List types
  (ReferenceAtomic=24/ReferenceCollection=26) use the 7-arg overload (destinationClass=CmPossibility=7
  + fieldListRoot). Value types: 4-arg/0.

### Non-blocking follow-ups (crew-flagged)
1. **checkState int-vs-IntEnum latent sibling** in `selection_wizard.py` (`_PagePhonology`, predates
   016) — standalone test-fragility cleanup.
2. **G-1 value-fill dispatch is live-only coverage** — `test_execute_action_value_fill_dispatch_skipped`
   is a documented skip; T026 is the live coverage holder. Consider a stub-level harness later.
3. **List-field runtime path unproven on a list-bearing source** — the 7-arg path is implemented +
   reasoned but not yet exercised against a real list-backed custom field (Ejagham corpus has none).

### Next blocking task
**None outstanding from Phase 0.** The prior handoff carried "T-Spike" forward as the next
blocking task — that was **stale**. T-Spike (`transfer_verb_vertical()` → `Lib/preview.py` +
`Lib/transfer.py` Preview/Move split) was **CLOSED 2026-06-19**; Layer 3 was unblocked and
delivered across Phase 3a/3b/3c, and features 010/013/015/016 all built on top of the split.
The only surviving `transfer_verb_vertical` references are historical comments/docstrings in
`Lib/models.py` and `Lib/transfer.py`. Next work is the non-blocking follow-ups listed under
feature 016 above (checkState sibling, G-1 stub harness, list-field runtime path).

---

## ▶▶▶ Feature 010 — Phonology Selector (Model-B) COMPLETE (2026-07-02)

**Branch**: `feature/010-phonology-selector` (off `main`)
**Spec**: [specs/010-phonology-selector/](specs/010-phonology-selector/) — all 30 tasks
resolved (T001–T012 Phase 1–2 in a prior session; **T013–T030 this session**).

### Shipped this session (Phases 3–8)

| Phase | Tasks | What |
|-------|-------|------|
| 3 (US1) | T013–T016 | `_PagePhonology` at wizard index 1 (grouped tree, 5 preselected category groups, counts on headers, target-status column, NO conflict-mode control per FR-012/SC-008); step titles now "of 7"; `collapse_phonology` picks merged into the Preview `Selection`. |
| 4 (US2) | T017–T019 | Tristate whole-block toggle (empty block ⇒ unchecked+disabled) + per-category AutoTristate headers + per-item deselect ⇒ `leaf_item_picks` subsets; full categories omit the key (transfer-all). |
| 5 (US3) | T020–T021 | Confirmed strata gating lives in `collapse_phonology` ({STRATA: True} iff a rule kept); strata never a group/row. |
| 6 (US4) | T022–T023 | Target-status column rendered; extended `build_phonology_inventory` to compute SIMILAR by casefolded label match (mirrors 008/009 `_entry_status`) alongside IN TARGET / NEW / blank. |
| 7 (US5) | T024–T026c | Shared `_phonology_excluded_lossy_for(wizard)` feeds intra-phonology missing-reference warnings into BOTH the Preview StatsPanel (`extra_excluded_lossy`) and the Finish Move gate's shared `el_count` (ONE consolidated dialog, FR-011). KL-010-1 Principle-V guard: kept metathesis/reduplication rule + NC/phoneme trim ⇒ coarse notice into the same gate. |
| 8 (Polish) | T027–T030 | Live integration scaffold `tests/integration/test_phonology_live.py` (Scenarios A–E, skip-by-default); regression sweep; this handoff + KL-010-1 backlog. |

### Test totals

- Unit: **633 passed**, 6 skipped, 13 xfailed, 1 xpassed (baseline was 624 passed;
  +9 new: 2 US1, 3 US2, 1 US4, 3 US5). The absent-`leaf_item_picks`-key back-compat
  contract held — zero regressions.
- Integration: `test_phonology_live.py` collects and skips cleanly (6 skipped); **live
  execution against Ejagham Mini → Ejagham Full GT-Test is deferred to a human session**
  with the FlexTools MCP active (quickstart.md prerequisites: fresh target restore).

### Post-010 backlog

- **KL-010-1 (metathesis/reduplication reference traversal)** — the EXCLUDED-LOSSY
  reference traversal in `build_phonology_inventory` covers `PhRegularRule` only
  (`StrucDescOS` + `rhs.Left/RightContextOA`). It does NOT traverse `PhMetathesisRule`
  (`Left/RightPartOfMetathesisOS`) or `PhReduplicationRule`
  (`Left/RightPartOfReduplicationOS`) part-sequences, whose `IPhSimpleContext*` entries
  can also reference NCs/phonemes. **Interim guard shipped** (T026b): a kept
  metathesis/reduplication rule + an NC/phoneme trim surfaces a coarse "reference check
  not supported" notice into the Move gate rather than transferring silently. **Fix**:
  extend `_rule_context_refs` to walk those two part-sequences + add
  metathesis/reduplication fixtures to `tests/unit/_fakes_phonology.py`. Safe to defer —
  the Ejagham corpus is `PhRegularRule`-only.

### Next pickup checklist (feature 010)

1. **Run the live Scenarios A–E** (`pytest tests/integration/test_phonology_live.py -m
   integration -v`) with Ejagham Mini open + a freshly-restored Ejagham Full GT-Test.
   Verify/adjust the quickstart count anchors (32 phonemes, 5 NCs, 2+ envs) inline.
2. **Optional** `/lex-lead` review cycle on the finished UI before merging to `main`
   (spec + plan already passed cycles 1–3).
3. **Then** close KL-010-1 if a metathesis/reduplication-bearing source becomes available.

---

**Updated**: 2026-06-21 (22:50 close-sweep)
**Branch**: `main`
**Phase**: Phase 3b **CLOSED** — all 41 tasks resolved (4 deferred-with-rationale; 37 shipped). US2 creation still blocked at flexicon layer (detect-and-report posture adopted). Phase 3c spec scaffolded at [specs/007-affixes-stems/](specs/007-affixes-stems/) — memo steps 14-18 (affixes, ad-hoc / compound rules, slots, affix templates, stems).

### Phase 3b close-sweep (2026-06-21 22:50)

- Unit suite: **324 passed, 5 skipped**
- Integration suite: **18 passed, 15 skipped** (all skips are live-FlexTools-required)
- Live-MCP gate: GREEN across Runs 1-3 in [specs/006-inflection-prep-block/verification-log.md](specs/006-inflection-prep-block/verification-log.md)
  - Run 1 (`194438a`): US1 Preview/Move — `InflectionFeatures` accessor fix landed; `gram_categories` semantic mismatch surfaced
  - Run 2 (`798dc0b`): US1 re-run after `gram_categories` → `project.POS` retarget — POS 20→21
  - Run 3 (`beeb60c`): US3 Preview/Move — VariantEntryTypes 12→13; 1792 GOLD semantic-domain skips; 5 source GUIDs verified
- Deferred tasks (4): T017 / T019 / T020 (US2 creation pending Phase 2 transaction mode), T039 (Scenario B/E regression — Runs 1-3 are write-mode evidence on same target)
- Open Scenario C (FR-327 feature-constraint closure) — requires a source with variant types carrying non-empty `InflFeatsOA`; unit-test coverage exists

### Note for future sessions — IDENTITY vs GUID skip semantics

US2 uses two distinct `SkipReason` codes for already-present detection:

- `ALREADY_PRESENT_BY_GUID` — real LCM Guid match (used by every other category with first-class ICmObject identity)
- `ALREADY_PRESENT_BY_IDENTITY` — Phase 3b US2 only. Custom fields have no LCM Guid; identity is the `(class_id, name)` tuple. The synthetic guid `cf:<owner>:<name>` is an internal key, not an LCM identity.

This distinction was deliberate (lex-domain ruling, cycle 3). Do not collapse the two codes when adding new no-Guid categories — pick `ALREADY_PRESENT_BY_IDENTITY` for tuple-keyed identity matches; reserve `ALREADY_PRESENT_BY_GUID` for real Guid matches.

### Phase 3c deferred items

- `contracts/custom-field-creation.md` still describes the would-be `AddCustomField` write path; rewrite during Phase 3c doc sweep.
- Colon-in-name guid escaping fragility on `_CustomFieldRecord` (benign now, fragile if guid ever parsed). Phase 3c.

### Phase 3b close-sweep deferred items (per LEX crew cycle 2-3, 2026-06-21)

- **Rename `GRAM_CATEGORIES` enum -> `PARTS_OF_SPEECH`** at next API-break window. Enum string `"gram_categories"` is a public serialized-plan surface; retargeted now (Option B per cycle 2) to unblock US3 + Scenario C live verification while preserving plan compatibility. Update dispatch tables in `preview.py` + `transfer.py` and all selection-dict references in the same atomic commit.
- **Add new `FEATURE_STRUC_TYPES` category** targeting `MsFeatureSystemOA.TypesOC` via `project.GramCat`. Salvages the pre-Option-B Phase 0 callback bodies (they correctly handle IFsFeatStrucType creation — just under the wrong label). Fills the ordering-memo gap: no current row exists for the feature-struct-type list.
- **Spec-006 US1 clarification**: document the two-path setup (Phase 0 verb-vertical closure handles real POSes via `_select_source_poses` / `_plan_pos_closure`; Phase 3b leaf-dispatch `GRAM_CATEGORIES` callbacks handle the same target via the leaf-dispatch loop). The verb-vertical collision guard in `gram_categories_execute_action` covers the dual-dispatch case.
- **Pattern audit** (lex-qc P2): sweep all `project.<Accessor>.GetAll()` callsites in `categories.py` against the flexicon fork's actual accessor names + the spec's claimed LCM collection. Two same-shape bugs (`InflectionFeature`/`InflectionFeatures` accessor mismatch, `GramCat`/`POS` collection mismatch) caught this session; a third could be hiding.

---

## ▶▶▶ Phase 3b session — 2026-06-21

### Shipped

| Commit | What |
|--------|------|
| 6beac7a | T001-T003 — `SEMANTIC_DOMAINS` enum + 4 stub registry entries + `_LEAF_DISPATCH_CATEGORIES` extended in preview.py + transfer.py |
| df77c9b | T004-T008 — MCP probes against Ejagham Full GT-Test (probe-results.md) |
| 50480d4 | T011-T012 (US1) — leaf-dispatch smoke (4 tests covering all 9 Phase 3b categories) |
| 61704ba | US2 BLOCKED memo — `CreateField` raises `FP_TransactionError` inside Phase-1 UoW; raw `AddCustomField` corrupts schema |
| 1b457d3 | US3 — variant_types + complex_form_types + semantic_domains full 5-callback implementations + 18 unit tests |

### Key probe findings (probe-results.md)

- `ICmPossibilityFactory` / `IPartOfSpeechFactory` / `ICmSemanticDomainFactory`: `Create(Guid, parent)` — Guid-mandatory.
- `MetaDataCacheAccessor.AddCustomField` returns Int32 flid; 0 == fail-loud.
- `ILexEntryTypeFactory` / `ILexEntryInflTypeFactory`: 0-method stubs in MCP catalog → use `Cache.ServiceLocator.GetInstance[T]()`. Variants use `ILexEntryInflType` (has `InflFeatsOA`), complex use base `ILexEntryType`.
- `InflFeatsOA` is **Owning Atomic** (single struct), NOT OS as initial spec assumed. Walk `InflFeatsOA.FeatureSpecsOC` → each `IFsFeatureSpecification.ValueRA.Guid`.

### US2 blocker (custom_fields)

`flexicon.CustomFieldOperations.CreateField` refuses to run inside an open
UoW with `FP_TransactionError`. Phase-1 transaction mode (the default in
flexicon `OpenProject`) keeps that envelope open for our entire
`transfer.execute()`. Raw `IFwMetaDataCacheManaged.AddCustomField` bypass
produces corrupt records on next FLEx UI open (per the flexicon docstring).

T014-T020 deferred. Unblock requires either:
1. flexicon exposes a `transaction_mode='direct'` flag on `OpenProject`.
2. Split `MainFunction` into schema-pre-pass + transaction-pass with separately-opened direct-mode handle.
3. Document a manual user workaround and ship without automation.

See [specs/006-inflection-prep-block/us2-blocker-memo.md](specs/006-inflection-prep-block/us2-blocker-memo.md).

### Test totals (end of session)

- Unit: **309 passed, 5 skipped** (was 287 at session start; +22 net)
  - +4 dispatch-smoke tests (test_phase3b_leaf_dispatch.py)
  - +18 US3 callback tests (test_categories_phase3b_us3.py)
- Integration: unchanged (host-required scaffolds still skipped)

### Next pickup checklist

1. **Resolve US2 blocker.** Choose one of the three remediation paths in the memo. The cleanest is path (2): two-phase `MainFunction` with a schema-pre-pass. Requires confirming flexicon exposes a direct-mode `OpenProject` flag.
2. **Live MCP verification of US1+US3** — Scenarios A.1, A.3, C in quickstart. Defer Scenario B (overwrite re-run) until a non-empty US3 source is available. Defer Scenario D (FR-308) — covered by dispatch smoke.
3. **Phase 3c spec** — memo steps 14-18 (affixes, ad-hoc/compound rules, slots, affix templates, stems). The leaf-dispatch pattern from 3a/3b extends naturally to these, modulo the heavy-category surfaces (affixes/templates/MSA) that don't fit the pure-leaf shape.

---

## ▶▶▶ Phase 3a CLOSED (2026-06-20 23:25)

---

## ▶▶▶ Phase 3a CLOSED (2026-06-20 23:25)

Phase 3a finished cleanly. The phonology+strata block transfers via
live MCP, FR-307 idempotency holds against Phase 0/1/2 verb-vertical,
empty-source UX lines render correctly, and all four pre-existing
Phase 0 orphan risks are now hardened with the `_safe_add_to_owner`
helper.

### Closeout work (after Phase 3a US1 ship)

| Commit | What |
|--------|------|
| 82d8664 | STATUS handoff after US1 ship |
| 3863ed2 | P0-A..D Phase 0 orphan hardening (`_safe_add_to_owner`) + 2 tests |
| (this)  | US2 strata smoke tests, US3 Scenario D live verify, US4 empty-source UX (FR-308), final regression |

### US2 (Strata)

Data path already shipped in 608b72c.  Ejagham Mini has 0 strata, so
live MCP verification deferred until a strata-bearing source is
available.  Unit smoke tests added: 3-strata enumeration→plan, partial
overlap (2 actions + 1 ALREADY_PRESENT_BY_GUID skip).

### US3 (PhEnv idempotency) — **LIVE VERIFIED**

Quickstart Scenario D probed via MCP: verb-vertical Phase 0/1/2
closure with `enable_overwrite=True` over Ejagham Mini → Ejagham Full
GT-Test after the phonology block had already populated environments.
Result: **0 `ph_environment` CREATE actions**, 2 overwrites, 4
ALREADY_PRESENT_BY_GUID skips.  FR-307 idempotency holds — the
phonology-block relocation is invisible to existing Phase 0/1/2
callers.

### US4 (Empty-source UX, FR-308)

`Lib/models.py.RunReport` gains `empty_categories: tuple = ()` field.
`Lib/report.py._build_from_plan` derives it from
`plan.selection.categories` minus the categories that produced
any actions/skips/overwrites.  `render_text_summary` emits
`[skip] no items in source for X` per FR-308.  Unit test confirms.

### Test totals

- 287 unit + 18 integration = **305 passing**, 20 skipped (all
  live-FlexTools-required).
- +5 from US1 ship: 2 US2 strata smoke, 1 US4 render, 2 P0 helper.

### Phase 3a session inventory

| Commit | Scope |
|--------|-------|
| c224e00 | spec |
| 072dddb | plan + research + data-model + contracts + quickstart |
| a6ac58c | tasks.md (47 tasks) |
| ac8a6b9 | T001-T010 setup + foundational MCP probes |
| 384de7c | T011-T029 US1 (six category callbacks + 29 tests) |
| 608b72c | T030-T034 leaf-dispatch wiring + `_create_with_guid` hardening + SegmentsRC wiring |
| 82d8664 | STATUS handoff |
| 3863ed2 | P0-A..D Phase 0 orphan hardening |
| (this)  | US2/US3/US4 + Polish |

### Next session

- **Phase 3b spec kickoff**: morphology block (memo steps 6-13: POS,
  inflection features, custom fields, inflection classes, stem names,
  exception features, variant types, complex form types, semantic
  domains).  Several leaf callbacks are already COMPLETE in
  categories.py from Phase 0; Phase 3b is largely wiring them through
  the leaf-dispatch loop that landed in 608b72c.
- Optional follow-up: QC P1-A — phonology categories' Carrier-B
  residue silently no-ops when target `Description` is absent.  Not
  blocking but residue tags aren't landing on disk for the new
  categories the same way they do for Phase 1's snap+merge writes.
  Probe via MCP first to confirm scope.
- US2 live MCP probe against a strata-bearing source project (when
  one becomes available).

---

## ▶▶▶ Phase 3a US1 complete (2026-06-20 23:00)

### Ship state

Phase 3a MVP — the six self-contained phonology+strata categories from
[specs/005-phonology-block/](specs/005-phonology-block/) per the
validated 22-step ordering memo — transfers end-to-end via the live
MCP path. Commits since 4c3cd1a (Phase 3 memo):

| Commit | Tasks | What |
|--------|-------|------|
| c224e00 | spec | FR-301..311, 4 user stories, 6 entities, quality checklist green |
| 072dddb | plan | research.md R1..R10 + data-model + contracts + quickstart |
| a6ac58c | tasks.md | 47 tasks across 7 phases; MVP = phases 1+2+3 (29 tasks) |
| ac8a6b9 | T001-T010 | enum + stubs + MCP probes (all factories support Create(Guid)) |
| 384de7c | T011-T029 | six category callbacks (phon_features, phonemes, NCs, ph_env, phon_rules, strata) + 29 unit tests |
| 608b72c | T030-T034 | leaf-dispatch wiring in preview.py + transfer.py; _create_with_guid hardened; SegmentsRC wiring; +4 cycle tests |

### Live MCP verification (write-mode, Ejagham Mini → Ejagham Full GT-Test)

- **PLAN**: 39 actions (32 phonemes + 5 NCs + 2 envs) + 2 PH_ENV skips
  (already present by GUID).
- **MOVE**: 39 actions executed via leaf-dispatch in **0.074 s**.
- **DELTA**: target phonemes 32→64, NCs 5→10, envs 3→5.
- **SegmentsRC matched on all 5 natural classes** (22 + 4 + 4 + 7 + 7
  phoneme references wired correctly). P1-C lex-qc finding resolved.
- `lcm_undoable_action_count = 42` (proper transaction).
- Zero warnings, zero errors.
- "Needs professional help" dialog did NOT recur on this write-mode run.

### Cycle 1+2 lex-lead crew work (this session)

- **lex-programmer** hardened `_create_with_guid`: removed no-arg
  Create() fallback; Add-after-Create-failure surfaces RuntimeError
  with "Orphan risk" message instead of silently leaking; +2 tests.
- **lex-qc** swept categories.py for sibling orphan risks. Found 4 P0
  sites in pre-existing Phase 0 categories (inflection_features value
  loop, gram_categories hand-rolled Create+Add,
  inflection_classes, stem_names) — out of scope for Phase 3a US1
  because none are enabled in Scenario A's Selection; tracked for the
  next commit (item #2 in next-up below).
- **lex-programmer cycle 2** wired SegmentsRC on natural_classes
  execute_action + deleted the P1-B dead `_apply_props_and_residue`
  helper; +2 tests.
- 282 unit tests pass (249 + 29 phonology surface + 2 orphan hardening
  + 2 SegmentsRC wiring).

### Next up

1. **Apply `_create_with_guid`-style hardening to P0-A..D** in Phase
   0 categories (inflection_features, gram_categories,
   inflection_classes, stem_names). Same shape as 608b72c; one
   commit. Eliminates latent orphan risk before any future Selection
   enables them.
2. **Phase 3a US2 (strata)**: data path already shipped in 608b72c;
   needs a Scenario A re-run with Strata enabled + a smoke test in
   tests/integration. Trivially close-out task.
3. **Phase 3a US3 (PhEnv idempotency)**: confirm Phase 0/1/2 allomorph
   closure produces zero new env creates when phonology block has
   already populated them. Quickstart Scenario D.
4. **Phase 3a US4 (empty-source UX)**: `[skip] no items in source for
   X` log lines per FR-308.
5. **Phase 3a Polish (T043-T047)**: full regression sweep + STATUS.md
   final + commit topic-aligned increments.
6. **Phase 3b spec** kickoff (memo steps 6-13: POS, inflection
   features, custom fields, inflection classes, stem names, exception
   features, variant types, complex form types, semantic domains).
   Most leaf categories already COMPLETE in categories.py from earlier
   sessions — Phase 3b is largely wiring them through the existing
   leaf-dispatch loop that landed in 608b72c.

---

## ▶▶▶ Phase 2 complete + Phase 3 memo (2026-06-20)

### Phase 2 ship state

All four user stories of Phase 2 ([specs/003-phase2-interactive-merge/](specs/003-phase2-interactive-merge/)) shipped this session:

- **US1 — per-conflict prompt** (commits af7da6b, 34c34dd): `detect_conflicts` + `_apply_merge_decisions` + executor wiring + `ConflictDialog` (PyQt5).
- **US2 — WS-mapping wizard** (4cf1f9c): `detect_ws_mismatches` + `fold_choices_into_ws_mapping` + `WSWizard` (PyQt5).
- **US3 — prior-run decision recall** (9b1715b): `load_prior_log` / `load_prior_decision` + ConflictDialog pre-fill.
- **Phase 2 wiring** (c050aa1): `phase2_interactive_move()` entry helper threading WS wizard → plan → ConflictDialog → execute. **Live MCP verified** end-to-end against Ejagham Mini → Ejagham Full GT-Test with FakeResolver doubles: 0 WS mismatches, 14 conflict prompts collected, all answered TAKE_SOURCE, 67 overwrites applied in 1.43s, zero errors.

**Test totals: 267 unit + integration tests green, 20 skipped (all live-FlexTools required).**

Residue tag wire format extended to 4-or-5-or-6 segments:
```
GT|<run_id>|<source>|<iso_ts>[|snap=<base64>][|merge=<base64>]
```

### Phase 3 readiness — validation memo

[specs/004-phase3-pipeline/ordering-memo.md](specs/004-phase3-pipeline/ordering-memo.md)
is the artifact for the next session. It confirms the **22-step
import ordering + 2 post-passes**, MCP-validated for every cross-reference:

1. WS → 2. PhonFeatures → 3. Phonemes → 4. NaturalClasses → 4b. **PhEnvs** *(moved here, was bundled with allomorphs)* → 5. PhonRules → **5b. Strata** *(new; MCP-confirmed RA from templates/MSAs/compound rules)* → 6. POS → 7. InflectionFeatures → 8. CustomFields → 9. InflectionClasses → 10. StemNames → 11. ExceptionFeatures → 12. VariantTypes → 13. ComplexFormTypes → **13b. SemanticDomains** *(user: in scope)* → 14. **Affixes** (LexEntries + owned children) → 15. **AdHoc + Compound Rules** *(moved AFTER affixes — single structural correction from user's draft)* → 16. Slots → 17. AffixTemplates + **17.1 MSA-slot wiring** *(deferred from #14)* → 18. **Stems** (LexEntries + owned children) → **post-pass A** *(inter-entry refs)* → **18b. ReversalIndices** *(user: in scope)* → 19. **Texts** *(user-picker driven; new `texts_picker.py` dialog)* → 20. **WordformAnalyses** *(human-only; source-wins; machine analyses ephemeral)* → **post-pass B**.

**Resolved open questions** (in memo):
- Audio WSes treated like any other WS in the wizard.
- Semantic domains + reversal indices both in scope.
- WfiAnalysis evaluation conflicts: human-only, source wins.
- Texts: user-picked subset via new PyQt picker.

**Owned vs Referenced** principle now explicitly carried as the
guiding rule: OA/OS/OC come with parent, RA/RS/RC must already exist
in target or be deferred to a later step.

### Implementation gap (for Phase 3 specification)

| Status | Categories |
|--------|-----------|
| **COMPLETE** | gram_categories (POS-internals subset), inflection_features, inflection_classes, stem_names, exception_features |
| **PARTIAL (verb-vertical hardcode)** | writing_systems_check, pos, entry, sense, msa, allomorph, ph_environment |
| **STUB** | custom_fields, variant_types, complex_form_types, adhoc_rules, compound_rules, affixes, templates |
| **ABSENT from enum** | phonological_features, phonemes, natural_classes, phonological_rules, strata, semantic_domains, reversal_indices, texts, wordform_analyses |

Next session's first move: `/speckit-specify` for Phase 3 driven by the
ordering memo. Suggested first slice — **phonology block (steps
2-5 + 5b Strata + 4b PhEnvs)**: 5-6 new self-contained categories with
no LexEntry coupling.

### Phase 1 ship state (reference; shipped earlier in the session)

FR-101..110 all live-verified — commits:
- e6cde61 — Phase 1.1 Entry + Sense overwrite via direct GUID
- e129b72 — Phase 1.2 MSA + Allomorph overwrite via fingerprint matching
- e5f322c — Phase 1.3a PhEnvironment overwrite via enable_overwrite
- 1097df5 — Phase 1.3b FR-106 pre-overwrite snapshot in residue tag
- aecd565, 50f873d — Phase 1.3c v1+v2: residue carrier-write fix (LiftResidue is Unicode single-string on Layer 3 LCM classes; setattr-on-None lands `snap=` on disk)
- f4cdd9c — Phase 1.4 FR-107 custom-field deduplication

### Manual TODO (not blocking Phase 3)

- **PyQt click-through verification**: open FlexTools, load Ejagham Full GT-Test, run `phase2_interactive_move()` without fake resolvers — confirm the QDialog renders, radios select, Apply commits, Cancel aborts. ~30 min, no code changes.

---

## ▶▶▶ Multi-POS walker + leaf categories + Phase 1 scaffold (2026-06-20)

---

## ▶▶▶ Multi-POS walker + leaf categories + Phase 1 scaffold (2026-06-20)

Phase 0 verb-vertical is now general-purpose:

- `Lib/preview._select_source_poses(source, selection)` returns the list of
  source POS objects to walk based on `selection.pos_picks` (frozenset of
  GUIDs). Empty `pos_picks` + any POS-closure category on → walks every
  top-level POS in source.
- `Lib/preview._plan_pos_closure(...)` and `_plan_layer3_for_pos(...)` take
  `src_pos` and run the same POS → Template → Slot → Entry → Sense → MSA
  → Allomorph → PhEnvironment walk per POS.
- `Lib/transfer.execute` iterates `_pos_guids_from_plan(plan)` (derived
  from the plan's POS PlannedActions + POS Skips) and calls
  `_execute_verb_vertical` + `_execute_layer3` for each, threading
  `src_pos_guid` through.
- `Selection.pos_picks: frozenset[str]` added per the spec model.

Live MCP verification on freshly-restored target with
`pos_picks=frozenset({verb_guid})`: **same 67 actions, 0 skips, 0.709s,
lcm_undoable_action_count=69** — byte-equivalent to the pre-multi-POS run.

**Leaf categories** implemented in `Lib/categories.py` (Stream 2 of the
parallel work):

- `gram_categories` (GOLD-aware via `CatalogSourceId`)
- `inflection_features` (GOLD-aware; co-creates IFsSymFeatVal values)
- `inflection_classes` (no GOLD; `IMoInflClassFactory.Create(Guid)`)
- `stem_names` (no GOLD; `IMoStemNameFactory.Create(Guid)`)
- `exception_features` (no GOLD; ref-wire only via target POS lookup)

Stubs remain for `custom_fields`, `variant_types`, `complex_form_types`,
`adhoc_rules`, `compound_rules`.

**Phase 1 scaffold** (Stream 3):

- `specs/002-phase1-overwrite/` with `spec.md` (FR-101..110 + SC-101..103)
  and stubs for plan/research/data-model/quickstart/tasks.
- `src/gramtrans/Lib/matcher.py`: `Match` frozen dataclass +
  `lookup_target(source_guid, category, target, *, source_obj,
  identity_remap, fingerprint_fn) → Match` that resolves via direct GUID
  hit → identity_remap fallback → fingerprint fallback. Fingerprint
  registry seeded with `fingerprint_for_msa` + `fingerprint_for_allomorph`.

**Tests**: 141 unit (up from 101) + 5 integration scaffolds skipped on
bare pytest.

Non-fatal stderr warnings during the multi-POS Move run: 26 instances of
`LexSenseOperations.GetSyncableProperties: 'ILangProject' object has no
attribute 'PublicationsOA'`. Silently skipped by the BaseOperations
patch's `cannot be converted to SIL.LCModel.` clause; queue for fork-level
cleanup in Phase 0.5.

## ▶▶ Layer 3 end-to-end transfer landed (2026-06-19 night)

After T-Spike closure, Layer 3 (LexEntry / LexSense / MSA / Allomorph /
PhEnvironment) was implemented and MCP-verified live against the Layer-1+2
target. Full run:

- **59 added, 8 skipped, wall-clock 0.387s, `lcm_undoable_action_count=62`**
- 13 LexEntries + 13 LexSenses with **GUIDs preserved** (LCM factory accepts
  `Create(Guid, owner)` on these)
- 13 MoInflAffMsas + 20 MoAffixAllomorphs created with new GUIDs (LibLCM's
  `IMoInflAffMsaFactory.Create(ILexEntry, SandboxGenericMSA)` and
  `IMoAffixAllomorphFactory.Create` don't expose Guid overloads;
  `identity_remap` captures the mapping per FR-012). Used flexicon's
  `MSAOperations.CreateInflAff(sense, pos, slots)` wrapper for the
  SandboxGenericMSA dance.
- 12 of 13 MSAs wired to a slot via `SlotsRC` (by GUID lookup against
  target Layer-2 slots); 1 unbound (the `ro~-` affix) — matches the MCP
  inventory's prediction exactly.
- 2 PhEnvironments shared with the target's FW-template defaults → reused
  via `Skip(ALREADY_PRESENT_BY_GUID)` and resolved from `target.Environments`.
- Allomorph `PhoneEnvRC` re-wired to the (reused) target environments.

**Fork patches landed during this work** (all under
`D:/Github/_Projects/_LEX/flexicon/flexicon/code/Lexicon/`):

- `LexEntryOperations.py`, `AllomorphOperations.py`, `LexSenseOperations.py`,
  `ExampleOperations.py`, `EtymologyOperations.py`, `LexReferenceOperations.py`,
  `PronunciationOperations.py` — all rewritten to enumerate writing
  systems via `self.project.WritingSystems.GetAll()` returning
  `CoreWritingSystemDefinition` objects (`.Handle`, `.Id`) instead of the
  nonexistent `GetAllWritingSystems()` / `GetWritingSystemTag(handle)` methods.
  Same fix pattern that was already applied to the Grammar Operations.

**Resolved 2026-06-19 night (Phase 0.5 patches):**

- Patched fork's `BaseOperations.ApplySyncableProperties` to handle two
  setattr gaps: (a) ITsString-typed string properties (raw `str` →
  `TsStringUtils.MakeString(value, default_ws)`); (b) object-reference
  properties (e.g. `MorphoSyntaxAnalysisRA`) where setattr-with-str fails
  with `cannot be converted to SIL.LCModel.<Iface>` — silently skip those,
  the caller wires cross-project references explicitly.
- Added explicit `MorphTypeRA` wiring in `_create_allomorph_with_guid` via
  GUID lookup against the target's `LangProject.LexDbOA.MorphTypesOA`
  possibility list (morphtype GUIDs are FW-global, shared across projects).
- Re-ran a clean Layer 1+2+3 end-to-end (full 67 actions, 0 skips) on a
  freshly-restored target. Result: 13/13 entries carry their lexeme form
  text AND morphtype reference — verified by reading back the headwords:
  `n~-1`, `n~-2`, `e~-`, `ro~-`, `a~-`, `ń~-3`, `ń~-2`, `o~-1`, `o~-2`,
  `á~-`, `kí~-`, `-k`, `ń~-1`. Wall clock 0.512s.
  `lcm_undoable_action_count=69`.

**Remaining (cosmetic)**:

- LexEntry/LexSense/MSA residue tags currently fall through to a Carrier B
  attempt that no-ops (those classes expose neither `LiftResidue` (None on
  fresh-created) nor `Description`). The residue trail is recoverable via
  `RunReport.identity_remap` + the per-allomorph PhoneEnvRC structure. A
  follow-up could explicitly initialize `LiftResidue` on these classes
  post-create.
- Homograph numbering (`-1`, `-2`, `-3`) is regenerated by FLEx based on
  how many entries share a form; matches source incidentally because the
  Verb-affix set is identical. With a non-empty pre-existing target,
  homograph numbers may shift.

## ▶ T-Spike step 3 fully closed (2026-06-19 evening)

Fresh-target Move re-run executed end-to-end through the new `Lib/preview` +
`Lib/transfer` pair against a `FieldWorks.exe -restore`-d Ejagham Full GT-Test:

- Preview produced 6 PlannedActions, 0 skips (correct — target was empty for these GUIDs)
- Move created POS `86ff66f6` 'Verb' + template `821a96d6` + 4 slots, all GUIDs preserved
- Run report: 6 added, 0 skipped, **wall-clock 0.082s** (vs SC-001's ≤5min budget)
- `lcm_undoable_action_count: 7` — `Ctrl+Z` reverts the entire run
- All 6 freshly-created objects carry parseable Carrier-B residue tags with run_id `GT-20260619-222958`
- Snapshot artifact at `tests/integration/_snapshots/spike_close_post.json`

**Constitution v5.0.0 Principle III closing-clause is now mechanically satisfied.**
Layer 3 (MSA / Allomorph / Environment) is unblocked.

## Late-session MCP verifications (2026-06-19, post-T-Spike)

Four MCP-driven checks against live LCM, all PASS:

1. **T-Spike step 3 (post-spike state)**: new `Lib/preview.build_run_plan` walked
   Ejagham Mini → Ejagham Full GT-Test and emitted 0 actions + 6 skips, with all 6
   GUIDs matching the spike's writes byte-for-byte. `is_certified_readonly=true,
   confidence=high` ⟶ SC-006 verified.
2. **Snapshot artifact** at `tests/integration/_snapshots/spike_close_post.json`
   (1833 bytes, contracts/run-report.md-compliant field order).
3. **Layer 3 inventory** of Ejagham Mini: 252 LexEntries, 13 verb-affix entries,
   20 allomorphs, 2 distinct PhEnvironments, 1 Unbound MSA (FR-007 bucket
   confirmed with real data). T051b PlannedAction estimate: ~61 + 6 Layer 1+2 =
   ~67 total, well under SC-001's 100-piece budget.
4. **Patched fork ApplySyncableProperties** confirmed at runtime on POS,
   MorphRules, LexEntry, Allomorphs (MCP indexer doesn't surface it but the
   runtime has it). Validates the `flexicon fork` dependency is correctly
   installed.

Plus one **bug fix** discovered via MCP: `Lib/residue.apply_carrier_b` previously
cast `obj` to `ICmPossibility` before reading `Description`. Live MCP probe
showed that cast raises `TypeError` on `IMoInflAffixTemplate` — the spike's
writes happened to land somehow (likely a flexicon-version-dependent fallback),
but a fresh write through the new code path would crash. Replaced with direct
`getattr(obj, "Description")` access; uniform across every Carrier-B class
(POS, Template, Slot, FsClosedFeature, ...). Round-trip parsed all 6 spike
tags successfully — including the template's residue.

Cross-session run_ids decoded from live Description fields:
- `GT-20260619-162337` Ejagham Mini — POS-only spike
- `GT-20260619-164210` Ejagham Mini — template + 4 slots spike

## TL;DR of this session

1. **`/speckit-analyze` audit** found Layer 1+2 work had outrun the planned
   scaffolding (v4.0.0 adapter pattern bypassed; Move-mode writes happened
   before any Preview engine existed).
2. **Constitution v5.0.0** retired the v4.0.0 adapter-contract requirement —
   `flavors/` is gone; flexicon is imported directly; the LibLCM-direct
   implementation moved to a separate post-Phase-2 sibling repository.
3. **T-Spike refactor**: the inline `transfer_verb_vertical()` Move logic was
   split into `Lib/preview.py` (plan builder, never mutates target) and
   `Lib/transfer.py` (plan executor, the only writer). Principle III is now
   mechanical.
4. **Foundation modules + 70 unit tests** landed (all green in 0.16 s) covering
   residue serialize/parse, FR-018 invariants, Selection invariants, WSMapping
   1:1, closure walker (incl. diamond dedup), WS-mapping validation, affix
   tree → Selection helpers, preview-no-writes, closure-off skip semantics,
   no-silent-drops, and the UI ↔ engine API surface.

The next session's blocking task is **T-Spike step 3** — a live re-run on
`Ejagham Full GT-Test` through the new Preview/Move pair to verify parity
with the original spike (rubric in tasks.md T-Spike).

---

## File layout (post-T-Spike, FLExTrans-style)

```text
src/gramtrans/
├── __init__.py          # v5.0.0 — package metadata only; no re-exports
├── gramtrans.py         # entry: docs dict + MainFunction(project, report, modifyAllowed)
│                        # site.addsitedir(Lib) per FLExTrans convention
└── Lib/                 # helpers (sibling dir, loaded at runtime)
    ├── __init__.py      # docstring only — no sys.path injection (caused double-loads)
    ├── models.py        # E1-E6 dataclasses + enums (renamed from `types.py`
    │                    #   to avoid shadowing stdlib `types` under addsitedir)
    ├── residue.py       # ImportResidueTag + Carrier A/B dispatchers
    ├── closure.py       # BFS walk(seeds, dep_fn) + topological reverse
    ├── ws_mapping.py    # validate / is_complete / required_ws_set +
    │                    #   WSMappingIncomplete / WSMappingOverspecified
    ├── selection.py     # PickerState + SourceAffixInventory +
    │                    #   compute_required_affixes/templates + build_selection
    ├── preview.py       # build_run_plan(...) → RunPlan; closure-on + closure-off
    │                    #   semantics; verb-vertical (POS→Template→Slots)
    ├── transfer.py      # execute(plan, source, target, sink, tag) → RunReport
    │                    #   per-layer creators preserved verbatim from the spike
    ├── report.py        # RunReport.build_from_plan classmethod + to_snapshot_json
    │                    #   method (per_category dict ordered by enum decl) +
    │                    #   render_text_summary for the FlexTools report pane
    ├── api.py           # UI ↔ engine facade (T058):
    │                    #   initialize_run / list_target_candidates / bind_target /
    │                    #   compute_preview / execute_move + exceptions
    └── ui/              # PyQt widgets (T054-T057, T074 — UI shells next)
        └── __init__.py
```

**No `flavors/` directory.** v5.0.0 retired the adapter contract.

---

## What's validated end-to-end against live data

Layer 1 (POS) + Layer 2 (Template + 4 Slots) cross-project transfer
**Ejagham Mini → Ejagham Full GT-Test** completed in the previous session.
That was the one-time "validation spike" per constitution v5.0.0 Principle III's
closing clause. The new Preview/Move pair (T-Spike steps 1-2 below) **mirrors**
that spike's behaviour byte-for-byte but lives behind the plan-builder /
plan-executor separation now.

### Layer 1 — POS — VERIFIED in spike; awaiting re-verify through Lib/transfer.py
- Source Verb POS copied to target with **GUID preserved** (`86ff66f6-…`)
- Multi-WS Name/Abbreviation/Description fields copied via
  `BaseOperations.ApplySyncableProperties` (patched fork)
- Carrier B residue tag appended to `Description` multistring
- FR-009 additive duplicate confirmed
- LCM UndoableUnitOfWork (FlexTools-runner's outer UOW) caught the writes;
  `Ctrl+Z` in FLEx undoes the run

### Layer 2 — Template + 4 Slots — VERIFIED in spike; awaiting re-verify
- Verb template GUID preserved (`821a96d6-…`)
- 4 slot GUIDs preserved (SbjAgr, Neg/Mood, Repetative, VSuffix)
- Slot reference sequences (`PrefixSlotsRS` / `SuffixSlotsRS`) wired in
  source order
- Residue tags on Description multistrings of template + each slot

### Layer 3 — LexEntry + Sense + MSA + Allomorph + PhEnvironment — OUTLINED

**Live inventory of Ejagham Mini (via MCP, 2026-06-19 evening)**:

| Entity | Count |
|---|---|
| Total LexEntries | 252 |
| Total senses | 250 |
| Verb-affix entries (sense.MSA is `IMoInflAffMsa` with PartOfSpeechRA=Verb) | **13** |
| InflAffMsas under Verb | 13 |
| ...of which Unbound (`SlotsRC.Count == 0`) | **1** ✓ (matches the FR-007 "Unbound bucket" use case) |
| Allomorphs across those 13 entries | 20 |
| Distinct `IPhEnvironment` referenced | 2 |

Sample verb-affix headwords (first 5): `n~-1`, `n~-2`, `e~-`, `ro~-`, `a~-`.

**MSA → Slot wiring (live, full set)** for T051b implementer:

| Headword | Slot |
|---|---|
| `n~-1`, `n~-2`, `e~-`, `a~-`, `ń~-3`, `ń~-2`, `o~-1`, `o~-2`, `á~-`, `ń~-1` | SbjAgr (10 affixes) |
| `kí~-` | Neg/Mood |
| `-k` | VSuffix |
| `ro~-` | (unbound — `SlotsRC.Count == 0`) |

`ILcmReferenceCollection[IMoInflAffixSlot]` supports direct Python iteration
(`for sl in msa.SlotsRC`) — DON'T try `.ElementAt(i)`, that raises
AttributeError. This pattern applies to all `SlotsRC` / `PhoneEnvRC` /
similar `Rc` reference collections in LCM.

Layer-3 PlannedAction count for a full verb-vertical run:
~13 LexEntry + 13 LexSense + 13 MSA + 20 Allomorph + 2 PhEnv = **~61 actions** beyond
Layer 1+2's 6 (POS + template + 4 slots) = **~67 objects total**. Well under SC-001's
≤100-piece / <5-min budget.

Layer 3 implementation is gated on T-Spike step 3 fresh-target re-run (per constitution
v5.0.0 Principle III). The post-spike state verified the planner sees the spike's
writes correctly; the fresh-target Move-path verification needs a `FieldWorks.exe -restore`
of `Ejagham Full.fwbackup` to re-test the create chain.

Factory + Apply pattern (all validated in spike):

| Object | Factory create | Owner attach |
|---|---|---|
| `ILexEntry` | `Create(Guid, ILexDb)` | one-shot |
| `ILexSense` | `Create(Guid, ILexEntry)` | one-shot |
| `IMoInflAffMsa` | `Create(Guid)` | `entry.MorphoSyntaxAnalysesOC.Add(msa)`; `sense.MorphoSyntaxAnalysisRA = msa` |
| `IMoAffixAllomorph` | `Create(Guid)` | `entry.LexemeFormOA = allo` OR `entry.AlternateFormsOS.Add(allo)` |
| `IPhEnvironment` | `Create(Guid)` | `cache.LangProject.PhonologicalDataOA.EnvironmentsOS.Add(env)` |

Residue carrier: **A** (`LiftResidue`) for `ILexEntry`/`ILexSense`/`IMoForm`/
`IMoMorphSynAnalysis`; **B** (`Description`-append) for `IPhEnvironment`.

---

## Tasks closed this session

**Foundation**: T001, T002, T003, T004, T006, T007, T009, T010, T011, T012, T013.

**Data-model + residue + report**: T019, T020, T021, T022.

**Foundational tests** (10): T023, T024, T025, T026.

**US1 (engine)**: T029, T036, T037, T052 (preview.py), T053 (transfer.py),
T058 (api.py).

**US2 (reporting)**: T063, T064, T065, T067.

**US3 (selection + closure-off)**: T072, T073, T076.

**Polish**: T083, T084, T085, plus T-Spike steps 1+2.

70 unit tests passing in ~0.16 s. Run with `pytest tests/unit/`.

---

## flexicon fork dependency (CLAUDE.md + README.md document this)

Runtime depends on **MattGyverLee/flexicon** at
`D:/Github/_Projects/_LEX/flexicon`. Two patches:

1. `GetSyncableProperties` writing-system enumeration fix
   (`project.WritingSystems.GetAll()`, not `ws_factory.WritingSystems`).
2. New `ApplySyncableProperties(item, props, ws_map=None)` on `BaseOperations`
   + 8 Grammar Operations subclasses.

Patched files (9):
`BaseOperations.py`, `Grammar/POSOperations.py`, `Grammar/MorphRuleOperations.py`,
`Grammar/GramCatOperations.py`, `Grammar/InflectionFeatureOperations.py`,
`Grammar/NaturalClassOperations.py`, `Grammar/EnvironmentOperations.py`,
`Grammar/PhonologicalRuleOperations.py`, `Grammar/PhonemeOperations.py`.

Install via `pip install -e D:/Github/_Projects/_LEX/flexicon`.

---

## Next session pick-up checklist

1. **Run T-Spike step 3** — restore `Ejagham Full GT-Test`, run
   `gramtrans.gramtrans.MainFunction` through FlexTools, verify the parity
   rubric (tasks.md T-Spike: same GUIDs, same residue tags, empty skip list,
   Ctrl+Z undoes, Preview produces no writes).
2. **Capture pre/post Import Residue snapshots** into
   `tests/integration/_snapshots/spike_close_{pre,post}.json` (T-Spike step 4).
3. **Then** begin Layer 3 — extend `Lib/preview.py._plan_verb_vertical` (and
   `Lib/transfer.py._execute_verb_vertical`) to walk entries/senses/MSAs/
   allomorphs/environments per the table above. Split into
   `Lib/categories_msas.py` per the plan.
4. **UI widget shells (T054-T057, T074)** — start with `Lib/ui/target_picker.py`
   since it has no LCM dependency beyond `list_target_candidates`.
5. **Integration tests** — T030 (full categories), T031 (pre-existing target
   not modified), T033/T033b (FR-019/FR-020 refusal), T034 (GUID preservation),
   T035 (GOLD inviolability).

---

## Reference notes

- **Restore the throwaway target**:
  ```powershell
  & 'C:\Program Files\SIL\FieldWorks 9\FieldWorks.exe' -restore `
    'D:\Github\_Projects\_LEX\GramTrans\backups\Ejagham Full.fwbackup' `
    -db 'Ejagham Full GT-Test' -include c
  ```
  Backups at `D:/Github/_Projects/_LEX/GramTrans/backups/`.

- **Open spec questions** (none blocking):
  - WS mapping (FR-011) is identity-only in the MVP. The
    `ApplySyncableProperties(item, props, ws_map=None)` signature is ready
    to accept a `ws_map` dict when the UI surfaces one.
  - "Unbound" affix bucket display: validated as
    `IMoInflAffMsa.SlotsRC.Count == 0`. Ejagham Mini has 1 such affix.

- **MCP validator quirks** worth knowing:
  - `getattr(project, "Cache")` / `getattr(project.POS, "ApplySyncableProperties")`
    dodge static checks when needed in MCP probes — never needed in actual runtime.
  - The runner pre-wraps every snippet in a UOW; don't nest your own
    `UndoableUnitOfWorkHelper.Do(...)`.
  - `from flexicon import (...)` MUST be a single line for the MCP parser.

- **Don't reintroduce `Flavor` enum**: v5.0.0 explicitly removed it.

- **Don't add `gramtrans.Lib` to sys.path inside `Lib/__init__.py`**: that
  caused a double-load of `models.py` (top-level + package) and two distinct
  `GrammarCategory` enums, silently breaking dict lookups. Helpers use
  `__package__`-aware imports instead (`from .models import ...` when loaded
  as `gramtrans.Lib.X`, `from models import ...` when loaded via
  `site.addsitedir(Lib)`).
