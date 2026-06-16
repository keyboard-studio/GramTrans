<!--
Sync Impact Report
==================
Version change: 2.0.0 → 3.0.0
Bump rationale: MAJOR — Principle II re-redefined. The two-flavor scope (flexlibs1 +
LibLCM, no flexlibs2) and the MCP-as-author-side-only stance from v2.0.0 are KEPT.
What changes: the two flavors are NO LONGER co-equal. **flexlibs1 is the preferred
flavor**; **LibLCM is a deliberate fallback** used only where flexlibs1 cannot
naturally express the operation. This is a backward-incompatible redefinition of how
operations are routed and requires that downstream artifacts (plan, research, tasks)
default to flexlibs1 unless a fallback is justified.

Principles defined:
  I.   FLEx Domain Fidelity (NON-NEGOTIABLE)
  II.  FlexTools-Compatible Output, flexlibs1-Preferred with LibLCM Fallback   (REDEFINED)
  III. Preview-Before-Mutate (NON-NEGOTIABLE)
  IV.  Phased Merge Discipline
  V.   Referential Completeness

Modified principles:
  II. v2.0.0 "Dual-Flavor APIs (flexlibs1 + LibLCM, co-equal)" →
      v3.0.0 "flexlibs1-Preferred with LibLCM Fallback" — flexlibs1 is the default
      surface for every operation; LibLCM is invoked only when flexlibs1 cannot
      express the operation, and each such fallback MUST be justified in the
      relevant plan's Constitution Check.

Kept from v2.0.0:
  - flexlibs2 is OUT OF SCOPE for reverse compatibility.
  - The FLExToolsMCP is a non-normative author-side assistant, not a runtime
    dependency.
  - The shipped artifact is a FlexTools-compatible module.

Removed framing:
  - "co-equal" flavor language.
  - The "route through whichever is most natural" rule (replaced with
    "flexlibs1 unless it can't do it").

Templates requiring updates:
  ✅ .specify/memory/constitution.md (this file)
  ⚠ .specify/templates/plan-template.md — Constitution Check should ask "for each
      operation that uses LibLCM, why can flexlibs1 not express it?"

Downstream artifact updates required (in this project):
  ⚠ specs/001-phase0-additive-transfer/research.md — R1 table must flip default to
      flexlibs1; per-row "Reason" column becomes "Reason flexlibs1 cannot suffice"
      where LibLCM is chosen.
  ⚠ specs/001-phase0-additive-transfer/plan.md — Summary, Constitution Check II,
      Technical Context Constraints wording.
  ⚠ specs/001-phase0-additive-transfer/contracts/category-transfer.md — flavor
      annotation guidance.

Deferred items: none.

---

Prior Sync Impact Report (v2.0.0)
---------------------------------
Version change: 1.1.0 → 2.0.0
Bump rationale: MAJOR — MCP reclassified as author-side; LibLCM promoted from
"C# fallback" to a runtime flavor (then v2.0.0 framed both flavors as co-equal,
which v3.0.0 reverses while keeping the MCP-demotion and flexlibs2-exclusion).

Prior Sync Impact Report (v1.1.0)
---------------------------------
Version change: 1.0.0 → 1.1.0
Bump rationale: MINOR — Principle II expanded to designate the FLExTools MCP as the
primary implementation/discovery surface. (Superseded by v2.0.0 and v3.0.0.)

Prior Sync Impact Report (v1.0.0)
---------------------------------
Version change: (uninitialized template) → 1.0.0
Bump rationale: Initial ratification of the GramTrans constitution. MAJOR baseline.
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

### II. FlexTools-Compatible Output, flexlibs1-Preferred with LibLCM Fallback

The module's shipped artifact MUST be a **FlexTools-compatible module** that runs inside a
standard FlexTools host. At runtime it MUST target two — and only two — LCM API flavors:

- **flexlibs1** (Python) — the legacy flexlibs API. **This is the preferred flavor.**
  Every operation defaults to flexlibs1 unless flexlibs1 cannot express it.
- **LibLCM** — the .NET LCM library, accessed from Python via the standard FlexTools
  .NET bridge. **This is a deliberate fallback**, used only where flexlibs1 cannot
  perform the operation (missing wrapper, missing capability, semantic mismatch).

Each use of the LibLCM fallback is a budgeted exception, not a co-equal choice:

- **flexlibs1 is the default.** All new code MUST attempt to use flexlibs1 first. The
  module MUST NOT reach for LibLCM "because it's nicer" — only because flexlibs1 cannot
  do the job.
- **Every LibLCM call site MUST be justified** in the relevant plan's Constitution Check
  with a one-line "flexlibs1 cannot do X because Y" statement.
- **LibLCM fallbacks MUST be isolated** behind a thin Python wrapper with a stable
  signature, so the call site reads like any other flavor-agnostic call and the LibLCM
  surface area is auditable.
- **flexlibs2 is OUT OF SCOPE** for this module. Although it is the author's preferred
  API, it is explicitly excluded to preserve **reverse compatibility** with installations
  that ship only flexlibs1 + LibLCM. Any temptation to depend on flexlibs2 idioms,
  imports, or behaviors MUST be rejected at review time.
- The FlexTools host MUST NOT be assumed to have any optional dependencies beyond
  flexlibs1 and LibLCM; the module MUST degrade gracefully (skip + report) if a flavor is
  unexpectedly unavailable.

**Note on the FLExTools MCP.** The FLExTools MCP is an *author-side* assistant used to
generate, scaffold, and discover patterns for the code in this repo. It is **not** a
runtime dependency, **not** part of the shipped module, and **not** normative for end
users. References to MCP tools belong in development workflow notes, not in module code.

Rationale: Reverse compatibility with the deployed FlexTools ecosystem requires the
flexlibs1 + LibLCM target. flexlibs1 is preferred because it is the established,
reviewable, portable surface for FlexTools modules; LibLCM is the escape hatch for what
flexlibs1 cannot express. Treating them as preferred/fallback (not co-equal) keeps the
runtime concentrated on the well-understood Python surface and makes every drop into
.NET a deliberate, audited choice — exactly the shape of a long-lived FlexTools module.

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

Rationale: Users will run this on real projects. Surprise writes are unacceptable.

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

Rationale: Each phase is independently useful and shippable. Phasing prevents Phase 2's
complexity from blocking the value of Phase 0.

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
- **Module shape:** a FlexTools-compatible module — standard module entry points,
  metadata, and packaging conventions per the FlexTools host.
- **Runtime API flavors (the only two permitted):**
  - **flexlibs1** — the legacy Python flexlibs API. **Preferred.** Default for every
    operation; reach for LibLCM only when flexlibs1 cannot express it.
  - **LibLCM** — the .NET LCM library, accessed from Python via the standard FlexTools
    .NET bridge. **Deliberate fallback.** Each call site MUST be justified in the
    plan's Constitution Check ("flexlibs1 cannot do X because Y").
  flexlibs2 is **explicitly excluded** for reverse compatibility.
- **UI:** PyQt, hosted inside the FlexTools window. The main window exposes
  (a) grammar-piece category selection, (b) auto-selection toggle, (c) Preview vs Move
  mode, (d) overwrite policy, (e) post-run statistics panel.
- **No optional runtime dependencies:** the module MUST run with only what a stock
  FlexTools install provides (Python + flexlibs1 + LibLCM bridge + PyQt). Anything else
  is a hard "no" without a constitutional amendment.

### Author-Side Tooling (Non-Normative)

The **FLExToolsMCP** is a multi-API author-side assistant used to generate this code;
it is *not* a runtime dependency, *not* part of the shipped module, and *not* normative
for end users. Author-side use is encouraged but unconstrained — it is allowed to draft,
scaffold, and check code against either flavor on the author's behalf. Any output it
generates is still subject to every other principle in this constitution (especially
Principle II's two-flavor restriction).
- **Source projects:** the module operates source → target between two FLEx projects open
  to FlexTools; it MUST NOT depend on FLEx itself being open during the transfer.
- **Identity strategy:** GUID-first matching, fingerprint fallback (fingerprint definition
  per object class MUST be documented in the design doc).
- **Residue tagging:** every Add/Overwrite MUST be reflected in Import Residue so users
  can audit what changed.

## Development Workflow & Quality Gates

- **Specification flow:** features go through `/speckit-specify` → optional
  `/speckit-clarify` → `/speckit-plan` → `/speckit-tasks` → optional `/speckit-analyze` →
  `/speckit-implement`. Phase boundaries (Phase 0/1/2) MUST each have their own spec.
- **Constitution Check:** every plan MUST include an explicit Constitution Check section
  citing Principles I–V. Any violation MUST be justified or the plan rejected.
- **Domain review:** non-trivial LCM operations SHOULD be reviewed against upstream
  cdfarrow/flexlibs conventions before merge.
- **Verification:** every shipped phase MUST include a verification run on a known toy
  project → target project pair, with pre/post Import Residue artifacts attached.
- **No silent skips:** any item the module decides not to transfer (missing dependency,
  unresolved writing system, unsupported LCM type) MUST appear in the post-run statistics
  panel.

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

**Version**: 3.0.0 | **Ratified**: 2026-06-15 | **Last Amended**: 2026-06-16
