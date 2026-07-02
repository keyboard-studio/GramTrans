# Transfer FLEx Grammar Module Design

# Problem statement:

When users work on a toy project either when testing FLExTrans or when getting parsing working, there’s no easy way to get all the grammar pieces from the toy project to the main project that will be used for production.

# Existing solution:

A user can export phonology grammar data from one project and import it to another project. That gets us part of the way there. I believe this takes care of the following items:

1. Phonemes  
2. Phonological Features  
3. Natural Classes  
4. Phonological Rules  
5. APRs?  
6. Environments? (phon rules and/or allomorphs) Same list?

# Big idea:

It would be nice to have a module that would transfer important grammar data from a toy project to another project. It would be great if it was interactive so the user could choose to only transfer some information.

Things we might want to transfer:

1. Check Writing Systems  
2. Gram Categories (Keep GOLD)  
3. Inflection Features\* (Keep GOLD)  
4. Custom Fields (especially the link custom field use for FLExTrans)  
5. Inflection Classes  
6. Stem Names  
7. Exception Features  
8. Variant Types (and associated inflection features)  
9. Complex Form Types  
10. Ad Hoc Rules  
11. Compound Rules  
12. Affixes\* (includes APRs and Allomorphs)  
13. Slots  
14. Templates\*  
    1. Add affixes to slots
15. Stems? 

Choosing to transfer some of the things above will automatically mean including other things. E.g. transferring templates might mean we transfer the affixes in that template. Transferring affixes might mean including all the features and classes associated.

It would be nice if FLEx itself would support this, but in the meantime we probably need to write our own module.

Flavor  
Flexlibs1 with C\# Fallback

## Main Window

1. Choose which of the grammar pieces to transfer  
2. Some choices will automatically select others  
   1. Perhaps this automatic selection could be deselected to get a more bare bones version  
3. Statistics, perhaps in the FlexTools window, about what was transferred  
4. Overwrite option?

## Selection UI Design (Phase 3c, revised 2026-07-01)

This section supersedes the loose "Main Window" bullets above for the Phase 3c
selection experience. ASCII only; no emoji. Constitution alignment notes inline
(Principles I / III / V — see .specify/memory/constitution.md).

### (0) BUILD DECISION 2026-07-01 -- wizard supersedes single-window

The item-anchor concept in (a) below is RETAINED, but the delivery vehicle is now
a 5-page QWizard, NOT the single side-by-side window. The single-window base
(commit 88f2925) is verified GREEN (422 passed / 22 skipped / 0 failed, all
constitution gates PASS) and its widgets are re-hosted verbatim into wizard pages.
The wizard REPLACES `main_window`. All item-anchor semantics (two mental models,
three-scope selector, four dispositions, warning gate) carry over unchanged; the
wizard only re-sequences their presentation and adds project-level Writing System
handling on page 1 and per-item conflict-mode gating.

#### 5-page wizard structure

  Page 1 -- Project + Writing Systems.
     Bind source + target projects (early target-bind, locked constraint). Enumerate
     and choose ACTIVE writing systems ONLY (analysis + vernacular currently active
     in the project; not the full installed inventory). This is now a PROJECT-LEVEL
     decision made once, up front. It RETIRES the old two-stage
     NEEDS_WS_MAPPING handshake (WS is no longer negotiated per-category mid-flow).

  Page 2 -- Item picker. The affix / stem / affix-template tree (Model A anchor).
     Stems tab is STUBBED / DISABLED for this build (Layer-3 stems land later).

  Page 3 -- Schema scope + conflict mode. Per-category three-scope selector
     (NONE / AS-NEEDED / ALL) from (c), plus per-item dependency deselection, plus
     the per-category CONFLICT MODE selector (ADD_NEW / MERGE / OVERWRITE) gated by
     the model in section (h).

  Page 4 -- Preview. StatsPanel output: dispositions (ADD / LINK / SKIP /
     EXCLUDED-LOSSY), closure disclosure, warning channel (entry-centric).

  Page 5 -- Finish (= Move). The single write point. The Finish button IS the
     confirm-on-Move gate: if `plan.excluded_lossy_count() > 0` the Finish handler
     MUST block and pop the summary dialog ("N entries will transfer with missing
     references. Proceed?") before writing. Confirm -> write; cancel -> stay.

#### Writing System rules (page-1 project-level, revised 2026-07-01)

- Enumerate ACTIVE writing systems only (not the installed superset).
- WS choice is made ONCE on page 1, project-level. The two-stage per-category
  NEEDS_WS_MAPPING handshake is RETIRED. Blast radius is low: only
  `tests/unit/test_api_surface.py` asserts on the handshake shape (2 assertions,
  rewritten); the other five `compute_preview` callers ride through unchanged.
- EMPTY-WS PRUNE AT MOVE: a multistring/multiunicode alternative that carries no
  content for a chosen WS is pruned at Move time. Content detection reuses the
  strings `GetSyncableProperties` ALREADY extracted -- no ITsMultiString cast, no
  extra LCM call.

#### Corrected WS-page spec (P0 defect 2, 2026-07-01)

The bare QListWidget on page 1 is REPLACED by a three-way MAP / CREATE / SKIP
control, split into two groups: Vernacular WS and Analysis WS (by WSKind).

- A dual-role WS (active in both vernacular and analysis) appears in BOTH groups.
- Vernacular is lead: when a vernacular row choice is set, the same-tag analysis
  row DEFAULTS to the vernacular choice and is independently overridable
  (linked-until-touched; link breaks on the first independent analysis change).
- Dual-role CREATE: both vernacular and analysis roles point at the SAME target
  WS ID (no double-create). WSMapping 1:1 invariant is satisfied because both
  entries share the same source_ws_id.
- The resulting WSMapping is THREADED into BOTH gt_api.compute_preview AND
  gt_api.execute_move (via the plan, which carries ws_mapping from compute_preview).

#### Idempotency-guard contract (P0 defect 1, 2026-07-01)

LCM factory.Create(existingGuid, owner) does NOT throw; it SILENTLY creates a
duplicate object permanently written to .fwdata on CloseProject. This is the
corruption root cause. There is NO TryGetObject in LCM 9.x.

Preferred existence check at every GUID-taking Create site:

    try:
        existing = target.Object(src_guid)
    except Exception:
        existing = None

FLExProject.Object(str_guid) calls ServiceLocator.GetObject and throws when
absent, so the except branch represents "not found".

Rules at every Guid-preserving Create site (BEFORE factory.Create):
1. If existing is None -> proceed with Create (normal path).
2. If existing is not None AND existing.ClassName == expected -> typed-cast
   and RETURN it; skip Create entirely (idempotency reuse).
3. If existing is not None AND existing.ClassName != expected -> log WARNING
   and return None; skip Create (wrong-class object, do not reuse).

Cast paths:
- PartOfSpeech      -> IPartOfSpeech(existing)        [direct; not in cast_to_concrete]
- MoInflAffixSlot   -> IMoInflAffixSlot(existing)     [direct; not in cast_to_concrete]
- PhEnvironment     -> IPhEnvironment(existing)       [direct; not in cast_to_concrete]
- MoInflAffixTemplate -> IMoInflAffixTemplate(existing)
- LexEntry          -> ILexEntry(existing)
- LexSense          -> ILexSense(existing)

Seven Guid-preserving Create sites guarded:
  _create_pos_with_guid          (transfer.py) -- expected PartOfSpeech
  _create_template_with_guid     (transfer.py) -- expected MoInflAffixTemplate
  _create_slot_with_guid         (transfer.py) -- expected MoInflAffixSlot
  _create_environment_with_guid  (transfer.py) -- expected PhEnvironment
  _create_lexentry_with_guid     (transfer.py) -- expected LexEntry
  _create_lexsense_with_guid     (transfer.py) -- expected LexSense
  (no seventh: MSA and allomorph EXCLUDED because they remap and take no Guid overload)

EXCLUDED from guard (intentional):
- _create_inflaff_msa_with_guid:  LCM IMoInflAffMsaFactory has no Guid overload;
  MSA GUIDs cannot be preserved. GUID is remapped via identity_remap.
- _create_allomorph_with_guid:    same; allomorph factories have no Guid overload.

Move non-repeatability: after a successful execute_move, the wizard's
_PagePreview._cached_plan is set to None. A subsequent double-click or re-entry
on page 5 finds no plan and aborts before calling execute_move, preventing a
second run that would trigger the guard on every object (harmless but wasteful)
and could corrupt state in edge cases where the guard lookup fails.

### (a) Item-anchor single-window layout

The window is anchored on LEXICAL ITEMS, not on the schema. The user picks the
things they actually care about -- affixes, stems, affix templates -- and the
grammatical SCHEMA those items depend on (parts of speech, inflection features,
inflection classes, natural classes, stem names, exception features, environments)
is resolved for them. NOTE (2026-07-01): the "one window, not a wizard" statement
below is HISTORICAL -- see (0); the item-anchor semantics survive intact but are
now presented across 5 wizard pages. The item picker (affix / stem / template
tree) and the schema-category scope controls are re-hosted onto pages 2 and 3
respectively. The dependency closure that the picked items require is NOT shown at
pick time; it is disclosed only in the Preview output (StatsPanel, page 4),
keeping the pick surface small.

Constitution III: nothing here writes. The wizard only builds a Selection; the
only write is at Finish/Move.

### (b) Two mental models

The selection model must serve BOTH of these, simultaneously, in one window:

- Model A (default, item-driven): "I picked these affixes/stems/templates; give
  me exactly the schema they need." Schema dependencies auto-preselect to the
  AS-NEEDED scope (see (c)) for each schema category the picked items reach.

- Model B (override, schema-driven): when the user turns attention to a schema
  category they may want to override the auto-preselection in two ways:
    (b.1) NOT copy a specific dependency, accepting that a copied entry will lose
          that link in the target (a deliberate, lossy waiver); and/or
    (b.2) copy the ENTIRE source category, including items nothing the user picked
          references (e.g. "bring ALL inflection features, even unused ones").

Model A and Model B are not modes to switch between; Model B is expressed by
adjusting the same per-category controls that Model A pre-populated.

### (c) Per-category three-scope selector + per-item exclusion

Each schema category is NOT a checkbox. It is a THREE-SCOPE selector:

- NONE       : do not transfer this category at all -- not even what the picked
               items' closure needs. (Strongest bare-bones; may produce lossy
               entries -- see the warning gate in (e).)
- AS-NEEDED  : (default) transfer exactly the closure the picked items require,
               and nothing else. This is Model A.
- ALL        : transfer the entire source category, including items no picked
               item references. This is Model B.2.

Within AS-NEEDED, the user may additionally DESELECT individual dependency items
(Model B.1) -- a per-item exclusion set layered on top of the computed closure.
This per-item deselect is exactly the "bare-bones, per-item" affordance the
constitution mandates (Principle V, lines 248-249: "The dependency closure MUST
be displayed in Preview Mode and MUST be deselectable on a per-item basis to
allow a 'bare-bones' transfer").

### (d) The four plan dispositions

Every dependency the closure touches resolves, against the early-bound + probed
target, to exactly one of four dispositions:

- ADD            : dependency absent from target -> create it (copy).
- LINK           : dependency already present in target by GUID (includes GOLD /
                   already-present items). Rendered READ-ONLY, "link, not copy":
                   the copied entry will reference the existing target object.
                   Silent / informational.
- SKIP           : dependency intentionally not transferred, and no copied entry
                   needs it -> harmless omission.
- EXCLUDED-LOSSY : NEW. The user deliberately dropped a dependency (via NONE scope
                   or per-item deselect) that a copied entry DOES reference, and
                   the target does not already have it. The entry transfers with a
                   null reference. This is distinct from DEPENDENCY_UNRESOLVED,
                   which is the ACCIDENTAL version of the same missing-reference
                   symptom and fails hard. EXCLUDED-LOSSY has the opposite intent
                   (deliberate) and opposite severity (warn+allow, never hard block).

### (e) Target-aware warning gate + confirm-on-Move

A soft gate for deliberate omissions. It NEVER hard-blocks. For each dependency the
user chose to drop, exactly one of three outcomes applies -- only the third warns:

  1. dropped dep EXISTS in target (by GUID) -> the copied entry links to it -> fine.
     This is just LINK (silent / info). No warning.
  2. dropped dep ABSENT from target AND nothing copied references it -> harmless.
     Silent.
  3. dropped dep ABSENT from target AND a copied entry references it -> WARN, ALLOW.
     Disposition EXCLUDED-LOSSY.

The warning is ENTRY-CENTRIC, not dep-centric. It names the affected payload item
and what it loses, e.g.:

    Entry '-PL' will have no Part of Speech.

not the abstract dependency ("POS 'Verb' not transferred"). One warning per
affected (entry, lost-reference) pair.

Because the target is bound and probed EARLY (locked constraint), the "exists in
target?" check in outcome 1 always has live target data at Preview time.

Gate mechanics:
- Warnings surface in the Preview output (StatsPanel) as a DISTINCT SEVERITY --
  not an error, not an ordinary skip.
- Move is the confirmation gate. If any warnings are outstanding, Move pops a
  summary dialog ("N entries will transfer with missing references. Proceed?")
  BEFORE writing. Confirm -> write; cancel -> return to selection. This preserves
  "the only write is at Move/Finish."

Constitution V is POSITIVE here: the gate is what makes the per-item closure
waiver INFORMED. Principle V requires the waiver be possible and requires that
items whose dependencies cannot be satisfied be REPORTED, not silently transferred
broken (lines 248-251). The entry-centric warning is that report; EXCLUDED-LOSSY
is the deliberate, reported counterpart to the hard-failing DEPENDENCY_UNRESOLVED.

### (f) Selection-model extension + preview.py per-scope branch

Data-model change (src/gramtrans/Lib/models.py, Selection ~line 140):
- REPLACE/AUGMENT the single global `include_closure: bool` with a per-category
  scope map, e.g. `category_scopes: dict[GrammarCategory, CategoryScope]` where
  `CategoryScope` is an enum {NONE, AS_NEEDED, ALL}. The current global
  include_closure=True corresponds to "every schema category AS_NEEDED"; the
  explicit category toggle that today enumerates a whole category corresponds to
  ALL. These two were conflated under one bool and are now separated.
- ADD a per-item exclusion set, e.g. `excluded_deps: frozenset[str]` (source GUIDs
  the user deselected inside AS-NEEDED).
- Preserve backward-compat construction so existing tests that pass
  include_closure keep working (map bool -> uniform scope) until migrated.

preview.py change: the closure branches at ~322, ~394, ~470, ~480 currently read
one flag `closure_on = selection.include_closure` and gate everything on it. Each
must become PER-CATEGORY-SCOPE-AWARE:
- NONE      -> do not pull the category in for closure; a referencing entry whose
              dep lands here becomes EXCLUDED-LOSSY (if target lacks it) rather
              than pulled-in.
- AS_NEEDED -> current closure behaviour, minus any GUID in `excluded_deps`
              (excluded ones follow the EXCLUDED-LOSSY / warning path).
- ALL       -> enumerate the whole source category regardless of what the picked
              items reference.

### (g) StatsPanel severity additions

StatsPanel (src/gramtrans/Lib/ui/stats_panel.py) today has a per-category table
(Added / Skipped / Pulled-in-by-closure) plus one flat Skip list. Additions:
- A distinct WARNING severity channel for EXCLUDED-LOSSY, rendered separately from
  errors and from ordinary skips (e.g. a "Warnings (entries with missing
  references)" list, entry-centric text per (e)).
- Optionally a per-category "Excluded-lossy" count column alongside Added/Skipped.
The confirm-on-Move summary dialog reads its N from this warning channel.

### (h) Conflict-mode model (per-category default + per-item IsProtected refinement)

When a source item would land on a target that already has (or could have) a
matching object, the user picks a CONFLICT MODE per category on wizard page 3.
This is orthogonal to the three-scope selector in (c): scope decides WHAT is in
the closure; conflict mode decides WHAT HAPPENS when a closure item meets the
target.

Enum `ConflictMode` {ADD_NEW, MERGE, OVERWRITE}.

The gate has TWO layers:

Layer 1 -- CATEGORY-KIND DEFAULT (structural possibility). Each GrammarCategory is
classified into one of three kinds; the kind decides which modes are structurally
offered, hidden, or forbidden:

  MULTI_INSTANCE -- category legally holds many peer instances. Offers all three
    (ADD_NEW, MERGE, OVERWRITE). Members: AFFIXES, STEMS, SLOTS, AFFIX_TEMPLATES,
    INFLECTION_CLASSES, STEM_NAMES, EXCEPTION_FEATURES, ADHOC_COMPOUND_RULES,
    PHONEMES, NATURAL_CLASSES, PHONOLOGICAL_RULES, PH_ENVIRONMENT.

  SINGLETON_NONDELETABLE -- category is a fixed singleton / non-deletable holder.
    ADD_NEW hidden; MERGE + OVERWRITE offered. Members: WRITING_SYSTEMS_CHECK,
    STRATA (see note), and CUSTOM_FIELDS (see conservative default).
    NOTE STRATA: `StrataOS` is an Owning SEQUENCE on `IMoMorphData` -> multiple
    strata are model-legal, so STRATA is reclassified to MULTI_INSTANCE-capable
    and offers all three modes. The live "usually one stratum" count is a display
    nicety, not a gate.
    CUSTOM_FIELDS conservative default: probe 4 (can LCM mutate a custom-field
    definition after creation?) is UNRESOLVED. Until a live write probe confirms
    mutability, CUSTOM_FIELDS is ADD hidden, OVERWRITE FORBIDDEN, MERGE offered as
    a no-op-if-identical. Safe either way; relax later if the probe confirms.

  GOLD_RESERVED -- category is (or may be) seeded with protected reference data.
    ADD_NEW hidden, OVERWRITE forbidden, MERGE/link-only offered. Category-default
    members: GRAM_CATEGORIES, INFLECTION_FEATURES, VARIANT_TYPES,
    COMPLEX_FORM_TYPES, POS, PHONOLOGICAL_FEATURES, SEMANTIC_DOMAINS.

Layer 2 -- PER-ITEM IsProtected REFINEMENT (data-driven downgrade). The category
default sets what is STRUCTURALLY possible; the specific bound target item then
refines it. `IsProtected` is defined on `ICmPossibility` and readable (with a
pythonnet cast) on the concrete types that matter: `ILexEntryType` (variant +
complex-form types), `IPartOfSpeech`, `ICmSemanticDomain`, `IMoMorphType`,
`ILexEntryInflType`, `ILexRefType`. FLEx sets `IsProtected=True` on factory-seeded
items. Rule at plan time, against the early-bound target:

  item.IsProtected == True  -> GOLD-reserved for THIS item: Add hidden, Overwrite
                               forbidden, Merge/link-only -- regardless of the
                               category default.
  item.IsProtected == False -> user-added item: all three modes eligible (still
                               capped by the category-kind default above).

This makes categories like VARIANT_TYPES / COMPLEX_FORM_TYPES / POS self-correcting:
built-in protected members lock to Merge/link, user-added members offer the full
set -- no blanket per-category lock needed. The read MUST be cast-safe (guard the
pythonnet cast; treat a failed cast / absent attribute as IsProtected=False =
user-added, i.e. the permissive default only when the protection cannot be proven).

Data-model encoding: a `category_conflict_modes: dict[GrammarCategory, ConflictMode]`
on Selection (default per category per Layer 1), plus a plan-time refinement pass
that downgrades any individual protected item to Merge/link-only per Layer 2.

### (i) Interim MERGE behavior (Option b -- link-if-present-by-GUID else ADD)

For this build, MERGE is DELIBERATELY SHALLOW and must be labeled as such in the
UI. Semantics:

- If a matching target object exists by GUID -> LINK to it (the copied entry
  references the existing target object). NO field-level update is performed.
- If no match by GUID -> ADD (create the object as a new copy).

There is NO field-by-field merge, NO conflict resolution of differing attribute
values in this build. The mode is effectively "link-if-present-by-GUID, else add."
The page-3 MERGE control MUST carry an explicit label to this effect (e.g.
"Merge (link existing by ID, else add; no field update)") so the user is not
misled into expecting attribute reconciliation. Full field-level merge is a
later phase.

## Affixes

1. Should include all allomorphs in the affix entry  
2. Should include APRs if not handled in FLEx’s export/import  
3. Should included all referenced items:  
   1. Inflection Features  
   2. Inflection Classes  
   3. Stem Names  
   4. Exception Features  
4. The user should be able choose which affixes to transfer

## Merging

### Phase 0 \- New

* Add new things even if duplicate  
* Tag new entries in Import Residue  
* No UI, just add everything  
* Update default vernacular (mapping)

### Phase 1 \- Overwrite

Overwrite intelligently?

- Try Guid  
- Fall back to fingerprint  
- UI Main Window to ask which pieces to transfer  
- Leave non-conflicting items  
- Dedup Custom Fields

### Phase 2 \- Proper Merging

* User prompted,   
* Accept merge, left, right, skip, other  
* Map the vernaculars (like SFM import)  
* Undoable

Architecture

* From Flextools,   
  * PyQT interface  
  * Preview Mode and Move Mode  
  * Overwrite in V1, Merge in V2 


### Phase 3

Copying Stems
Filtering:
  "interesting" stems containing Items 1-14
  Date range (by date or since branching)
  Filtered Chooser