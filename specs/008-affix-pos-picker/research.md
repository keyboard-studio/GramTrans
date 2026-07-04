# Phase 0 Research: Affixes-by-POS Item Picker

All items below were resolved live via the FlexTools MCP (read-only) against
**Ejagham Full GT-Test** and **Esperanto**. The MCP is the source of truth per the
project's author-side tooling convention.

## R1 — Affix enumeration accessor

**Decision**: Enumerate `source.Cache.LangProject.LexDbOA.Entries`, filter to entries
whose `LexemeFormOA.MorphTypeRA.IsAffixType` is true.

**Rationale**: Live probe confirmed `ILexDb` exposes `.Entries`, not `.EntriesOC`
(`AttributeError: 'ILexDb' object has no attribute 'EntriesOC'. Did you mean: 'Entries'?`).
Counts: Ejagham 4,317 entries → 33 affixes; Esperanto 15,318 → 68 affixes.

**Alternatives considered**: `project.LexEntry.GetAll()` (flexicon wrapper) — viable
but the builder takes a raw `source` handle and the direct `LexDbOA.Entries` walk keeps
the fake-handle test shape simple. The existing `affixes_enumerate_source` uses
`.EntriesOC` — that is bug #2 (out of scope; do NOT copy it).

## R2 — MSA type dispatch and POS fields

**Decision**: Branch on `msa.ClassName`:
- `MoInflAffMsa` → cast `IMoInflAffMsa`, read `PartOfSpeechRA` (attaches-to).
- `MoUnclassifiedAffixMsa` → cast `IMoUnclassifiedAffixMsa`, read `PartOfSpeechRA`
  (attaches-to).
- `MoDerivAffMsa` → cast `IMoDerivAffMsa`, read `FromPartOfSpeechRA` (attaches-to) and
  `ToPartOfSpeechRA` (produces).
- Any other/unrecognized `ClassName`, or all POS fields null → route the affix to the
  Unattached drawer.

**Rationale**: `get_object_api IMoDerivAffMsa` confirms it has *only* `FromPartOfSpeechRA`
+ `ToPartOfSpeechRA` (no `PartOfSpeechRA`). Both require casting to `IMoDerivAffMsa`.
Live kind distribution — Ejagham: infl=33, deriv=0, uncl=0. Esperanto: infl=41, deriv=31,
uncl=12.

**Alternatives considered**: Reading `PartOfSpeechRA` uniformly (what bug #1 does) — drops
all derivational grouping. Rejected.

## R3 — Casting requirements (pythonnet)

**Decision**: Guard every polymorphic access with a concrete cast:
- POS label: `ICmPossibility(pos)` then `.Abbreviation` (preferred) → `.Name` (fallback),
  each `.BestAnalysisAlternative.Text`, normalizing `***`/empty.
- Form: `ILexEntry(entry).LexemeFormOA`, then `IMultiAccessorBase(form.Form)
  .BestVernacularAlternative.Text`.
- MSA fields: cast to the concrete MSA interface (R2) before reading POS refs.
- POS hierarchy walk: `SubPossibilitiesOS` on the concrete POS.

**Rationale**: MCP casting-preflight flagged `Abbreviation`/`Name` as missing on `ICmObject`
(need `ICmPossibility`), `LexemeFormOA` as needing `ILexEntry`, and
`BestVernacularAlternative` as needing `IMultiAccessorBase`. All confirmed by successful
live runs after applying the casts. A failed/absent cast MUST be treated defensively
(skip that datum) so a malformed object degrades to the Unattached drawer rather than
crashing the builder.

**Note (author-side only)**: the MCP casting validator false-positives on a call-rooted
receiver (`ILexEntry(e).LexemeFormOA`); split the cast onto its own line when running via
MCP. Irrelevant to shipped code.

## R4 — Presentation rules

**Decision**: Form = best-vernacular. Glosses = each sense's
`Gloss.BestAnalysisAlternative`, deduplicated, joined with `"; "`, `"(no gloss)"` when
empty. POS label = analysis Abbreviation, else Name. Ordering: POS in source
`PossibilitiesOS`/`SubPossibilitiesOS` hierarchy order; affix rows alphabetical by form.
One row per `(entry, POS-group, direction-role)`; multiple senses landing in the same
group collapse to one row with concatenated glosses.

**Rationale**: Matches the grilled design and reads cleanly on live data (Unicode forms
`aĵo`, `igi`, `ino` render correctly; example `igi From=Root To=v`).

## R5 — Selection collapse + cross-appearance mirroring

**Decision**: Selection identity is the affix **entry GUID**. Collapse gathers checked
leaf rows' entry GUIDs, deduplicated, into `Selection.affix_picks` via the existing
`build_selection` (reusing `PickerState.checked_affixes`; templates/slots left empty).
An entry appearing in multiple groups (multi-POS, or deriv shown under From + produces)
shares one selection state; `itemChanged` mirrors the check state to all tree items
carrying the same GUID, guarded by a re-entrancy flag to avoid signal recursion.
Group-header check sweeps only the two attaches-to subgroups (Qt auto-tristate on the
POS node), never the "produces" subgroup — implemented by making "produces" rows children
of a non-swept subgroup node (or excluding them from the header's tristate set).

**Rationale**: Whole-entry transfer is the only meaningful unit; dedup-by-GUID makes the
collapse correct even absent mirroring, so mirroring is UX-consistency. Esperanto has 13
affixes attaching to >1 POS — exercises multi-appearance mirroring for real.

**Alternatives considered**: Persisting group-level intent — rejected; the picker rebuilds
from live source each run, so a resolved GUID snapshot suffices.

## R6 — Legacy `affix_tree_picker.py`

**Decision**: Treat the standalone `AffixTreePicker` dialog as **legacy/unused** for this
feature. The wizard's page-2 `_PageItemPicker` is the live surface; `AffixTreePicker` is a
pre-wizard dialog not on the wizard path. Do not port the POS grouping into it now; add a
module docstring note marking it legacy and pointing at `_PageItemPicker`. Leaves its
existing unit tests green (they exercise the template-shaped `SourceAffixInventory`, which
is retained).

**Rationale**: Minimizes blast radius; avoids duplicating the new tree logic in two places.
Revisit if a non-wizard entry point is ever needed.

## R7 — Empty / degenerate sources

**Decision**: Zero affixes → render an empty but labeled tree (no error). Entry with no
sense or no MSA → Unattached drawer, "no sense / no analysis" subgroup. Entry with MSA(s)
but every POS ref null → Unattached drawer, "no part of speech" subgroup. Ejagham: 1
no-POS junk; Esperanto: 7 no-POS junk (0 no-MSA in both).

**Rationale**: Constitution "no silent skips" — everything the picker sees is either in a
POS group or visibly in the drawer.
