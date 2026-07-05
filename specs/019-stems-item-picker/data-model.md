# Data Model: Stems Item Picker (019)

## Selection (extended)

Existing dataclass in [Lib/models.py](../../src/gramtrans/Lib/models.py). Add one field.

| Field | Type | Notes |
|-------|------|-------|
| `affix_picks` | `frozenset[str]` | Existing. Picked affix-entry GUIDs. |
| **`stem_picks`** | **`frozenset[str]`** | **NEW.** Picked stem-entry GUIDs. Sibling to `affix_picks`. |
| `categories` | mapping | Existing. `GrammarCategory.STEMS` toggles stem transfer. |

**Invariant (mirrors affix invariant)**: a non-empty `stem_picks` requires
`categories[GrammarCategory.STEMS]` to be on. Enforced in `Selection` validation; covered by
`tests/unit/test_selection_invariants.py`.

## Stem entry (partition input)

A `LexEntry` classified into the **stem** partition. Classification is **not** a stored field —
it is computed at enumeration time from `LexemeFormOA.MorphTypeRA.IsAffixType`.

| Rule | Result |
|------|--------|
| `IsAffixType == True` (explicit) | AFFIX (Affixes tab) |
| `IsAffixType == False` | STEM |
| `LexemeFormOA` null | STEM (include-on-exception) |
| `MorphTypeRA` null | STEM (include-on-exception) |
| morphtype cast raises `AttributeError`/`TypeError` | STEM (include-on-exception) |

Partition is **complete and disjoint**: every `LexDbOA.Entries` entry lands in exactly one tab.

## StemRow (inventory row — UI)

Parallel to the affix inventory row produced by `build_pos_grouped_inventory`.

| Field | Source |
|-------|--------|
| `guid` | `LexEntry.Guid` |
| `label` | lexeme form (headword) |
| `pos` | `MoStemMsa.PartOfSpeechRA` (grouping key) |
| `target_status` | NEW / IN TARGET / SIMILAR via `_build_target_sets` (blank if no target bound) |
| `checked` | user pick state → `stem_picks` |

## Derived grammatical dependency (Model-A closure)

Computed from picked stems; preselected on Skeleton / Grammatical-deps pages.

| Dependency | Accessor |
|------------|----------|
| Part of speech | `MoStemMsa.PartOfSpeechRA` |
| Inflection class | `POS.InflectionClassesOC` (via POS, **not** the MSA) |
| Stem name | `IPartOfSpeech.StemNamesOC` |
| Inflectable feature | `POS.InflectableFeatsRC` |
| Exception/inflection feature | `MoStemMsa.MsFeaturesOA` |

Shared dependencies deduplicate by GUID across affix and stem pick sets.

## Owned-child closure (travels with the stem)

`SensesOS`, `MorphoSyntaxAnalysesOC`, `AlternateFormsOS`, `ExamplesOS` (via senses),
`LexemeFormOA` — same walk as the affix path, morphtype-agnostic.

## Missing-reference warning

A `(kept-stem, stranded-dependency)` pair produced when a needed dependency is deselected and
absent from the target. Emitted into `build_excluded_lossy_warnings()`; aggregated by
`plan.excluded_lossy_count()` into the single shared Move confirmation. One warning per kept
stem with an unresolvable dependency — never one prompt per stranded dependency.
