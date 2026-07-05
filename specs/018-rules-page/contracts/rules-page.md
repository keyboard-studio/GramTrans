# Contract — 018 Rules Page (engine callbacks + page↔selection)

## Engine callback contracts (categories.py)

Registered under `LEAF_CATEGORIES[GrammarCategory.ADHOC_COMPOUND_RULES]` (already
wired). Signatures are fixed by the leaf-dispatch protocol.

### `adhoc_compound_rules_enumerate_source(context, selection) -> Iterable[obj]`
- Returns every user-defined ad hoc prohibition (from `AdhocCoProhibitionsOS`,
  **recursing** `IMoAdhocProhibGr.MembersOC`) and every compound rule (from
  `CompoundRulesOS`).
- When `selection.leaf_picks_for(ADHOC_COMPOUND_RULES)` is not None, filter to
  rows whose `_guid_str_from(obj)` is in the subset (absent key => all).
- GOLD-shipped rules excluded (Constitution I).

### `adhoc_compound_rules_dependencies(piece) -> tuple[str, ...]`
- Per-subclass member-reference GUIDs (normalized): allo→`IMoForm`s;
  morph→`IMoMorphSynAnalysis`es; compound→owned-MSA `PartOfSpeechRA` POS;
  group→union of children. `getattr`/cast-guarded; None refs skipped.

### `adhoc_compound_rules_required_writing_systems(piece) -> tuple`
- Returns `()`. Name/Description travel via `ApplySyncableProperties`; no
  dedicated WS enumeration needed (parity with `phonological_rules_*`).

### `adhoc_compound_rules_plan_action(piece, context, ws_mapping) -> PlannedAction | Skip`
- GUID-first via `_phonology_simple_plan(piece, context, ADHOC_COMPOUND_RULES,
  <ops_attr>, <label>)`: `Skip(ALREADY_PRESENT_BY_GUID)` if target already has the
  GUID; else `PlannedAction`. (ADHOC_COMPOUND_RULES is NOT GOLD_RESERVED → simple
  skip/add branch.)

### `adhoc_compound_rules_execute_action(action, context, ws_mapping, tag) -> obj | None`
- Locate source rule by `action.source_guid`.
- Dispatch on `ICmObject(src).ClassName`:
  - pick factory + owner (top OS, or parent group `MembersOC` for group children);
  - `new = _create_with_guid(factory_iface, owner, src_guid, target)` (GUID pinned);
  - `props = source.MorphRules.GetSyncableProperties(src)` then
    `target.MorphRules.ApplySyncableProperties(new, props, ws_map=ws_mapping)`;
  - **manual reference wiring** by GUID (see research R3/R4): allomorphs/morphemes
    (adhoc), owned member/result MSAs + their `PartOfSpeechRA` (compound), children
    re-parented under created group `MembersOC` (group);
  - `apply_carrier_b(new, cache.DefaultAnalWs, tag, strict=False)` residue tag.
- **Unhandled ClassName => raise** (FR-006, SC-008), never return None-as-skip.
- Idempotency: re-run finds GUID present at plan → Skip (SC-002).

## Page ↔ selection contract (selection_wizard.py)

- `_PageRules.initializePage()` calls `build_rules_inventory(source, target)` and
  renders two grouped tristate trees + whole-block toggle; all rows checked.
- On leaving, collapse checked GUIDs into
  `Selection.leaf_item_picks[ADHOC_COMPOUND_RULES]` per data-model rules.
- `_PagePreview` merges this pick set when building the plan; `_PageFinish` Move gate
  consumes any `MissingRefWarning`s aggregated in `preview.py`.
- Page inserted before `_page_finish`; reached only via the P-1 named accessor
  `page_rules()` — no literal page indices.

## Invariants

- No write occurs before Move (Constitution III).
- No ADD_NEW/MERGE/OVERWRITE control on the page (FR-016).
- GUID normalization via `_guid_str_from` on every side (010 invariant).
- Missing references → aggregated warning + single Move confirmation, never silent
  (FR-014/FR-015, Constitution V).
