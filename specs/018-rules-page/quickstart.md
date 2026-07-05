# Quickstart — 018 Rules Page validation

Prerequisites: FlexTools host with flexicon (pyflexicon); source = **Ejagham Mini**,
throwaway target = **Ejagham Full GT-Test** (per STATUS.md pairing). Live checks via
FLExTools MCP (`flextools_start` → `flextools_run_module`); never guess LCM API.

## Unit (fake handles) — `pytest`

```
pytest tests/unit/test_rules_inventory.py \
       tests/unit/test_rules_leaf_item_picks.py \
       tests/unit/test_rules_plan_dispatch.py \
       tests/unit/test_rules_missing_ref.py \
       tests/unit/test_wizard_page_order.py
```

Expected: 2 categories with correct counts; all rows preselected (SC-003); subset
filter honored + grouping recursion; GUID-first skip/add + idempotent re-plan;
missing-ref aggregation; `page_rules()` returns `_PageRules` in order.

## Live engine (US1, SC-001/002/008) — MCP `run_module`

Against a fresh target with a source bearing one of each subclass
(`MoAlloAdhocProhib`, `MoMorphAdhocProhib`, `MoEndoCompound`, `MoExoCompound`, and a
`MoAdhocProhibGr` with children):

1. Plan then execute the ADHOC_COMPOUND_RULES category.
2. **Expect**: one target object per source rule of the matching subclass,
   GUID-preserved; adhoc allomorph/morpheme refs resolved to target objects;
   compound member/result POS wired via owned MSAs; group children owned by the
   transferred group.
3. Re-run → all Skip (zero duplicates, SC-002).
4. Inject a synthetic unknown subclass → **loud failure**, not silent skip (SC-008).

Confirm the compound member-MSA field names (research R3a) with a live probe BEFORE
wiring:

```python
# run_module probe (read-only): dump one compound rule's owned-MSA + POS path
rules = project.MorphRules.GetAllCompoundRules()
for r in rules[:1]:
    report.Info(str([p for p in dir(r) if "Msa" in p]))
```

## Wizard (US2/US3/US5) — manual / headless page

- Open to Rules page: both categories preselected, correct counts (SC-003/004).
- Advance unchanged → plan per-category counts equal source inventory (SC-004).
- Whole-block toggle off → plan has zero rules; back on → all restored (SC-005).
- Deselect one compound rule → plan omits exactly that rule.
- source=target → every row IN TARGET; fresh target → NEW (SC-007).
- No ADD_NEW/MERGE/OVERWRITE control anywhere on the page (SC-009).

## Referential completeness (US4, SC-006)

Keep a compound rule whose left-member POS was deselected on Grammatical deps and is
absent from target → Preview shows ONE aggregated warning naming the rule; Move pops
a single consolidated confirmation (not per-reference). No warning when the POS
resolves in target.
