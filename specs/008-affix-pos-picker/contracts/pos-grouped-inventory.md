# Contract: POS-Grouped Affix Inventory (builder + collapse + mirroring)

Location: `src/gramtrans/Lib/selection.py`. All functions are pure Python and MUST be
unit-testable with duck-typed fake handles (no live LCM).

## build_pos_grouped_inventory(source) -> PosGroupedAffixInventory

**Input**: a `source` handle exposing `source.Cache.LangProject.LexDbOA.Entries` and
`source.Cache.LangProject.PartsOfSpeechOA.PossibilitiesOS` (recursive `SubPossibilitiesOS`).

**Behavior**:
1. Build the POS hierarchy (`PosNode` tree) from `PartsOfSpeechOA`, in
   `PossibilitiesOS`/`SubPossibilitiesOS` order; label = `ICmPossibility` Abbreviation
   else Name.
2. Enumerate `LexDbOA.Entries`; keep entries where `LexemeFormOA.MorphTypeRA.IsAffixType`.
3. For each affix entry, iterate `MorphoSyntaxAnalysesOC`; dispatch on `msa.ClassName`
   (R2). Accumulate attaches-to POS guids and produces POS guids, plus `msa_kind`.
4. Read form (best-vernacular) and glosses (deduped, joined) once per entry.
5. Place one `AffixRow` per `(entry, pos_guid, role)` into the matching node's
   `inflectional` / `deriv_attaches` / `deriv_produces` list. An MSA POS guid with no
   matching node is created defensively as a root node (should not happen for valid data).
6. Entries reaching no POS → `JunkDrawer.no_pos` (had MSAs) or `no_analysis` (no
   sense/MSA).
7. Sort affix rows alphabetically by `form` within each list.

**Guarantees**: pure (retains no LCM handles); never raises on a single malformed
object (degrades that object to junk); deterministic ordering.

**Casting** (R3): guard `ICmPossibility`, `ILexEntry`, `IMultiAccessorBase`, and concrete
MSA casts; a failed cast is treated as "unreadable" → defensive skip / junk.

## collapse_pos_grouped(checked_guids, inventory) -> Selection

**Input**: the set of checked leaf-row entry GUIDs from the tree; the inventory.

**Behavior**: dedup `checked_guids` ∩ `inventory.all_affix_guids()`; construct
`PickerState(checked_affixes=frozenset(...))`; return
`build_selection(picker, <adapter>, ...)` such that `Selection.affix_picks` equals the
deduped set and template/slot picks are empty. No closure-engine change.

**Guarantee**: an entry checked in N appearances resolves to exactly one GUID in
`affix_picks`.

## mirror_check_state(all_items_for_guid, new_state) -> list[(item, state)]  (pure helper)

**Input**: the tree items sharing an `entry_guid` and the newly-set check state.

**Behavior**: return the list of `(item, new_state)` assignments needed so every
appearance matches. The Qt `itemChanged` handler applies these under a re-entrancy guard
(set a `_mirroring` flag; skip handling while set) to prevent signal recursion.

**Rationale for extraction**: keeps the mirroring decision testable without Qt; the Qt
handler is a thin apply-loop.

## Acceptance anchors (integration, live via MCP)

| Project | affixes | infl/deriv/uncl | attaches-to groups | multi-POS | junk no-POS |
|---|---|---|---|---|---|
| Ejagham Full GT-Test | 33 | 33 / 0 / 0 | v:14, n:11, num:6, pro:1 | 0 | 1 |
| Esperanto | 68 | 41 / 31 / 12 | Root:43, v:12, VRoot:9, ARoot:3, n:3, NRoot:2, adj:2 | 13 | 7 |
| Esperanto (produces) | — | — | n:14, v:10, adj:5, adv:1 | — | — |

These exact counts are the regression assertions for
`tests/integration/test_affix_pos_picker_live.py`. (Counts are distinct-affix per group;
an affix may appear in multiple attaches-to groups, so group sums exceed the affix total.)
