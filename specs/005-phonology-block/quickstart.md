# Phase 3a Quickstart — Validation Scenarios

Runnable validation guide that proves Phase 3a works end-to-end.
Implementation details live in `tasks.md`; this file is the run-book
for verification.

## Prerequisites

- Phases 0, 1, 2 shipped (commits 531211a … c050aa1; 267 tests passing).
- flexicon fork installed (D:/Github/_Projects/_LEX/flexicon).
- Ejagham Mini source project has at least: 1 phoneme, 1 natural class,
  1 phonological rule, 1 stratum. (If not, populate manually before
  running Scenario A — or use the `populate-phonology.py` helper that
  Phase 3a's tasks.md prescribes.)
- A throwaway target project (clone of Ejagham Full GT-Test recommended).

## Scenario A — Pure phonology block, additive

**Goal**: Prove the six categories transfer cleanly when no overlap
with target exists.

**Setup**: Target has empty `PhonologicalDataOA` and empty
`MorphologicalDataOA.StrataOS`.

**Run**:
```python
sel = Selection(
    categories={
        GrammarCategory.PHONOLOGICAL_FEATURES: True,
        GrammarCategory.PHONEMES:              True,
        GrammarCategory.NATURAL_CLASSES:       True,
        GrammarCategory.PH_ENVIRONMENT:        True,
        GrammarCategory.PHONOLOGICAL_RULES:    True,
        GrammarCategory.STRATA:                True,
    },
    enable_overwrite=False,
)
plan = build_run_plan(ctx, sel, WSMapping(entries=()), src, project)
execute(plan, src, project, report, tag)
```

**Expected**:
- Plan: `actions=<source_count>` per category, `skips=0`,
  `overwrites=0`.
- Wall clock < 5s for a 30-phoneme / 10-NC / 5-rule / 2-stratum source.
- Target `PhonologicalDataOA.PhonemeSetsOS[0].PhonemesOC` contains
  source's phonemes (GUID-matched where the factory allows; otherwise
  `plan.identity_remap` populated).
- Target `MorphologicalDataOA.StrataOS` contains source's strata.

**Pass criteria**: probe each target collection; every source GUID
either appears in target by GUID OR is mapped via `identity_remap` to a
new target GUID.

## Scenario B — Re-run with overwrite enabled

**Goal**: Phase 1 overwrite semantics apply to phonology.

**Setup**: Scenario A has already run. Target now has the source's
phonology.

**Run**: Same selection as Scenario A, plus `enable_overwrite=True`.

**Expected**:
- Plan: every source item that's GUID-matched in target lands as
  PlannedOverwrite; no new actions.
- Run report shows per-category `added=0 overwritten=<source_count>`.
- Each touched object's residue tag carries the Phase 1 `snap=`
  segment.

**Pass criteria**: confirm the 6-segment residue tag round-trip for at
least one phoneme + one natural class + one rule.

## Scenario C — Dependency-unresolved skip on phonological rule

**Goal**: FR-304 enforces dependency closure.

**Setup**: Same source. Target has empty phonology BEFORE the run.

**Run**: deselect Phonemes (`PHONEMES: False`); keep Phonological Rules
selected.

**Expected**:
- Every source rule that references a phoneme (almost all of them)
  emits `Skip(DEPENDENCY_UNRESOLVED)` with a detail line naming the
  unresolved phoneme GUIDs.
- Run completes; no LCM mutations on the rule path.

**Pass criteria**: report contains ≥1 `Skip` with
`reason=DEPENDENCY_UNRESOLVED` and `category=PHONOLOGICAL_RULES`.

## Scenario D — PhEnvironment idempotency with Phase 0/1/2 allomorph closure

**Goal**: FR-307 — running Phase 3a populates envs, then a follow-up
Phase 0/1/2 verb-vertical produces ZERO new IPhEnvironment creates.

**Setup**: Scenario A has run, populating PhEnvs. Target is otherwise
fresh.

**Run**: Now invoke the existing Phase 0 verb-vertical (without the
phonology block):
```python
sel = Selection(
    categories={
        GrammarCategory.POS: True,
        GrammarCategory.TEMPLATES: True,
        GrammarCategory.SLOTS: True,
        GrammarCategory.ENTRY: True,
        GrammarCategory.SENSE: True,
        GrammarCategory.MSA: True,
        GrammarCategory.ALLOMORPH: True,
        GrammarCategory.PH_ENVIRONMENT: True,   # already populated from Scenario A
    },
    pos_picks=frozenset({VERB_GUID}),
)
```

**Expected**:
- `ph_environment added=0` in the run report (everything matched by
  GUID; Phase 1 overwrite for the PhEnv category fires if enabled).
- Allomorph creation succeeds with PhoneEnvRC references resolving to
  the just-pre-populated environments.

**Pass criteria**: report contains `ph_environment added=0` and
allomorph closure completes without DEPENDENCY_UNRESOLVED skips.

## Scenario E — Phase 0/1/2 invariance when phonology block NOT selected

**Goal**: FR-311 — no Phase 0/1/2 regression.

**Setup**: Target same state as before any Scenario.

**Run**: standard Phase 0 verb-vertical selection (the existing baseline)
WITHOUT enabling any of the five new categories.

**Expected**:
- Identical to the Phase 2 Scenario A baseline: 67 overwrites, 0 skips,
  no Phase 3a code paths fire.
- Wall clock within 10% of the Phase 2 baseline (~1.5-2.0s).

**Pass criteria**: byte-equivalent run report compared to the Phase 2
v0.2.0 reference logs.

## Test suite

```powershell
# All Phase 3a unit tests
python -m pytest tests/unit/test_categories_phon_features.py `
                tests/unit/test_categories_phonemes.py `
                tests/unit/test_categories_natural_classes.py `
                tests/unit/test_categories_ph_environments.py `
                tests/unit/test_categories_phon_rules.py `
                tests/unit/test_categories_strata.py `
                -v

# Full regression
python -m pytest tests/unit -q

# Integration (mocked LCM)
python -m pytest tests/integration/test_phase3a_phonology_e2e.py -v
```

Expected end state: 267 Phase 0/1/2 tests + ~40 new Phase 3a tests = ~310 passing.

## Live MCP validation order

1. Scenario E (regression baseline) — confirm Phase 2 still passes.
2. Scenario A (additive happy path).
3. Scenario B (re-run with overwrite).
4. Scenario C (dependency-unresolved skip).
5. Scenario D (idempotency with allomorph closure).

If any scenario fails, halt Phase 3a — the validated ordering memo
holds the answer.

## Done When

- All five scenarios pass.
- pytest full unit + integration green.
- One live MCP run on Ejagham Mini → Ejagham Full GT-Test demonstrates
  Scenarios A through D.
- STATUS.md updated to reflect Phase 3a ship.
