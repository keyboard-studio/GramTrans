# Contract: MultiString Custom-Field Read Fallback

**Module**: `src/gramtrans/Lib/merge_preview.py` (`_read_custom_fields`, extended). Qt-free.

## Problem

`CustomFieldOperations.GetValue(obj, field_name)` raises for **MultiString** custom fields:
`AttributeError: 'ITsMultiString' object has no attribute 'BestAnalysisVernacularAlternative'`
(inside `FLExProject.GetCustomFieldValue`). Today this is caught per-field and the field is **silently
dropped** — violates Principle I. Verified live: field `Plural` (flid 5002502) on
`Ejagham Full GT-Test` affix entries.

## Interface

`_read_custom_fields(handle, obj, owner_class, prefix) -> dict[str, Any]` — unchanged signature; new
internal fallback path.

## Behavior

1. Try `GetValue` → coerce via `_coerce_cf_value` (existing).
2. On the known MultiString failure, **fall back** to a direct multi-string read across the project's
   writing systems (via the flexicon multi-string accessor / `sda.get_MultiStringAlt` per WS by the
   field's flid from `GetAllFields`), returning `{ws_id: text}`.
3. Apply `_is_empty_value` (existing) — empty MultiString CF is suppressed (FR-008).
4. If **both** paths fail, emit a **read-failure note** for that field (not a silent drop) and
   continue with the rest of the entry.

## Guarantees

- **G1**: a populated MultiString custom field appears in the preview with its value (SC-004).
- **G2**: an empty MultiString custom field is suppressed like any other empty field (FR-008).
- **G3**: no MultiString custom field is ever silently omitted — value or visible note (FR-007, SC-004).
- **G4**: containment — a CF failure never aborts the entry gather (FR-012).

## Acceptance

- US2-AS1/AS2, SC-004; spec Edge Case "unreadable field".
