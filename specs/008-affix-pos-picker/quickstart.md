# Quickstart / Validation Guide: Affixes-by-POS Item Picker

## Prerequisites

- MattGyverLee/flexicon fork installed (`pip install -e D:/Github/_Projects/_LEX/flexicon`).
- PyQt6 available.
- FLEx projects present: `Ejagham Full GT-Test` and `Esperanto`.

## Unit tests (fake handles, no LCM)

```powershell
python -m pytest tests/unit/test_pos_grouped_inventory.py tests/unit/test_affix_pos_collapse.py -v
```

Expected: builder groups fake affixes by attaches-to POS; a fake derivational MSA lands
in both `deriv_attaches` (From) and `deriv_produces` (To); a multi-POS fake affix appears
in each group but collapses to one `affix_picks` GUID; a fake affix with null POS lands in
`junk.no_pos`; `mirror_check_state` returns matching assignments for all appearances of a
shared GUID.

## Integration (live, FlexTools MCP — read-only)

Run the builder over each project and assert the counts in
[contracts/pos-grouped-inventory.md](./contracts/pos-grouped-inventory.md):

- **Ejagham**: 33 affixes, all inflectional; groups v/n/num/pro; 1 no-POS junk; 0 multi-POS.
- **Esperanto**: 68 affixes (41/31/12); 13 multi-POS; 7 no-POS junk; produces n/v/adj/adv.

```powershell
python -m pytest tests/integration/test_affix_pos_picker_live.py -v
```

## Manual UI smoke

1. Launch the wizard; bind source = Esperanto on page 1.
2. Advance to page 2. The tree MUST populate (no empty pane).
3. Confirm nested POS groups, subgroups (Inflectional / Derivation—attaches / —produces),
   4 columns, and the Unattached drawer with 7 no-POS affixes.
4. Check the Verb group → all verb-attaching affixes check; produces-only affixes do NOT.
5. Uncheck a multi-POS affix in one group → it unchecks in its other appearance.
6. Advance to Preview (page 4); confirm the plan reflects the selected affix GUIDs.

## Done When

- Both unit test files pass.
- Live integration counts match the acceptance anchors for both projects.
- Manual UI smoke passes on Esperanto.
