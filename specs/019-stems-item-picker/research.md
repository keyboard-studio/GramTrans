# Research: Stems Item Picker (019)

All decisions below are MCP-verified (FlextoolsMCP) against the live `selection.py` engine
during the cycle-1 investigation (2026-07-05). No NEEDS CLARIFICATION remain.

## Decision 1 — Live UI engine is `Lib/selection.py`, not `categories.py`

- **Decision**: Build the stem partition into the four `selection.py` builders. Treat the
  `categories.py` `affixes_*/stems_*` callbacks (`NotImplementedError`, ~1817-1916) as
  out-of-scope.
- **Rationale**: The wizard calls `build_pos_grouped_inventory` at
  `selection_wizard.py:722`; `collapse_pos_grouped(...affix_picks)` at :1189; pages 3–5 read
  `page_items().collect_selection().affix_picks` (:1786-1790). The `categories.py` stubs are
  never on the live UI path — they are the separate Phase-3c LibLCM-direct track (Constitution
  IV: a sibling repo, not in this tree).
- **Alternatives considered**: Implementing against `categories.py` — rejected; would code the
  wrong (unused) engine.

## Decision 2 — Partition rule + null-guard inversion (FR-002)

- **Decision**: An entry is an **affix** only when
  `LexEntry.LexemeFormOA.MorphTypeRA.IsAffixType` is explicitly `True`. Everything else —
  `IsAffixType == False`, null `LexemeFormOA`, null `MorphTypeRA`, or an uncastable morphtype
  — is a **stem**. The stem filter uses **include-on-exception**: on `AttributeError`/
  `TypeError` traversing the chain, place the entry in the stem bucket.
- **Rationale**: MCP confirms `IsAffixType` is a boolean on `IMoMorphType` and both
  `LexemeFormOA`/`MorphTypeRA` are nullable. The affix filter's `except (...): continue`
  (`selection.py:658`) correctly skips null entries *for the affix tab*, but copying that
  pattern into the stem filter would silently drop exactly the entries FR-002 says must default
  to stem. Inverting the guard is mandatory and is the highest-risk correctness point.
- **Alternatives considered**: Copy the affix skip pattern — rejected (violates FR-002,
  drops null-morphtype entries from both tabs).

## Decision 3 — Stem MSA dispatch + dependency accessors (FR-004/FR-013)

- **Decision**: Add a `MoStemMsa` arm to the MSA dispatch (`selection.py:706-810`). Stem POS
  via `MoStemMsa.PartOfSpeechRA`; exception/inflection features via `MoStemMsa.MsFeaturesOA`;
  inflection classes via `POS.InflectionClassesOC`; stem names via
  `IPartOfSpeech.StemNamesOC`; inflectable features via `POS.InflectableFeatsRC`.
- **Rationale**: MCP confirms `MoStemMsa` is a first-class MSA subclass with `PartOfSpeechRA`
  and `MsFeaturesOA`. **`InflectionClassRA` (RA → `IMoInflClass`) and `SlotsRC` (RC) BOTH
  exist on `IMoStemMsa` (MCP-confirmed 2026-07-05; both require a cast to `IMoStemMsa`).**
  **InflectionClassRA: READ-IF-PRESENT (defensive).** The stem dep walk casts to `IMoStemMsa`,
  reads `InflectionClassRA` with a None-check, and treats a non-null value as a referential edge
  feeding the FR-009 missing-reference aggregation (a kept stem whose inflection class is absent
  from target = silent broken transfer). If null it is a no-op. Live data (Ejagham Full GT-Test,
  read-only dry-run): 0/2444 stem MSAs have `InflectionClassRA` populated — no behavior change
  on Ejagham confirmed. This check is ADDITIVE TO, not a replacement for, the primary inflection-
  class source `POS.InflectionClassesOC`. **SlotsRC: OUT.** Empty on live data (0/2444) AND
  architecturally affix-only (slot membership; a stem MSA is never cast to `IMoInflAffMsa`).
  Never read. The affix arm reads `SlotsRC` on `IMoInflAffMsa` and enters the slot/template
  skeleton builder; that arm is strictly affix-only.
- **Alternatives considered**: Reuse the affix MSA arm for stems — rejected (wrong dependency
  closure; the affix arm targets `IMoInflAffMsa` slot/template semantics that do not apply to
  a stem entry). NOTE: the prior "phantom API" rejection of `MoStemMsa.InflectionClassRA` was
  a factual error — the MCP re-check (2026-07-05) confirms the property is real.

## Decision 4 — Owned-child closure shared with affix path (FR-005)

- **Decision**: Reuse the affix owned-child walk unchanged for stems: `SensesOS`,
  `MorphoSyntaxAnalysesOC`, `AlternateFormsOS`, `ExamplesOS` (via senses), `LexemeFormOA`.
- **Rationale**: MCP confirms these owning collections exist on `ILexEntry` and are already
  traversed by the affix path (`selection.py:221-237`, `merge_preview.py:1283-1308`). The
  closure is entry-level, morphtype-agnostic. Pronunciations/etymologies/entry-refs exist on
  `ILexEntry` but are only referenced by the stubbed `categories.py` block — out of scope here.

## Decision 5 — `stem_picks` sibling field + dedup by GUID

- **Decision**: Add `Selection.stem_picks: frozenset[str]` sibling to `affix_picks`, with its
  own STEMS-category invariant. Shared dependencies (e.g. a POS needed by both a picked affix
  and a picked stem) deduplicate by GUID.
- **Rationale**: Mirrors the shipped affix pick-set threading (Page 2 tree → `collect_selection`
  → pages 3–5). Keeps the two pick sets independent and testable; GUID dedup is already how the
  closure engine collapses shared dependencies.

## Decision 6 — Warnings route into the existing Move gate (FR-009/FR-010)

- **Decision**: Stem missing-reference warnings feed `build_excluded_lossy_warnings()` and the
  `plan.excluded_lossy_count()` aggregation (`selection_wizard.py:3171`). No pane-specific
  dialog.
- **Rationale**: The Move gate already aggregates skeleton/deps deselections into a single
  consolidated confirmation (:3190-3200). Stems are just another source of entry-centric
  warnings into the same channel.
