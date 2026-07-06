# Contract: Nested Entry Gather

**Module**: `src/gramtrans/Lib/merge_preview.py` (`props_for` / `_gather_props` /
`_append_custom_fields`, extended). Qt-free.

## Interface

`props_for(handle, category, guid, *, owner_guid="", ops_table=None) -> dict | None`
— unchanged signature. For entry-category (`affixes`, `stems` → resolved key `entry`) the returned
dict now additionally contains child standard fields under fingerprint-based machine keys, and the
service is given a parallel meta map (see below).

Internally, a new helper produces both:

```
_gather_entry_nested(handle, obj) -> (props: dict[str, Any], meta: dict[str, KeyMeta])
KeyMeta = tuple(display_name: str, sort_key: tuple, indent: int)
```

## Guarantees

- **G1 (child standard fields)**: for each non-empty sense, allomorph, and matched MSA, the returned
  props include the fields enumerated in research R5, coerced to text / `{ws: text}` / `list[str]`.
- **G2 (join keys)**: each child field key is `f"{kind}\x1f{token_hash}\x1f{field}"`; a source child
  and its content-equivalent target child produce the **same** key (enabling per-field diff).
- **G3 (ordering meta)**: `meta[key]` gives `display_name` ("Sense 1 ▸ Gloss"), `sort_key`
  ((group_order, field_order)), and `indent` (0 entry / 1 child).
- **G4 (empty suppression)**: empty fields and empty child groups contribute nothing (FR-008).
- **G5 (exclusions)**: `_is_excluded_key` bookkeeping exclusions apply to new keys (FR-009).
- **G6 (containment)**: any single field/child read failure is caught; the rest of the entry still
  gathers (FR-012). A recoverable-but-unread field yields a read-failure note (see multistring
  contract), not a silent drop.
- **G7 (no live objects)**: values are plain data only (FR-013).
- **G8 (backward compat)**: non-entry categories return exactly today's dict with `meta = None`;
  `diff_props`/pane behavior for them is unchanged.

## Acceptance (maps to spec)

- US1-AS1/AS2/AS3, US3-AS1, SC-001, SC-002, SC-006.
