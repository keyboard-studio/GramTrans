# Phase 3a Research: Phonology Block

Resolves the technical unknowns in [plan.md](plan.md) before data-model
and contracts begin. Each finding cites its MCP probe or flexicon
source location.

---

## R1. Strata have NO dedicated Operations class

**Decision**: Implement strata callbacks directly via
`project.GetService(IMoStratumFactory)` and
`LangProject.MorphologicalDataOA.StrataOS.Add(...)`. No new
`StratumOperations` wrapper added to the flexicon fork in this phase.

**Rationale**: MCP `search_by_capability("stratum operations")` returns
only `MorphRuleOperations.GetStratum/SetStratum` and
`PhonologicalRuleOperations.GetStratum/SetStratum` — both ACCESS
strata, neither CREATES or enumerates them. flexicon has no
`Grammar/StratumOperations.py`. Constitution Principle II explicitly
sanctions `project.GetService(IFooFactory)` as the fallback when no
Operations class covers the surface (see flexicon worked example
`servicelocator-factory-pattern`).

**Alternatives considered**:
- *Add a `StratumOperations` class to the flexicon fork.* Rejected
  for this phase — keeps the fork's diff minimal; upstreamable later
  if Phase 3b morphology demonstrates a real need beyond Get/Set.

---

## R2. Phoneme factory may not preserve GUIDs

**Decision**: Probe `IPhPhonemeFactory.Create` signatures in Phase 3a's
first implementation commit; if no Guid overload exists, fall back to
`identity_remap` per FR-303. Document the result here once probed.

**Rationale**: The flexicon worked example shows
`phoneme_factory.Create()` with no Guid argument. The Phase 1 pattern
(MSA / Allomorph) already handles this case — `identity_remap` is
populated by the executor for downstream reference resolution.

**Alternatives considered**:
- *Cast to a hidden Guid-accepting constructor via pythonnet.* Rejected
  — fragile and undocumented. The Phase 1 identity_remap pattern works.

**Probe deferred to implementation**: T-series tasks include "MCP-probe
IPhPhonemeFactory.Create signatures before coding T-phonemes-execute"
as a sub-step.

---

## R3. Natural classes have two distinct LCM subtypes

**Decision**: The category implementation handles both `IPhNCSegments`
(membership-based) and `IPhNCFeatures` (feature-based) in the same
callback. The executor branches at `ICmObject(obj).ClassName` to choose
the right factory and the right property to wire.

**Rationale**: MCP probe earlier this session confirmed
`IPhNCFeatures.FeaturesOA` is an OA (owned) on the class itself —
feature-struct dependency is intra-object, no special ordering. For
`IPhNCSegments`, `SegmentsRC` references phonemes — phonemes-precedes
holds via the validated ordering.

**Alternatives considered**:
- *Split into two GrammarCategory members.* Rejected — the linguist
  thinks "natural classes" as one category; splitting would surface
  internal-only LCM type discrimination in the UI.

---

## R4. Phonological-rule reference scan for FR-304

**Decision**: The planner's `phonological_rules.plan_action` walks the
rule's input segments, output segments, and left/right contexts
(reachable via the documented `PhonologicalRuleOperations` accessors),
collects every referenced phoneme or natural class GUID, and emits
`Skip(DEPENDENCY_UNRESOLVED)` if any GUID is not present in target by
post-step-4-completion (already-imported in this run or pre-existing in
target).

**Rationale**: FR-304 requires this; it mirrors the existing
verb-vertical closure walker. The Operations surface
(`PhonologicalRuleOperations.AddInputSegment`, `AddOutputSegment`,
`SetLeftContext`, `SetRightContext`) provides the access methods —
inverting them gives a `GetInputSegments`, etc., either via Operations
or direct LCM property walks.

**Alternatives considered**:
- *Skip dependency scan and let LCM raise at write time.* Rejected —
  Principle III requires Preview-Before-Mutate; the user should see
  unresolved deps before any write.

---

## R5. PhEnvironment relocation is logical, not physical

**Decision**: The existing `Lib/categories.py` keeps an
`environment_create_or_reuse` function unchanged. What changes is the
ORDER in which preview.py emits PhEnvironment plan actions — they now
come from the phonology-block category enumeration (which fires
project-wide), not from per-allomorph closure walks.

**Rationale**: FR-307 idempotency requires that Phase 0/1/2 allomorph
closure paths find environments already present by GUID. Achieved by
running the phonology-block category BEFORE the lexicon block in any
mixed transfer.

**Alternatives considered**:
- *Remove environment creation from the allomorph closure entirely.*
  Rejected — would break Phase 0 single-allomorph-only transfers
  (which never enable the phonology block). Idempotent dual-source
  creation is safer.

---

## R6. Default phoneme set assumption

**Decision**: All phonemes import into `PhonemeSetsOS[0]` (the default
phoneme set). Multi-phoneme-set projects are out of Phase 3a scope.

**Rationale**: MCP probe `PhonologicalData.PhonemeSets → PhonemeSetsOS`
(OS, owned sequence) — multiple sets are possible but rare. FLEx UI
treats the default set as the de-facto phoneme inventory.

**Alternatives considered**:
- *Enumerate all phoneme sets and transfer each.* Deferred to Phase 3b
  if a real project surfaces the need.

---

## R7. Skip-empty per-category

**Decision**: Each new category's `enumerate_source` returns an empty
sequence when the source has zero items. The planner already
short-circuits this case via the existing `_filter` / category-dispatch
path — no new code needed. Run report rendering shows the per-category
`added=0 skipped=0` line as today.

**Rationale**: Phase 3 memo UX section requires `[skip] no items in
source for X` log lines; the existing report renderer produces
equivalent output via the per-category counters. A small enhancement
to `render_text_summary` may add the explicit skip-noted line for
zero-source-zero-target-zero-conflict categories, but is cosmetic.

---

## R8. Phase 1 + Phase 2 mechanics inherit unchanged

**Decision**: The new categories register their callbacks following the
existing five-callback contract. The Phase 1 `_execute_overwrite`
dispatcher already routes by `GrammarCategory`; adding new categories
to the dispatch table is a one-line addition per category. The Phase 2
`collect_overwrite_conflicts` walks `plan.overwrites` regardless of
category — phonology overwrites flow through unchanged.

**Rationale**: FR-309 / FR-310 mandate this. Confirmed by the existing
5 COMPLETE categories (gram_categories, inflection_features,
inflection_classes, stem_names, exception_features), which already
register through the same pattern.

---

## R9. Test-double strategy (no new doubles needed)

**Decision**: Phase 3a unit tests use the same Phase 1 / Phase 2 fake
patterns. New tests construct minimal fake source/target objects with
the relevant Operations stubs (e.g. `_FakePhonemeOps` returning a
fixed list from `GetAll()`). No new conftest fixtures required; the
existing `FakeConflictResolver` / `FakeWSResolver` serve interactive
flows when the integration test wants Phase 2 prompts.

**Rationale**: Phase 0-2 set the precedent; no reason to depart.

---

## R10. Live MCP verification scope

**Decision**: Phase 3a's live verification probes:
- A fresh source project (Ejagham Mini, or a copy with phonology
  pre-populated) → throwaway target. Confirm Scenario A from
  quickstart (additive phonology block).
- A second run against the same target with `enable_overwrite=True`.
  Confirm Scenario B (Phase 1 overwrite semantics).
- A third run with the existing Phase 0 verb-vertical also enabled.
  Confirm Scenario D (FR-307 ph_environment idempotency).
- Zero new MCP probes are required for design; design is fully
  determined by the memo + the probes already in
  [specs/004-phase3-pipeline/ordering-memo.md](../004-phase3-pipeline/ordering-memo.md).

**Rationale**: All ordering hazards were resolved during memo
authoring. Phase 3a is execution work over a validated design.
