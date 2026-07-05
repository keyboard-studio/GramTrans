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
