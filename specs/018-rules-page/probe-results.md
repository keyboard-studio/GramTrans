# 018 Rules Page — FLExTools MCP Probe Results (authoritative API)

**Probed**: 2026-07-05 via `flextools-mcp` (api_mode=flexicon). These are the
ground-truth API facts for the rules engine. **Do not guess** — where the
flexicon wrapper docstrings and the concrete LCM interfaces disagree, the
concrete LCM interfaces (confirmed below) win. Module code imports LCM /
flexicon directly (constitution v5.1.0 Principle II).

## [WARN] Wrapper docstring inaccuracy (must avoid)

The flexicon `AdhocProhibition` wrapper (`Grammar/adhoc_prohibition`) exposes
`as_allomorph_prohibition()` / `as_morpheme_prohibition()` whose **docstrings
reference properties that DO NOT EXIST** on the real classes:

- docstring claims `AllomorphRA` / `ProhibitedAllomorphRA` — **wrong**
- docstring claims `MorphemeRA` / `ProhibitedMorphemeRA` — **wrong**

The concrete LCM interfaces (below) are authoritative. The engine walks/wires
via `IMoAlloAdhocProhib` / `IMoMorphAdhocProhib` directly, NOT via the wrapper's
claimed properties. `AdhocProhibition.prohibition_type` /
`is_allomorph_prohibition` / `is_morpheme_prohibition` /
`is_grammatical_prohibition` (bool discriminators) ARE reliable and may be used
for subclass detection alongside `ICmObject(obj).ClassName`.

## Ad hoc prohibitions — `MorphologicalDataOA.AdhocCoProhibitionsOS`

Enumerate via `project.MorphRules.GetAllAdhocCoProhibitions()` (wrapper) or the
OS collection directly.

### IMoAlloAdhocProhib  (allomorph adjacency prohibition)
| Field | Kind | Target | Notes |
|---|---|---|---|
| `FirstAllomorphRA` | RA (read/write) | `IMoForm` | the anchor allomorph |
| `RestOfAllosRS` | RS (read-only seq) | `IMoForm` | trailing allomorphs |
| `AllomorphsRS` | RS (read-only seq) | `IMoForm` | full member sequence |

### IMoMorphAdhocProhib  (morpheme adjacency prohibition)
| Field | Kind | Target | Notes |
|---|---|---|---|
| `FirstMorphemeRA` | RA (read/write) | `IMoMorphSynAnalysis` | anchor morpheme (MSA) |
| `RestOfMorphsRS` | RS (read-only seq) | `IMoMorphSynAnalysis` | trailing morphemes |
| `MorphemesRS` | RS (read-only seq) | `IMoMorphSynAnalysis` | full member sequence |

### IMoAdhocProhibGr  (grouping node — owns children)
| Field | Kind | Target | Notes |
|---|---|---|---|
| `MembersOC` | OC (owns collection) | `IMoAdhocProhib` | child prohibitions (allo/morph/nested group) |
| `Name` | IMultiUnicode | — | |
| `Description` | IMultiString | — | |

> The OS collection can contain top-level allo/morph prohibitions AND grouping
> nodes; grouping nodes own further prohibitions in `MembersOC`. Enumeration
> must recurse into `MembersOC` (spec FR-001, FR-002).

### Factories (all confirmed in `SIL.LCModel`, `SIL.LCModel.dll`)
- `IMoAlloAdhocProhibFactory`
- `IMoMorphAdhocProhibFactory`
- `IMoAdhocProhibGrFactory`

> No `CreateAdhocProhibition` wrapper exists — adhoc creation uses these LCM
> factories via the existing `_create_with_guid(factory_iface, owner, guid, target)`
> helper. Owner = `target.Cache.LangProject.MorphologicalDataOA.AdhocCoProhibitionsOS`.
> Group children are added to the created group's `MembersOC`, not the top OS.

## Compound rules — `MorphologicalDataOA.CompoundRulesOS`

Enumerate via `project.MorphRules.GetAllCompoundRules()`.

### IMoCompoundRule (base)
| Field | Kind | Target | Notes |
|---|---|---|---|
| `Name` | IMultiUnicode | — | |
| `Description` | IMultiString | — | |
| `Disabled` | Boolean | — | |
| `StratumRA` | RA | `IMoStratum` | wire like phonological_rules StratumRA |
| `ToProdRestrictRC` | RC | `ICmPossibility` | productivity restrictions |

> [OPEN — confirm live] The left/right member MSAs (`LeftMsaOA` / `RightMsaOA`,
> owned `IMoStemMsa` each referencing a POS via `PartOfSpeechRA`) are the
> standard LCM MoCompoundRule fields but the MCP indexer returned an INCOMPLETE
> property set for `IMoCompoundRule` (0 props under a `Msa` filter; 5 props
> unfiltered). The programmer MUST confirm the exact member-MSA field names and
> the POS reference path with a live `run_module` probe against the bound
> project before wiring. Do not hardcode from memory.

### [CONFIRMED LIVE 2026-07-05] Compound member wiring (R3a/R4a resolved)

Confirmed by .NET reflection (full inherited walk) + live dump of **Esperanto**'s
5 compound rules (the rule-bearing test source — Ejagham Mini/Full, GT-Test, and
the FLExTrans/HC parser projects all have ZERO rules):

- The left/right members live on the **subclasses** (`IMoEndoCompound` /
  `IMoExoCompound`), NOT on base `IMoCompoundRule`. Base has only
  `Name/Description/Disabled/StratumRA/ToProdRestrictRC`.
- **`IMoEndoCompound`**: `LeftMsaOA`, `RightMsaOA`, `OverridingMsaOA` (all owned
  `IMoStemMsa`), `LinkerOA` (owned `IMoAffixForm`, optional), `HeadLast` (bool).
- **`IMoExoCompound`**: `LeftMsaOA`, `RightMsaOA`, `ToMsaOA` (all owned
  `IMoStemMsa`), `LinkerOA` (optional).
- Each member/result MSA is an **owned** `MoStemMsa` with its own GUID whose
  `PartOfSpeechRA` → `IPartOfSpeech`. Engine must CREATE each owned MSA in the
  target (GUID-preserved via `IMoStemMsaFactory`) and set its `PartOfSpeechRA` to
  the POS resolved by GUID. The POS is the cross-category dependency (FR-005);
  the owned MSA travels as a child of the rule.
- `IMoStemMsaFactory`, `IMoEndoCompoundFactory`, `IMoExoCompoundFactory` all
  confirmed importable from `SIL.LCModel`.
- Live example ("Noun Combo", MoEndoCompound): LeftMsaOA POS=Nominal Root,
  RightMsaOA POS=Nominal Root, OverridingMsaOA POS=Nominal Root; StratumRA None.
- **Test-data gaps**: no project surveyed has ad hoc prohibitions or exo
  compounds. Adhoc + exo live coverage needs authored fixtures in a throwaway
  target; Esperanto covers endo-compound live transfer.

### [CONFIRMED LIVE 2026-07-05] IMoStemMsaFactory signature (P0 resolution data)

Full inherited method walk (Esperanto) of `IMoStemMsaFactory`:
- `IMoStemMsaFactory.Create(ILexEntry entry, SandboxGenericMSA sandboxMsa) -> IMoStemMsa` (entry-owned convenience)
- `ILcmFactory<IMoStemMsa>.Create() -> IMoStemMsa`  (inherited)
- `ILcmFactory<IMoStemMsa>.Create(Guid guid) -> IMoStemMsa`  (inherited)

=> `factory.Create(parsed_guid)` IS a valid overload (inherited from ILcmFactory).
The QC/domain "P0" (missing overload / orphan risk) is NOT a missing-signature bug.
For an **owned-atomic (OA)** slot the correct idiom is `Create(Guid)` then assign the
property (`rule.LeftMsaOA = msa`) — the LCM-generated OA setter sets the owner
back-ref + OwningFlid. This is legitimately DIFFERENT from `_create_with_guid`
(which does `owner.Add()` for owning COLLECTIONS OS/OC). Live-confirmed that a
populated rule's `LeftMsaOA.Owner` is the MoEndoCompound (ownership via OA slot
holds in existing data). REMAINING unproven-without-write: that the OA setter
persists ownership through a fresh Move-commit — covered by the deferred
write-enabled integration test (Esperanto -> throwaway).

### IMoEndoCompound (endocentric)
| Field | Kind | Target | Notes |
|---|---|---|---|
| `HeadLast` | Boolean | — | head position |
| `OverridingMsaOA` | OA (owns atomic) | `IMoStemMsa` | overriding/result MSA → POS |

### IMoExoCompound (exocentric)
| Field | Kind | Target | Notes |
|---|---|---|---|
| `ToMsaOA` | OA (owns atomic) | `IMoStemMsa` | result MSA → POS |

### Factories (confirmed in `SIL.LCModel`)
- `IMoEndoCompoundFactory`
- `IMoExoCompoundFactory` (same namespace/pattern — confirm live)

> `MorphRuleOperations.CreateCompoundRule(name, endocentric=True, description=None)`
> exists but does NOT allow GUID pinning — for GUID-preserving transfer use the
> LCM factory + `_create_with_guid`. Owner = `...MorphologicalDataOA.CompoundRulesOS`.

## Syncable-properties surface (scalar/text only — refs are manual)

`MorphRuleOperations.GetSyncableProperties(item)` returns keys:
`['Name', 'Description', 'StratumGuid', 'Disabled']`.
`ApplySyncableProperties(item, props, ws_map=None, fill_gaps=False)` applies
those. **It does NOT wire member references** (allomorphs/morphemes/POS/MSAs).
Reference + owned-MSA wiring is done MANUALLY in `execute_action` by GUID
resolution against the target — exactly as `phonological_rules_execute_action`
hand-wires `StratumRA` after `ApplySyncableProperties`.

> `GetSyncableProperties`/`ApplySyncableProperties`/`CompareTo` are declared on
> `MorphRuleOperations` (matches the 8-engine pattern; CLAUDE.md lists
> `Grammar/MorphRuleOperations.py` as one of the 8 override-declaring classes).

## [RESOLVED 2026-07-05] Live write validation + base-interface-hiding bug fix

A write-enabled MCP session against **Ejagham Full GT-Test** (throwaway) ran the live
validation the crew had deferred. Two outcomes:

**1. OA-ownership persists through commit — CONFIRMED.** Created a MoEndoCompound via
`IMoEndoCompoundFactory.Create(Guid)` + `IMoStemMsaFactory.Create(Guid)` assigned to
`LeftMsaOA`, wired `PartOfSpeechRA`, committed, then RE-OPENED in a fresh session: the
rule + owned MSA persisted GUID-preserved with `owner=MoEndoCompound` and POS intact.
The `Create(Guid)` + OA-slot-assign idiom is proven end-to-end. (Test object deleted
afterward; GT-Test left clean.)

**2. BASE-INTERFACE-HIDING BUG found and fixed.** LCM owning collections
(`CompoundRulesOS`, `AdhocCoProhibitionsOS`, `MembersOC`) yield elements typed as the
BASE interface (`IMoCompoundRule` / `IMoAdhocProhib`). pythonnet exposes only the base
type's members, so subclass-only slots — `LeftMsaOA`/`RightMsaOA`/`OverridingMsaOA`/
`ToMsaOA` (compound) and `FirstAllomorphRA`/`AllomorphsRS`/`FirstMorphemeRA`/`MorphemesRS`
(adhoc) — read back as **None** off the base reference, silently dropping member/POS
wiring and dependencies. Live proof on Esperanto's 5 compound rules: base-typed
`LeftMsaOA` visible **0/5**; after casting to `IMoEndoCompound`, **5/5** (POS resolves).
Fake-handle unit tests could NOT catch this (fakes are plain Python — attributes always
visible). **Fix**: `_cast_rule_concrete(obj)` casts each enumerated object to its concrete
subclass at the `_rules_enumerate_all` choke point (safe no-op in the fake env). Regression
tests added (`test_cast_rule_concrete_passthrough_without_lcm`, `test_enumerate_all_applies_cast`).

Remaining live gap (minor, non-blocking): a full engine round-trip exercising exo-compound
and adhoc subclasses has no live source data (Esperanto is endo-only); those stay
fake-handle + the now-proven cast mechanism. Seed a target with exo/adhoc rules for full
SC-001/002/008 live coverage if desired.

## Engine pattern to reuse (from categories.py)

- `_guid_str_from(obj)` — normalized lowercase GUID string.
- `_create_with_guid(factory_iface, owner_collection, guid_str, target)` —
  `factory.Create(Guid)` + `owner.Add(new_obj)`, fails loud on orphan risk.
- `_phonology_simple_enumerate(context, ops_attr, selection, category)` —
  GetAll + per-item pick subset filter (`selection.leaf_picks_for(category)`).
- `_phonology_simple_plan(...)` — GUID-first ALREADY_PRESENT_BY_GUID Skip / PlannedAction.
- `apply_carrier_b(new_obj, ws, tag, strict=False)` — Layer-B residue carrier.
- Reference wiring: resolve source ref GUID, loop target collection for match,
  assign `.RA` / add to `.RS`/`.OC`. Fail-loud on unhandled subclass (FR-006).
