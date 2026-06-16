# Research: Phase 0 — Additive Grammar Transfer

**Plan**: [plan.md](plan.md)
**Spec**: [spec.md](spec.md)
**Date**: 2026-06-16

This document consolidates the research and decisions made during Phase 0 planning.
Each entry has a **Decision**, a **Rationale**, and **Alternatives considered**. Open
items that require validation against the live flexlibs1 / LibLCM APIs (via the
FLExToolsMCP author-side tooling) are explicitly flagged.

---

## R1. Per-operation flavor mapping (flexlibs1 preferred, LibLCM as fallback)

**Decision**: Per constitution v3.0.0 Principle II, **flexlibs1 is the default for
every operation**. LibLCM is invoked only where flexlibs1 cannot express the
operation. The authoritative per-operation mapping is recorded in `flavors/base.py`
(one abstract method per operation; the flexlibs1 adapter implements every method, and
the LibLCM adapter implements only those flexlibs1 cannot). The first-pass assignment:

| Operation family | Flavor | Reason flexlibs1 cannot suffice (if LibLCM) |
|------------------|--------|---------------------------------------------|
| Project handle, opening source for read, opening target for write | **flexlibs1** | — (flexlibs1 default; established FlexTools entry point) |
| LCM object traversal (read-only walks of source) | **flexlibs1** | — |
| Object creation in target (Make* / Add* methods) | **flexlibs1** (provisional) | TBD — only fall back to LibLCM per-class where flexlibs1 lacks a Make/Add wrapper. Validate via `mcp__flextools-mcp__flextools_get_object_api` per category. |
| GUID-preserving creation | **flexlibs1 if it can; LibLCM otherwise** | flexlibs1 wrappers may not expose `Guid` at creation for some classes; those specific classes fall back to LibLCM. Enumerated in D5. |
| Writing-system inventory + creation (target side) | **flexlibs1 if available; LibLCM otherwise** | TBD — flexlibs1's WS coverage to be validated; fall back only where needed. |
| Import Residue tagging | **flexlibs1 if the residue field is exposed; LibLCM otherwise** | TBD per class. Some residue fields are reportedly not exposed by flexlibs1; those specific classes fall back. Enumerated in D6. |
| Undo wrapping (single `UndoableUnitOfWork` for Move Mode) | **flexlibs1 if it exposes the unit-of-work helper; LibLCM otherwise** | flexlibs1's undo wrapping has historically been partial; if its wrapper does not cover the full transfer loop atomically, LibLCM's `UndoableUnitOfWork` is the documented fallback. Validate in D7. |

**This table is provisional. The default is flexlibs1; each row that names LibLCM
MUST be validated against the actual flexlibs1 API surface (via
`mcp__flextools-mcp__flextools_get_object_api` and `flextools_find_wrappers_for_lcm`)
during implementation, and reverted to flexlibs1 wherever flexlibs1 turns out to
suffice after all.** Every LibLCM call site that survives validation MUST be
justified in the plan's Constitution Check ("flexlibs1 cannot do X because Y") per
Principle II.

**Rationale**: Constitution v3.0.0 explicitly preferred flexlibs1 with LibLCM as a
budgeted fallback. Concentrating the runtime on flexlibs1 keeps the module reviewable
in pure Python; reaching into the .NET bridge is a deliberate, audited exception.

**Alternatives considered**:
- *Co-equal "whichever fits best" routing (v2.0.0 framing).* Rejected — superseded by
  constitution v3.0.0; co-equal routing biased the design toward LibLCM in places
  flexlibs1 could likely have handled.
- *LibLCM for everything.* Rejected — gives up flexlibs1's idiom benefits and forces
  every read through the .NET bridge.
- *Decide per-call at runtime via a strategy object.* Rejected — over-engineered for
  Phase 0; the per-operation static mapping is easier to audit.

---

## R2. Testing approach for an LCM-bound Python module

**Decision**: Split tests three ways:

1. **Unit tests (pytest, no FlexTools, no LCM)** — `tests/unit/`. Cover pure logic:
   selection model, closure graph traversal, WS-mapping validation, Import Residue
   tag formatting, run-report aggregation, preview-no-writes assertions over fake
   data structures.
2. **Integration tests (pytest, FlexTools + LCM required)** — `tests/integration/`.
   Run against the fixture project pair in `tests/fixtures/`. Each test sets up a
   *copy* of `empty_target/` per test so writes don't pollute the fixture.
3. **Manual verification** — quickstart.md. UI flows that aren't worth automating
   (mostly visual: tree-picker layout, WS mapping dialog, stats panel rendering).

**Rationale**: The constitution's verification requirement (Development Workflow
section) says every phase release ships with pre/post Import Residue artifacts; the
integration tests produce exactly that. Unit tests cover the bits where bugs are
cheapest to fix and hardest to chase if they slip.

**Alternatives considered**:
- *Mock LCM entirely in tests.* Rejected — Import Residue + GUID-preserving creation
  is exactly the kind of behavior that mocks lie about; integration tests against
  real LCM are non-negotiable for the write path.
- *Skip unit tests, only run end-to-end.* Rejected — closure traversal and WS
  mapping validation are dense logic that deserves direct unit coverage.

---

## R3. FlexTools module entry point shape

**Decision**: A `module.py` at the package root exposing the standard FlexTools
`FlexToolsModuleClass` object with `docs` metadata + a `Main` (or equivalent) entry
function. The function instantiates the PyQt main window and surfaces it inside the
FlexTools host window. The exact attribute names and signatures are determined by the
FlexTools host version in use and MUST be validated via
`mcp__flextools-mcp__flextools_get_module_template` /
`flextools_list_skeletons` before implementation begins.

**Rationale**: Use the established skeleton; do not hand-author boilerplate. This is
the one place where the FLExToolsMCP author-side tooling is most valuable.

**Alternatives considered**:
- *Custom entry shape independent of FlexTools conventions.* Rejected — fights the
  host for no gain and defeats Principle II's "FlexTools-compatible output" mandate.

---

## R4. PyQt hosting inside the FlexTools window

**Decision**: The module's main window is a PyQt `QDialog` (modal-by-default) so that
the host's window remains the parent and the module's UI does not need to manage
top-level window lifecycle. Subordinate UIs (target picker, WS mapping dialog, affix
tree picker, stats panel) are nested `QDialog`s or `QWidget` panels inside the main
window's layout.

**Open question for implementation**: confirm that PyQt is the toolkit the current
FlexTools host ships with (vs PySide). If PySide, switch imports; the design
otherwise stands. Verify via `mcp__flextools-mcp__flextools_find_examples` against
existing FlexTools modules.

**Rationale**: Spec FR-002 mandates PyQt-shaped UI. A modal dialog keeps the
interaction focused and prevents the user from drifting away to FLEx mid-run.

**Alternatives considered**:
- *Tkinter or wx UI.* Rejected — constitution and spec both call out PyQt.
- *Non-modal main window.* Rejected — Preview/Move flow benefits from focused
  interaction; an inadvertent click in FLEx during Move could corrupt state.

---

## R5. Target project picker mechanism

**Decision**: Enumerate the user's available FLEx projects via the standard project
list location used by FLEx (the user's projects folder), filtered to exclude the
currently-open source project. Present them in `target_picker.py` as a single-select
list with project name + path; refuse Run until a target is chosen.

**Open question for implementation**: confirm the canonical mechanism for listing
projects — flexlibs1 may expose a helper, or LibLCM may, or it may require directly
inspecting the standard project directory. Resolve via
`mcp__flextools-mcp__flextools_search_by_capability` (query: "list FLEx projects").

**Rationale**: Clarification Q2 makes the open project the source by convention,
which simplifies role assignment. The picker only needs to list candidate targets.

**Alternatives considered**:
- *Free-form path browser to a `.fwdata`.* Rejected — power-user feature, can be a
  Phase 1 addition.
- *Two pickers, neither implicit.* Rejected — Clarification Q2 explicitly chose
  open=source.

---

## R6. GUID preservation across projects

**Decision**: On creating an LCM object in the target that corresponds to a source
object, set the target object's `Guid` to the source object's `Guid` *where LCM
permits*. For object classes where LCM does not permit GUID-on-create (some classes
have factory-generated GUIDs that cannot be overridden), record the mapping
`source_guid → new_target_guid` in the run report's `identity_remap` section and
surface it in the stats panel (FR-012).

**Open question for implementation**: enumerate which LCM classes permit GUID-on-
create and which don't. Resolve via
`mcp__flextools-mcp__flextools_get_object_api` per category during implementation.

**Rationale**: GUID-preservation is the core mechanism Phase 1 will rely on to detect
"already exists" duplicates. Phase 0 accepts duplicates but still preserves GUIDs so
Phase 1 / Phase 2 can identify them later. This is also Principle I.

**Alternatives considered**:
- *Always create with new GUIDs in target.* Rejected — burns Phase 1's matching
  strategy.
- *Refuse to create when GUID-on-create is denied.* Rejected — too restrictive for
  Phase 0; the remap entry in the report is the documented escape hatch.

---

## R7. Import Residue tag location

**Decision**: Use the LCM `LiftResidue` / `ImportResidue` field (whichever the host
exposes for the given object class — both names exist in LCM historically) to write
the structured tag. The tag string format per Q5:

```text
GT|<run-id>|<source-project-name>|<iso-timestamp>
```

where `run-id` is `GT-YYYYMMDD-HHMMSS` matching `iso-timestamp`. The `GT|` prefix
makes the tag string machine-parseable, and the same schema is reusable by Phase 1
(overwrite) and Phase 2 (merge) — they only need to introduce an extra field
(`|action=overwrite`, `|action=merge`).

**Open question for implementation**: confirm that every object class transferred by
Phase 0 has a residue field available on it. For classes without one (if any),
either (a) tag the parent object and treat the absent-tag child as inheriting, or
(b) skip with reason — to be decided when the enumeration is complete. Resolve via
`mcp__flextools-mcp__flextools_resolve_property` for the residue field per LCM type.

**Rationale**: Q5's structured tag is the audit foundation. A pipe-delimited form is
deliberately simple and human-readable in FLEx's Residue view.

**Alternatives considered**:
- *JSON tag.* Rejected — Residue is a single string; embedding JSON makes the field
  look noisy in the FLEx UI.
- *Per-run sentinel object in target.* Rejected — pollutes the target with non-
  grammar items; orthogonal to the per-object audit need.

---

## R8. Dependency-closure traversal

**Decision**: Closure traversal is a breadth-first graph walk implemented in
`core/closure.py`. Each category in `categories/` exposes a `dependencies(piece) ->
Iterable[Ref]` function returning the outgoing references the closure walker should
follow. The walker dedups by `(category, source_guid)` to handle diamond dependencies
(Edge Case "same item appears via two paths").

The Phase 0 closure relations are:
- Affix → its allomorphs, APRs, referenced inflection features, classes, stem names,
  exception features (FR-005)
- Template → its slots → the affixes filling those slots (FR-006)
- Variant Type → its associated inflection features (FR-004)
- Allomorph → its environments (when present)
- Slot → its containing template (downward direction not followed; slots are reached
  from templates)
- Inflection class / feature / category → no outgoing closure references (leaves)

**Rationale**: Centralizing the walk keeps Principle V in one place. Categories
declare their edges; the walker enforces the semantics.

**Alternatives considered**:
- *Per-category closure inlined into category copy logic.* Rejected — duplicates the
  dedup + visited-set logic across many files.
- *Pull from LCM's reference-tracking machinery directly.* Rejected — couples the
  closure semantics to LCM internals; Q4's tree picker needs the closure logic to
  run at planning time too (before any LCM open-for-write).

---

## R9. Preview/Move separation (Principle III)

**Decision**: Preview Mode returns an immutable `RunPlan` object built by
`core/preview.py`. Move Mode is `core/transfer.py.execute(plan, target)` and is the
only function in the module that mutates the target. The PyQt main window only
allows clicking the Move button after a Preview was computed in the current session
state — if the user changes any selection after a preview, the Move button is
re-disabled until they preview again.

**Rationale**: Principle III is a hard gate. Making "current preview is for current
selection state" mechanical (rather than convention) prevents UI drift.

**Alternatives considered**:
- *Allow Move without prior Preview.* Rejected — directly violates Principle III.
- *Re-compute the plan inside Move and assume the cached preview is stale.* Rejected
  — the user needs to see exactly what's about to happen; recomputing throws that
  away.

---

## R10. Undo scope

**Decision**: Wrap the Move-Mode write loop in a single LCM `UndoableUnitOfWork` (the
LibLCM-flavored undo wrapper). On success, the user can `Ctrl+Z` once in FLEx to
revert the entire run. On exception mid-loop, attempt to commit what's already been
written, surface the failure in the stats panel with the source GUIDs that failed,
and let the user undo (or not) at their discretion.

**Open question for implementation**: confirm `UndoableUnitOfWork` (or equivalent)
is accessible from Python through the LibLCM bridge. Resolve via
`mcp__flextools-mcp__flextools_find_wrappers_for_lcm` for "UndoableUnitOfWork".

**Rationale**: FR-016 says Move SHOULD route through standard undo; this is the
mechanism. Single unit-of-work for the whole run gives the user the "one undo
reverts everything" expectation, which matches FLEx mental model (Principle I).

**Alternatives considered**:
- *One UoW per object created.* Rejected — would require dozens of Ctrl+Z presses.
- *No undo wrapping; rely on Import Residue tag for manual cleanup.* Rejected — the
  spec assumption explicitly says undo via FLEx undo stack is the goal.

---

## R11. Project enumeration & lock detection

**Decision**: Before showing the target picker, the module enumerates available FLEx
projects in the user's projects directory. When the user selects a target, the
module opens it for write and surfaces any lock / read-only / permission error
(FR-020) before showing the WS mapping dialog. If the target equals the source by
path, abort immediately (FR-019).

**Rationale**: Failing early on a locked target is the kindest UX — the user gets
the error before they spend time on the WS mapping step.

**Alternatives considered**:
- *Lazy lock detection at write time.* Rejected — punishes the user with a late
  error after they've done all the mapping work.

---

## Items deferred to implementation

The following are not blocked for planning but MUST be resolved at the start of
implementation using the FLExToolsMCP. They are listed here so the
`/speckit-tasks` output can include them as concrete tasks:

- **D1**: Confirm flexlibs1 vs LibLCM availability of each operation listed in R1's
  table and update the table.
- **D2**: Confirm FlexTools module entry shape (R3) against the host version in
  use.
- **D3**: Confirm PyQt vs PySide (R4).
- **D4**: Confirm project enumeration mechanism (R5, R11).
- **D5**: Enumerate per-LCM-type GUID-on-create permissibility (R6).
- **D6**: Enumerate per-LCM-type residue-field availability (R7).
- **D7**: Confirm `UndoableUnitOfWork` Python accessibility (R10).
