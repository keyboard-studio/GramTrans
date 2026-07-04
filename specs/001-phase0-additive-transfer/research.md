# Research: Phase 0 — Additive Grammar Transfer

**Plan**: [plan.md](plan.md)
**Spec**: [spec.md](spec.md)
**Date**: 2026-06-16

This document consolidates the research and decisions made during Phase 0 planning.
Each entry has a **Decision**, a **Rationale**, and **Alternatives considered**.
Validation against the live flexicon API surface (via the FLExToolsMCP author-side
tooling) was performed on 2026-06-19; entries below are post-validation.

---

## R1. Per-operation flexicon surface (direct imports; no adapter)

**Decision**: Per constitution v5.0.0 Principle II, **every Phase 0 operation imports
flexicon directly**. There is no `flavors/` adapter contract in this repo. The
LibLCM-direct implementation lives in a **separate post-Phase-2 sibling repository**
(see Principle IV) that re-implements the same module against raw LCM, sharing only
the spec artifacts (spec.md, data-model.md, contracts/) — not source. The
"LibLCM-port note" column below survives as informational guidance to the future fork
authors, not as an in-tree adapter contract.

| Operation family | flexicon surface (direct import in `Lib/*.py`) | LibLCM-fork note (sibling repo, informational) |
|---|---|---|
| Project handle, opening source for read, opening target for write | `FLExProject.OpenProject(name, writeEnabled=True/False)` | LibLCM: open via `LcmCache` / `FdoCache` directly. |
| Project enumeration (target picker) | Filesystem scan of the FieldWorks projects directory (`C:\ProgramData\SIL\FieldWorks\Projects`) — no flexiconmethod enumerates the disk. Implemented in `Lib/ui/target_picker.py`. | LibLCM: same filesystem mechanism; no LCM equivalent. |
| LCM object traversal (read-only walks of source) | `project.<Operations>.GetAll()` per category accessor: `POS`, `MorphRule`, `InflectionFeature`, `Allomorph`, `WritingSystem`, `GramCat`, `Variant`, `CustomField`, `Phonemes`, etc. | LibLCM: `Cache.LangProject.PartsOfSpeechOA.PossibilitiesOS` style traversal. |
| Object creation in target — most categories | `project.POS.Create`, `project.MorphRule.CreateAffixTemplate`, `project.InflectionFeature.CreateClosedFeatureWithValues`, `project.Phonemes.Create`, `project.MSA.CreateStem` / `CreateInflAff` / `CreateDerivAff` / `CreateUnclassifiedAffix`, `project.WritingSystem.<Create>`. | LibLCM: `IPartOfSpeechFactory.Create`, `IMoInflAffixTemplateFactory.Create`, `IFsClosedFeatureFactory.Create`, etc. resolved via `Cache.ServiceLocator.GetInstance<T>()`. |
| ServiceLocator fallback (when no Operations wrapper) | `project.GetService(IFooFactory)` — flexicon discoverable wrapper around `Cache.ServiceLocator.GetService(...)`. No `clr.GetClrType()` needed. | LibLCM: direct `Cache.ServiceLocator.GetInstance<T>()` / `GetService<T>()`. |
| GUID-preserving creation | Some flexicon factory wrappers DO accept a `Guid` parameter on `Create()` — validated against `POSOperations`, `MorphRuleOperations.CreateAffixTemplate`, slot factory during the STATUS.md Layer 1+2 spike. Where they don't, the pattern is `factory.Create()` → add to owner → assign `obj.Guid`. The helper lives inline at the top of `Lib/transfer.py` (no separate adapter helper). | LibLCM: identical pattern, just without the `GetService` wrapper. |
| Writing-system inventory + creation (target side) | Read: `project.GetAllAnalysisWSs()`, `project.GetAllVernacularWSs()`, `project.GetWritingSystems()`, `project.WSHandle(tag)`, `project.WSUIName(handle)`. Create: `project.WritingSystem.<Create>` (per Operations accessor). | LibLCM: `Cache.ServiceLocator.WritingSystemManager` directly. |
| Sync writable properties on existing/new objects | `BaseOperations.ApplySyncableProperties(item, props, ws_map=None)` — the inverse of `GetSyncableProperties`. **Only available in the patched MattGyverLee/flexicon fork** (see [CLAUDE.md](../../CLAUDE.md)); stock flexicon does not expose it. | LibLCM: open-coded multistring/string apply with the same dict shape. |
| Polymorphic property access (`LiftResidue`, `Description`, `Guid`, etc.) | `CastingOperations.cast_to_concrete(obj)` from flexicon — wraps the pythonnet cast. The MCP polymorphic-casting validator auto-rewrites violations. | LibLCM: explicit `((IConcreteType)obj).Property` casts. |
| Import Residue tagging — Carrier A (LCM residue field) | For `ILexEntry`, `ILexSense`, `ILexEntryRef`, `ILexEtymology`, `ILexPronunciation`, `ILexReference`, `ILexExampleSentence`, `IMoForm`, `IMoMorphSynAnalysis`: set `LiftResidue` (validated as the residue carrier on these classes). Helper: `Lib/residue.py.apply_carrier_a(obj, tag)`. | LibLCM: identical property, accessed via explicit cast. |
| Import Residue tagging — Carrier B (Description-append) | For grammar-piece classes lacking a residue field (`IPartOfSpeech`, `IMoInflAffixTemplate`, `IMoInflAffixSlot`, `IFsClosedFeature`, `IFsComplexFeature`, `IFsFeatStrucType`, `IFsSymFeatVal`, `IMoInflClass`, `IMoStemName`, `IMoCompoundRule`, `IMoAdhocProhibGr`, `IPhPhonemeSet`, `IPhEnvironment`, `IPhNaturalClass`, `IPhSegmentRule`, etc.): append `\n[GT-Tag]: GT\|<run_id>\|<source>\|<iso_ts>` to the inherited `Description` multistring (defined on `ICmPossibility`, `ICmMajorObject`, `IFsFeatDefn`, and others — confirmed via `resolve_property` casting index). Append is non-destructive; existing prose preserved. Helper: `Lib/residue.py.apply_carrier_b(obj, tag)`. | LibLCM: identical strategy; same inherited interfaces. |
| Undo wrapping | The FlexTools runner already wraps each `MainFunction` invocation in an `UndoableUnitOfWork` (verified per STATUS.md "MCP validator quirks": nesting your own raises "Nested tasks are not supported"). Module code does NOT open its own UOW. | LibLCM-fork repo: same constraint applies under FlexTools. Stand-alone LibLCM tools open their own UOW via `UndoableUnitOfWorkHelper.Do(...)` from `SIL.LCModel.Infrastructure`. |

**Rationale**: The v4.0.0 adapter-contract experiment added overhead with no payoff
during a single-flavor build. v5.0.0 retires it. Direct flexicon imports keep module
code idiomatic; the LibLCM-fork repo is free to pick natural raw-LCM idioms in its own
codebase, sharing the spec artifacts above as the contract instead of a Python-shaped
adapter base class.

**Alternatives considered**:
- *Mandatory `flavors/` adapter contract (v4.0.0 framing).* Rejected — added a layer
  of indirection across `core/` ↔ `flavors/` ↔ flexicon with no payoff during the
  single-flavor build. The LibLCM port is cleaner as a separate sibling repo where
  raw-LCM idioms are first-class instead of squeezed through a Python-shaped adapter.
- *flexlibs1-preferred with LibLCM fallback (v3.0.0 framing).* Rejected — flexlibs1
  lacks the `project.MSA`, `project.MorphRule.CreateAffixTemplate`, and
  `project.InflectionFeature.CreateClosedFeatureWithValues` surfaces that Phase 0
  needs.
- *Co-equal "whichever fits best" routing (v2.0.0 framing).* Rejected — biased the
  design toward LibLCM where flexicon had perfectly good wrappers.
- *LibLCM for everything from day one.* Rejected — gives up flexicon's idiom
  benefits, casting helpers, and Operations classes; pushes complexity into every
  call site.
- *Decide per-call at runtime via a strategy object.* Rejected — over-engineered for
  Phase 0.

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

**Decision** (validated 2026-06-19, confirmed by STATUS.md): The entry file is
`src/gramtrans/gramtrans.py` following the **FLExTrans module convention** (e.g.,
`FLExTrans/FlexTools_2.3.2/FlexTools/Modules/Chinese/Update_Pinyin_Fields.py`):

```python
# src/gramtrans/gramtrans.py
from flextoolslib import *

import site
site.addsitedir(r"Lib")

# direct flexicon imports
from flexicon.BaseOperations import ApplySyncableProperties
# ...

docs = {
    FTM_Name       : "GramTrans — Additive Grammar Transfer",
    FTM_Version    : "0.1.0",
    FTM_ModifiesDB : True,
    FTM_Synopsis   : "Copy grammar pieces from a toy source project to a target.",
    FTM_Help       : r"Doc\GramTrans Help.pdf",
    FTM_Description: "...",
}

def MainFunction(project, report, modifyAllowed):
    # instantiate PyQt main window from Lib/ui/main_window.py
    ...
```

The `FlexToolsModuleClass` wrapper is **NOT** required (the official `flextoolslib`
template returned by `mcp__flextools-mcp__flextools_get_module_template` omits it; the
module-level `docs` dict + `MainFunction` are sufficient for FlexTools to discover and
invoke the module).

**Rationale**: Use the established FLExTrans skeleton; do not hand-author boilerplate.
Helpers live under `Lib/` and are loaded via `site.addsitedir(r"Lib")` per the
FLExTrans pattern.

**Alternatives considered**:
- *`module.py` with `FlexToolsModuleClass` wrapper (v4.0.0 plan).* Rejected — the
  current FlexTools template doesn't require the wrapper; adds boilerplate for no
  gain.
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

**Resolved (2026-06-19)**: filesystem scan of `C:\ProgramData\SIL\FieldWorks\Projects`
is the canonical mechanism — no flexicon / LCM helper enumerates the disk. The
MCP's own `flextools_list_projects` is the reference implementation.
`Lib/ui/target_picker.py` implements the scan directly (no adapter indirection) and
filters out the currently-open source by path equality.

**Rationale**: Clarification Q2 makes the open project the source by convention,
which simplifies role assignment. The picker only needs to list candidate targets.

**Alternatives considered**:
- *Free-form path browser to a `.fwdata`.* Rejected — power-user feature, can be a
  Phase 1 addition.
- *Two pickers, neither implicit.* Rejected — Clarification Q2 explicitly chose
  open=source.

---

## R6. GUID preservation across projects

**Decision** (revised 2026-06-19 against STATUS.md Layer 1+2 spike): Several flexicon
Operations wrappers in the patched MattGyverLee fork DO accept a `Guid` parameter on
their `Create()` overloads (validated against POS, affix template, and slot factories
during the Layer 1+2 spike — source GUIDs were preserved end-to-end, see STATUS.md
"Layer 2 — Template + 4 Slots"). Where the wrapper does not accept a Guid, the
standard pattern is:

1. Resolve the factory via `project.GetService(IFooFactory)` (flexicon's discoverable
   wrapper around `Cache.ServiceLocator.GetService`).
2. Call `factory.Create()` (or the appropriate Create overload) to instantiate.
3. Add the new object to its owning collection (e.g., `PhonemesOC.Add(new_phoneme)`)
   so it has an ICmObject identity.
4. Immediately assign `new_obj.Guid = source_guid` BEFORE any further mutation.
5. If LCM rejects the GUID assignment (rare; some classes are factory-frozen), record
   the mapping `source_guid → new_target_guid` in the run report's `identity_remap`
   section per FR-012.

Phase 0 implementation keeps this pattern inline in `Lib/transfer.py` (no adapter
indirection per constitution v5.0.0). Category functions either call the
`Create(Guid, ...)` overload directly when available, or fall through to the
`Create()` + `obj.Guid = ...` pattern; the choice is documented per-category in
[contracts/category-transfer.md](contracts/category-transfer.md).

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

**Decision** (validated 2026-06-19): Dual-carrier residue tagging, because
`resolve_property` confirmed that most Phase 0 grammar-piece classes have NO
residue field at all. The tag string format per Q5:

```text
GT|<run-id>|<source-project-name>|<iso-timestamp>
```

where `run-id` is `GT-YYYYMMDD-HHMMSS` matching `iso-timestamp`. The `GT|` prefix
makes the tag string machine-parseable, and the same schema is reusable by Phase 1
(overwrite) and Phase 2 (merge) — they only need to introduce an extra field
(`|action=overwrite`, `|action=merge`).

- **Carrier A — `LiftResidue` (preferred when available)**. Set the tag directly
  on the `LiftResidue` multistring. Validated as available on: `ILexEntry`,
  `ILexEntryRef`, `ILexEtymology`, `ILexExampleSentence`, `ILexPronunciation`,
  `ILexReference`, `ILexSense`, `IMoForm`, `IMoMorphSynAnalysis`.
- **Carrier B — `Description`-append (fallback for grammar-only classes)**. For
  classes lacking `LiftResidue` (most grammar pieces: `IPartOfSpeech`,
  `IMoInflAffixTemplate`, `IMoInflAffixSlot`, `IFsClosedFeature`,
  `IFsComplexFeature`, `IFsFeatStrucType`, `IFsSymFeatVal`, `IMoInflClass`,
  `IMoStemName`, `IMoCompoundRule`, `IMoAdhocProhibGr`, `IPhPhonemeSet`,
  `IPhEnvironment`, `IPhNaturalClass`, `IPhSegmentRule`, etc.), append the tag to
  the inherited `Description` multistring (defined on `ICmPossibility`,
  `ICmMajorObject`, `IFsFeatDefn`, and a few others — confirmed via the
  `resolve_property` casting index). Append format:

  ```text
  <existing Description prose, unchanged>

  [GT-Tag]: GT|<run_id>|<source_project_name>|<iso_timestamp>
  ```

  The `[GT-Tag]:` line prefix is the machine-parseable marker. Append is
  non-destructive: existing prose is preserved exactly; the tag goes on its own
  trailing line after a blank-line separator. The parser
  (`ImportResidueTag.parse(s)`) handles both Carrier A (single-line tag) and
  Carrier B (find the `[GT-Tag]:` line in a multi-line value).

Implementation: `Lib/residue.py` exposes `apply_carrier_a(obj, tag)` and
`apply_carrier_b(obj, tag)` plus a dispatcher `apply_residue(obj, tag)` that picks
the right carrier based on the object's class (Carrier A class list above is the
lookup table). Category code in `Lib/categories*.py` calls `apply_residue` once per
created object; it does not need to know which carrier is in use.

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
`Lib/closure.py`. Each category module under `Lib/` (`Lib/categories.py` for the
leaves; `Lib/categories_affixes.py`, `Lib/categories_templates.py`,
`Lib/categories_msas.py` for the heavy ones) exposes a `dependencies(piece) ->
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
`Lib/preview.py`. Move Mode is `Lib/transfer.py.execute(plan, target)` and is the
only function in the module that mutates the target. The PyQt main window only
allows clicking the Move button after a Preview was computed in the current session
state — if the user changes any selection after a preview, the Move button is
re-disabled until they preview again.

The STATUS.md Layer 1+2 work currently lives inline in
`src/gramtrans/gramtrans.py.transfer_verb_vertical()`; **tasks.md T-Spike** refactors
it into the Preview/Move pair per constitution v5.0.0 Principle III closing clause
before Layer 3 begins.

**Rationale**: Principle III is a hard gate. Making "current preview is for current
selection state" mechanical (rather than convention) prevents UI drift.

**Alternatives considered**:
- *Allow Move without prior Preview.* Rejected — directly violates Principle III.
- *Re-compute the plan inside Move and assume the cached preview is stale.* Rejected
  — the user needs to see exactly what's about to happen; recomputing throws that
  away.

---

## R10. Undo scope

**Decision** (validated 2026-06-19 via the STATUS.md Layer 1+2 spike): The FlexTools
runner **already wraps each `MainFunction` invocation in an `UndoableUnitOfWork`** —
nesting our own raises `"Nested tasks are not supported"` (STATUS.md "MCP validator
quirks"). Therefore `Lib/transfer.py` does NOT open its own UOW; it iterates over
`RunPlan.actions` inside the runner's outer unit. On success, the user can `Ctrl+Z`
once in FLEx to revert the entire run — confirmed end-to-end during the Layer 1+2
spike against `Ejagham Full GT-Test`. On exception mid-loop, the runner's standard
semantics roll the unit of work back; the stats panel reports the source GUIDs that
were not written.

The LibLCM-fork sibling repo will need to choose its own UOW strategy depending on
whether it runs under FlexTools (same constraint) or as a stand-alone LibLCM tool
(opens its own UOW via `UndoableUnitOfWorkHelper.Do(...)` from
`SIL.LCModel.Infrastructure`).

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
projects in the user's projects directory (filesystem scan per R5). When the user
selects a target, the module opens it for write via
`FLExProject.OpenProject(name, writeEnabled=True)` and catches the failure mode that
LCM raises when the project is locked or read-only — surfacing it as a user-visible
error before showing the WS mapping dialog (FR-020). If the target equals the source
by path, abort immediately (FR-019).

**Detection mechanism (T033b reference)**: Under flexicon, a locked target raises
on `OpenProject(..., writeEnabled=True)`. The exact exception type to catch is
LCM-side (`SIL.LCModel.LcmFileLockedException` or similar); confirm during T033b
implementation by triggering the condition (open the target in FLEx itself before
running the module) and inspecting the raised .NET exception. Wrap the open call in
a `try/except` that maps the LCM exception to a user-friendly `TargetLockedError`
and aborts before the WS mapping step.

**Rationale**: Failing early on a locked target is the kindest UX — the user gets
the error before they spend time on the WS mapping step.

**Alternatives considered**:
- *Lazy lock detection at write time.* Rejected — punishes the user with a late
  error after they've done all the mapping work.
- *Probe via a sentinel write.* Rejected — touches the target before consent;
  violates Principle III.

---

## Items deferred to implementation

All D-validation items from the v3.0.0 draft of this document were resolved on
2026-06-19 against the live flexicon surface via the FLExToolsMCP. Findings are
baked into R1, R6, R7, R10 above. Status:

- ~~**D1**: per-operation flavor mapping~~ → resolved in R1; constitution bumped
  to v4.0.0 (flexicon-primary) on 2026-06-19, then to v5.0.0 (no adapter contract;
  LibLCM port = separate sibling repo) on the same date.
- ~~**D2**: FlexTools module entry shape~~ → resolved; the FLExTrans-style
  convention is `docs = {...}` dict + `MainFunction(project, report, modifyAllowed)`
  in a flat entry file (`src/gramtrans/gramtrans.py`) with helpers under `Lib/`
  loaded via `site.addsitedir(r"Lib")`. The `FlexToolsModuleClass` wrapper is NOT
  required. See R3 above.
- **D3**: PyQt vs PySide — the MCP did not surface explicit examples; verified by
  inspecting the installed FlexTools host directly during `Lib/ui/main_window.py`
  implementation. Default to PyQt5 per `pyproject.toml`; switch to PySide2 if the
  host import fails.
- ~~**D4**: project enumeration mechanism~~ → resolved as filesystem scan of the
  FieldWorks projects directory; no flexicon / LCM method enumerates the disk
  (the MCP's own `flextools_list_projects` does this and is the reference
  implementation).
- ~~**D5**: per-LCM-type GUID-on-create permissibility~~ → resolved in R6 (revised
  2026-06-19 against the STATUS.md Layer 1+2 spike): some flexicon factory
  wrappers DO accept a `Guid` parameter on `Create()`; where they don't, the
  pattern is `factory.Create()` → add to owner → assign `obj.Guid`.
- ~~**D6**: per-LCM-type residue-field availability~~ → resolved in R7 (dual
  carrier: `LiftResidue` where present, `Description`-append otherwise).
- ~~**D7**: `UndoableUnitOfWork` Python accessibility~~ → resolved in R10
  (revised 2026-06-19): the FlexTools runner pre-wraps each `MainFunction`
  invocation in a UOW; module code does NOT nest its own.
