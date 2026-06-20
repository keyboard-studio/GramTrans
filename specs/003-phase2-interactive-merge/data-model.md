# Phase 2 Data Model

Pure-Python dataclasses + enums to be added to `src/gramtrans/Lib/models.py`. All Phase 2 entities are immutable (`frozen=True`) and import only from stdlib; they survive into the LibLCM-fork sibling repo unchanged per constitution Principle II.

---

## E10 — MergeResolution (enum)

```python
class MergeResolution(enum.Enum):
    TAKE_SOURCE  = "take_source"   # source value wins (FR-109 default)
    KEEP_TARGET  = "keep_target"   # target value preserved
    MERGE        = "merge"         # deterministic concatenation per research R4
    SKIP         = "skip"          # field omitted from this run
    EDIT_CUSTOM  = "edit_custom"   # user typed a free-text value
```

Validation rules:
- `EDIT_CUSTOM` requires `MergeDecision.custom_value` to be non-None.
- All other resolutions require `custom_value` to be None.

---

## E11 — MergeDecision (dataclass)

```python
@dataclass(frozen=True)
class MergeDecision:
    field_name: str             # syncable-property key, e.g. "Comment", "CitationForm"
    resolution: MergeResolution
    left_value: object | None   # target's pre-overwrite value (JSON-serializable repr)
    right_value: object | None  # source's value (JSON-serializable repr)
    custom_value: object | None = None  # only set when resolution == EDIT_CUSTOM
    prior_run_id: str = ""      # run_id of the prior run if this was carried over (US3)
```

Validation rules:
- `field_name` MUST be non-empty.
- `resolution == EDIT_CUSTOM` ⇒ `custom_value is not None`.
- `resolution != EDIT_CUSTOM` ⇒ `custom_value is None`.
- If `prior_run_id` is set, the run_id MUST match `_RUN_ID_PATTERN` from `residue.py`.

---

## E12 — MergeDecisionLog (dataclass)

```python
@dataclass(frozen=True)
class MergeDecisionLog:
    target_guid: str             # GUID of the touched object
    decisions: tuple             # tuple[MergeDecision, ...] — ordered by field_name
```

Validation rules:
- `target_guid` MUST be a valid GUID string (8-4-4-4-12 hex).
- `decisions` MUST contain no two entries with the same `field_name`.

Serialization: `MergeDecisionLog.to_json() -> str` and `MergeDecisionLog.from_json(s)` produce stable JSON used inside the residue tag's `merge=` segment.

---

## E13 — ConflictPrompt (dataclass)

```python
@dataclass(frozen=True)
class ConflictPrompt:
    target_guid: str
    target_class_name: str       # LCM class, e.g. "LexEntry"
    field_name: str
    left_value: object | None    # from tgt_pre_props
    right_value: object | None   # from src_props
    prior_decision: MergeDecision | None = None  # from residue if US3 recall hit
    merge_eligible: bool = True  # False for scalars (int/bool/GUID-ref) per R4
```

Validation rules:
- `target_guid` and `target_class_name` MUST be non-empty.
- `field_name` MUST be non-empty.
- If both `left_value` and `right_value` are None or structurally equal, this prompt is INVALID — the planner MUST suppress identical-valued prompts (FR-216).

State transitions: `ConflictPrompt` is a Preview-phase output. It transitions into a `MergeDecision` after the user (or `ConflictResolver` test double) responds.

---

## E14 — WSMismatch (dataclass)

```python
@dataclass(frozen=True)
class WSMismatch:
    source_ws_id: str            # e.g. "ko-x-Latn"
    source_ws_kind: WSKind       # VERNACULAR | ANALYSIS (existing E from Phase 0)
    target_ws_candidates: tuple  # tuple[str, ...] of target WS ids, similarity-sorted
```

Validation rules:
- `source_ws_id` MUST be non-empty.
- `target_ws_candidates` MAY be empty (the "map" choice is unavailable; only "create" or "skip" remain).

---

## E15 — WSMappingChoice (dataclass)

```python
class WSChoice(enum.Enum):
    MAP    = "map"     # user picked an existing target WS
    CREATE = "create"  # create a new target WS preserving the source tag
    SKIP   = "skip"    # transfer objects whose only WS-keyed content is in this WS are skipped

@dataclass(frozen=True)
class WSMappingChoice:
    source_ws_id: str
    source_ws_kind: WSKind
    choice: WSChoice
    target_ws_id: str = ""       # required when choice == MAP; ignored otherwise
```

Validation rules:
- `choice == MAP` ⇒ `target_ws_id` MUST be non-empty.
- `choice in {CREATE, SKIP}` ⇒ `target_ws_id` MUST be empty.

Cross-entity rule: When folded into `WSMapping.entries`, each `WSMappingChoice` becomes a `WSMappingEntry` with `create_in_target=True` iff `choice == CREATE`. The user_choice field is preserved for audit but not used downstream.

---

## E16 — InteractiveSession (dataclass)

```python
@dataclass(frozen=True)
class InteractiveSession:
    ws_mapping_choices: tuple    # tuple[WSMappingChoice, ...]
    merge_decisions_by_guid: dict  # dict[str, MergeDecisionLog]
    cancelled: bool = False
```

Validation rules:
- If `cancelled == True`, both other fields MAY be empty (no decisions collected before cancel).
- `merge_decisions_by_guid` keys MUST be valid GUID strings.

Lifecycle: built incrementally by the wizard / dialog; passed frozen to `transfer.execute()`. Holds the entire user-interactive state for one Move run.

---

## Modified Phase 0/1 Entities

### Selection (E2 — modified)

Adds:
```python
interactive_merge: bool = False  # Phase 2 gate (default off for backward compat)
ws_mapping_choices: tuple = ()   # populated by WSWizard before plan build
```

Validation: `interactive_merge=True` requires `enable_overwrite=True` (Phase 1 prerequisite). Interactive merge on an additive-only run is meaningless.

### RunPlan (E4 — modified)

Adds:
```python
conflicts: tuple = ()  # tuple[ConflictPrompt, ...] — collected during build_run_plan
```

Validation: `len(conflicts) > 0` requires `plan.selection.interactive_merge == True`.

### ImportResidueTag (E5 — modified)

Adds:
```python
merge_b64: Optional[str] = None  # base64(MergeDecisionLog.to_json())
```

`serialize()` widens to optionally append `|merge=<merge_b64>` after `|snap=<snapshot_b64>`. `parse()` accepts 4/5/6 segments; segment ordering is enforced by prefix recognition (snap= before merge=).

New methods:
- `with_merge_log(log: MergeDecisionLog) -> ImportResidueTag` — clone with `merge_b64` set from `log.to_json()`.
- `decode_merge_log() -> Optional[MergeDecisionLog]` — recover the log or None.

### CategoryReport (E6 — modified)

Adds:
```python
interactive_resolved: int = 0    # count of fields with non-default decisions
interactive_skipped: int = 0     # count of SKIP resolutions
ws_mapped: int = 0
ws_created: int = 0
ws_skipped: int = 0
```

### SkipReason (enum — modified)

Adds:
```python
INTERACTIVE_SKIP            = "interactive_skip"
UNMAPPED_WS_USER_CHOSE_SKIP = "unmapped_ws_user_chose_skip"
```

---

## Entity Relationship Summary

```
Selection
  ├─ ws_mapping_choices: tuple[WSMappingChoice]
  └─ interactive_merge: bool
        ↓
WSWizard ─▶ tuple[WSMappingChoice] ─▶ Selection.ws_mapping_choices
                                       ↓
                                build_run_plan(...)
                                       ↓
                          RunPlan {conflicts: tuple[ConflictPrompt]}
                                       ↓
ConflictDialog ─▶ tuple[MergeDecision] ─▶ MergeDecisionLog (per target_guid)
                                                  ↓
                                       transfer.execute(plan, session)
                                                  ↓
                                ImportResidueTag.with_merge_log(...)
                                                  ↓
                                LiftResidue (target object on disk)
```

---

## Invariants

1. **No silent loss**: every field present in `src_props` that conflicts with `tgt_pre_props` MUST result in either a `ConflictPrompt` (and downstream `MergeDecision`) or be filtered by FR-216 (identical values). The planner emits both data structures from the same loop pass.
2. **Round-trip integrity**: `ImportResidueTag.parse(t.serialize()) == t` for every `t`, including the 6-segment form. The Phase 1 5-segment round-trip property is preserved.
3. **Decision uniqueness**: within one `MergeDecisionLog`, no two `MergeDecision` entries share the same `field_name`.
4. **Cancellation atomicity**: if `InteractiveSession.cancelled == True`, `transfer.execute()` MUST exit before any LCM write.
5. **Phase 1 fallback**: when `selection.interactive_merge == False`, all Phase 2 entities (`ConflictPrompt`, `MergeDecisionLog`, etc.) are empty / unused; the executor's behavior is bit-identical to Phase 1.
