# US2 Blocker: Custom-Field Schema Mutation vs. UnitOfWork Envelope

**Date**: 2026-06-21
**Status**: RESOLVED — Option C (detect-and-report) adopted per LEX crew cycle-1 unanimous approval (lex-domain PASS, lex-author 9/10, lex-doc/lex-programmer/lex-qc converged). T014-T020 superseded; see code shipped in commit (this one) and spec.md US2 / FR-323 / FR-325 rewrites. Creation remains blocked at flexicon layer; promotion path documented below.
**Discovery vector**: MCP probe of `CustomFieldOperations.CreateField` docstring during T014 implementation prep.

## The constraint

Per the flexicon docstring on `CustomFieldOperations.CreateField`:

> Custom field creation is a SCHEMA mutation and cannot run inside an
> open UnitOfWork. In Phase 1 transaction mode (the default),
> `OpenProject()` opens a non-undoable envelope that remains open until
> `CloseProject()`, so `CreateField()` will refuse with
> `FP_TransactionError`.
>
> Bypassing this guard with raw LCM (`IFwMetaDataCacheManaged.AddCustomField`)
> creates the field in memory only; subsequent SetValue calls appear to
> succeed but the schema does NOT persist, producing corrupted records
> on next FLEx UI open.

## Why it blocks Phase 3b US2

GramTrans's `transfer.execute()` (and `flextools_run_module` itself)
runs inside the Phase-1 transaction envelope. Our `custom_fields_execute_action`
callback fires from within that envelope. There is no in-script path
to:

1. Exit the UoW
2. Run `CreateField` (which mutates schema durably)
3. Re-enter the UoW to continue with downstream actions (POS, etc.)

Both possible workarounds are unsatisfactory:

- **Raw `AddCustomField`**: produces corruption on next FLEx UI open per the
  docstring. Hard veto.
- **Two-process workflow**: user runs a custom-field-creation module first
  outside any other transfer, then runs GramTrans. Pushes complexity to
  the linguist; defeats the "one Run button" UX goal.

## Open architectural questions (for next session)

1. Can `MainFunction(project, report, modifyAllowed)` open a *second*
   project handle in a separate process / connection that doesn't enter
   the Phase-1 envelope? (Probably no -- FlexTools sandbox is one
   process.)
2. Does flexicon expose a "schema-mutation pre-pass" hook that runs
   before `OpenProject` enters Phase-1 mode? Worth searching the fork
   for `before_open`-style hooks.
3. Does the LCM C# layer offer a way to `Save()` the schema mutation
   without closing the UoW? Need to consult `docs/CUSTOM_FIELDS.md` in
   the flexicon fork (the docstring references it but it's not surfaced
   through MCP discovery).

## Recommended Phase 3b path

**Defer US2 implementation** (T014-T020). Mark in tasks.md as
"BLOCKED — UoW conflict; see us2-blocker-memo.md".

**Continue with US3** (variant_types + complex_form_types +
semantic_domains, T021-T033) — these are normal `ICmObject` creations
inside the UoW and have no schema-mutation constraint.

**Continue with US4** (empty-source UX, T034-T036) — applies only to
the eight non-custom-fields categories.

The five COMPLETE callbacks from Phase 0 era (T009-T013, ALREADY SHIPPED
in commit 50480d4) are unaffected; they create regular `ICmObject`s
inside the UoW.

## Future remediation (Phase 3c or 3d)

The cleanest fix is a `pre-execute` schema-mutation phase added to
`MainFunction`:

```python
def MainFunction(project, report, modifyAllowed):
    # Phase A: schema mutations (custom fields) -- runs in its own
    # short-lived project handle without entering Phase-1 transaction
    if modifyAllowed:
        _apply_custom_field_schema(source_path, target_path, plan)

    # Phase B: regular transfer -- enters Phase-1 transaction envelope
    project = OpenProject(target_path, write_enabled=True)
    execute(plan, project, ...)
```

This requires:
- Splitting the planner: schema mutations vs. object-graph mutations.
- New `_apply_custom_field_schema` helper that uses a short-lived
  `OpenProject(undoable=False, transaction_mode='direct')` -- need to
  confirm flexicon exposes a direct-mode flag.
- Plumbing the source-side custom-field record extraction so it runs
  before the UoW opens (i.e., on a read-only source handle).

A more conservative alternative: ship Phase 3b without US2, document the
manual workaround for users who need custom-field transfer
("Run the Phase 3b transfer first; then in a second pass, use FLEx UI
or a one-off custom-field-creation script to add the missing custom
fields by hand").

## Acceptance criteria for unblocking US2

US2 can resume when ONE of the following is true:

1. flexicon fork exposes a `transaction_mode='direct'` (or equivalent)
   on `OpenProject` that bypasses the Phase-1 envelope.
2. We adopt the two-phase `MainFunction` shape above, with the
   schema-pre-pass running in a separately-opened, direct-mode project
   handle.
3. The user accepts the manual-workaround posture and we document it
   in the FR/Spec instead of shipping automation.

Until then: spec FR-325 / FR-322 references to `custom_fields` should
be downgraded from "MUST land in target before Phase 3c" to "MAY
require a manual pre-step; see us2-blocker-memo.md".
