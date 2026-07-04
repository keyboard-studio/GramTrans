# Contract: Five-Callback Registry per Category

Every category registered in `Lib/categories.py` implements five
callbacks. Phase 3a adds six new registrations (five new categories +
the relocated `ph_environment`) matching the contract that the five
existing COMPLETE categories already satisfy.

## Callback signatures

```python
def enumerate_source(context: RunContext, selection: Selection) -> Iterable[piece]:
    """READ-ONLY. Walk the source project and yield every piece this
    category cares about. Returns empty iterable if source is empty
    for this category (FR-308 skip-empty).

    Args:
        context: RunContext (carries source_handle).
        selection: Selection (the planner respects subcategory filters
            like pos_picks; phonology has no such filters in 3a).

    Returns:
        Iterable of LCM object wrappers (flexicon yields .concrete-bearing
        wrappers; downstream callbacks must _unwrap before casting).
    """

def dependencies(piece) -> tuple[str, ...]:
    """READ-ONLY. Return the GUIDs of objects this piece's closure
    requires to already exist (or be in the same run's plan) before
    this piece can be transferred.

    For leaf categories (phon features, strata, env), returns ().
    For phonological rules, returns the GUIDs of referenced phonemes
    + natural classes + environments (per FR-304).
    """

def required_writing_systems(piece) -> frozenset[tuple[str, WSKind]]:
    """READ-ONLY. Return the set of (ws_id, kind) pairs this piece's
    multistring / unicode fields use. Drives Phase 2 WS-wizard
    detection.

    Phon features / phonemes / strata: typically empty (their names
    live in analysis WSes already mapped). Natural classes / envs /
    rules: same.
    """

def plan_action(piece, context, ws_mapping) -> PlannedAction | PlannedOverwrite | Skip:
    """READ-ONLY. Decide what the executor should do with this piece:
    - additive create: PlannedAction
    - GUID-matched target (Phase 1 overwrite enabled): PlannedOverwrite
    - dependency unresolved / GOLD / etc.: Skip(reason=...)

    Per FR-304, phonological_rules.plan_action emits
    Skip(DEPENDENCY_UNRESOLVED) when any referenced phoneme / class /
    env GUID is neither present in target by GUID nor in the in-flight
    plan's actions.
    """

def execute_action(action, context, ws_mapping, tag) -> Optional[object]:
    """MUTATES TARGET. Apply the action. Returns the new LCM object
    when relevant (for identity_remap stashing when GUID could not be
    preserved).

    For PlannedOverwrite, the dispatcher's _execute_overwrite handles
    syncable-property apply + residue stamp; this callback fires only
    for PlannedAction.
    """
```

## Registry shape

```python
LEAF_CATEGORIES = {
    # ... existing 5 ...
    GrammarCategory.PHONOLOGICAL_FEATURES: {
        "enumerate_source": phon_features_enumerate_source,
        "dependencies":     phon_features_dependencies,
        "required_writing_systems": phon_features_required_writing_systems,
        "plan_action":      phon_features_plan_action,
        "execute_action":   phon_features_execute_action,
    },
    GrammarCategory.PHONEMES:           { ... },
    GrammarCategory.NATURAL_CLASSES:    { ... },
    GrammarCategory.PH_ENVIRONMENT:     { ... },  # relocated
    GrammarCategory.PHONOLOGICAL_RULES: { ... },
    GrammarCategory.STRATA:             { ... },
}
```

## Contract guarantees

1. **READ-ONLY in plan-time callbacks**: enumerate_source, dependencies,
   required_writing_systems, plan_action MUST NOT call any LCM mutating
   method (no Create, no Add, no set_*). Verified by Principle III's
   Preview gate.
2. **Idempotent execute_action on already-present GUIDs**: for
   GUID-preserving factories, an action targeting an already-existing
   GUID in target is a no-op (Phase 1 routes this through
   PlannedOverwrite instead, so execute_action only fires when GUID
   is genuinely absent).
3. **identity_remap on factory limitation**: when the factory cannot
   accept a Guid, execute_action returns the newly-created object so
   the executor populates `plan.identity_remap[source_guid] →
   target_guid`. Downstream cross-reference resolution uses this map
   transparently.
4. **Dependency closure**: dependencies() returns ONLY direct
   first-degree dependencies. The planner walks transitively via
   recursive resolution. For phonology this is at most depth 2:
   rule → (phonemes + classes + envs) → (features, optionally).
