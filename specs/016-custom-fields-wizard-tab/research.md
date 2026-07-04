# Research Notes: Custom Fields Wizard Tab (016)

**Status**: Partially populated.  Sections marked "pending probe-results.md" require
the T004 write-probe results before they can be finalized.

---

## 1. CellarPropertyType -> Human Label Mapping

These are the types displayable on custom-field rows in the wizard UI.
Values from SIL FieldWorks / LibLCM `CellarPropertyType` enum.

| CellarPropertyType value | Internal name       | Human label shown in wizard |
|--------------------------|---------------------|-----------------------------|
| 1                        | Boolean             | Boolean                     |
| 2                        | Integer             | Integer                     |
| 8                        | GenDate             | Date                        |
| 13                       | String              | Text                        |
| 14                       | MultiString         | Multi-string                |
| 16                       | MultiUnicode        | Multi-Unicode               |
| 23                       | OwningAtomic        | Item (owned)                |
| 24                       | ReferenceAtomic     | List item                   |
| 26                       | ReferenceCollection | List item                   |

Notes:
- Both ReferenceAtomic (24) and ReferenceCollection (26) map to "List item" because from
  the user's perspective both reference a possibility list; the distinction is single vs
  multi-valued.
- MultiString (14) stores analysis-language strings; MultiUnicode (16) stores Unicode
  strings without a fixed analysis language.
- OwningAtomic (23) is the type used for structured sub-objects owned by the field;
  this is rare in practice but appears in some SIL field configurations.
- GenDate (8) is FLEx's partially-known-date type (day/month/year individually optional).

The `custom_field_type_label(field_type: int) -> str` helper in `categories.py` (T006)
implements this mapping.  Unknown type integers should fall back to
`f"Type {field_type}"` rather than raising.

---

## 2. Owner Class -> Level Name Mapping

Used by the wizard grouped-tree (T009) and the level-header labels.

| LCM owner class name  | Level name displayed |
|-----------------------|----------------------|
| LexEntry              | Entry                |
| LexSense              | Sense                |
| LexExampleSentence    | Example              |
| MoForm                | Allomorph            |

The canonical ordering for groups is the declaration order of
`_CUSTOM_FIELD_OWNER_CLASSES` in `categories.py`:
`("LexEntry", "LexSense", "LexExampleSentence", "MoForm")`.

Class IDs (confirmed from live MCP probe and flexicon source):

| LCM owner class name  | GetClassId() |
|-----------------------|--------------|
| LexEntry              | 5002         |
| LexSense              | 5016         |
| LexExampleSentence    | 5004         |
| MoForm                | 5035         |

---

## 3. Identity and Collision Policy

Custom fields have **no LCM GUID**; their identity key is `(owner_class, field_name)`.

- A source field whose `(owner_class, name)` matches an existing target field is classified
  as **IN_TARGET** (already present).  No new field is created; the existing flid is reused
  for value-fill.
- A **type difference** on a matched `(owner_class, name)` is **NOT a collision** and MUST
  NOT block the transfer.  It is surfaced as an informational `type_diff_note` on the row.
  The transfer proceeds using the target's existing field type.
- There is no `IDENTITY_COLLISION` for custom fields; the 006 contract's framing does not
  apply to the wizard-driven path (overridden by spec.md identity policy section).
- A source field with no match in the target is classified as **NEW**.

The classifier `classify_custom_field(record, target) -> (status, type_diff_note|None)`
in `categories.py` (T007) implements this logic.

---

## 4. AddCustomField Signature Correction

The 006 contract (`contracts/custom-field-creation.md`) cites the signature as:

    AddCustomField(class_name, field_name, field_type, list_root_guid)   # WRONG

**This is incorrect.**  The real LibLCM signature confirmed by live MCP probe (2026-07-04)
is:

    # 4-arg overload:
    AddCustomField(className: str, fieldName: str, fieldType: int, destinationClass: int) -> int

    # 7-arg extended overload:
    AddCustomField(className: str, fieldName: str, fieldType: int,
                   destinationClass: int,
                   fieldHelp: str, fieldWs: int, fieldListRoot: Guid) -> int

The 4th positional argument is `destinationClass` (an `Int32` class ID such as 5002 for
`LexEntry`), **not** `list_root_guid`.  The list root GUID is the **7th** argument in the
extended overload.

All fake implementations (`FakeTargetMDC.AddCustomField` in
`tests/unit/_fakes_custom_fields.py`) and any production call in `categories.py` (T017)
MUST follow this corrected signature.

---

## 5. GetAllFields Return Shape

From live MCP probe, `CustomFieldOperations.GetAllFields(className)` yields tuples of:

    (field_id: int, name: str, field_type: int, list_root_guid: str)

The fakes expose this 4-tuple shape.  The existing Phase-3b categories.py code
unpacks only `(field_id, label)` (2-tuple) — T006 must extend unpacking to
`(field_id, label, field_type, list_root_guid)` when populating `_CustomFieldRecord`.

---

## 6. Probe Questions (pending T003/T004 results)

The following questions are answered by the write probe (T004) against the throwaway
`Ejagham Full GT-Test` project.  Results will be recorded in
`specs/016-custom-fields-wizard-tab/probe-results.md`.

### 6a. Creation inside UoW (the Phase-3b blocker)
- Does `Cache.MetaDataCacheAccessor.AddCustomField(...)` succeed inside the FlexTools
  UoW envelope that wraps `execute_action`?
- Does the Phase-3b `FP_TransactionError` still occur?
- Is the MDC-direct path (`AddCustomField`) distinct from
  `CustomFieldOperations.CreateField` (which was the blocked path)?

### 6b. Nonzero flid confirmation
- Does `AddCustomField` return a nonzero `int` flid on success?
- What happens on a duplicate `(class_name, field_name)` call — does it return the
  existing flid or raise?

### 6c. Schema persistence and corruption check
- After `AddCustomField` inside UoW + commit, does the field survive a FLEx-UI reopen
  without schema corruption?
- Is the field enumerable by `GetAllFields` on the next open?

### 6d. Help/label MDC setter availability
- Are `SetFieldHelp`, `SetFieldLabel`, or equivalent MDC setters available to set
  human-readable metadata alongside the field registration?

**These cells remain PENDING until probe-results.md is written (T004).**
The T004 result is the go/no-go gate for US3's create-definition path.
