# Phase 3c Live MCP Verification Log

**Phase**: 3c | **Target Pair**: Ejagham Mini → Ejagham Full GT-Test | **Spec**: [spec.md](./spec.md) | **Date Run**: [TBD]

---

## Scenario A — MVP Full Chain (Empty Target, US1+US2)

**Goal**: Verify Phase 3a+3b+3c integration end-to-end on Ejagham Mini → Ejagham Full GT-Test (empty target) with US1+US2 MVP. Affixes (13 entries with owned-child closure), slots (~25 total), templates (~5) with 17.1 MSA-slot wiring.

**Expected Outputs**:
- AFFIXES: 13 entries created, 13 senses, 13 MSAs (InflAff), ~20 allomorphs, ~6 entry-refs
- SLOTS: ~25 slots created under POSes, Description multistring copied, Carrier B residue
- AFFIX_TEMPLATES: ~5 templates, all 5 slot-ref sequences wired (Prefix/Suffix/Enclitic/Proclitic/Slots), Final/Disabled/Stratum copied
- 17.1 sub-pass: 12 MSA-slot bindings (one short — `ro~-` unbound), 0 DEPENDENCY_UNRESOLVED skips
- Wall-clock: target < 30s (FR-301 performance gate)

### Pre-flight
- [ ] Restore `Ejagham Full GT-Test` from `backups/Ejagham Full.fwbackup`
- [ ] MCP server ready, FlexTools host connected
- [ ] Source: Ejagham Mini at `C:/ProgramData/SIL/FieldWorks/Projects/Ejagham Mini`
- [ ] Target: Fresh restore at `C:/ProgramData/SIL/FieldWorks/Projects/Ejagham Full GT-Test`

### Run

- [ ] Launch `gramtrans_main()` with Ejagham Mini → GT-Test, AFFIXES+SLOTS+AFFIX_TEMPLATES selected
- [ ] Preview: assert planner produces ~50 actions (13 + ~25 + ~5 + 17.1 tail wires)
- [ ] Move: execute full chain
- [ ] Inspect target post-move

### Evidence

**Planner Output**:
```
[TODO: paste preview summary]
```

**Move Output**:
```
[TODO: paste move summary]
```

**Target Inspection** (live MCP queries):
- Total affixes created: ___ (expect 13)
- Total slots created: ___ (expect ~25)
- Total templates: ___ (expect ~5)
- Template 1 prefix-slots wired: ___ (confirm > 0)
- MSA slot bindings (17.1): ___ (expect 12)
- Unbound MSAs: ___ (expect 1 — ro~-)
- Wall-clock duration: ___ seconds (target < 30s)
- DEPENDENCY_UNRESOLVED skips: ___ (expect 0)

### Result

- [ ] **PASS**: All counts match expected + wall-clock ✓
- [ ] **FAIL**: [describe discrepancy]
- [ ] **DEFERRED**: [reason]

---

## Scenario B — Re-run Idempotency (Populated Target, US1+US2)

**Goal**: Verify FR-307 (re-run produces 0 new actions when target already has all items).

**Setup**: Run Scenario A first (target now populated), then re-run the same transfer.

**Expected Outputs**:
- `added_count == 0` (FR-307)
- All 13+25+5 items skip as ALREADY_PRESENT_BY_GUID
- No 17.1 tail writes (membership checks prevent duplicate Add calls)

### Run

- [ ] Launch fresh preview on populated target
- [ ] Move: execute
- [ ] Inspect report

### Evidence

**Report**:
```
[TODO: paste summary]
```

### Result

- [ ] **PASS**: `added_count == 0`, no new wires ✓
- [ ] **FAIL**: [describe discrepancy]
- [ ] **DEFERRED**: [reason]

---

## Scenario C — Phase 1 Overwrite Path (Pre-edited Sense, US1)

**Goal**: Verify FR-338 (overwrite inheritance for affixes). Edit a sense in the target, then run Phase 1 overwrite mode on that affix entry.

**Setup**: Populate target via Scenario A, then manually edit an affix sense's gloss in FLEx, then run transfer with `enable_overwrite=True` on AFFIXES.

**Expected Outputs**:
- 1 AFFIXES PlannedOverwrite (not Skip) for the edited entry
- Phase 1 entry-overwrite executor runs (shared with ENTRY/STEMS, no Phase-3c-specific merge)
- Sense residue merged per Phase 1 logic

### Run

- [ ] Manually edit sense gloss in target FLEx (e.g., Verb affix sense #1)
- [ ] Save target
- [ ] Launch preview with `enable_overwrite=True` on AFFIXES
- [ ] Inspect plan: expect 1 PlannedOverwrite for the edited entry
- [ ] Move: execute
- [ ] Inspect residue in target

### Evidence

**Plan**:
```
[TODO: paste relevant PlannedAction/PlannedOverwrite summary]
```

**Residue Inspection**:
```
[TODO: paste target sense entry, verify residue structure]
```

### Result

- [ ] **PASS**: 1 Overwrite emitted + merged correctly ✓
- [ ] **FAIL**: [describe discrepancy]
- [ ] **DEFERRED**: [reason]

---

## Scenario D — Phase 2 Interactive Conflict Resolution (US1)

**Goal**: Verify Phase 2 ConflictPrompt flow when a field differs between source/target entry.

**Setup**: Populate target, edit an affix entry's field (e.g., different morph-type category), run Phase 2 conflict mode.

**Expected Outputs**:
- 1 AFFIXES ConflictPrompt for the field mismatch
- User resolves (skip/overwrite) via FakeResolver
- Result flows through Phase 2 pipeline

### Run

- [ ] Manually edit an affix entry field in target (e.g., category code)
- [ ] Launch preview with Phase 2 conflict mode
- [ ] Inspect plan: expect 1 ConflictPrompt
- [ ] (Simulated resolve via report inspection)

### Evidence

**ConflictPrompt**:
```
[TODO: paste conflict details]
```

### Result

- [ ] **PASS**: ConflictPrompt emitted + resolvable ✓
- [ ] **FAIL**: [describe discrepancy]
- [ ] **DEFERRED**: [reason]

---

## Scenario E — Preview-Only (No Writes, US1+US2)

**Goal**: Verify `modifyAllowed=False` prevents writes while still planning.

**Setup**: Run preview with `modifyAllowed=False` on populated target.

**Expected Outputs**:
- Plan produced (shows what would be transferred)
- `Cache.UnitOfWorkService.IsDirty == False` after preview (no side effects)

### Run

- [ ] Launch preview with `modifyAllowed=False`
- [ ] Inspect dirty flag post-preview
- [ ] Move: should be skipped or error (read-only mode)

### Evidence

**Preview Plan**:
```
[TODO: paste summary]
```

**Dirty Flag**:
```
Cache.UnitOfWorkService.IsDirty = ___
```

### Result

- [ ] **PASS**: Preview clean, no writes ✓
- [ ] **FAIL**: [describe discrepancy]
- [ ] **DEFERRED**: [reason]

---

## Scenario F — Phase 0 Verb-Vertical Re-run Post-Phase-3c (SC-303, US1+US2)

**Goal**: Verify SC-303 — after Phase 3c US1+US2 transfer, Phase 0 verb-vertical re-run sees no new actions (FR-334 collision guard).

**Setup**: Run Phase 3c (Scenario A), then run Phase 0 verb-vertical-only transfer on the same target.

**Expected Outputs**:
- 0 new ENTRY/POS/etc. actions (all already in target)
- FR-334 collision guard emits 0 actions
- Wall-clock < 5s (quick recheck)

### Run

- [ ] After Scenario A completes, launch fresh preview with Phase 0 verb-vertical only
- [ ] Inspect plan: expect `added_count == 0`
- [ ] Move: execute (should be instant)

### Evidence

**Phase 0 Re-run Plan**:
```
[TODO: paste summary]
```

**Wall-Clock**:
```
___ seconds
```

### Result

- [ ] **PASS**: `added_count == 0`, < 5s ✓
- [ ] **FAIL**: [describe discrepancy]
- [ ] **DEFERRED**: [reason]

---

## Notes

### US4 Status (Compound Rules + Ad-Hoc Prohibitions)

**NOTE**: Ejagham Mini has 0 compound rules + 0 ad-hoc prohibitions per T012 probe. US4 live verification is **blocked**. Scenarios A–F above test US1+US2 only.

**Mitigation** (per probe-results T066 rationale):
- US4 unit + fake-LCM-surface integration tests cover the dispatch logic (T056–T065)
- Live MCP verification deferred until a source with compound rules is available
- Document the gap in this log under "Known Limits"

### Known Limits

- US4 not verified live (Ejagham Mini has 0 compound/ad-hoc)
- Phase 2 Conflict mode (Scenario D) simulated (requires FakeResolver in live environment)

---
