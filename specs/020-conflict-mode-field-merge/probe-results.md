# 020 Conflict-Mode Field Merge — FLExTools MCP Probe Results (authoritative API)

**Probed**: 2026-07-05 via `flextools-mcp` (api_mode=flexicon, **read-only**,
write_enabled=false) against **Ejagham Full** and **Esperanto**. These are the
ground-truth API facts for the conflict-mode UI + field-level merge. **Do not
guess** — where the spec's optimistic "already exists, just wire it" framing and
the live API disagree, the live API (recorded here) wins. Module code imports
LCM / flexicon directly (constitution v5.1.0 Principle II).

Two of these facts **refute or refine** the pre-probe assumptions carried in the
spec Assumptions block — see [WARN] items §4 and §5.

## §1 — `GetSyncableProperties` key sets per category (LIVE, authoritative)

Exact key sets returned by `<ops>.GetSyncableProperties(item)` on the first item
of each category. Scalar/text keys are **in field-merge scope**; atomic `*RA`
GUID refs are **also in scope** (surface as GUID-valued conflicts, see §4);
`*RS` / `*OC` sequence/collection refs are **excluded upstream** by flexicon's
enumeration (never appear in the dict).

| Category (ops) | Live key set | Scope note |
|---|---|---|
| **POS** (`project.POS`) | `Abbreviation, CatalogSourceId, Description, Name` | all scalar/text; in `_OW_OPS` today |
| **InflectionFeature** (`project.InflectionFeatures`, `FeatureGetAll()`) | `Abbreviation, Description, Name` | all scalar/text |
| **NaturalClass** (`project.NaturalClasses`) | `Abbreviation, Description, Name` | all scalar/text; confirmed on **both** projects |
| **LexEntry** (`project.LexEntry`) | `Bibliography, CitationForm, Comment, DoNotPublishInRC, DoNotShowMainEntryInRC, HomographNumber, ImportResidue, LexemeForm, LiteralMeaning` | scalar/text; `HomographNumber` int (non-merge-eligible); in `_OW_OPS` |
| **Sense** (`project.Senses`) | `Bibliography, Definition, DiscourseNote, DoNotPublishInRC, DoNotShowMainEntryInRC, EncyclopedicInfo, GeneralNote, Gloss, GrammarNote, ImportResidue, MorphoSyntaxAnalysisRA, PhonologyNote, Restrictions, ScientificName, SemanticsNote, SenseTypeRA, SocioLinguisticsNote, Source, StatusRA` | scalar/text **+ atomic RA refs** (`MorphoSyntaxAnalysisRA`, `SenseTypeRA`, `StatusRA`); in `_OW_OPS` |
| **Allomorph** (`project.Allomorphs`) | `Form, IsAbstract, MorphTypeRA` | `Form` text, `IsAbstract` bool, **`MorphTypeRA` atomic ref**; in `_OW_OPS` |
| **Phoneme** (`project.Phonemes`) | **RAISES** — see §5 | BLOCKED by flexicon bug |
| **PhEnvironment** (`project.Environments`) | **RAISES** — see §5 | BLOCKED by flexicon bug |
| **MorphRule / PhonRule / Compound** | not live-probeable here (no items in Ejagham Full / Esperanto) | cite 018 probe: `Name, Description, StratumGuid, Disabled` (not re-probed live in 020) |

> `StratumGuid` is a text-encoded GUID string; `ApplySyncableProperties` writes
> it as text and does **not** wire `StratumRA`. That wiring is manual (018 probe).

## §2 — `ApplySyncableProperties` / `fill_gaps` merge semantics (LIVE)

Confirmed signature on all 8 Grammar ops + lexicon ops:

```text
ApplySyncableProperties(item, props, ws_map=None, fill_gaps=False)
```

- `fill_gaps=False` (default, `write_mode="overwrite"`): source values overwrite
  target unconditionally for every key in `props`.
- `fill_gaps=True` (`write_mode="merge"`): source values written **only** to
  target fields that are empty/None; non-empty target fields preserved.

`fill_gaps` and per-field decisions are **orthogonal**: the executor filters the
`props` dict to the fields the user chose (`TAKE_SOURCE` in, `KEEP_TARGET` out)
*before* the call (`transfer.py` `_resolve_and_tag`); `fill_gaps` then governs
how each surviving key is applied. Grammar-ops call sites in `categories.py`
currently pass the default (`fill_gaps=False`); only the lexicon path threads it.

## §3 — `IsProtected` cast behavior (LIVE)

`IsProtected` is a native `ICmPossibility` property, absent on base `ICmObject`.
Live results on a POS from `project.POS.GetAll(recursive=True)`:

```text
POS wrapper type      = IPartOfSpeech      (already concrete; no .concrete wrapper)
getattr(pos,'IsProtected') = False (bool)  # bare access does NOT raise at runtime
ICmPossibility(pos).IsProtected = False    # explicit cast agrees
ICmObject(pos).ClassName = 'PartOfSpeech'
```

**Runtime vs. static-validator divergence (important for module code):** because
flexicon `GetAll()` returns objects already typed to the concrete interface
(`IPartOfSpeech`), a bare `.IsProtected` **resolves at runtime** (returns a bool,
does not raise). BUT the FLExTools MCP **static validator rejects** bare
`.IsProtected` in module source and requires `ICmPossibility(x).IsProtected`.
Therefore module code MUST use the cast to be validator-clean, even though the
permissive `except`-branch in `protection.py._is_protected` rarely fires at
runtime for these ops iterators.

## §4 — [WARN] REFUTES spec Assumption: atomic RA refs ARE in the conflict set

The spec/pre-probe assumption "field-level conflict == scalar/text syncable props
only; references are wired manually and out of scope" is **only partly true**.
Live proof: `Sense.MorphoSyntaxAnalysisRA`, `Sense.SenseTypeRA`,
`Sense.StatusRA`, and `Allomorph.MorphTypeRA` **appear in the
`GetSyncableProperties` dict**. `detect_conflicts` (which diffs that dict) will
therefore surface these atomic RA references as **GUID-valued field conflicts**.

Corrected scope rule: **020 field-diff = scalar/text fields PLUS atomic `*RA`
GUID refs; `*RS` / `*OC` sequence & collection refs are excluded** (flexicon
never enumerates them into the syncable dict). The plan/spec must state this
precisely and must NOT claim a flat "references are out of scope."

## §5 — [WARN] NEW blocking finding: Phoneme/Environment `GetSyncableProperties` throws

`GetSyncableProperties` **raises** for phonemes and phonological environments:

```text
Phoneme:     AttributeError("'ITsString' object has no attribute 'get_String'")
Environment: AttributeError("'ITsString' object has no attribute 'get_String'")
```

Reproduced on **both** Ejagham Full and Esperanto ⇒ this is a **flexicon-level
defect**, not project data. Consequence: field-level detection for **PHONEMES**
and **PH_ENVIRONMENT** is **BLOCKED upstream**, not merely "missing from
`_OW_OPS`." FR-012 field-diff for these two categories cannot ship in 020 until
flexicon is fixed. They get mode-selector-only. File the bug separately against
flexicon (see plan.md §Follow-ups) and reference the bug id when marking Tier C.

## §6 — Confidence / could-not-probe

- POS, InflectionFeature, NaturalClass, LexEntry, Sense, Allomorph key sets: **HIGH** (live, Ejagham Full; NaturalClass also Esperanto).
- Phoneme / Environment throw: **HIGH** (reproduced on two projects).
- IsProtected runtime/static behavior: **HIGH** (live POS + MCP static validator rejection observed directly).
- MorphRule / PhonRule / Compound key sets: **MEDIUM** — no live items in the probed projects; carried from the 018 probe, flagged as not-re-probed. A live re-probe against a rule-bearing project is a plan-time follow-up if a rule category is put in Tier A.
