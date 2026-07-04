<!--
Sync Impact Report
==================
Version change: 4.0.0 → 5.1.0
Bump rationale: MAJOR (5.0.0) — Principle II redefined again. v4.0.0's mandatory
flavor-adapter contract (`flavors/base.py` + per-flavor adapters as the only
allowed import point for LCM operations) is REMOVED. v5.0.0 says: every
Phase 0/1/2 module file imports `flexicon` directly. The LibLCM-direct port
is now a **separate fork project** (a sibling repo built on the same spec/plan
artifacts), not a same-contract in-tree re-implementation. This redefinition
codifies the actual shape on disk (the FLExTrans-style entry file plus a `Lib/`
sibling directory of helpers) and the chosen flexicon-fork dependency model.

MINOR (5.1.0) — Principle II updated: flexicon (dist pyflexicon) is now the
runtime dependency in place of the MattGyverLee/flexicon fork. flexicon is a
standalone independent project — NOT a fork of stock flexicon. The flexicon
package name resolves via a deprecation shim (removal targeted flexicon v5.0.0);
new code MUST use flexicon imports. pyproject.toml declares `pyflexicon>=4.1`.
Last Amended date set to 2026-07-04.

Additionally, Principle III (Preview-Before-Mutate) is preserved unchanged in
spirit but gains an explicit, one-time validation-spike clause acknowledging
that the Layer 1 + Layer 2 work in STATUS.md ran Move-mode writes against a
live throwaway target before the Preview engine existed. All further Move
work is gated on the Preview engine.

Principles defined:
  I.   FLEx Domain Fidelity (NON-NEGOTIABLE)
  II.  FlexTools-Compatible Output, flexicon-Direct                    (REDEFINED)
  III. Preview-Before-Mutate (NON-NEGOTIABLE)                          (clarified)
  IV.  Phased Merge Discipline                                         (clarified)
  V.   Referential Completeness

Modified principles:
  II. v4.0.0 "flexicon-Primary with LibLCM Backport (adapter pattern mandatory)"
      → v5.0.0 "flexicon-Direct (no adapter pattern in this repo)"
      → v5.1.0 "flexicon-Direct". Module code imports flexicon directly. There
      is no `flavors/base.py`, no `flavors/flexicon_adapter.py`, no
      `flavors/liblcm_adapter.py` in this tree. flexicon (dist pyflexicon) is
      a standalone independent project — NOT a fork of stock flexicon. The
      flexicon package name resolves via a deprecation shim (removal targeted
      flexicon v5.0.0); new code MUST use flexicon imports. The LibLCM-direct
      port lives in a separate sibling repository authored after all merge phases
      ship, sharing only the spec artifacts (spec.md, data-model.md, contracts/)
      — not source files.

  III. Preview-Before-Mutate (NON-NEGOTIABLE) is unchanged in normative force.
      Added: a one-time, recorded validation spike (STATUS.md Layer 1 + Layer 2)
      is acknowledged as predating the Preview engine. All further Move-mode
      work — Layer 3 included — MUST go through `Lib/preview.py` (plan-builder)
      and `Lib/transfer.py` (plan-executor).

  IV. Phase 3 redefined from "in-tree LibLCM port" to "LibLCM fork project".
      Phase 3 is no longer part of this repo's tree.

Kept from v4.0.0:
  - The shipped artifact is a FlexTools-compatible module.
  - The FLExToolsMCP is a non-normative author-side assistant, not a runtime
    dependency.
  - flexicon (pyflexicon) is the runtime flavor for Phase 0/1/2.
  - flexlibs1 is NOT used.
  - GOLD inviolability, GUID-first identity, dual-carrier residue.

Removed framing:
  - "flavor adapter pattern is mandatory from day one" (removed).
  - "`flavors/base.py` defines the contract; `flavors/flexicon_adapter.py` is
    implemented in full" (removed — no `flavors/` directory exists).
  - "All `core/` and `categories/` code calls the adapter contract — never raw
    flexicon imports directly" (reversed — modules import flexicon directly).

Added framing:
  - flexicon (dist pyflexicon) is a standalone independent project — NOT a fork
    of stock flexicon. It natively provides the `WritingSystems` enumeration
    fix and the `ApplySyncableProperties` method on `BaseOperations` + 8
    Grammar Operations subclasses. The flexicon package name resolves via a
    deprecation shim (removal targeted flexicon v5.0.0). pyproject.toml declares
    `pyflexicon>=4.1`; the install path is documented in [CLAUDE.md](../../CLAUDE.md)
    and the repo README. The disk directory is literally named `flexicon` and
    MUST NOT be renamed.
  - File layout follows the **FLExTrans module convention**: a flat entry
    file (`src/gramtrans/gramtrans.py` with `docs = {...}` + `def MainFunction(
    project, report, modifyAllowed)`) plus a sibling `Lib/` subdirectory of
    helpers loaded via `site.addsitedir(r"Lib")`. No `flavors/`, no `ui/`,
    `core/`, `categories/` subpackages — instead flat helpers under `Lib/`.

Templates requiring updates:
  ✅ .specify/memory/constitution.md (this file)
  ⚠ .specify/templates/plan-template.md — Constitution Check should describe
      the post-Phase-2 LibLCM fork as a sibling deliverable, not an in-tree
      port.

Downstream artifact updates required (in this project):
  ⚠ specs/001-phase0-additive-transfer/plan.md — Summary, Technical Context,
      Constitution Check Row II, Project Structure (FLExTrans layout).
  ⚠ specs/001-phase0-additive-transfer/spec.md — FR-001 clarifies the entry
      shape; Assumptions API-surface paragraph.
  ⚠ specs/001-phase0-additive-transfer/data-model.md — drop the `Flavor` enum
      LIBLCM forward-compat field on PlannedAction (Phase 3 is a separate
      fork project; this tree only ever produces FLEXICON actions).
  ⚠ specs/001-phase0-additive-transfer/contracts/category-transfer.md — drop
      the flavor-adapter framing; categories call flexicon directly.
  ⚠ specs/001-phase0-additive-transfer/tasks.md — drop T016 / T017 / T018
      (flavor adapter scaffolding + stub); collapse leaf-category tasks
      (T039–T048) into one inline `Lib/categories.py` task; keep dedicated
      files only for affixes / templates / MSAs; add the Layer 1+2 refactor
      spike task; add an FR-020 (target-locked) task.

Deferred items: none new. The LibLCM-direct port is now a separate fork
project, not a deferred in-tree task.

---

Prior Sync Impact Reports
-------------------------
v3.0.0 → v4.0.0: flexicon-primary with mandatory adapter pattern; LibLCM as
  in-tree backport target.
v2.0.0 → v3.0.0: flexlibs1-preferred, LibLCM-fallback (reversed in v4.0.0).
v1.1.0 → v2.0.0: MCP demoted to author-side; LibLCM promoted to runtime flavor.
v1.0.0 → v1.1.0: FLExTools MCP designated primary discovery surface.
(uninitialized) → v1.0.0: Initial ratification.
-->

# GramTrans Constitution

GramTrans is a FlexTools module that transfers FieldWorks Language Explorer (FLEx) grammar
data — phonology, morphology, lexicon scaffolding, and templates — from a "toy" project to
a production project. This constitution governs how the module is designed, built, and
evolved.

## Core Principles

### I. FLEx Domain Fidelity (NON-NEGOTIABLE)

All transfer operations MUST preserve the semantics defined by the FieldWorks Language and
Culture Model (LCM) and the user's mental model in FLEx. Specifically:

- GUIDs are the primary identity for LCM objects; preserve them on transfer whenever the
  target project does not already contain a colliding GUID.
- Reserved/GOLD categories and inflection features MUST be retained — never overwritten,
  renamed, or deleted as a side effect of import.
- Writing-system identity (vernacular/analysis mappings) MUST be validated and explicitly
  mapped before any string-bearing field is written.
- Cross-references (affix → slot, slot → template, allomorph → environment, APR → category,
  etc.) MUST resolve to real objects in the target after transfer, or the transfer for that
  item MUST fail loudly rather than silently drop the reference.

Rationale: A transfer that corrupts LCM invariants or breaks FLEx's UI assumptions is worse
than no transfer at all — users will lose trust and revert.

### II. FlexTools-Compatible Output, flexicon-Direct

The module's shipped artifact MUST be a **FlexTools-compatible module** that runs inside a
standard FlexTools host. At runtime it imports **flexicon directly**. There is no
flavor-adapter contract in this repository — the v4.0.0 `flavors/base.py` requirement is
removed.

- **flexicon (dist pyflexicon) is the direct runtime dependency.** flexicon is a standalone
  independent project — NOT a fork of stock flexicon. Every Phase 0/1/2 file imports
  flexicon modules at the top (`from flexicon.BaseOperations import ApplySyncableProperties`,
  `from flexicon.Grammar.POSOperations import POSOperations`, etc.). The Operations-class
  API is the canonical surface (`project.POS`, `project.MorphRule`,
  `project.InflectionFeature`, `project.MSA`, `project.Phonemes`, `project.PhonRules`,
  `project.WritingSystem`, `project.LexEntry`, `project.LexSense`, `project.Allomorph`,
  `project.Variant`, `project.CustomField`, etc.); `project.GetService(IFooFactory)` is the
  fallback when no Operations wrapper covers a specific LCM surface;
  `CastingOperations.cast_to_concrete(obj)` is used when polymorphic property access
  requires casting (per MCP polymorphic-casting validator). `pyproject.toml` declares
  `pyflexicon>=4.1`. The flexiconpackage name resolves via a deprecation shim (removal
  targeted flexicon v5.0.0); new code MUST use flexicon imports. The install path is at
  `D:/Github/_Projects/_LEX/flexicon` (the disk directory is literally named `flexicon`
  and MUST NOT be renamed); install and override inventory are documented in the repo README
  and [CLAUDE.md](../../CLAUDE.md).
- **LibLCM (.NET) is NOT consumed in this repository.** The LibLCM-direct implementation
  is a **separate fork project** — a sibling repo authored after all three merge phases
  ship. It shares only the spec artifacts (spec.md, data-model.md, contracts/*) and
  re-implements the same module against raw LCM. No `flavors/`, `liblcm_adapter.py`, or
  "deferred port" stub lives in this tree.
- **flexlibs1 is NOT used.** v4.0.0 already retired flexlibs1; v5.1.0 carries that
  forward. Historical mentions in spec artifacts and `Transfer FLEx Grammar Module.md` are
  read as historical context, not normative direction.
- **The FlexTools host MUST NOT be assumed to have any optional dependencies beyond
  flexicon (pyflexicon) and PyQt.** The module MUST degrade gracefully (skip + report) if
  flexicon is unexpectedly unavailable.

**Note on the FLExToolsMCP.** The FLExToolsMCP is an *author-side* assistant used to
generate, scaffold, and discover patterns for the code in this repo. It is **not** a
runtime dependency, **not** part of the shipped module, and **not** normative for end
users. References to MCP tools belong in development workflow notes, not in module code.

Rationale: The flavor-adapter pattern was tried in v4.0.0 and produced overhead with no
payoff during a single-flavor build. The post-Phase-2 LibLCM port is a clean re-implementation
better authored in a sibling repo where the team can pick the natural raw-LCM idioms
instead of contorting to fit a Python-shaped adapter contract. Both repos share the spec,
not the code; that is the right boundary.

### III. Preview-Before-Mutate (NON-NEGOTIABLE)

Every transfer MUST support two execution modes, and Preview MUST be the default:

- **Preview Mode** — compute the full set of intended additions, overwrites, and skips and
  present them to the user without writing anything to the target project.
- **Move Mode** — perform the writes only after the user has reviewed a preview from the
  current session's selection state.

Preview output MUST list, per item: source GUID, target match (by GUID then fingerprint),
proposed action (Add / Overwrite / Skip / Merge), and the dependency closure that will be
pulled along. Move Mode MUST be undoable through FLEx's standard undo stack wherever LCM
permits, and MUST tag newly created entries in Import Residue.

**One-time validation-spike clause** (recorded for honesty, not licence to repeat): the
Layer 1 + Layer 2 work documented in `STATUS.md` (Verb POS, Verb template, 4 slots copied
from Ejagham Mini to a throwaway `Ejagham Full GT-Test` target) ran Move-mode writes
before the Preview engine existed. This was a deliberate validation spike to confirm the
flexicon surface end-to-end against a real LCM target. It is acknowledged as a one-time
exception. All further Move work — Layer 3 included — MUST route through `Lib/preview.py`
(plan-builder) and `Lib/transfer.py` (plan-executor), and the existing
`gramtrans.py.transfer_verb_vertical()` MUST be refactored into that pair before Layer 3
begins.

Rationale: Users will run this on real projects. Surprise writes are unacceptable, and
the validation-spike clause is recorded so future maintainers do not read STATUS.md as
permission to skip the Preview engine.

### IV. Phased Merge Discipline

Merge sophistication ships in phases, and phases MUST be released in order. A later phase
MUST NOT be partially implemented before the prior phase is complete and validated:

- **Phase 0 — Additive.** Add new things unconditionally; duplicates are allowed; new
  entries are tagged in Import Residue; default vernacular mapping is updated; no merge
  UI. This phase MUST work end-to-end before Phase 1 begins.
- **Phase 1 — Overwrite.** Match by GUID first, fingerprint second; overwrite matched
  items; leave non-conflicting items untouched; deduplicate custom fields; UI lets the
  user choose which grammar piece categories to transfer.
- **Phase 2 — Interactive Merge.** Per-conflict prompt with {accept-merge, take-left,
  take-right, skip, other}; vernacular mapping wizard (SFM-import style); undoable.
- **Phase 3 (post-merge) — LibLCM fork project.** After Phases 0/1/2 ship in this repo
  against flexicon, a **separate sibling repository** re-implements the same module
  against raw LibLCM, reusing this repo's `spec.md`, `data-model.md`, and `contracts/`
  artifacts as the contract. No user-visible behavior changes; only the runtime flavor
  swaps. Phase 3 is NOT a task in this repo's tasks.md.

Rationale: Each phase is independently useful and shippable. Phasing prevents Phase 2's
complexity from blocking Phase 0's value, and the LibLCM port is decoupled from feature
work entirely by living in a sibling repo.

### V. Referential Completeness

When the user selects a grammar piece to transfer, the module MUST compute and transfer
its full dependency closure by default, including (non-exhaustive):

- Affixes pull their allomorphs, APRs, referenced inflection features, inflection classes,
  stem names, and exception features.
- Templates pull their slots and the affixes filling those slots.
- Inflection features and classes pull the categories they attach to.

The dependency closure MUST be displayed in Preview Mode and MUST be deselectable on a
per-item basis to allow a "bare-bones" transfer. Items whose dependencies cannot be
satisfied MUST be reported, not silently transferred in a broken state.

Rationale: Transferring an affix without its features produces a broken affix. Closure-by-
default is the only safe semantics; opt-out lets advanced users override.

## Technology & Architecture Constraints

- **Language & runtime:** Python 3, hosted by a standard FlexTools installation.
- **Module shape:** a FlexTools-compatible module — the entry file (`src/gramtrans/gramtrans.py`)
  exposes a `docs = {...}` metadata dict and a `MainFunction(project, report, modifyAllowed)`
  callable, per the FLExTrans-style convention (e.g.,
  `FLExTrans/FlexTools_2.3.2/FlexTools/Modules/Chinese/Update_Pinyin_Fields.py`). Helper
  modules live under `src/gramtrans/Lib/` and are loaded via `site.addsitedir(r"Lib")`.
- **Runtime API flavor:**
  - **flexicon (pyflexicon)** — the Pythonic Operations-class API, a standalone independent
    package providing `GetSyncableProperties` and `ApplySyncableProperties` natively.
    Imported directly by module files (`pyflexicon>=4.1`). No adapter indirection. The
    flexicon package name resolves via a deprecation shim; new code MUST use flexicon
    imports.
  - **LibLCM** — NOT consumed in this repo. The LibLCM-direct port is a separate
    post-Phase-2 sibling repository that re-implements the same spec.
  - **flexlibs1** — NOT used.
- **UI:** PyQt, hosted inside the FlexTools window. The main window exposes
  (a) grammar-piece category selection, (b) auto-selection toggle, (c) Preview vs Move
  mode, (d) overwrite policy, (e) writing-system mapping step, (f) post-run statistics
  panel.
- **No optional runtime dependencies:** the module MUST run with only what a stock
  FlexTools install plus flexicon (pyflexicon) and PyQt provide. Anything else is a hard
  "no" without a constitutional amendment.

### Author-Side Tooling (Non-Normative)

The **FLExToolsMCP** is a multi-API author-side assistant used to generate this code;
it is *not* a runtime dependency, *not* part of the shipped module, and *not* normative
for end users. Author-side use is encouraged but unconstrained — it is allowed to draft,
scaffold, and check code on the author's behalf. Any output it generates is still
subject to every other principle in this constitution.

- **Source projects:** the module operates source → target between two FLEx projects open
  to FlexTools; it MUST NOT depend on FLEx itself being open during the transfer.
- **Identity strategy:** GUID-first matching, fingerprint fallback (fingerprint definition
  per object class MUST be documented in the design doc).
- **Residue tagging:** every Add/Overwrite MUST be reflected in the per-object residue
  carrier so users can audit what changed. For LCM classes that expose `LiftResidue` /
  `ImportResidue`, that field is the carrier. For classes that do not (most grammar
  pieces — `IPartOfSpeech`, `IMoInflAffixTemplate`, `IMoInflAffixSlot`, `IFsClosedFeature`,
  etc.), the tag is appended to the inherited `Description` field with the marker
  `[GT-Tag]: GT|<run_id>|<source>|<iso_ts>` on its own line. The append is
  non-destructive (existing prose preserved).

## Development Workflow & Quality Gates

- **Specification flow:** features go through `/speckit-specify` → optional
  `/speckit-clarify` → `/speckit-plan` → `/speckit-tasks` → optional `/speckit-analyze` →
  `/speckit-implement`. Phase boundaries (Phase 0/1/2) MUST each have their own spec. The
  Phase 3 LibLCM-fork project re-uses Phase 0/1/2 specs verbatim in its sibling repo.
- **Constitution Check:** every plan MUST include an explicit Constitution Check section
  citing Principles I–V. Any violation MUST be justified or the plan rejected.
- **Domain review:** non-trivial LCM operations SHOULD be reviewed against upstream
  flexicon conventions before merge.
- **Verification:** every shipped phase MUST include a verification run on a known toy
  project → target project pair, with pre/post Import Residue artifacts attached.
- **No silent skips:** any item the module decides not to transfer (missing dependency,
  unresolved writing system, unsupported LCM type) MUST appear in the post-run statistics
  panel.
- **Preview engine first:** before Layer 3 (LexEntry / Sense / MSA / Allomorph /
  PhEnvironment) implementation begins, the existing inline Move logic in
  `gramtrans.py.transfer_verb_vertical()` MUST be refactored into a plan-builder
  (`Lib/preview.py`) and a plan-executor (`Lib/transfer.py`) per Principle III. This is
  the closing of the one-time validation-spike clause.

## Governance

This constitution supersedes ad-hoc development practices for the GramTrans module.

- **Amendments** require: (a) a written rationale, (b) a version bump per the policy
  below, (c) propagation through `.specify/templates/*` so plans, specs, and task lists
  remain consistent, and (d) an updated Sync Impact Report at the top of this file.
- **Versioning policy** (semantic):
  - MAJOR — a principle is removed, redefined, or made non-binding; or a phase is
    reordered.
  - MINOR — a principle or normative section is added or materially expanded.
  - PATCH — clarifications, wording, typo fixes, non-semantic refinements.
- **Compliance reviews** occur at each phase release boundary and whenever a `/speckit-plan`
  Constitution Check flags a violation.
- **Source of truth:** `.specify/memory/constitution.md`. The notes in
  `Transfer FLEx Grammar Module.md` are advisory and MUST be reconciled with this
  constitution when they conflict.

**Version**: 5.1.0 | **Ratified**: 2026-06-15 | **Last Amended**: 2026-07-04
