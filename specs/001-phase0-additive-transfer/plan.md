# Implementation Plan: Phase 0 — Additive Grammar Transfer

**Branch**: `001-phase0-additive-transfer` | **Date**: 2026-06-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from [specs/001-phase0-additive-transfer/spec.md](spec.md)

**Note**: This plan is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Deliver a FlexTools-compatible Python module that copies a user-selected set of grammar
pieces (and their full dependency closure) from the currently-open FLEx project (source)
to a user-picked target FLEx project, additively, with a Preview Mode default and a
structured Import Residue tag on every newly added object. Implementation uses
**flexlibs1 as the preferred API flavor**, with **LibLCM as a deliberate fallback only
where flexlibs1 cannot express the operation**, per constitution v3.0.0 Principle II.
flexlibs2 is out of scope. The UI is PyQt, hosted inside the FlexTools window, and
includes a writing-system mapping step (both vernacular and analysis WSs, 1:1, create on
demand) before any transfer writes occur.

## Technical Context

**Language/Version**: Python 3 (whatever version the host FlexTools install ships with;
no language-version constraints introduced by this module beyond what FlexTools requires).

**Primary Dependencies**:
- **flexlibs1** — legacy Python flexlibs (LCM Python wrappers). **Preferred runtime
  flavor.** Every operation defaults here.
- **LibLCM** — the .NET LCM library, accessed from Python via the FlexTools .NET bridge.
  **Deliberate fallback** invoked only where flexlibs1 cannot express the operation.
  Each LibLCM call site MUST be justified in the Constitution Check.
- **PyQt** — UI toolkit, hosted inside the FlexTools main window.

flexlibs2 is **explicitly excluded** per constitution Principle II for reverse
compatibility.

**Storage**: None of its own. The module reads from the source FLEx project (read-only)
and writes to the target FLEx project via LCM. All persistence is delegated to the LCM
data layer the host already provides.

**Testing**:
- **Unit tests** (`pytest`) for pure-Python logic: selection model, dependency-closure
  traversal, Import Residue tag formatter, run-report aggregation, WS-mapping
  validation. These run without FlexTools / LCM.
- **Integration tests** against a small fixture pair of FLEx projects (a toy source and
  an empty target) shipped in `tests/fixtures/`. These require a FlexTools host.
- **Manual verification** per `quickstart.md` for end-to-end UI flows that aren't
  reasonable to automate.

**Target Platform**: Windows + FlexTools host (FLEx is Windows-primary). The module
shape is platform-agnostic Python, but its runtime context is whatever FlexTools
supports.

**Project Type**: FlexTools module (Python module embedded in a desktop host). Single
deliverable, no separate frontend/backend split.

**Performance Goals**: Per spec SC-001 — a ≤100-piece benchmark grammar transfers in
under 5 minutes wall-clock. No throughput target beyond that; this is an interactive
authoring tool, not a bulk pipeline.

**Constraints**:
- **flexlibs1 is preferred; LibLCM is fallback only.** Every operation defaults to
  flexlibs1; LibLCM call sites require Constitution-Check justification.
- No flexlibs2.
- Preview is the default mode (Constitution Principle III).
- GOLD categories / inflection features inviolable (Principle I).
- Same-version source/target precondition (Clarification Q1).
- WS mapping step is mandatory before write (Clarification Q3, FR-011).

**Scale/Scope**:
- Realistic toy source projects: tens of grammar pieces, low hundreds at the high end.
- Affix counts may reach low hundreds (drives the tree-picker UI shape per
  Clarification Q4).
- Phase 0 only — Phase 1 (overwrite) and Phase 2 (interactive merge) are deferred.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Evaluated against [.specify/memory/constitution.md](../../.specify/memory/constitution.md) v2.0.0.

| # | Principle | Status | Plan compliance |
|---|-----------|--------|-----------------|
| I | FLEx Domain Fidelity (NON-NEGOTIABLE) | **PASS** | GUID-first identity (FR-012); GOLD inviolability (FR-022); WS mapping is mandatory and explicit (FR-011); cross-refs must resolve or the item is skipped (FR-021, SC-003). |
| II | flexlibs1-Preferred with LibLCM Fallback; no flexlibs2 | **PASS** | `flavors/` package isolates the two adapters. flexlibs1 is the default for every operation per research.md R1; LibLCM is used only where flexlibs1 cannot express the operation, and each such call site is enumerated and justified in research.md R1's table and in the implementation tasks. MCP is author-side only, not in the runtime tree. |
| III | Preview-Before-Mutate (NON-NEGOTIABLE) | **PASS** | Preview is the default mode (FR-014); Move Mode requires a current-session preview first (FR-015); preview produces no writes (SC-006). Implementation: `preview.py` computes the full plan; `transfer.py` consumes a plan object — they are separate code paths. |
| IV | Phased Merge Discipline | **PASS** | This plan ships Phase 0 only. No overwrite, no merge UI, no conflict prompts. The Import Residue tag schema is forward-compatible (Clarification Q5) so Phase 1/2 can adopt it unchanged, but Phase 0 ships independently and is independently useful. |
| V | Referential Completeness | **PASS** | `core/closure.py` is a first-class component; closure-by-default toggle in the main window (FR-013); items whose closure cannot be satisfied are skipped entire, not partial (FR-021). |

**No violations. No entries in Complexity Tracking.**

The plan also honors Clarifications Q1–Q5:
- Q1 (same-version precondition): documented in Technical Context; no runtime version check needed.
- Q2 (open=source, picker=target): wired into `ui/main_window.py` and the `data-model.md` `RunContext` entity.
- Q3 (manual 1:1 WS mapping, vernacular + analysis, create on demand): `ui/ws_mapping_dialog.py` + `core/ws_mapping.py`.
- Q4 (affix tree picker by template → slot → affix, with Unbound bucket): `ui/affix_tree_picker.py`.
- Q5 (structured Import Residue tag): `core/residue.py` formats `GT-YYYYMMDD-HHMMSS` + source project name + ISO timestamp.

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

```text
src/
└── gramtrans/                        # Python package — the module itself
    ├── __init__.py
    ├── module.py                     # FlexTools module entry point (FlexToolsModuleClass)
    ├── ui/                           # PyQt UI layer
    │   ├── __init__.py
    │   ├── main_window.py            # Category toggles + closure toggle + run button
    │   ├── target_picker.py          # FR-003: open=source, picker=target
    │   ├── ws_mapping_dialog.py      # FR-011 / Q3: vernacular + analysis 1:1 mapping
    │   ├── affix_tree_picker.py      # FR-007 / Q4: template → slot → affix + Unbound
    │   └── stats_panel.py            # FR-017 post-run report panel
    ├── core/                         # Engine — flavor-agnostic
    │   ├── __init__.py
    │   ├── selection.py              # Selection model (category toggles + per-affix)
    │   ├── closure.py                # Dependency-closure traversal (Principle V)
    │   ├── ws_mapping.py             # Validates user-supplied WS mapping
    │   ├── preview.py                # Builds the run plan; never writes
    │   ├── transfer.py               # Executes the run plan against a target
    │   ├── residue.py                # Q5 structured Import Residue tag
    │   └── report.py                 # Run report aggregation (added / skipped / why)
    ├── flavors/                      # API-flavor adapters (Principle II)
    │   ├── __init__.py
    │   ├── base.py                   # Abstract per-operation interface
    │   ├── flexlibs1_adapter.py      # flexlibs1-backed implementations
    │   └── liblcm_adapter.py         # LibLCM-backed implementations
    └── categories/                   # Per-category transfer logic (FR-004)
        ├── __init__.py
        ├── writing_systems.py        # Q3-mediated mapping; not raw copy
        ├── gram_categories.py        # FR-022 GOLD inviolable
        ├── inflection_features.py    # FR-022 GOLD inviolable
        ├── custom_fields.py
        ├── inflection_classes.py
        ├── stem_names.py
        ├── exception_features.py
        ├── variant_types.py
        ├── complex_form_types.py
        ├── adhoc_rules.py
        ├── compound_rules.py
        ├── affixes.py                # FR-005: includes allomorphs + APRs
        ├── slots.py
        └── templates.py              # FR-006: includes slots + filling affixes

tests/
├── unit/                             # No host required
│   ├── test_selection.py
│   ├── test_closure.py
│   ├── test_ws_mapping.py
│   ├── test_residue_format.py        # Q5 tag format
│   ├── test_report.py
│   └── test_preview_no_writes.py     # Verifies preview produces no mutations
├── integration/                      # Requires FlexTools + LCM
│   ├── test_e2e_all_categories.py    # SC-001 benchmark
│   ├── test_closure_pull_in.py       # Acceptance Scenario US1-3
│   ├── test_ws_mapping_required.py   # Q3 enforcement
│   ├── test_affix_tree_picker.py     # Q4
│   ├── test_residue_tagging.py       # FR-010 / Q5 in real target
│   └── test_same_project_refused.py  # FR-019
└── fixtures/
    ├── toy_source/                   # Tiny FLEx project with ≤20 grammar pieces
    └── empty_target/                 # Pristine empty FLEx project
```

**Structure Decision**: Single-project Python package (Option 1 from the template),
because GramTrans ships as exactly one FlexTools module. The internal layering is
**UI → core → flavors / categories**:

- **`ui/`** holds nothing but PyQt widgets and translates user actions into calls on
  `core/`. It must not import from `flavors/` or `categories/`.
- **`core/`** holds flavor-agnostic engine logic. It coordinates selection, closure,
  preview, transfer, residue, and reporting. It depends on `categories/` (for per-
  category traversal) and on `flavors/` (for the actual LCM calls), but knows neither
  PyQt nor LCM directly.
- **`flavors/`** is the only layer that imports flexlibs1 or LibLCM. Constitution
  Principle II's "which flavor per operation" choice lives here; research.md fills in
  the per-operation mapping.
- **`categories/`** holds the per-grammar-piece-category semantics (what counts as a
  dependency, how to copy this kind of object, what makes an item's closure
  unsatisfied). Each category file calls into `flavors/` for the underlying LCM ops.

This layering directly serves Principle III (Preview/Move are two consumers of the
same `core` plan), Principle II (flavor choice isolated to one layer), and Principle V
(closure logic lives in one well-tested module, not sprinkled across categories).

## Complexity Tracking

> No violations — section intentionally empty.
