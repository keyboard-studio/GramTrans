# Contract: Conflict Prompt

The contract between the Preview-phase conflict detector and the user-interactive resolver (PyQt dialog or test double).

## Producer: `Lib/conflict.py`

```python
def detect_conflicts(
    src_props: dict,
    tgt_pre_props: dict,
    target_guid: str,
    target_class_name: str,
    prior_log: MergeDecisionLog | None = None,
) -> tuple[ConflictPrompt, ...]:
    ...
```

Behavior:
1. For every key `k` present in BOTH `src_props` and `tgt_pre_props`:
   - If `src_props[k] == tgt_pre_props[k]` (structural equality): suppress (FR-216).
   - Otherwise emit a `ConflictPrompt(target_guid, target_class_name, field_name=k, left_value=tgt_pre_props[k], right_value=src_props[k])`.
   - If `prior_log` carries a `MergeDecision` for field `k`, attach it as `prior_decision`.
2. Keys present only in one side are NOT emitted (Phase 1 source-wins or target-preserved applies).
3. Determine `merge_eligible` from value type: True for str / dict-of-str-keys-multistring / list, False for int / bool / GUID-reference patterns.

Return invariant: returned tuple is ordered alphabetically by `field_name`. Empty tuple if no conflicts.

## Consumer protocol: `ConflictResolver`

```python
class ConflictResolver(Protocol):
    def resolve(self, prompts: tuple[ConflictPrompt, ...]) -> tuple[MergeDecision, ...]:
        """Block until the user has answered every prompt. Length and order
        of the returned tuple MUST match `prompts`.

        Raises:
            UserCancelled: if the user dismisses the dialog without answering.
        """
```

Production implementation: `Lib/ui/conflict_dialog.py.ConflictDialog`.
Test double: `tests/unit/conftest.py.FakeConflictResolver`.

## Contract guarantees

1. **No prompt for identical values**: FR-216. The producer suppresses; the consumer never sees them.
2. **Order preservation**: `resolve()` returns decisions in the same order as `prompts` — callers can `zip()` safely.
3. **Cancellation is atomic**: raising `UserCancelled` MUST leave no state changes pending. The caller catches and exits before any LCM write.
4. **EDIT_CUSTOM safety**: when the user picks EDIT_CUSTOM, `MergeDecision.custom_value` MUST be set; the consumer is responsible for validating field-type compatibility before returning.
5. **Prior-decision recall**: if `prior_decision` is set on a `ConflictPrompt`, the UI MUST pre-select that resolution (US3, SC-204). Accepting it MUST emit the SAME `MergeDecision` (including the original `prior_run_id`) to mark it as carried-over (FR-208).
