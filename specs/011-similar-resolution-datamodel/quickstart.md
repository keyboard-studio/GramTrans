# Quickstart / Validation Guide: Similar-Candidate Capture & Per-Item Resolution (011)

This is a validation guide, not an implementation. It lists the runnable scenarios that prove 011
works end-to-end. Implementation bodies belong in the code + `tasks.md`. The two collision fixtures
below are drawn from **live** FLExTools MCP evidence against **Ejagham Full GT-Test** (research
D1/D3) so the empirically-proven collision classes are regression-locked.

## Prerequisites

- Python 3 with the repo installed (dev): `pip install -e D:/Github/_Projects/_LEX/flexicon`
  then `pip install -e .` for GramTrans. (011 itself imports no flexicon in `Lib/models.py`; the
  unit tests use fake source/target handles — no live FLEx needed to run the suite.)
- Test runner: `pytest`.

## Run the suite

```powershell
cd d:/Github/_Projects/_LEX/GramTrans
python -m pytest tests/unit -q
```

Expected: the existing selection/model suite passes **unmodified** (SC-006, back-compat via
defaulted fields), plus the new 011 assertions below.

---

## Scenario 1 — Affix candidate capture (US1 / FR-001–FR-005, SC-001, SC-002)

Build the POS-grouped inventory from a fake source/target where a source affix shares a normalized
form with two target entries.

**Assert:**
- The SIMILAR affix row exposes `suggested_target_guid` == the **first** candidate's GUID for that
  form (HVO-ascending; research D2).
- A NEW affix row's `suggested_target_guid is None` (SC-001).
- `inventory.target_affix_candidates` contains every distinct target affix candidate **exactly
  once** (dedup) and covers 100% of the candidates referenced by individual rows (SC-002).
- With **no target bound**: all rows `status=None`, `suggested_target_guid=None`,
  `target_affix_candidates == ()`, no error.

### Live-grounded fixture 1a — the `'n'` → 5-candidate case

Reproduce the observed collision: one source affix with normalized form `n`, target containing 5
distinct affix entries all with form `n` (glosses `1.n`, `9pl.n`, `3pl.n`, `3sg.n`, `9sg.n`) and
ascending HVOs.

**Assert:** `form_to_candidates["n"]` has length 5, is HVO-ascending, and the SIMILAR row's
`suggested_target_guid` equals the lowest-HVO candidate's GUID.

---

## Scenario 2 — Per-item resolution type (US2 / FR-007, FR-008, SC-003, SC-004)

Construct `SimilarResolution` values directly (three-way action: `overwrite` / `merge` / `create_new`).

**Assert:**
- `SimilarResolution(entry_guid="g", action="overwrite")` (no `target_guid`) → `ValueError` (SC-003).
- `SimilarResolution(entry_guid="g", action="merge")` (no `target_guid`) → `ValueError` (SC-003).
- `SimilarResolution(entry_guid="g", action="overwrite", target_guid="t")` → valid.
- `SimilarResolution(entry_guid="g", action="merge", target_guid="t")` → valid.
- `SimilarResolution(entry_guid="g", action="create_new")` → valid.
- `SimilarResolution(entry_guid="g", action="create_new", target_guid="t")` → `ValueError`
  (symmetry).
- `action="bogus"` → `ValueError`.

**Inertness (SC-004, FR-010):**
- A frozen `Selection` with a populated `similar_resolutions` map produces **byte-identical** plans
  to the same `Selection` without it across the existing planner regression suite.
- `selection.similar_resolution_for(guid)` returns `None` for an unrecorded GUID (no fabricated
  default).

---

## Scenario 3 — Phonology SIMILAR rows remember their match (US3 / FR-006, SC-005)

Build the phonology inventory against a target with a label-matching item.

**Assert:**
- A SIMILAR phonology row carries a non-None `matched_target_guid` present in the target's GUID set.
- A NEW phonology row's `matched_target_guid is None`.
- With **no target bound**: every row `matched_target_guid is None`, no error (SC-005).

### Live-grounded fixture 3a — the NaturalClass label-collision case (research D3)

Reproduce the observed collision: a target with two natural classes both named `Consonants`
(distinct GUIDs, ascending HVOs), and a source NC also named `Consonants`.

**Assert:**
- The SIMILAR source row's `matched_target_guid` == the **lowest-HVO** target `Consonants` GUID.
- Exactly one `INFO` log line is emitted announcing the collision collapse for label `consonants`.

---

## Scenario 4 — Back-compat & the gloss-merge fix (FR-009, SC-006, research D8)

**Assert (back-compat):** every existing `AffixRow`, `PosGroupedAffixInventory`, `PhonologyRow`,
and `Selection` construction in `tests/unit/` still succeeds unmodified (defaulted tail fields).

### Regression fixture 4a — `_merge_row_glosses` forwards the suggestion (lex-qc P1)

Build an inventory where a SIMILAR affix entry contributes **two MSAs to the same POS/role**
(triggering `_merge_row_glosses`).

**Assert:** after the gloss-merge, the surviving row still has its `suggested_target_guid` set
(not reset to `None`). This converts the P1 from a hope into a tested invariant.

---

## Optional — re-run the live probes (author-side, read-only)

The planning probes can be re-run against the live target to refresh the evidence (FLExTools MCP,
`flexicon`, `write_enabled=false`, project `Ejagham Full GT-Test`): affix form-collision scan and
phonology within-category label-collision scan. This is author-side validation only — **not** a
test dependency (constitution: the MCP is non-normative and not part of the shipped module).

## Success criteria coverage

| SC | Scenario |
|----|----------|
| SC-001 | 1 + 1a |
| SC-002 | 1 |
| SC-003 | 2 |
| SC-004 | 2 |
| SC-005 | 3 + 3a |
| SC-006 | 4 |
