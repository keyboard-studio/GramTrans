# Phase 1 Data Model: Merge-Preview Diff Engine (012)

All types live in `src/gramtrans/Lib/merge_preview.py`. They are pure value types — frozen
dataclasses and enums — with **no Qt import** and **no retained LCM handle**. Reused types
(`WsRole`, `WsFont`, `WsFontRegistry`) come from `Lib/ws_fonts.py` unchanged.

## Enum — `SegmentKind`

The kind tag on a run of diff text.

| Value | Meaning | Render (US2) |
|-------|---------|--------------|
| `added` | present/winning on the source | green |
| `unchanged` | equal, or target-preserved | default color |
| `removed` | target value being replaced | red + strike-through |
| `note` | explanatory annotation (not a value) | gray italic |

> May be modeled as a `str`-valued `Enum` or a `Literal`/constant set; the contract only
> requires the four names. `kind in {added, unchanged, removed, note}` (FR-001).

## Type — `DiffSegment(text, kind, ws_role=None)` (FR-001)

The atom of the diff: one run of text with a kind and optional writing-system role.

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `text` | `str` | — | Raw (unescaped) text; `to_html` escapes it. |
| `kind` | `SegmentKind` | — | One of added/unchanged/removed/note. |
| `ws_role` | `Optional[WsRole]` | `None` | `None` = chrome / default font (spec Edge Cases). |

Frozen dataclass. **`rtl` is NOT a field** (decision, lex-simplify cycle 1): script direction
is resolved at render time in `to_html` from the `WsFontRegistry` (`WsFont.rtl`). Storing it
would force `diff_props` to take a registry just to set one bool, breaking its purity against
plain dicts. `diff_props` never touches a registry.

## Type — `FieldDiff(field_name, segments, indent=0)` (FR-001)

One field's ordered segments plus a nesting depth for indentation.

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `field_name` | `str` | — | The property key (e.g. `"CitationForm"`). Rendered bold. |
| `segments` | `Tuple[DiffSegment, ...]` | — | Ordered; for multistrings, ws-labeled runs interleave. |
| `indent` | `int` | `0` | Nesting depth (e.g. per-ws rows under a multistring field). |

Frozen dataclass.

## Type — `MergePreview(status, fields, notes=())` (FR-001)

The full computed diff for one item.

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `status` | `str` | — | An **opaque pass-through** supplied by the caller (014) — the row-status vocabulary defined in feature 011 (`Lib/models.py`, e.g. the `"similar"` family). This module does not enumerate or validate it; it stores and renders whatever the caller passes to `preview_for(..., status, ...)`. It is part of the cached **value**, never the cache **key**. |
| `fields` | `Tuple[FieldDiff, ...]` | — | **Alphabetical by `field_name`** (FR-006, SC-003). |
| `notes` | `Tuple[str, ...]` | `()` | Free-text notes (e.g. props-fetch-failed, LINK-ONLY skip). |

Frozen dataclass.

## Conflict modes (constants) (FR-002 – FR-004a)

`NEW`, `LINK_ONLY`, `OVERWRITE`, `MERGE_KEEP` — string constants (or an enum) consumed by
`diff_props(..., mode, ...)`. Mapping to 011 `SimilarResolution.action` and per-mode
semantics are specified in [research.md](research.md) R2. Value-shape dispatch rules
(multistring / str / list-tuple-set / scalar / other) per FR-005.

## Category props table (module-level)

Per-transfer-category mapping used by `props_for`:

| Column | Meaning |
|--------|---------|
| category key | `GrammarCategory.value`-style key (e.g. `"pos"`, `"entry"`, `"slot"`). |
| ops accessor | attribute on the flexlibs2 project handle (e.g. `"POS"`, `"LexEntry"`). |
| finder | linear GUID lookup (mirrors `conflict._find_target_*_by_guid`). |
| needs_owner | whether the wrapper requires an owner GUID (templates/slots). |
| fallback | direct-read flag for the fork-gap categories (Slots, Phon Features, Stem Names). |

Membership per [research.md](research.md) R4 (CORRECTED): **4 fully covered** (POS, LexEntry,
Senses, Allomorphs — existing finders), **8 finder-needed** (Phonemes, NaturalClasses,
Environments, PhonRules, Strata, GramCat, InflectionFeatures, MorphRules/templates — net-new
`_find_target_<cat>_by_guid` finders required; templates use the two-level owner-POS finder of
R4a), **3 gaps** (Slots, Phonological Features, Stem Names — direct-read fallback). Only 4 of
the finders exist today; the props table MUST NOT imply the other 8 do. Direct fallback returns
the `{field: {ws_id: text}}` shape for Name/Abbreviation/Description (+ optional slot bool
`IMoAffixSlot.Optional`), or `None` + a note on hard failure (FR-008, SC-005).

### Enumerated rows (concrete starting point for T022)

Category keys mirror the `GrammarCategory.value` / `conflict._OW_OPS` style. **Accessor names
marked "confirm" MUST be verified against `categories.py` / the flexlibs2 Operations class
before wiring** — they are the module's best-known guess, not confirmed API (this is the
open work T022/T023 must close, not silently invent):

| category key | tier | ops accessor | finder | needs_owner | fallback |
|--------------|------|--------------|--------|-------------|----------|
| `pos` | covered | `POS` | `_find_target_pos_by_guid` (exists) | no | no |
| `entry` | covered | `LexEntry` | `_find_target_entry_by_guid` (exists) | no | no |
| `sense` | covered | `Senses` | `_find_target_sense_by_guid` (exists) | owner=entry | no |
| `allomorph` | covered | `Allomorphs` | `_find_target_allo_by_guid` (exists) | owner=entry | no |
| `phoneme` | finder-needed | `Phonemes` | `_find_target_phoneme_by_guid` (T023) | no | no |
| `natural_class` | finder-needed | `NaturalClasses` | `_find_target_natural_class_by_guid` (T023) | no | no |
| `environment` | finder-needed | `Environments` *(confirm)* | `_find_target_environment_by_guid` (T023) | no | no |
| `phon_rule` | finder-needed | `PhonRules` *(confirm)* | `_find_target_phon_rule_by_guid` (T023) | no | no |
| `stratum` | finder-needed | `Strata` *(confirm)* | `_find_target_stratum_by_guid` (T023) | no | no |
| `gram_cat` | finder-needed | `GramCat` *(confirm; IFsFeatStrucType)* | `_find_target_gram_cat_by_guid` (T023) | no | no |
| `inflection_feature` | finder-needed | `InflectionFeatures` (→ IMoInflClass) | `_find_target_inflection_feature_by_guid` (T023) | no | no |
| `template` | finder-needed | `POS.AffixTemplatesOS` (via owner POS) | `_find_target_template_by_guid` (T024) | **owner=POS** | no |
| `slot` | gap | *(none — direct read)* | *(n/a)* | owner=template/POS | **yes** |
| `phon_feature` | gap | *(none — `PhonFeatureOperations` has no GetSyncableProperties)* | *(n/a)* | no | **yes** |
| `stem_name` | gap | *(none — direct read)* | *(n/a)* | no | **yes** |

## Type — `MergePreviewService` (FR-011, FR-012)

Qt-free cache/orchestrator.

| Member | Type | Notes |
|--------|------|-------|
| source / target handles | flexlibs2 project handles | Held for the wizard life; re-fetch by GUID on first click. |
| `ws_role_of` | `Callable[[str], Optional[WsRole]]` or `{ws_id: WsRole}` | From `ws_role_map`. |
| target GUID index | `dict[str, ...]` | **Lazy**; built once per service (linear `GetAll()` scan). |
| props cache | `dict[key, dict]` | Caches property **dicts**, never LCM objects (FR-012). |
| preview cache | `dict[(category, source_guid, target_guid, mode), MergePreview]` | Memoized (FR-011). |

Methods:
- `preview_for(category, source_guid, target_guid, status, mode, owner_guid="")` — compute
  lazily, memoize on the **4-tuple `(category, source_guid, target_guid, mode)`**; re-link
  (different `target_guid`) and resolution change (different `mode`) are each a distinct key.
  A 3-tuple key would return a stale diff on an in-page resolution flip (no `invalidate()`
  fires) — see FR-011 rationale.
- `invalidate()` — clear the cache for wizard page re-entry.

## Relationships & invariants

- `MergePreview.fields` is **always** sorted alphabetically by `field_name` (SC-003).
- A `DiffSegment` with `ws_role is None` renders as chrome in the default font.
- The service caches **dicts only**; no `DiffSegment`/`FieldDiff`/`MergePreview` holds an LCM
  handle (constitution I, FR-012).
- Target-only keys are emitted `unchanged` (never implies deletion — spec Edge Cases).
- Keys absent on both sides are not emitted.
- **Upstream (011):** `status` and the `overwrite`/`merge`/`create_new` action vocabulary are
  provided by `Lib/models.py` `SimilarResolution`.
