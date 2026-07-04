# Contract: Custom Fields Wizard Page

Wizard-driven counterpart to
[006-inflection-prep-block/contracts/custom-field-creation.md](../../006-inflection-prep-block/contracts/custom-field-creation.md).
Where the two differ, this contract governs the **wizard-selected** transfer path (spec 016).

## Producer

`Lib/categories.py.custom_fields_enumerate_source(context, selection)` → an ordered list of
custom-field records, one per source custom field on the supported owner classes
(`LexEntry`, `LexSense`, `LexExampleSentence`, `MoForm`). Each record carries:

- `owner_class: str` — mapped to a UI level (Entry / Sense / Example / Allomorph)
- `name: str`
- `field_type: int` — CellarPropertyType (rendered to a human label in the UI)
- `list_root_guid` — for list-backed types; `Guid.Empty` when N/A
- `guid: str` — synthetic `"cf:<owner_class>:<name>"` (custom fields have no LCM GUID)

## Consumer

`_PageCustomFields` (in `selection_wizard.py`) renders the records grouped by level, all
preselected, with a whole-block toggle, per-field trim, tristate group toggles, and a
NEW / IN TARGET status column. Reached via `page_custom_fields()`.

## Identity, reuse, and the not-a-collision rule

- Identity is `(owner_class, name)`.
- A source field whose `(owner_class, name)` matches an existing target field is **reused**:
  no create-definition action, values filled into the existing flid.
- A **data-type difference** on a `(owner_class, name)` match is **NOT a collision**. It MUST
  NOT emit `IDENTITY_COLLISION`, MUST NOT block, and MUST be surfaced as an informational note
  on the row. (Overrides the 006 contract's `IDENTITY_COLLISION` framing for this path.)

## Create-definition action (target-absent fields only)

Per selected field absent from the target, emit exactly one:

```python
tgt_mdc = target.Cache.MetaDataCacheAccessor
new_flid = tgt_mdc.AddCustomField(class_name, field_name, field_type, list_root_guid)
if new_flid == 0:
    raise RuntimeError(f"AddCustomField returned flid=0 for ({class_name}, {field_name})")
```

Help/label multistrings applied via MDC setters where the fork exposes them (probe at
planning time). Fail-loud, no orphan flid — per 006.

## Ordering guarantee (create early, fill later)

Within Move, **every** create-definition action MUST execute **before any value-fill action**
that writes into that field, across all downstream pages. The wizard *step* is early; the
*writes* are at Move; definitions precede content. Nothing on the page writes to the target.

## Idempotency

Re-running the same transfer finds prior-created fields by `(owner_class, name)` and emits
zero new create-definition actions.
