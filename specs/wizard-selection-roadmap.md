# GramTrans Wizard — Selection Roadmap (all data types)

Cross-feature planning map: every transferable data type, which wizard page/group it
belongs to, its selection model, and its build status. Derived from the "Things we
might want to transfer" list in `Transfer FLEx Grammar Module.md` plus the phonology
block (spec 005) and the grilled 008-follow-up grouping (2026-07-01).

## Two selection models

- **Model A (item-derived):** the user picks lexical items; the grammatical schema they
  depend on is computed, preselected, and shown for review/trim/extend.
- **Model B (independent block):** self-contained grammar transferred wholesale
  (NONE / ALL, with optional per-item trim); not derived from a lexical pick.

## Page order (dependency-layered)

```
Project+WS  →  Phonology  →  Affixes  →  Skeleton  →  Grammatical deps  →  Preview  →  Finish
            └ Model-B block ┘ └───────────── item-derived (Model A) ─────────────┘
```

## Coverage map

| # | Data type | LCM anchor | Page / group | Model | Status |
|---|-----------|-----------|--------------|-------|--------|
| 1 | Writing Systems (check/map) | WS factory | Project + WS | project-level | **DONE** (wizard page 1) |
| 2 | Phonemes | `PhonologicalDataOA.PhonemeSetsOS` | Phonology | B | LATER (engine: spec 005) |
| 3 | Phonological Features | `PhFeatureSystemOA` | Phonology | B | LATER |
| 4 | Natural Classes | `PhonologicalDataOA.NaturalClassesOS` | Phonology | B | LATER |
| 5 | Environments (PhEnvironment) | `PhonologicalDataOA.EnvironmentsOS` | Phonology | B | LATER (005 US3 relocates here) |
| 6 | Phonological Rules | `PhonologicalDataOA.PhonRulesOS` | Phonology | B | LATER |
| 7 | Strata | `MorphologicalDataOA.StrataOS` | (Phonology, **auto/invisible**) | auto | LATER (005 US2 — never user-picked) |
| 8 | Affixes (LexEntry, affix morphtype) | `LexDbOA.Entries` | Affixes | A | **DONE**; preselect-all = current slice |
| 9 | Allomorphs | `entry.AlternateFormsOS` | (Affixes, **auto** closure) | auto | engine done (Phase 0/1) |
| 10 | APRs / allomorph environments | `allomorph.PhoneEnvRC` | (Affixes, **auto** closure) | auto | pulled with affixes |
| 11 | Parts of Speech (POS) | `PartsOfSpeechOA` | Skeleton | A (derived) | **CURRENT SLICE** |
| 12 | Slots (IMoInflAffixSlot) | `POS.AffixSlotsOC` | Skeleton | A (derived) | **CURRENT SLICE** |
| 13 | Templates (IMoInflAffixTemplate) | `POS.AffixTemplatesOS` | Skeleton | A (derived) | **CURRENT SLICE** |
| 14 | Inflection Features | `MsFeatureSystemOA` / `POS.InflectableFeatsRC` | Grammatical deps | A (derived, preselected) | **CURRENT SLICE** |
| 15 | Inflection Classes | `POS.InflectionClassesOC` | Grammatical deps | A (derived, preselected) | **CURRENT SLICE** |
| 16 | Stem Names | `POS.StemNamesOC` | Grammatical deps | A (derived, preselected) | **CURRENT SLICE** |
| 17 | Exception Features | `POS.ExceptionFeaturesOC` (IFsSymFeatVal refs) | Grammatical deps | A (derived, preselected) | **CURRENT SLICE** |
| 18 | Variant Types | `LexDbOA.VariantEntryTypesOA` | Lexical-entry types | B | LATER (engine done) |
| 19 | Complex Form Types | `LexDbOA.ComplexEntryTypesOA` | Lexical-entry types | B | LATER (engine done) |
| 20 | Ad Hoc Rules | `MorphologicalDataOA.AdhocCoProhibitionsOS` | Rules | B | LATER |
| 21 | Compound Rules | `MorphologicalDataOA.CompoundRulesOS` | Rules | B | LATER |
| 22 | Custom Fields | metadata cache | Custom Fields | B (detect + report) | LATER (creation blocked at flexlibs2 layer; detect-only) |
| 23 | Stems (LexEntry, stem morphtype) | `LexDbOA.Entries` | Stems | A (item picker) | LATER (pane stubbed/disabled) |

## Undecided / to revisit

- **Semantic Domains** (`SemanticDomainListOA`, engine FR-326 implemented): lexicon-side,
  not in the original grammar-transfer list. Decide whether it gets a page or stays
  engine-only.
- **Conflict mode UI** (ADD_NEW / MERGE / OVERWRITE): deferred for all pages this phase;
  Layer-1 category defaults apply automatically and the target-status column
  (NEW / IN TARGET / SIMILAR) carries the informational weight. Real per-category conflict
  UI lands in the phase that implements field-level merge.

## Cross-cutting (every selection page)

- **Target-status column** (FR-018): NEW / IN TARGET / SIMILAR against the early-bound target.
- **EXCLUDED-LOSSY safety** (Constitution V): deselecting a dep a picked item needs →
  grouped entry-centric warnings in Preview + a single confirm-on-Move dialog (never
  per-item prompts).
- **GOLD inviolability** + **GUID-first identity** + **dual-carrier residue** (Constitution I).

## Build sequence

1. **Current slice** — preselect affixes + Skeleton page + Grammatical-deps page
   (spec `009-skeleton-deps-selectors`).
2. Phonology page (Model-B block; engine from spec 005).
3. Lexical-entry types + Rules + Custom Fields (Model-B blocks).
4. Stems item picker (un-stub).
5. Conflict-mode UI + field-level merge (its own phase).
