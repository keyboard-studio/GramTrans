# Phase 1 Data Model: Nested Preview Field Gathering

All types are Qt-free and carry only plain Python data (no live LCM objects) — consistent with the
preview cache contract (FR-013, feature 012 FR-012).

## 1. Extended `FieldDiff` (modify existing)

`merge_preview.py` — add two optional fields; existing construction sites stay valid.

| Field | Type | Existing? | Meaning |
|---|---|---|---|
| `field_name` | `str` | yes | **Machine key** — for nested children this is the fingerprint-based join key (stable across source/target); for scalars, the property name (unchanged). |
| `segments` | `tuple[DiffSegment, ...]` | yes | Ordered diff runs (unchanged). |
| `indent` | `int` | yes | Nesting depth for rendering (0 = entry-level, 1 = child group member). Already present. |
| `display_name` | `str` (default `""`) | **new** | Human label shown in the pane, e.g. `"Allomorph 1 ▸ Comment"`. Empty → renderer falls back to `field_name` (preserves current scalar rendering). |
| `sort_key` | `tuple` (default `()`) | **new** | Ordering hint `(group_order:int, field_order:int)`. Empty → alphabetical by `field_name` (preserves feature-012 SC-003 for scalars). |

**Ordering rule in `diff_props`**: if any assembled `FieldDiff` has a non-empty `sort_key`, sort the
whole list by `sort_key` (ties broken by `field_name`); otherwise sort alphabetically by `field_name`
as today. Mixed use within one entry preview is expected (entry scalars can share the nested list;
give them a low group_order so they sort first).

## 2. Child join token (new, `Lib/fingerprints.py`)

Content-derived, cross-project-stable discriminators. Each returns a hashable tuple used to build the
machine key. Documented per class (constitution I: "fingerprint definition per object class MUST be
documented").

| Class | Token | Source of truth |
|---|---|---|
| Allomorph | `("allomorph", lexeme_form_text, morph_type_id)` | content half of `matcher.fingerprint_for_allomorph` (drops `owner_entry_guid`); `morph_type_id` = global morph-type GUID if present else morph-type name |
| Sense | `("sense", gloss_text)` | analysis-WS gloss; ordinal-disambiguated on collision |
| MSA / grammatical info | `("msa", label_text)` | `label_text` = POS abbrev + slot names (e.g. `n:NC`); content half of `preview._msa_fingerprint` (drops raw `pos_guid`) |

**Machine key construction**: `f"{kind}\x1f{token_hash}\x1f{field}"` where `token_hash` is a stable
short digest of the token and `field` is the child field name (`Form`, `Comment`, `Gloss`, …). The
`\x1f` (unit separator) guarantees no collision with human text. `display_name` is assigned
separately from source order (see §3).

**Collision / ambiguity**: if two source children share a token, assign them successive ordinals in
source order and suffix the token (`…#2`) so their keys differ (spec Edge Case "ambiguous
fingerprint"; deterministic first-unused-wins).

## 3. `EntryPreviewGather` intermediate (new, internal to `merge_preview.py`)

Not a persisted type — the working structure `_gather_props` builds before flattening into the
`{field: value}` dict + a parallel `{machine_key: (display_name, sort_key, indent)}` metadata map.

- **Entry scalars**: existing behavior; `indent=0`, `sort_key=(0, field_order)`.
- **Child group** (one per sense / allomorph / MSA), carrying:
  - `kind`: `"sense" | "allomorph" | "msa"`
  - `ordinal`: 1-based source position (for `display_name` "Sense 1", "Allomorph 2")
  - `token`: the join token (§2)
  - `fields`: `{field_label: value}` non-empty child fields (values already coerced to text /
    `{ws: text}` / `list[str]`)
  - `group_order`: `(kind_rank, ordinal)` → drives `sort_key[0]`; kinds ordered
    entry(0) < sense(1) < msa(2, under its sense) < allomorph(3), matching FLEx's top-to-bottom layout.

Flattening: for each child field, emit
`dict[machine_key] = value` and
`meta[machine_key] = (display_name=f"{Kind} {ordinal} ▸ {field_label}", sort_key=(group_order, field_order), indent=1)`.

`diff_props` receives the flat dicts as today; the **meta map** is passed alongside (new optional
param, default `None`) so it can stamp `display_name`/`sort_key` onto emitted `FieldDiff`s. When
`meta is None` (all non-entry categories) behavior is identical to today.

## 4. Value shapes (unchanged vocabulary)

Child field values use the **same shapes** the diff engine already handles, so no new segment logic:

| Field kind | Value shape |
|---|---|
| Single vernacular/analysis string (Form, Gloss, Definition, Comment) | `{ws_id: text}` (multi-WS) or `str` |
| Morph type, grammatical-info label, category | `str` |
| Environments | `list[str]` (sequence shape — `_segments_for_sequence`) |
| MultiString custom field (recovered) | `{ws_id: text}` |

## 5. Read-failure note (new, minor)

When a field cannot be read even after fallback (R4), attach a `DiffSegment(kind=NOTE)` to that
field's `FieldDiff` with text like `"<field>: could not read (…)"`. This is a **visible** marker
distinguishing "could not read" from "empty" (FR-007, spec Key Entity "Read-failure notice"). It
also flows into `MergePreview.notes` for the summary.

## 6. Relationships & invariants

- One `MergePreview` per previewed entry (unchanged); its `fields` now include child groups.
- A matched child contributes fields under keys present on **both** sides → per-field status.
- An unmatched source child → keys source-only → all ADDED. Unmatched target child → keys
  target-only → target-only unchanged (never implies deletion; consistent with existing
  OVERWRITE/MERGE_KEEP target-only handling).
- Empty fields and empty child groups are suppressed (FR-008): a group with no non-empty fields emits
  nothing (no empty header).
- No live LCM object is stored in the dict, the meta map, or the cache (FR-013).
