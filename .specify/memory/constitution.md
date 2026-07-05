<!--
Sync Impact Report
==================
Version change: 5.1.0 → 6.0.0
Bump rationale: MAJOR — Principle IV mode vocabulary redefined. ConflictMode
  {ADD_NEW, MERGE, OVERWRITE} → mode {ADD_NEW, LINK, UPDATE, OVERWRITE} with a
  computed per-item disposition {IGNORE, SKIP, ADD, UPDATE, OVERWRITE}. Adds the
  non-destructive UPDATE write semantic and field-identity-based true-SKIP.
  "MERGE" renamed to "LINK" (it never merged — it linked). Data migration: reader
  shim aliases persisted "merge" → "link" for >=1 release; no value maps to UPDATE.
Principles modified: IV (Phased Merge Discipline) — mode vocabulary + dispositions.
Templates requiring updates:
  [WARN] models.py ConflictMode enum + _DEFAULT_CONFLICT_MODES + allowed_modes_for
  [WARN] conflict.py write-semantic dispatch (add UPDATE policy; true-SKIP downgrade)
  [WARN] protection.py apply_isprotected_layer2 (LINK is the safe downgrade target)
  [WARN] specs referencing ConflictMode.MERGE (008/009/010/016/018/019/020/021)
  [WARN] residue tag reader (merge= alias shim)

---

Prior Sync Impact Reports
-------------------------
v4.0.0 → v5.1.0: MAJOR (5.0.0) — Principle II redefined. v4.0.0's mandatory
  flavor-adapter contract removed; every Phase 0/1/2 module file imports flexicon
  directly. LibLCM-direct port is a separate fork project. MINOR (5.1.0) — flexicon
  (dist pyflexicon) designated as the runtime dependency (standalone independent
  project, NOT a fork of stock flexicon). Principle III gained the one-time
  validation-spike clause for Layer 1+2. Principle IV: Phase 3 redefined from
  in-tree LibLCM port to LibLCM fork project. Last Amended 2026-07-04.
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
proposed action (Add / Link / Update / Overwrite / Skip / Ignore), and the dependency closure that will be
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

**Mode vocabulary (category-level user intent):**

The collision policy each category operates under is one of four modes:

| Mode | Meaning |
|---|---|
| `ADD_NEW` | Always create a new copy; never match against existing target objects. |
| `LINK` | If present by GUID, reference the existing target object and write nothing. Otherwise ADD. (Replaces the former `MERGE` naming — the old behavior never merged data; it linked.) |
| `UPDATE` | Write divergent fields from source into the target; never blank a target field from an empty source (non-destructive, source-preferring). DEFAULT for MULTI_INSTANCE categories. |
| `OVERWRITE` | Source wins on every field, including blanking a target field when the source field is empty. Explicit opt-in required; not a default. |

A reader shim MUST alias the persisted value `"merge"` to `"link"` for at least one
release so that saved selections written before v6.0.0 continue to load correctly.
No existing selection maps to `UPDATE`; it is opt-in only for SINGLE_INSTANCE categories.

**Per-item disposition (computed outcome at plan time):**

At plan time each selected item receives a computed disposition:

| Disposition | When |
|---|---|
| `IGNORE` | Item or category is unchecked — never enters the plan. |
| `SKIP` | Selected and present in target, but all user-editable fields are already in sync. Report must distinguish SKIP from IGNORE. |
| `UPDATE` | Selected, present, diverges from target, and category mode is UPDATE — selective non-destructive write. |
| `OVERWRITE` | Selected, present, diverges from target, and category mode is OVERWRITE — wholesale write. |
| `ADD` | Selected and not present in target (or category mode is ADD_NEW) — create. |

SKIP is determined by field-identity comparison, not merely by GUID presence. On a
re-run, the residue baseline (`load_prior_log`) enables a genuine "untouched since last
transfer" test; on a first transfer only a 2-way identical/diverged comparison is
available. Reports and UI copy MUST NOT claim more certainty than the available baseline
supports — "identical now" on first transfer, "untouched since last run" on re-runs.

**The three write semantics (for reference):**

| Semantic | Rule |
|---|---|
| fill-gaps | Write source to target only where the target field is empty. (Existing, pre-v6.0.0.) |
| update | Write source to target wherever source is non-empty; keep target where source is empty. (NEW in v6.0.0.) |
| overwrite | Write every field; empty source blanks target. (Existing, pre-v6.0.0.) |

`UPDATE` mode uses the update semantic, implementable as a default-resolution pass over
the existing `MergeResolution` machinery: auto `TAKE_SOURCE` on a divergent non-empty
field, auto `KEEP_TARGET` where the source value is empty.

Rationale: Each phase is independently useful and shippable. Phasing prevents Phase 2's
complexity from blocking Phase 0's value, and the LibLCM port is decoupled from feature
work entirely by living in a sibling repo. The mode-vocabulary redefinition (v6.0.0)
corrects three defects in the prior model: "MERGE" was a misnomer (it linked, never
merged), there was no non-destructive update path, and SKIP was conflated with IGNORE.

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

**Version**: 6.0.0 | **Ratified**: 2026-06-15 | **Last Amended**: 2026-07-05
