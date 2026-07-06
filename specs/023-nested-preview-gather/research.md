# Phase 0 Research: Nested Preview Field Gathering

## R1 — Where the gather happens and how it flows to the diff

**Decision**: Extend the existing entry-category path inside `merge_preview.py`
(`props_for` → `_gather_props`/`_append_custom_fields`) to emit child standard fields into the
same flat `{field: value}` dict. Do **not** restructure the service flow.

**Rationale**: `MergePreviewService.preview_for` fetches source and target props **independently and
per-side** (`_fetch_props("source"…)`, `_fetch_props("target"…)`, each cached separately), then
calls `diff_props(src, tgt, mode)` which matches purely by dict key. Any design that requires the
source gather to "see" the target (or vice versa) breaks this cache model and the Qt-free purity of
`diff_props`. Emitting child fields as extra keys keeps the whole pipeline intact.

**Alternatives considered**:
- *Combined source+target gather for entries* (fetch both, pair in one pass): rejected — breaks the
  per-side props cache, complicates the 4-tuple memo, and couples gather to the diff.
- *A parallel nested `EntryPreview` object bypassing `diff_props`*: rejected — would duplicate the
  entire NEW/LINK/OVERWRITE/MERGE_KEEP taxonomy already implemented and tested in `diff_props`.

## R2 — Child pairing: fingerprint-derived join keys (the crux)

**Decision**: Each child field's dict key encodes a **content-derived child join token** so that a
source child and its target counterpart land on the **same key** when they correspond. `diff_props`
then produces per-field status automatically:
- matched child → shared key → equal/different per field (IN TARGET / SIMILAR);
- source-only child → key absent from target → ADDED (NEW);
- target-only child → key absent from source → target-only unchanged.

Join tokens per class (content-derived, cross-project stable):
- **Allomorph**: `(lexeme_form_text, morph_type_identifier)` — mirrors `fingerprint_for_allomorph`'s
  discriminating content (`matcher.py:151`), dropping the cross-project-unstable `owner_entry_guid`.
  Morph-type identifier uses the global FW morph-type list (standard types share GUIDs across
  projects; where a GUID is unavailable, fall back to the morph-type name).
- **Sense**: `(gloss_text)` in the analysis WS, disambiguated by first-unused ordinal on collision.
- **MSA / grammatical info**: the FLEx-style label token (POS abbrev + slot names, e.g. `n:NC`);
  this is the same content `_msa_fingerprint` (`preview.py:1126`) keys on, minus the raw `pos_guid`
  (unstable across projects).

**Rationale**: The Move matchers (`_match_allomorphs_by_fingerprint`, `_match_msas_by_fingerprint`)
key on fingerprints that include `owner_entry_guid` / `pos_guid`. Move can rely on those because it
normalizes owner GUID across sides and transfers POS GUID-first, so the GUIDs agree by the time
matching runs. A **fresh preview against a pre-existing target cannot assume GUID agreement**, so the
preview must pair on the *content* the fingerprints actually discriminate on (form text, gloss,
label). In the common case this yields the **same pairing Move computes** (SC-006). Documented
divergence: if a target POS/allomorph differs only by a field not in the token (e.g. two allomorphs
with identical form + morph type but different environments), pairing falls back to first-unused-wins
in source order (spec Edge Case "ambiguous fingerprint") — deterministic and stable.

**Shared code**: factor the content-token derivation into a small helper reachable from
`merge_preview.py` **without** importing Qt or Move-execution code. Options: (a) a new tiny
`Lib/fingerprints.py` holding the content tokens, imported by both `preview.py` and
`merge_preview.py`; (b) import the existing `matcher.py` tokens and strip the GUID components in
`merge_preview.py`. **Chosen: (a)** — a single documented source of the *content* discriminators,
which both the Move matchers and the preview reference, minimizing preview/Move drift (the exact risk
this feature exists to prevent). `matcher.py`/`preview.py` fingerprints then compose the content
token with their GUID components.

**Alternatives considered**:
- *Reuse Move fingerprints verbatim as the join key*: rejected — their `owner_entry_guid`/`pos_guid`
  differ across the source/target projects, so matched children would never share a key.
- *Pair by child GUID*: rejected — explicitly ruled out in clarification (child GUIDs are not stable
  across the project pair).

## R3 — Ordering & display: `FieldDiff` extension

**Decision**: Add two optional fields to `FieldDiff`: `display_name: str` (human label, e.g.
"Allomorph 1 ▸ Comment") and `sort_key: tuple` (group-order, field-order). `diff_props` sorts by
`sort_key` when present and falls back to the current alphabetical `field_name` sort otherwise, so
all existing scalar categories are byte-for-byte unchanged. The machine dict **key** carries the
join token (fingerprint-based, stable across sides); `display_name` carries the ordinal label
assigned from **source order** at gather time; unmatched target-only children are appended after
matched ones in target order.

**Rationale**: The join key must be side-stable (fingerprint) but the visible label must be
source-ordered and readable — these are two different strings, so the model must carry both.
`FieldDiff` already has `indent`, so nesting depth is free; only label + ordering are missing.

**Alternatives considered**:
- *Encode ordinal + label into `field_name` and keep alpha sort*: rejected — collapses true source
  order (alpha ≠ source order) and leaks the join token into the visible label.
- *Global switch of `diff_props` to insertion order*: rejected — regresses feature 012 SC-003
  (scalar categories are specified to render alphabetically).

## R4 — MultiString custom-field read crash (silent drop)

**Decision**: In `_read_custom_fields`, wrap the `CustomFieldOperations.GetValue` call so that on the
known flexicon failure (`AttributeError: 'ITsMultiString' object has no attribute
'BestAnalysisVernacularAlternative'`) it falls back to a **direct multi-string read** across the
project's writing systems, returning a `{ws_id: text}` dict (the same shape standard multi-string
fields use). If the fallback also fails, emit a visible **read-failure note** for that field rather
than dropping it silently.

**Rationale**: Verified live against `Ejagham Full GT-Test`: `GetValue` on a MultiString custom field
(`Plural`, flid 5002502) raises inside `FLExProject.GetCustomFieldValue` at
`ITsString(mua.BestAnalysisVernacularAlternative)` — `mua` is an `ITsMultiString`, whose correct
accessor is `IMultiAccessorBase(mua).BestAnalysisVernacularAlternative`. Today `_read_custom_fields`
catches this per-field and drops it → violates Principle I ("no silent drops"). The direct read
(`sda.get_MultiStringAlt` / the flexicon multi-string accessor per WS) recovers the value.

**Alternatives considered**:
- *Patch flexicon*: out of scope — flexicon is an external dependency (spec Dependencies). Contain
  in our code.
- *Skip MultiString CFs entirely with a note*: rejected — the value is recoverable; showing it
  satisfies SC-004 fully.

## R5 — Which standard child fields to gather (scope of FR-001…FR-004)

**Decision**: Gather, when non-empty, exactly:
- **Entry**: existing `GetSyncableProperties` scalars + `MorphType` (from `LexemeFormOA.MorphTypeRA`).
- **Each Sense**: `Gloss`, `Definition`, `Grammatical Info` (MSA label, e.g. `n:NC`).
- **MSA (per matched sense)**: `Slots`, `Category info` — **label + slots/category only**
  (clarification: deep MSA breakdown out of scope).
- **Each Allomorph** (`LexemeFormOA` + `AlternateFormsOS`): `Form`, `Morph Type`, `Environments`,
  `Comment`, plus existing per-child **custom** fields.

**Rationale**: This is the set Move transfers (transfer.py creates "senses + MSAs + allomorphs +
environment wiring + morph types"), intersected with what FLEx displays for the entry (the reference
screenshot). Field selection is driven by Move (spec Assumption), so preview == Move (SC-006).

**Alternatives considered**: full MSA breakdown (inflection features, from/to POS) — deferred by
clarification; recorded in spec Out of Scope.

## R6 — Empty suppression, exclusions, graceful degradation

**Decision**: Reuse the existing `_is_empty_value` / `_coerce_cf_value` / `_is_excluded_key` /
`_filter_props` machinery for every new field. Extend `_coerce_cf_value` usage to child standard
fields (values may be `ITsString`/`IMultiString`). Every per-child and per-field read is wrapped so a
single failure is contained (logged at DEBUG or surfaced as a note), never aborting the entry
(FR-012). No live LCM objects are retained; only `str` / `{ws: text}` / `list[str]` land in the dict
(FR-013).

**Rationale**: These helpers already implement R-b (empty suppression) and R-c (bookkeeping
exclusion) correctly; the new fields must obey the same rules for consistency (FR-008, FR-009).

## R7 — Qt-free constraint

**Decision**: All gather + fingerprint-token logic lives in `merge_preview.py` /
`Lib/fingerprints.py`, both Qt-free. Only `merge_preview_pane.py` (already Qt) changes for rendering
ordered child groups, consuming `FieldDiff.indent` + `display_name`.

**Rationale**: Feature 012 SC-007 forbids Qt imports in `merge_preview.py`; the shared token helper
must not pull Qt or Move-execution code either.

## Resolved unknowns

All Technical Context items resolved; no `NEEDS CLARIFICATION` remain. The two spec clarifications
(child fingerprint pairing; MSA depth = label + slots/category) are incorporated in R2 and R5.
