# Contract: Custom-Field Creation via MetaDataCacheAccessor

Custom fields are virtual flids registered in FLEx's meta-data cache.
They are NOT first-class `ICmObject`s and have no GUID. Phase 3b's
`custom_fields` category creates them via a direct MDC call.

## Source-side enumeration

```python
mdc = project.Cache.MetaDataCacheAccessor
all_flids = mdc.GetFieldIds()
custom_flids = [f for f in all_flids if mdc.IsCustom(f)]
for flid in custom_flids:
    yield CustomFieldRecord(
        class_id=mdc.GetOwnClsId(flid),
        name=mdc.GetFieldName(flid),
        type=mdc.GetFieldType(flid),  # CellarPropertyType enum int
        help=mdc.GetFieldHelp(flid),
        label_override=mdc.GetFieldLabel(flid),
        list_id=mdc.GetFieldListRoot(flid),  # 0 / Guid.Empty when N/A
    )
```

## Identity & sync detection

Identity is the `(class_id, name)` tuple. In `plan_action`, look up
target's flid registry the same way and treat a name match on the same
class as already-synced — no `PlannedAction`. Mismatched type on the
same `(class_id, name)` is a Phase-2 conflict (defer to interactive
merge); for additive Phase 0, emit `Skip(IDENTITY_COLLISION)` with
detail noting the type mismatch.

## Target-side creation

```python
tgt_mdc = target_project.Cache.MetaDataCacheAccessor
new_flid = tgt_mdc.AddCustomField(
    class_name,        # resolved from class_id via GetClassName
    field_name,
    field_type,        # CellarPropertyType
    list_root_guid,    # Guid.Empty when N/A
)
if new_flid == 0:
    raise RuntimeError(
        f"AddCustomField returned flid=0 for ({class_name}, {field_name}); "
        f"target MDC refused creation."
    )
```

Help text and label-override multistrings are set via subsequent MDC
calls (`SetFieldHelp` / `SetFieldLabel`) IF the flexlibs2 fork exposes
them; otherwise apply through `Cache.DomainDataByFlid.SetMultiStringAlt`
on the meta-data-cache itself. Probe at planning time.

## Fail-loud discipline

`AddCustomField` failure raises `RuntimeError` immediately — no
silent return, no orphan flid. Matches the Phase 3a
`_create_with_guid` discipline applied to ICmObject creation.

## Re-run idempotency

Re-running the same Phase 3b transfer MUST find the previously-created
custom fields by `(class_id, name)` match in `enumerate_source`'s sync
check and emit zero new `PlannedAction`s. Validated in
[quickstart.md](../quickstart.md)'s Scenario B (overwrite re-run).
