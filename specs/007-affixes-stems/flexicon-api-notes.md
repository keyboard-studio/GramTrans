# pyflexicon API notes — LCM-write layer (Feature 007, Phase 3c)

**Purpose:** reference for the LCM-write layer that transfers affix/stem
`LexEntry` objects and wires `MSA.SlotsRC` + `LexEntryRef`
component/primary sequences via pyflexicon (`pyflexicon>=4.1`).

## Provenance / important caveat

The requested docs site **`https://flexicon.langtech.cloud/` was NOT reachable**
from this environment. It is blocked by the session's egress policy:

- `WebFetch` → `HTTP 403 Forbidden`.
- `curl -I https://flexicon.langtech.cloud/` → `curl: (56) CONNECT tunnel failed, response 403`.
- Agent proxy status recorded: `kind: "connect_rejected"`,
  `detail: "gateway answered 403 to CONNECT (policy denial or upstream failure)"`,
  `host: "flexicon.langtech.cloud:443"`.

Per the proxy README this is an organization egress denial (not an origin
error); it must not be retried or routed around. **No content from that site is
reproduced here.**

Instead, every API detail below was read directly from the **authoritative
package source** — `pyflexicon` **4.1.1** sdist on PyPI
(`pyflexicon-4.1.1.tar.gz`, `files.pythonhosted.org`, both allowlisted hosts).
Anything not verifiable from that source is flagged as such. Line references
point into the 4.1.1 source tree (`flexicon/code/...`).

### Package facts (from PyPI metadata)

- Distribution name **`pyflexicon`**; **import name is `flexicon`** (not
  `pyflexicon`). Legacy alias `flexlibs2` still imports (deprecated, to be
  removed in v5.0.0). It is a successor to `cdfarrow/flexlibs`.
- Latest released versions: **4.1.0, 4.1.1** (4.1.1 is latest). `requires-python >=3.8,<3.14`.
- Repo/changelog: `https://github.com/MattGyverLee/flexicon`.
- It is a **Python.NET (pythonnet) wrapper over SIL LibLCM** (`SIL.LCModel.*`)
  and requires an installed FieldWorks (FLEx 9.0.17–9.3.1). It cannot run
  without the .NET FieldWorks assemblies present, so the write layer must be
  exercised on a machine/CI with FieldWorks installed.
- Author: `matthew_lee@sil.org`.

The interface names (`ILexEntry`, `IMoStemMsa`, `SandboxGenericMSA`, `SlotsRC`,
`ComponentLexemesRS`, `PrimaryLexemesRS`, `TargetsRS`, etc.) are LCM/LibLCM
types; pyflexicon exposes them via pythonnet and wraps the common create/attach
idioms in `*Operations` helper classes.

---

## 1. Session lifecycle & the `FLExProject` facade

```python
import flexicon
flexicon.FLExInitialize()             # boots the .NET FLEx engine (once per process)

project = flexicon.FLExProject()
project.OpenProject("MyProject", writeEnabled=True, undoable=False)
# ... do work via project.LexEntry / project.MSA / project.Allomorphs / ...
project.CloseProject()                # saves changes + releases the lock
flexicon.FLExCleanup()
```

- `OpenProject(projectName, writeEnabled=False, undoable=False)`
  (`FLExProject.py:163`). `projectName` is either a full path ending `.fwdata`
  or a bare project name in the default location.
  - **Writes require `writeEnabled=True`** or LCM raises. Every mutating
    operation first calls `_EnsureWriteEnabled()`, which raises
    `FP_ReadOnlyError` when the project is read-only (`BaseOperations.py:1666`).
  - `undoable=True` selects "Phase 2" transaction semantics (writes become a
    single named entry in FLEx's Ctrl+Z undo menu). `undoable=False` (default)
    is "Phase 1" — programmatic rollback-only, invisible to the FLEx user.
  - **Nothing is persisted to disk until `CloseProject()`.**
- The `FLExProject` instance is a facade exposing topic-area *Operations*
  objects as properties. Relevant ones for the write layer:
  `project.LexEntry`, `project.Senses`, `project.MSA`, `project.Allomorphs`,
  `project.Examples`, `project.Pronunciation(s)`, `project.Etymology`,
  `project.Variants`, `project.LexReferences`, `project.SemanticDomains`,
  `project.WritingSystems`, `project.POS`/`project.GramCat`,
  `project.Stratum`. (Property names are the public accessors used in the
  docstrings; confirm the exact attribute against the installed build.)
- `project.project` is the underlying LCM `LcmCache`/project object;
  `project.project.ServiceLocator.GetService(IFactory)` /
  `.GetInstance(IFactory)` obtain LCM factories.
- `project.Object(hvoOrGuid)` resolves an HVO or GUID to a live LCM object
  (`FLExProject.py:3000`). Most `*Operations` methods accept **either a live
  object or an int HVO** — see the `__Resolve*` helpers.

---

## 2. Transactions & write semantics (`_TransactionCM`)

Multi-mutation write methods wrap their body in `self._TransactionCM(label)`
(`BaseOperations.py:1703`, implemented in `transaction.py`):

- Use it for methods doing **2+ LCM mutations** (`factory.Create()` +
  `OS.Add()` + property sets). A single atomic mutation does not need it.
- Phase 1 (`undoable=False`): `_FLExTransaction` marks a rollback point and
  rolls back on exception. Nests safely (inner rollback → inner mark).
  **Caveat in this build:** the LCM Mark/RollbackToMark API is reportedly not
  discoverable, so on failure it logs a warning and proceeds *without* rollback
  rather than raising (see the package's `docs/RESEARCH_NEEDED.md`). Do not
  assume automatic rollback protects you — validate inputs before mutating.
- Phase 2 (`undoable=True`): outermost block opens one `UndoableOperation`
  named undo task; **nested `_TransactionCM` blocks become no-ops** (LCM
  `BeginUndoTask`/`EndUndoTask` cannot nest). All inner mutations are absorbed
  into the single outer undo entry.
- Depth is tracked on `project._transaction_depth`, so nesting across
  Operations boundaries (e.g. `LexEntry.Create` → sense creation) is handled.
- For your own batch import you can wrap many entry creations in one outer
  `with project.Transaction("batch"):` (Phase 1) or
  `with project.UndoableOperation("Transfer affixes"):` (Phase 2).

**Order rule enforced everywhere:** call `_EnsureWriteEnabled()` and all
validation/lookups that may raise *before* entering `_TransactionCM`, and keep
the `return` *inside* the `with` block.

---

## 3. Writing systems (multilingual string fields)

WS handling is the single most repeated pattern. Rules distilled from the
source:

- A **WS "handle" is an `int`.** LCM multistring accessors
  (`MultiUnicode`/`MultiString`) and `TsStringUtils.MakeString(text, wsHandle)`
  all take the int handle.
- `project.WSHandle(languageTag)` → int handle for a BCP-47 tag; case- and
  `-`/`_`-insensitive; returns `None` if not found (`FLExProject.py:2608`).
  Example tags: `"en"`, `"fr"`, `"en-fonipa"` (IPA).
- Each Operations class has private `__WSHandle` helpers that accept **`None`,
  a str tag, an int handle, or a WS definition object** and normalize to an int
  (`FLExProject.py:3058`, `normalize_ws_handle` coerces objects with `.Handle`).
  - `None` defaults to the appropriate WS for the field:
    **vernacular** for lexeme/allomorph/pronunciation forms
    (`DefaultVernWs`), **analysis** for glosses/definitions/notes
    (`DefaultAnalWs`). See `__WSHandle` vs `__WSHandleAnalysis`/`Vernacular`.
  - An unresolvable tag raises `FP_WritingSystemError`.
- **Set a multilingual string field** (the low-level idiom used internally):

  ```python
  from SIL.LCModel.Core.Text import TsStringUtils
  tss = TsStringUtils.MakeString(text, wsHandle)     # build an ITsString
  obj.Form.set_String(wsHandle, tss)                 # MultiUnicode field
  obj.Gloss.set_String(wsHandle, tss)
  ```

  In pythonnet, indexed multistring writes use `set_String(ws, tss)` (and reads
  `get_String(ws)`), not Python `[]` indexing.
- Prefer the high-level setters (they do the `MakeString`/`set_String` dance and
  WS defaulting for you): `LexEntry.SetLexemeForm/SetCitationForm/SetHeadword`,
  `Senses.SetGloss/SetDefinition`, `Allomorphs.SetForm`, `Examples.SetExample/
  SetTranslation`, `Etymology.SetForm/SetGloss/SetSource`, etc. — each takes an
  optional `wsHandle`.
- `project.WritingSystems` (`WritingSystemOperations`) exposes
  `GetAll/GetVernacular/GetAnalysis/GetDefaultVernacular/GetDefaultAnalysis/
  Exists/Create(language_tag, name, is_vernacular=True)/GetLanguageTag/
  GetBestString(string_obj)`. Only `Create` new WSes if a needed tag is absent.

---

## 4. Creating a LexEntry and its owned children

All via `project.LexEntry` (`LexEntryOperations`), `project.Senses`
(`LexSenseOperations`), etc.

### 4.1 LexEntry

`LexEntry.Create(lexeme_form, morph_type_name=None, wsHandle=None, create_blank_sense=True)`
(`LexEntryOperations.py:131`):

- `morph_type_name`: `None`→`"stem"`. Stem-family (`stem`, `root`, `clitic`,
  `=enclitic`, `proclitic-`, `bound root`, `particle`, `phrase`) →
  auto-creates a **`MoStemAllomorph`** lexeme form; affix-family (`prefix`,
  `suffix`, `infix`, `simulfix`, `suprafix`, `circumfix`) → **`MoAffixAllomorph`**.
  Selection is by `__IsStemType(morph_type)` on the resolved `IMoMorphType`.
- **GUID is auto-generated** by the factory; do not set it. `Factory.Create()`
  auto-adds the entry to the repository — **no explicit `Add()`**.
- `create_blank_sense=True` (default) adds one empty sense (mirrors FLEx GUI).
  Pass `False` for affix/stem transfer where you build senses explicitly.
- Internally: get `ILexEntryFactory` → `Create()`; get
  `IMoStemAllomorphFactory` **or** `IMoAffixAllomorphFactory` → `Create()`;
  **attach the allomorph to `entry.LexemeFormOA` FIRST**, *then* set
  `Form.set_String(ws, tss)` and `MorphTypeRA`. (Attach-before-property-set is a
  hard ordering requirement throughout the codebase.)

Other useful setters/getters: `SetLexemeForm/GetLexemeForm`,
`SetCitationForm/GetCitationForm`, `SetHeadword/GetHeadword`,
`SetMorphType/GetMorphType`, `GetGuid`, `SetHomographNumber`,
`SetImportResidue`, `SetComment/SetBibliography/SetLiteralMeaning/
SetRestrictions/SetSummaryDefinition`, `SetDoNotUseForParsing`,
`SetExcludeAsHeadword`, `Find(lexeme_form, wsHandle=None)`,
`Exists(...)`, `Delete`, `MergeObject`.

### 4.2 Senses

- `LexEntry.AddSense(entry, gloss, wsHandle=None)` (`LexEntryOperations.py:1782`)
  — factory `ILexSenseFactory.Create()` → `entry.SensesOS.Add(sense)`
  (**add before setting props**) → `sense.Gloss.set_String(ws, tss)`. Default
  WS is analysis.
- `project.Senses` (`LexSenseOperations`) is the richer API:
  `Create(entry, gloss, wsHandle=None)`, `CreateSubsense(parent_sense, gloss)`,
  `SetGloss/SetDefinition`, **`SetPartOfSpeech(sense, pos, msa_kind="auto", ...)`**
  (creates/updates the MSA automatically — see §5), `SetGrammaticalInfo(sense, msa)`,
  `GetGrammaticalInfo`, `AddExample`, `AddSemanticDomain/RemoveSemanticDomain`,
  many `Set*Note` fields, `AddPicture`, `Reorder`.

`sense.MorphoSyntaxAnalysisRA` is the sense's reference to its MSA (see §5).
`sense.Entry` / walking `OwnerOfClass(LexEntryTags.kClassId)` gets the owning entry.

### 4.3 Allomorphs

`project.Allomorphs` (`AllomorphOperations`).
`Create(entry_or_hvo, form, morphType=None, wsHandle=None)`
(`AllomorphOperations.py:201`):

- `morphType`: `IMoMorphType` object, or a name string (display markers like
  `-`, `=`, `~`, `<`, `>` are stripped and matched case-insensitively), or
  `None` → **inherit from `entry.LexemeFormOA.MorphTypeRA`** (FLEx behavior).
- Chooses **`IMoStemAllomorphFactory`** vs **`IMoAffixAllomorphFactory`** by
  `__IsStemType(morphType)`.
- Attachment: if `entry.LexemeFormOA` is empty the new allomorph becomes the
  lexeme form; otherwise it is appended to **`entry.AlternateFormsOS`**
  (ownership sequence). Attach before setting `Form` / `MorphTypeRA`.
- Other methods: `SetForm/GetForm` (WS-aware), `SetMorphType/GetMorphType`,
  `AddPhoneEnv/RemovePhoneEnv/GetPhoneEnv` (phonological environments),
  `SetFormAudio/GetFormAudio`, `Delete`, `Duplicate`.

Allomorph concrete classes / interfaces (LCM):
- Stems: **`IMoStemAllomorph`** (`MoStemAllomorph`).
- Affixes: **`IMoAffixAllomorph`** (`MoAffixAllomorph`). (LCM also has
  `MoAffixProcess` for process morphology; pyflexicon's `Create` only produces
  stem/affix allomorph forms.)
- Base interface: `IMoForm` (`GetAll` returns `IMoForm`).

### 4.4 Examples

`project.Examples` (`ExampleOperations`):
`Create(sense, example_text, wsHandle=None)` (`ExampleOperations.py:147`),
`SetExample`, `AddTranslation/SetTranslation/GetTranslations`,
`SetReference`, `AddMediaFile`, `SetLiteralTranslation`, `Reorder`.
Examples live in `sense.ExamplesOS`.

### 4.5 Pronunciations

`project.Pronunciation` (`PronunciationOperations`):
`Create(entry, form, wsHandle=None)` (`PronunciationOperations.py:153`),
`SetForm`, `SetLocation`, `AddMediaFile`, `Reorder`.
Owned in `entry.PronunciationsOS`. Default WS vernacular.

### 4.6 Etymologies

`project.Etymology` (`EtymologyOperations`):
`Create(entry, source=None, form=None, gloss=None, ws=None)`
(`EtymologyOperations.py:159`),
`SetSource/SetForm/SetGloss/SetComment/SetBibliography/SetLanguage`.
Owned in `entry.EtymologyOS`.

### 4.7 Variants (a kind of entry-ref)

`project.Variants` (`VariantOperations`):
`Create(entry, variant_form, variant_type, wsHandle=None)`
(`VariantOperations.py:352`), `AddComponentLexeme/RemoveComponentLexeme/
GetComponentLexemes`, `SetType/SetForm`. Variant types via `GetAllTypes/FindType`.

---

## 5. MSAs — creation, subclasses, and `SlotsRC`

Everything MSA-related is in `project.MSA` (`MSAOperations`,
`Lexicon/MSAOperations.py`). This is the most relevant module for Phase 3c.

### 5.1 The four concrete MSA types

An MSA is owned by the **entry** (`entry.MorphoSyntaxAnalysesOC`, an *owning
collection*) and referenced by the sense (`sense.MorphoSyntaxAnalysisRA`).
All share base `IMoMorphSynAnalysis`. The four concrete subtypes and their
factories/`MsaType` enum values:

| Kind | Interface | Factory | `MsaType` | POS fields |
|---|---|---|---|---|
| Stem | `IMoStemMsa` (`MoStemMsa`) | `IMoStemMsaFactory` | `MsaType.kStem` | `PartOfSpeechRA` |
| Derivational affix | `IMoDerivAffMsa` (`MoDerivAffMsa`) | `IMoDerivAffMsaFactory` | `MsaType.kDeriv` | `FromPartOfSpeechRA`, `ToPartOfSpeechRA` |
| Inflectional affix | `IMoInflAffMsa` (`MoInflAffMsa`) | `IMoInflAffMsaFactory` | `MsaType.kInfl` | `PartOfSpeechRA` + `SlotsRC`, `InflFeatsOA` |
| Unclassified affix | `IMoUnclassifiedAffixMsa` (`MoUnclassifiedAffixMsa`) | `IMoUnclassifiedAffixMsaFactory` | `MsaType.kUnclassified` | `PartOfSpeechRA` |

`ClassName` string values (used for dispatch): `"MoStemMsa"`, `"MoDerivAffMsa"`,
`"MoInflAffMsa"`, `"MoUnclassifiedAffixMsa"`.

### 5.2 The universal create-and-attach idiom (`SandboxGenericMSA`)

All four use the same pattern (from `MSAOperations.__CreateAndAttach`,
`MSAOperations.py:584`):

```python
from SIL.LCModel.DomainServices import SandboxGenericMSA
from SIL.LCModel import MsaType, ILexEntry, LexEntryTags
import clr

sandbox = SandboxGenericMSA()
sandbox.MsaType = MsaType.kStem            # or kDeriv / kInfl / kUnclassified
sandbox.MainPOS = pos_obj                  # primary POS
sandbox.SecondaryPOS = to_pos_obj          # only meaningful for kDeriv (to-POS)

# The factory service must be fetched by the .NET System.Type of the interface:
factory = project.project.ServiceLocator.GetService(clr.GetClrType(IMoStemMsaFactory))

# The OWNER passed to Create() is the owning ENTRY, not the sense:
entry = ILexEntry(sense.OwnerOfClass(LexEntryTags.kClassId))
new_msa = factory.Create(entry, sandbox)   # 2-arg overload: (owner, sandbox)
sense.MorphoSyntaxAnalysisRA = new_msa     # attach to the sense
```

Key gotchas encoded here:
- **Owner is the entry, resolved via `sense.OwnerOfClass(LexEntryTags.kClassId)`**
  — critical for subsenses, whose `sense.Owner` is the parent sense, not the
  entry (issue #129).
- **`ServiceLocator.GetService` needs `clr.GetClrType(factory_interface)`**, not
  the raw pythonnet interface object.
- After `Create`, cast with the interface constructor
  (`IMoStemMsa(new_msa)`) to get typed field access.

### 5.3 The wrapper methods (use these)

- `MSA.CreateStem(sense, pos)` → `IMoStemMsa`. Sets `MainPOS`.
- `MSA.CreateDerivAff(sense, from_pos, to_pos=None)` → `IMoDerivAffMsa`.
  `MainPOS`=from, `SecondaryPOS`=to. **`to_pos=None` is valid** ("output not yet
  determined"); it explicitly sets `ToPartOfSpeechRA=None` after create because
  the sandbox mapping may not clear it (Cycle 4 / issue #91).
- `MSA.CreateInflAff(sense, pos, slots=None)` → `IMoInflAffMsa`. **This is the
  `SlotsRC` path** (see §5.4).
- `MSA.CreateUnclassifiedAffix(sense, pos)` → `IMoUnclassifiedAffixMsa`.
- `MSA.SetStemMsaPos(sense, pos)` / `MSA.SetDerivAffMsaPos(sense, from_pos=None,
  to_pos=None)` — update POS on an *existing* MSA of matching type; raise
  `FP_ParameterError` on type mismatch (no in-place type conversion).
- `MSA.ChangeAffixVariant(msa, target_kind)` — convert between `'infl'`,
  `'deriv'`, `'unclassified'`; creates a new MSA, copies transferable fields,
  repoints all senses' `MorphoSyntaxAnalysisRA`, removes the old MSA from
  `entry.MorphoSyntaxAnalysesOC` when unreferenced. Warns (logs) about fields
  that cannot transfer *only when populated*: `SlotsRC`, `InflFeatsOA`,
  `FromPartOfSpeechRA`, `From/ToInflectionClassRA`, `StratumRA`,
  `From/ToProdRestrictRC`. Note: `WfiMorphBundle.MsaRA` references are NOT
  updated by this method.
- Alternatively `Senses.SetPartOfSpeech(sense, pos, msa_kind="auto", ...)`
  picks stem-vs-affix MSA kind automatically based on the entry's morph type
  (`__EntryHasAffixMorphType`).

### 5.4 Writing `MSA.SlotsRC` (inflectional slots)

`SlotsRC` on `IMoInflAffMsa` is an **unordered reference collection (RC)** of
`IMoInflAffixSlot` objects. From `CreateInflAff` (`MSAOperations.py:182`):

```python
new_msa = MSA.CreateInflAff(sense, pos)          # or pass slots=[...]
for slot in slots:                               # IMoInflAffixSlot objects
    new_msa.SlotsRC.Add(resolved_slot)
```

- `CreateInflAff(sense, pos, slots=None)` already loops
  `new_msa.SlotsRC.Add(self.__Resolve(slot))` for each item in `slots` when
  provided, inside its own `_TransactionCM`.
- **RC ordering note (explicit in the source):** "Phase 2 ownership-ordering
  doesn't apply to reference collections" — the order you `Add` slots to an RC
  does **not** define a linguistic sequence. Slots being a *collection* not a
  *sequence*, membership is what matters. (The actual affix-template ordering of
  slots lives elsewhere, on the POS affix template, not on the MSA's `SlotsRC`.)
- HermitCrab caveat (docstring): if the language uses inflection classes and the
  target slot restricts them, populate `SlotsRC` here and separately configure
  each slot's `InflectionClassesRC`, or the parser rejects analyses.

---

## 6. `LexEntryRef` — `ComponentLexemesRS` and `PrimaryLexemesRS`

`LexEntryRef` objects live in `entry.EntryRefsOS` (owning sequence) and model
complex-form and variant relations. Wiring them is done in
`LexEntryOperations.AddComplexFormComponent` (`LexEntryOperations.py:2665`).

```python
from SIL.LCModel import ILexEntryRefFactory, LexEntryRefTags

# find-or-create the complex-form entry-ref
entry_ref = None
for ref in complex_entry.EntryRefsOS:
    if ref.RefType == LexEntryRefTags.krtComplexForm:
        entry_ref = ref; break

if entry_ref is None:
    factory = project.project.ServiceLocator.GetInstance(ILexEntryRefFactory)
    entry_ref = factory.Create()
    complex_entry.EntryRefsOS.Add(entry_ref)          # add to owning seq FIRST
    entry_ref.RefType = LexEntryRefTags.krtComplexForm
    entry_ref.HideMinorEntry = 0                      # 0 = show

# ComponentLexemesRS: ORDERED ref sequence of components (entries OR senses)
if not any(x.Hvo == component.Hvo for x in entry_ref.ComponentLexemesRS):
    entry_ref.ComponentLexemesRS.Add(component)

# PrimaryLexemesRS: ORDERED ref sequence; first component becomes primary
if entry_ref.PrimaryLexemesRS.Count == 0:
    entry_ref.PrimaryLexemesRS.Add(component)

# ShowComplexFormsInRS: visibility (published-in) sequence
if not any(x.Hvo == component.Hvo for x in entry_ref.ShowComplexFormsInRS):
    entry_ref.ShowComplexFormsInRS.Add(component)
```

Key points:
- **`RefType`** is set from `LexEntryRefTags`: `krtComplexForm` (complex
  forms/compounds/idioms) vs `krtVariant` (variants).
- **`ComponentLexemesRS` and `PrimaryLexemesRS` are RS (ordered reference
  sequences)** — order is preserved and meaningful (`GetComplexFormComponents`
  returns `list(entry_ref.ComponentLexemesRS)` "order preserved"). Targets may
  be **either `ILexEntry` or `ILexSense`**.
- Convention: the **first component added is also added to
  `PrimaryLexemesRS`** (the published/primary location).
- **De-dup before Add** — `.Add()` on RS/RC does not prevent duplicates; the
  code guards with `any(x.Hvo == component.Hvo ...)`.
- Remove mirrors add: `RemoveComplexFormComponent` removes the item from
  `ComponentLexemesRS`, `PrimaryLexemesRS`, and `ShowComplexFormsInRS`.
- `AddComplexFormComponent(complex_entry, component)` /
  `RemoveComplexFormComponent` / `GetComplexFormComponents` are the public
  wrappers — prefer them over hand-rolling the entry-ref.

---

## 7. Reference collections vs sequences — the `RC`/`RS`/`OC`/`OS`/`RA`/`OA` convention

LCM field-name suffixes tell you the relationship kind and how to write it:

| Suffix | Meaning | Multiplicity | Write API |
|---|---|---|---|
| `RA` | **R**eference **A**tom | single ref | assign: `obj.FooRA = target` (or `= None`) |
| `OA` | **O**wning **A**tom | single owned | assign a freshly-created object: `obj.FooOA = child` |
| `RC` | **R**eference **C**ollection | many refs, **unordered** | `obj.FooRC.Add(t)` / `.Remove(t)` / `.Count` |
| `RS` | **R**eference **S**equence | many refs, **ordered** | `obj.FooRS.Add(t)` (appends) / `.Remove(t)` |
| `OC` | **O**wning **C**ollection | many owned, unordered | `obj.FooOC.Add(child)` |
| `OS` | **O**wning **S**equence | many owned, ordered | `obj.FooOS.Add(child)` (appends) |

Examples used above: `sense.MorphoSyntaxAnalysisRA` (RA), `entry.LexemeFormOA`
(OA), `MSA.SlotsRC` (RC), `entry_ref.ComponentLexemesRS`/`PrimaryLexemesRS` (RS),
`entry.SensesOS`/`entry.EntryRefsOS`/`entry.AlternateFormsOS` (OS),
`entry.MorphoSyntaxAnalysesOC` (OC).

**Ownership vs reference matters for creation order:** an **owned** object
(`OA`/`OC`/`OS`) must be created by a factory and then attached to its owner
*before* you set its properties (the codebase does `entry.LexemeFormOA = form`
then `form.Form.set_String(...)`; `entry.SensesOS.Add(sense)` then set gloss).
A **reference** (`RA`/`RC`/`RS`) just points at an already-existing, already-
owned object — never create the target via the reference.

### `StratumRA` and semantic-domain refs

- **`StratumRA`** is a single reference atom (`RA`) to an `IMoStratum` living in
  `project.lp.MorphologicalDataOA.StrataOS` (obtain via `project.Stratum`:
  `GetAll/Find(name)/Create(name, abbreviation="")`). Set/clear it directly:
  `rule.StratumRA = stratum` or `rule.StratumRA = None`
  (`MorphRuleOperations.py:663/667`; also present on phonological rules and
  affix templates). Note it is one of the fields `ChangeAffixVariant` will drop
  if it can't carry it across an affix-variant conversion.
- **Semantic domains** attach to senses via wrappers, not raw RC writes:
  `Senses.AddSemanticDomain(sense, domain)` / `RemoveSemanticDomain` (backed by
  `sense.SemanticDomainsRC`). Resolve domains with
  `project.SemanticDomains.Find(number)` / `FindByName(name)`.
- **Lexical relations** (synonym/antonym/etc.) use `project.LexReferences`
  (`LexReferenceOperations`): `Create(ref_type_or_name, targets)` builds an
  `ILexReference` via `ILexReferenceFactory`, adds it to
  `ref_type.MembersOC.Add(new_ref)`, then adds each target to
  **`new_ref.TargetsRS`** (an ordered ref sequence; ≥2 targets, all the same
  class — all senses or all entries). Mapping types via `LexRefMappingTypes`
  (`SYMMETRIC=1`, `ASYMMETRIC=2`, `TREE=3`, `SEQUENCE=4`) →
  `CreateType(name, mapping_type, reverse_name=None)`.

---

## 8. GUIDs, ownership & object-creation-order gotchas (summary)

- **Never set GUIDs.** `Factory.Create()` auto-assigns them; `entry.GetGuid()` /
  `obj.Guid` reads them. Match/dedup logic keys off GUIDs (e.g.
  `str(rule.StratumRA.Guid)` in syncable-property maps).
- **Factory pattern:** `project.project.ServiceLocator.GetService(IXxxFactory)`
  (or `.GetInstance(...)`); for MSAs the factory must be looked up by
  `clr.GetClrType(IXxxFactory)`. `Factory.Create()` adds top-level objects
  (entries) to their repository automatically — no manual `Add()` for the entry
  itself, but **owned children must be `.Add()`ed / assigned to their owner**.
- **Attach-before-set:** always attach an owned child to its owner
  (`OA` assign or `OC/OS.Add`) *before* setting its string/reference fields.
  This is required repeatedly across the source and is the most common ordering
  bug to avoid.
- **MSA owner is the entry, not the sense** — resolve via
  `sense.OwnerOfClass(LexEntryTags.kClassId)`; then reference it from the sense
  with `sense.MorphoSyntaxAnalysisRA = msa`.
- **RS/RC `.Add()` does not dedupe** — guard with an `Hvo` membership check
  before adding component/primary lexemes or slots.
- **HVO vs object:** operations accept int HVO or live object; `project.Object`
  resolves HVO/GUID. Wrapper objects expose `._obj` (unwrapped lazily).
- **Persistence:** changes are cached until `CloseProject()`. Do all writes with
  `writeEnabled=True`; wrap multi-mutation sequences in `_TransactionCM` (or an
  outer `project.UndoableOperation`/`project.Transaction`), and do not rely on
  Phase-1 auto-rollback in this build.
- **Runtime dependency:** `flexicon` is a pythonnet shim over FieldWorks .NET
  assemblies — the write layer must run where FieldWorks/LibLCM is installed
  (32/64-bit Python must match FieldWorks). There is no pure-Python fallback.

---

## 9. Open items to confirm against the live docs / installed build

Because `flexicon.langtech.cloud` was blocked, verify these against the online
API reference (bundled locally as `flexicon.APIHelpFile` →
`docs/flexlibsAPI/flexlibs2.html`) or the installed build when available:

1. Exact public property names on the `FLExProject` facade
   (`project.Pronunciation` vs `Pronunciations`, `project.POS` vs
   `project.GramCat`) — inferred from docstrings, not asserted.
2. Whether an `IMoInflAffixSlot` create/find helper exists in pyflexicon or
   whether slots must be obtained from the target POS's affix-slot list before
   `SlotsRC.Add` (source only shows adding pre-existing slot objects).
3. `InflectionClassesRC` configuration API for slots (referenced in docstrings,
   no wrapper method seen in the Lexicon module).
4. Any 4.1-specific additions beyond 4.1.1 (only 4.1.0/4.1.1 are published as of
   this writing — 2026-07-06).
