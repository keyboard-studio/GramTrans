# Phase 0 Research — 018 Rules Page

All API facts sourced from [probe-results.md](./probe-results.md) (FLExTools MCP,
2026-07-05) and the existing `phonological_rules` engine in `categories.py`.

## R1 — Enumeration source & shape

**Decision**: Enumerate two collections:
`target.Cache.LangProject.MorphologicalDataOA.AdhocCoProhibitionsOS` (via
`project.MorphRules.GetAllAdhocCoProhibitions()`) and `...CompoundRulesOS` (via
`project.MorphRules.GetAllCompoundRules()`). The adhoc collection is heterogeneous:
top-level `IMoAlloAdhocProhib` / `IMoMorphAdhocProhib` AND `IMoAdhocProhibGr`
grouping nodes that own children in `MembersOC`. Enumeration **recurses** into
`MembersOC` (which may itself hold nested groups) and yields every leaf prohibition
plus each group node.

**Rationale**: FR-001/FR-002 require every prohibition including group children;
FR-004 requires group ownership preserved. Recursion yields both.

**Alternatives**: flat `GetAllAdhocCoProhibitions()` only — rejected, would miss
group children if the wrapper does not flatten (unverified; recurse defensively).

## R2 — Per-subclass dispatch (FR-341)

**Decision**: Dispatch on `ICmObject(obj).ClassName` (matching the
`phonological_rules_execute_action` factory-map idiom) across the five concrete
classes. Discriminator map:

| ClassName | Factory | Owner collection | Distinguishing refs |
|---|---|---|---|
| `MoAlloAdhocProhib` | `IMoAlloAdhocProhibFactory` | `AdhocCoProhibitionsOS` (or parent `MembersOC`) | `FirstAllomorphRA`, `RestOfAllosRS`, `AllomorphsRS` → `IMoForm` |
| `MoMorphAdhocProhib` | `IMoMorphAdhocProhibFactory` | same | `FirstMorphemeRA`, `RestOfMorphsRS`, `MorphemesRS` → `IMoMorphSynAnalysis` |
| `MoAdhocProhibGr` | `IMoAdhocProhibGrFactory` | same | owns `MembersOC` children |
| `MoEndoCompound` | `IMoEndoCompoundFactory` | `CompoundRulesOS` | base members + `OverridingMsaOA`, `HeadLast` |
| `MoExoCompound` | `IMoExoCompoundFactory` | `CompoundRulesOS` | base members + `ToMsaOA` |

Any other ClassName → **raise** (FR-006, SC-008), never silent skip.

**Rationale**: ClassName-keyed factory selection is the proven pattern for the
heterogeneous PhonRules list. Fail-loud on the else branch satisfies FR-006.

## R3 — Reference wiring (manual, by GUID)

**Decision**: `MorphRuleOperations.GetSyncableProperties` returns only
`Name/Description/StratumGuid/Disabled` — it does NOT wire member references. After
`ApplySyncableProperties(new, props, ws_map)`, wire references manually by resolving
each source ref GUID against the target collection (loop-match on `_guid_str_from`),
exactly as `phonological_rules_execute_action` wires `StratumRA`:

- **Allo adhoc**: set `FirstAllomorphRA`; rebuild `RestOfAllosRS` / `AllomorphsRS`
  by adding resolved target `IMoForm`s in source order.
- **Morph adhoc**: set `FirstMorphemeRA`; rebuild `RestOfMorphsRS` / `MorphemesRS`
  with resolved target `IMoMorphSynAnalysis` (MSA) objects.
- **Compound**: wire base left/right member MSAs and the endo `OverridingMsaOA` /
  exo `ToMsaOA` result MSA. These are **owned** `IMoStemMsa` objects whose
  `PartOfSpeechRA` points at a POS — [OPEN R3a] confirm the exact base member-MSA
  field names (`LeftMsaOA`/`RightMsaOA`) live before wiring; the MCP indexer
  returned an incomplete `IMoCompoundRule` property set. The programmer runs a live
  `run_module` probe on the bound project to confirm, per the "use MCP not guess"
  rule.

**Rationale**: Matches shipped engine idiom; keeps wiring explicit and fail-loud.

**Alternatives**: rely on `ApplySyncableProperties` for refs — rejected, it does not
carry them (confirmed by the returned key set).

## R4 — Owned MSAs on compound rules

**Decision**: The compound member/result MSAs are **owned** (`OA`) children, not
references. Transferring a compound rule must **create** these MSAs in the target
(GUID-preserved) and set their `PartOfSpeechRA` to the resolved target POS. The
POS is the *cross-category dependency* surfaced by `dependencies()`; the MSA itself
travels as an owned child of the rule (created in `execute_action`), not as a
separate category item.

**Rationale**: Owned children belong to their owner's transfer unit (spec:
"transfer unit is the individual rule object"). Only the POS (a reference target)
is a closure dependency.

## R5 — dependencies() cross-category refs (FR-005)

**Decision**: `adhoc_compound_rules_dependencies(piece)` returns the GUIDs of:
- adhoc allo → each referenced `IMoForm` (allomorph);
- adhoc morph → each referenced `IMoMorphSynAnalysis` (morpheme/MSA);
- compound → the POS referenced by each owned member/result MSA (`PartOfSpeechRA`),
  resolved through the owned MSA;
- adhoc group → union of its children's refs.
Uses `getattr` + cast guards like `phonological_rules_dependencies`; returns a tuple
of normalized GUID strings. Absent/None refs are skipped (they surface as
missing-reference warnings at plan/Preview, not here).

**Rationale**: FR-005 requires closure to pull member refs when a rule is kept.

## R6 — Missing-reference warning routing (FR-014/FR-015)

**Decision**: Reuse the 010 EXCLUDED-LOSSY / missing-reference machinery in
`preview.py`. For each **kept** rule, if a member ref is (a) NOT being transferred
(its source object deselected on the Model-A pages) AND (b) absent from the target
by GUID, emit ONE entry-centric warning naming the rule. All such warnings feed the
**shared aggregated Move gate** (one confirmation across all pages) — never
per-reference prompts. When the ref resolves in target or is in-flight, no warning.

**Rationale**: FR-014/FR-015, Constitution V. Matches 010's single-gate design.

## R7 — Wizard page / builder (FR-007..FR-012)

**Decision**: `build_rules_inventory(source, target=None)` returns a `RulesInventory`
with two category groups (Ad Hoc, Compound), each listing user-defined rules with
`checked=True` default, grouping-node position (for adhoc), and target-status
(NEW/IN TARGET/SIMILAR via the shared 008/009/010 status helper; blank when no
target). `_PageRules` renders two grouped, tristate-toggle trees + a whole-block
toggle, mirroring `_PagePhonology`/`_PageCustomFields`. Empty category renders empty
(FR-011). Selections collapse into `Selection.leaf_item_picks[ADHOC_COMPOUND_RULES]`
(the existing per-item subset field from 010) and merge at `_PagePreview`.

**Rationale**: Direct reuse of the 010/021 Model-B page and the existing
`leaf_item_picks` engine field — no new engine selection mechanism.

## GUID-normalization invariant (carried from 010)

Both the item-pick trim filter and the builder MUST normalize GUIDs through the same
`_guid_str_from` helper (lowercase, braces stripped) on both sides. Raw
`str(obj.Guid)` is uppercase-with-braces and would make every trim/skip lookup miss.

## Open items for implementation-time MCP confirmation

- **R3a** — exact base member-MSA field names on `IMoCompoundRule`
  (`LeftMsaOA`/`RightMsaOA`?) and the POS reference path. Confirm live before wiring.
- **R4a** — the MSA factory + ownership call needed to create owned `IMoStemMsa`
  children on the new compound rule (likely `project.MSA.*` or `IMoStemMsaFactory`).
- Confirm `IMoExoCompoundFactory` exists (endo confirmed; exo same namespace).
