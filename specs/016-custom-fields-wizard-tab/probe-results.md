# Probe Results — T004 Creation-Route Gate (spec 016)

**Date**: 2026-07-04 | **Probed by**: main session via flextools-mcp (LibLCM + flexicon layers)
**Target**: `Ejagham Full GT-Test` (throwaway) | **Source read**: `Ejagham Full`

## VERDICT: **GO** — creation is REACHABLE and PERSISTS in Phase-2 (undoable) transaction mode

The Phase-3b NO-GO (`FP_TransactionError` / issue-#21 corruption) is **specific to Phase-1
transaction mode**. In **Phase-2 / undoable mode**, `IFwMetaDataCacheManaged.AddCustomField`
called at `CurrentDepth == 0` inside a `NonUndoableUnitOfWorkHelper.Do(...)` block **succeeds
and persists cleanly across a full close/reopen** — no corruption.

US3 (the create-definition core) is **feasible**, with one hard architectural requirement:
**GramTrans must open the TARGET project in undoable (Phase-2) mode and run the create-definition
pre-pass at `CurrentDepth == 0`, before any value-write UndoableOperation block.**

## Evidence (op ids in the flextools-mcp session log)

| Step | op | Result |
|------|-----|--------|
| Read probe, Ejagham Full | 002 | `GetClassId`: LexEntry=5002, LexSense=5016, LexExampleSentence=5004, MoForm=5035 |
| Phase-1 write attempt | 003 | `Cache.MetaDataCacheAccessor` is base `IFwMetaDataCache` — **no `AddCustomField`** (needs managed-interface cast); `GetFields(int,bool,int)` needs array out-param |
| Managed-cast enumerate (undoable) | 005 | `CurrentDepth == 0` at snippet start; `IFwMetaDataCacheManaged(cache.MetaDataCacheAccessor)` cast works; GT-Test has **11 custom fields** incl. the issue-#21 `Plural` (MultiUnicode) field |
| Create+readback+delete (undoable) | 006 | `AddCustomField("LexEntry","GT016ProbeInt",Integer,0)` → flid returned; readback OK; count 11→12; `DeleteCustomField` → 12→11. No exceptions. |
| Create + leave (undoable) | 007 | field created, left on disk |
| **Reopen + verify persistence** | 008 | **`FieldExists=True` after full reopen** — field survived to `.fwdata`; read back cleanly (Integer, isCustom); flid renumbered on reload (normal); then deleted → back to 11 |

## Answers to the T004 probe questions

- **(a) Does `AddCustomField` succeed in the FlexTools UoW?** In Phase-1 (non-undoable envelope
  open for the whole session) — NO (genuine LCM contract, confirmed in
  `flexicon/docs/CUSTOM_FIELDS.md` and the `CreateField` guard at
  `CustomFieldOperations.py:301`). In **Phase-2/undoable** at `CurrentDepth==0` wrapped in
  `NonUndoableUnitOfWorkHelper.Do` — **YES**.
- **(b) Nonzero flid?** Yes.
- **(c) Survives reopen, no corruption?** **Yes** — persisted across a full session reopen and
  re-enumerated cleanly. (The issue-#21 corruption was schema-not-persisting-while-data-does; here
  the schema persisted.)
- **(d) Is `CustomFieldOperations.CreateField` still blocked?** Yes — the wrapper's guard fires in
  Phase-1, and its Phase-2 no-UoW path is an **unimplemented placeholder**
  (`CustomFieldOperations.py:321` raises "not yet implemented"). GramTrans must drive **raw
  `AddCustomField`** itself (managed-interface cast + `NonUndoableUnitOfWorkHelper`).
- **(e) Help/label setters?** `IFwMetaDataCacheManaged.UpdateCustomField(flid, fieldHelp, fieldWs,
  userLabel)` is exposed (and the 7-arg `AddCustomField` overload takes `fieldHelp`/`fieldWs`).
- **(f) Wrapper vs LibLCM constraint?** GENUINE LibLCM/UoW constraint in Phase-1 (schema mutation
  forbidden inside an active data UoW: `UndoStack.CheckNotProcessingDataChanges`). Phase-2 mode
  removes the always-open envelope, opening the safe `CurrentDepth==0` gap.

## Corrected API facts (fix the 006 + 016 contracts)

- **Real signatures** (managed interface `IFwMetaDataCacheManaged`, cast from
  `cache.MetaDataCacheAccessor`):
  - `AddCustomField(className, fieldName, fieldType: CellarPropertyType, destinationClass: Int32)`
  - `AddCustomField(className, fieldName, fieldType, destinationClass, fieldHelp: String, fieldWs: Int32, fieldListRoot: Guid)`
  - The **4th arg is `destinationClass` (Int32)**, NOT `list_root_guid`. The list root is the
    **7th** arg of the extended overload. The 006 contract's
    `AddCustomField(class, name, type, list_root_guid)` is **wrong** and must be corrected.
- `AddCustomField` lives on `IFwMetaDataCacheManaged`, not the base `IFwMetaDataCache` returned by
  `cache.MetaDataCacheAccessor` — a cast is required:
  `IFwMetaDataCacheManaged(cache.MetaDataCacheAccessor)` (import from `SIL.LCModel.Infrastructure`).
- Enumeration: `mdcm.GetFieldIds()` + `mdcm.IsCustom(flid)`; per-field `GetFieldName`,
  `GetOwnClsName`, `GetFieldType` (int CellarPropertyType), `GetFieldListRoot`.
- CellarPropertyType values seen live in GT-Test: **13 = String**, **16 = MultiUnicode**.

## Live custom-field inventory in `Ejagham Full GT-Test` (11 fields)

| flid (pre-reload) | owner | name | type |
|------|-------|------|------|
| 5002500 | LexEntry | Noun class | 13 (String) |
| 5002501 | LexEntry | Noun class Eastern E | 13 |
| 5002502 | LexEntry | Plural | 16 (MultiUnicode) |
| 5002503 | LexEntry | Root East E ?? | 13 |
| 5002504 | LexEntry | Root West E ?? | 13 |
| 5002505 | LexEntry | Tone class | 13 |
| 5002506 | LexEntry | Tone class Eastern E | 13 |
| 5002507 | LexEntry | Tone class Western E | 13 |
| 5016500 | LexSense | Noun gender | 16 |
| 5016501 | LexSense | POS note | 13 |
| 5035500 | MoForm | Allomorph Comment | 16 |

## Open items for Cycle-2 verification (lex-verification)

1. **Value round-trip**: create field + write a value on one entry + reopen → confirm BOTH field
   and value persist (the exact issue-#21 scenario; only field-only persistence tested so far).
2. **How GramTrans opens the target in undoable mode**: confirm `api.py` / target-bind path can
   open the bound target with `undoable=True` (or an equivalent Phase-2 open), since the create
   pre-pass depends on it. The MCP proves the LCM capability; the GramTrans plumbing must be wired.
3. **Ordering**: create-definition pre-pass runs at `CurrentDepth==0` BEFORE the value-write
   UndoableOperation blocks (FR-010).
