# Implementation Plan: Phase 0 — Additive Grammar Transfer

**Branch**: `001-phase0-additive-transfer` | **Date**: 2026-06-19 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from [specs/001-phase0-additive-transfer/spec.md](spec.md)

**Note**: This plan was last reconciled with constitution v5.0.0 on 2026-06-19 after the
`/speckit-analyze` audit. See `.specify/templates/plan-template.md` for the original
execution workflow.

## Summary

Deliver a FlexTools-compatible Python module that copies a user-selected set of grammar
pieces (and their full dependency closure) from the currently-open FLEx project (source)
to a user-picked target FLEx project, additively, with a Preview Mode default and a
structured per-object residue tag on every newly added object. Implementation imports
**flexicon directly** (no flavor-adapter contract) per constitution v5.0.0 Principle II.
The runtime depends on the patched MattGyverLee/flexicon fork (carrying the
`WritingSystems` enumeration fix and the new `ApplySyncableProperties` method). A
LibLCM-direct re-implementation is a **separate post-Phase-2 sibling repository**, not a
deliverable in this tree. The UI is PyQt, hosted inside the FlexTools window, and
includes a writing-system mapping step (both vernacular and analysis WSs, 1:1, create on
demand) before any transfer writes occur.

## Technical Context

**Language/Version**: Python 3 (whatever version the host FlexTools install ships with;
no language-version constraints introduced by this module beyond what FlexTools requires).

**Primary Dependencies**:
- **flexicon (forked)** — Pythonic Operations-class LCM wrapper. **Direct runtime
  dependency.** Consumed from the MattGyverLee/flexicon fork at
  `D:/Github/_Projects/_LEX/flexicon` (or its published GitHub fork URL) which carries
  two patches required by GramTrans: (a) `GetSyncableProperties` enumerates writing
  systems via `project.WritingSystems.GetAll()` instead of the nonexistent
  `ws_factory.WritingSystems` attribute; (b) a new
  `ApplySyncableProperties(item, props, ws_map=None)` method on `BaseOperations` plus the
  8 Grammar Operations subclasses. `pyproject.toml` declares `flexicon>=2.0`; the fork
  is installed manually and the dependency is documented in
  [../../CLAUDE.md](../../CLAUDE.md) and the repo README.
- **PyQt** — UI toolkit, hosted inside the FlexTools main window.

flexlibs1 is **not used**. LibLCM is **not consumed in this repo** — the LibLCM-direct
implementation is a separate post-Phase-2 sibling repository per constitution v5.0.0
Principle IV.

**Storage**: None of its own. The module reads from the source FLEx project (read-only)
and writes to the target FLEx project via LCM. All persistence is delegated to the LCM
data layer the host already provides.

**Testing**:
- **Unit tests** (`pytest`) for pure-Python logic: selection model, dependency-closure
  traversal, Import Residue tag formatter, run-report aggregation, WS-mapping
  validation. These run without FlexTools / LCM.
- **Integration tests** against a pair of live FLEx projects — **Ejagham Mini** as the
  canonical toy source (at `C:\ProgramData\SIL\FieldWorks\Projects\Ejagham Mini`) and a
  **fresh snapshot of Ejagham Full** restored before each run to
  `C:\ProgramData\SIL\FieldWorks\Projects\Ejagham Full GT-Test` (via `FieldWorks.exe
  -restore`). These require a FlexTools host.
- **Manual verification** per `quickstart.md` for end-to-end UI flows that aren't
  reasonable to automate.

**Target Platform**: Windows + FlexTools host (FLEx is Windows-primary). The module
shape is platform-agnostic Python, but its runtime context is whatever FlexTools
supports.

**Project Type**: FlexTools module (Python module embedded in a desktop host). Single
deliverable, no separate frontend/backend split. Layout follows the **FLExTrans module
convention**: flat entry file + sibling `Lib/` directory of helpers.

**Performance Goals**: Per spec SC-001 — a ≤100-piece benchmark grammar transfers in
under 5 minutes wall-clock. No throughput target beyond that; this is an interactive
authoring tool, not a bulk pipeline.

**Constraints**:
- **flexicon imported directly** (no adapter contract). Constitution v5.0.0 Principle II.
- **flexicon is a forked dependency** — see Primary Dependencies above.
- No flexlibs1 (dropped in favor of flexicon; not used in any version of this plan).
- No LibLCM in this repo (Phase 3 is a separate sibling repo).
- Preview is the default mode (Constitution Principle III).
- GOLD categories / inflection features inviolable (Principle I).
- Same-version source/target precondition (Clarification Q1).
- WS mapping step is mandatory before write (Clarification Q3, FR-011).
- Layer 1+2 work documented in `STATUS.md` ran ahead of the Preview engine as a one-time
  validation spike; the inline Move logic MUST be refactored into `Lib/preview.py` +
  `Lib/transfer.py` before Layer 3 begins (Principle III closing clause).

**Scale/Scope**:
- Realistic toy source projects: tens of grammar pieces, low hundreds at the high end.
- Affix counts may reach low hundreds (drives the tree-picker UI shape per
  Clarification Q4).
- Phase 0 only — Phase 1 (overwrite) and Phase 2 (interactive merge) are deferred;
  Phase 3 (LibLCM port) is a separate sibling repo.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Evaluated against [.specify/memory/constitution.md](../../.specify/memory/constitution.md) v5.0.0.

| # | Principle | Status | Plan compliance |
|---|-----------|--------|-----------------|
| I | FLEx Domain Fidelity (NON-NEGOTIABLE) | **PASS** | GUID-first identity (FR-012); GOLD inviolability (FR-022); WS mapping is mandatory and explicit (FR-011); cross-refs must resolve or the item is skipped (FR-021, SC-003). |
| II | FlexTools-Compatible Output, flexicon-Direct | **PASS** | No `flavors/` directory; `gramtrans.py` and `Lib/*.py` files import flexicon modules directly. flexicon is consumed as a patched fork (see Primary Dependencies). LibLCM is not consumed; Phase 3 is a sibling repo. MCP is author-side only, not in the runtime tree. |
| III | Preview-Before-Mutate (NON-NEGOTIABLE) | **PASS (with closing-spike clause)** | Preview is the default mode (FR-014); Move Mode requires a current-session preview first (FR-015); preview produces no writes (SC-006). The STATUS.md Layer 1+2 Move-mode validation spike predates the Preview engine; `Lib/preview.py` (plan-builder) and `Lib/transfer.py` (plan-executor) MUST land before Layer 3 — tracked as task T-Spike in tasks.md. |
| IV | Phased Merge Discipline | **PASS** | This plan ships Phase 0 only. No overwrite, no merge UI, no conflict prompts. The Import Residue tag schema is forward-compatible (Clarification Q5) so Phase 1/2 can adopt it unchanged. Phase 3 LibLCM port lives in a sibling repo per v5.0.0. |
| V | Referential Completeness | **PASS** | `Lib/closure.py` is a first-class component; closure-by-default toggle in the main window (FR-013); items whose closure cannot be satisfied are skipped entire, not partial (FR-021). |

**No violations. No entries in Complexity Tracking.**

The plan also honors Clarifications Q1–Q5:
- Q1 (same-version precondition): documented in Technical Context; no runtime version check needed.
- Q2 (open=source, picker=target): wired into `Lib/ui/main_window.py` and the `data-model.md` `RunContext` entity.
- Q3 (manual 1:1 WS mapping, vernacular + analysis, create on demand): `Lib/ui/ws_mapping_dialog.py` + `Lib/ws_mapping.py`.
- Q4 (affix tree picker by template → slot → affix, with Unbound bucket): `Lib/ui/affix_tree_picker.py`.
- Q5 (structured Import Residue tag): `Lib/residue.py` formats `GT-YYYYMMDD-HHMMSS` + source project name + ISO timestamp.

## Project Structure

### Documentation (this feature)

```text
specs/001-phase0-additive-transfer/
├── plan.md              # This file (/speckit-plan command output)
├── spec.md              # Feature specification (already exists)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   ├── category-transfer.md
│   ├── module-ui.md
│   └── run-report.md
├── checklists/
│   └── requirements.md  # Spec quality checklist (already exists)
└── tasks.md             # Phase 2 output (/speckit-tasks - NOT created by /speckit-plan)
```

### Source Code (repository root)

Layout follows the **FLExTrans module convention** (e.g.,
`FLExTrans/FlexTools_2.3.2/FlexTools/Modules/Chinese/Update_Pinyin_Fields.py` +
`Modules/Chinese/Lib/*.py`):

```text
src/
└── gramtrans/
    ├── gramtrans.py                 # FlexTools entry: `docs = {...}` + `MainFunction(project, report, modifyAllowed)`
    │                                # Loads Lib via `site.addsitedir(r"Lib")`
    └── Lib/                         # Sibling helpers (flat, no subpackages except ui/)
        ├── residue.py               # Q5 structured Import Residue tag + parser
        ├── closure.py               # Dependency-closure traversal (Principle V)
        ├── ws_mapping.py            # Validates user-supplied WS mapping
        ├── selection.py             # Selection model (category toggles + per-affix tree)
        ├── preview.py               # Builds the run plan; never writes (Principle III)
        ├── transfer.py              # Executes the run plan against a target
        ├── report.py                # Run-report aggregation (added / skipped / why)
        ├── categories.py            # Leaf-category transfer functions (gram_categories,
        │                            # custom_fields, inflection_classes, stem_names,
        │                            # exception_features, variant_types,
        │                            # complex_form_types, adhoc_rules, compound_rules)
        ├── categories_affixes.py    # FR-005: affixes + allomorphs + APRs + closure
        ├── categories_templates.py  # FR-006: templates + slots
        ├── categories_msas.py       # MSA wiring (entry → senses → MSAs → allomorphs)
        └── ui/                      # PyQt widgets (the only nested subpackage)
            ├── main_window.py       # FR-002: category toggles, closure toggle, Preview/Move buttons
            ├── target_picker.py     # FR-003: open=source, picker=target
            ├── ws_mapping_dialog.py # FR-011 / Q3: vernacular + analysis 1:1 mapping
            ├── affix_tree_picker.py # FR-007 / Q4: template → slot → affix + Unbound
            └── stats_panel.py       # FR-017 post-run report panel

tests/
├── unit/                            # No host required
│   ├── test_selection.py
│   ├── test_closure.py
│   ├── test_ws_mapping.py
│   ├── test_residue_format.py       # Q5 tag format
│   ├── test_report.py
│   └── test_preview_no_writes.py    # Verifies preview produces no mutations
├── integration/                     # Requires FlexTools + LCM + Ejagham fixtures
│   ├── test_e2e_all_categories.py   # SC-001 benchmark
│   ├── test_closure_pull_in.py      # Acceptance Scenario US1-3
│   ├── test_ws_mapping_required.py  # Q3 enforcement
│   ├── test_affix_tree_picker.py    # Q4
│   ├── test_residue_tagging.py      # FR-010 / Q5 in real target
│   └── test_same_project_refused.py # FR-019
└── fixtures/
    ├── toy_source/                  # Pointer to live Ejagham Mini (README only)
    └── copy_target.py               # Restores Ejagham Full → Ejagham Full GT-Test
```

**Structure Decision**: Single-project Python package, FLExTrans-style. The entry file
(`gramtrans.py`) is what FlexTools discovers and runs; it lives at the package root so
the FlexTools module loader picks it up via its standard convention. Helpers go under
`Lib/` (sibling, flat) and are loaded via `site.addsitedir(r"Lib")` per the FLExTrans
pattern. The PyQt widgets are the only nested subpackage (`Lib/ui/`) so the import paths
in the main window stay readable.

There is **no** `flavors/`, `core/`, or `categories/` subpackage. The v4.0.0 layered
plan was retired by constitution v5.0.0; instead, flexicon is imported directly by each
helper that needs it.

**Per-category split**: only the heavy categories (affixes, templates, MSAs) get their
own files because their closure traversal is genuinely complex. The leaf categories
(gram_categories, custom_fields, inflection_classes, stem_names, exception_features,
variant_types, complex_form_types, adhoc_rules, compound_rules) share `Lib/categories.py`
as flat module-level functions.

## Complexity Tracking

> No violations — section intentionally empty.
