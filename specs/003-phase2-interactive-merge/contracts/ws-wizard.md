# Contract: Writing-System Mapping Wizard

The contract between the pre-plan WS detector and the WS wizard widget.

## Producer: `Lib/ws_mapping.py`

```python
def detect_ws_mismatches(source, target) -> tuple[WSMismatch, ...]:
    ...
```

Behavior:
1. Enumerate source WSes via `source.WritingSystems.GetAll()`.
2. Enumerate target WSes via `target.WritingSystems.GetAll()`.
3. For every source WS whose `Id` is NOT present in the target's set, emit a `WSMismatch`.
4. `target_ws_candidates` is sorted by similarity heuristic:
   - exact language-script-region prefix match first
   - same primary language tag (`ko-*`) next
   - all remaining target WSes last
5. Return empty tuple if every source WS already exists in target.

## Consumer protocol: `WSResolver`

```python
class WSResolver(Protocol):
    def resolve(self, mismatches: tuple[WSMismatch, ...]) -> tuple[WSMappingChoice, ...]:
        """Block until the user has answered every mismatch.  Length and
        order of the returned tuple MUST match `mismatches`.

        Raises:
            UserCancelled: if the user dismisses the wizard without
            completing it.
        """
```

Production implementation: `Lib/ui/ws_wizard.py.WSWizard` (PyQt5 `QWizard`).
Test double: `tests/unit/conftest.py.FakeWSResolver`.

## Contract guarantees

1. **Empty mismatch tuple is a no-op**: when the producer returns an empty tuple, the consumer is NOT invoked (the wizard never opens). FR-209 short-circuits.
2. **Ordering**: `resolve()` returns choices in the same order as `mismatches`.
3. **MAP validation**: `WSMappingChoice(choice=MAP)` MUST set `target_ws_id` to an `Id` that exists in the target's current WS list (validated by the wizard at confirm-time). Producer pre-populates candidates; consumer rejects invalid picks.
4. **CREATE side-effect**: when the user picks CREATE, the new WS MUST be created in the target project BEFORE `build_run_plan` is called (FR-212). This is the wizard's responsibility, not downstream code.
5. **SKIP propagation**: `WSMappingChoice(choice=SKIP)` flows into `Selection.ws_mapping_choices` and ultimately causes `Skip(reason=UNMAPPED_WS_USER_CHOSE_SKIP)` for any object whose only WS-keyed content is in this WS.
6. **Cancellation atomicity**: raising `UserCancelled` MUST leave the target project bit-identical — no WS may have been created before the cancel. Implies the wizard collects all choices first, then applies CREATE choices in a single "Finish" step.
