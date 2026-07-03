# Phase 1 Data Model: Similar-Candidate Capture & Per-Item Resolution (011)

Pure-Python frozen dataclasses. `Lib/models.py` types stay flavor-agnostic (no flexlibs2/LCM
imports); `Lib/selection.py` types are built from `_cast`-guarded LCM access already present in the
file. Every new field is **tail-appended and defaulted** for back-compat (FR-009 / research D7).

Field naming, defaults, and ordering were confirmed against the codebase conventions by lex-qc
(91/100). The two collision shapes referenced below are live-proven (research D1, D3).

---

## New type — `SimilarCandidate` (FR-001) — `Lib/models.py`

One target entry a SIMILAR source item could merge into. Immutable; the unit that populates the
resolution dropdown in a later chunk.

| Field | Type | Notes |
|-------|------|-------|
| `target_guid` | `str` | Lower-cased target entry GUID — the identity (Principle I, GUID-first). |
| `form` | `str` | Display vernacular form (from `_best_form`). Carries identity even when gloss is empty. |
| `gloss` | `str` | Display gloss (from `_collect_glosses`); may be `"(no gloss)"`. |

- Frozen dataclass. No `__post_init__` (a candidate is a plain value; validation of *use* lives on
  `SimilarResolution`).
- **Ordering contract:** `SimilarCandidate` itself carries no ordering key. Candidate tuples are
  **pre-sorted HVO-ascending at construction** (research D2); the *tuple order is the contract*.
  Consumers MUST treat the position in `PosGroupedAffixInventory.target_affix_candidates` and in the
  per-form tuple as canonical and MUST NOT re-sort. (If a future chunk needs to re-sort, add an
  explicit `hvo: int` field then — 011 does not, to keep the type minimal and flavor-agnostic.)

## New type — `SimilarResolution` (FR-007) — `Lib/models.py`

A per-source-entry overwrite / merge / create decision. The typed contract the pane emits and the
013 planner will read.

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `entry_guid` | `str` | — | Source entry GUID the resolution is for. |
| `action` | `str` | — | Exactly `"overwrite"`, `"merge"`, or `"create_new"`. |
| `target_guid` | `Optional[str]` | `None` | Required iff `action` is `"overwrite"` or `"merge"`. |

**Action semantics (execution deferred to 013; 011 only defines + validates the vocabulary):**

- `"overwrite"` — source wins on every field (import golden). This is the historical single-write
  behavior and the seeded default (research D6), so introducing the three-way vocabulary does not
  change what an un-touched SIMILAR row does.
- `"merge"` — target-preserving fill-the-gaps: source content written only where the target field
  is empty.
- `"create_new"` — a fresh entry, no link. ("Keep target unchanged" is *not* an action — the user
  expresses it by leaving the item unchecked.)

**Invariant (in `SimilarResolution.__post_init__`, NOT `Selection.__post_init__`):**

- `action` MUST be one of `{"overwrite", "merge", "create_new"}` → else `ValueError`.
- `action` in `{"overwrite", "merge"}` MUST have a non-empty `target_guid` → else `ValueError`
  (FR-007).
- `action == "create_new"` with `target_guid=None` is valid; `create_new` with a non-None
  `target_guid` is rejected (symmetry with the other frozen types' strict invariants, e.g.
  `WSMappingChoice`).

Rationale for placement: this is a property of the type itself, like `MergeDecision` /
`WSMappingChoice` / `ExcludedLossy` invariants — placing it on `Selection.__post_init__` would
couple `Selection` to `SimilarResolution` internals and fire even when the map is unused
(research D6, lex-qc §3).

---

## Modified type — `Selection` (FR-008) — `Lib/models.py`

Add one field + one accessor, following the `leaf_item_picks` inert-when-off precedent **exactly**
(research D6):

```text
similar_resolutions: dict = field(default_factory=dict)   # dict[str, SimilarResolution]
                                                          # key = source entry GUID
```

- **No `__post_init__` guard** (deliberate, matching `leaf_item_picks`). A resolution for an entry
  that is not otherwise selected is inert — nothing in 011 reads the map.
- New accessor:

```text
def similar_resolution_for(self, guid: str) -> Optional[SimilarResolution]:
    return self.similar_resolutions.get(guid)   # None on absence; fabricate no default
```

- **FR-010 / SC-004 guarantee:** because no planner/closure/executor code path consults
  `similar_resolutions` in this feature, a `Selection` carrying it produces byte-identical plans to
  one without it. This holds by construction (the field simply rides the frozen struct).

---

## Modified type — `AffixRow` (FR-004) — `Lib/selection.py`

Append after the existing `status` field (tail, defaulted):

```text
suggested_target_guid: Optional[str] = None
```

- Populated **only when `status == "similar"`**, with the suggested target GUID for the row's
  normalized form (research D2 — first candidate = lowest HVO). `None` for NEW / IN-TARGET rows and
  whenever no target is bound.
- **`_merge_row_glosses` MUST forward it** on reconstruction (research D8 / lex-qc P1):
  `AffixRow(..., suggested_target_guid=row.suggested_target_guid)`.

## Modified type — `PosGroupedAffixInventory` (FR-005) — `Lib/selection.py`

Append after `roots` / `junk` (first defaulted field on this class; `= ()` is safe for an immutable
empty tuple, matching `ws_mapping_choices: tuple = ()`):

```text
target_affix_candidates: Tuple[SimilarCandidate, ...] = ()
```

- The flat, **deduplicated** (SC-002), **HVO-ascending** collection of every distinct target affix
  candidate across the source — the backing store for a global searchable dropdown. Empty when no
  target is bound. Tuple order is canonical (see `SimilarCandidate` ordering contract).

## Modified type — `PhonologyRow` (FR-006) — `Lib/selection.py`

Append after the existing `runs` field (tail, defaulted):

```text
matched_target_guid: Optional[str] = None
```

- Populated for SIMILAR phonology rows by resolving the row's casefold label through the
  collision-aware `label → target_guid` resolution (research D3 — lowest-HVO pick on collision,
  INFO-logged). `None` for NEW rows and when no target is bound.
- Phonology gets **no** interactive merge/create workflow in this feature (spec Assumptions) — only
  this match hint, for a later diff (012/014).

---

## Helper changes (capture logic) — `Lib/selection.py`

| Helper | Change | FR / research |
|--------|--------|----------------|
| `_build_target_sets(target)` | Return shape extended: `(guids, forms)` → `(guids, forms, form_to_candidates, all_candidates)`. Entries sorted HVO-ascending before building candidate tuples; `'?'` forms excluded. | FR-002 / D1,D2,D4 |
| `build_pos_grouped_inventory(...)` | Consume new shape; set `AffixRow.suggested_target_guid` for SIMILAR rows; carry `target_affix_candidates` onto the returned inventory. Single call site of `_build_target_sets` (@536). | FR-002/004/005 / D4 |
| `_suggested_target_guid_for(form, form_to_candidates)` (new) | Return first candidate's GUID for a form, else `None`. Leaves `_entry_status` unchanged. | FR-003 / D2 |
| `_phon_target_sets(target, accessor, *, phoneme=...)` | Return the collision-aware `label → target_guid` dict in addition to `(guids, labels)`; lowest-HVO pick + INFO log on collision. | FR-006 / D3,D5 |
| `build_phonology_inventory(...)` | Thread the per-category `label → guid` dict into row build; set `PhonologyRow.matched_target_guid` for SIMILAR rows. | FR-006 / D5 |
| `_merge_row_glosses(...)` | **FIX**: forward `suggested_target_guid` on `AffixRow` reconstruction. | D8 / lex-qc P1 |

See [contracts/target-set-builders.md](contracts/target-set-builders.md) for the exact old→new
return-shape signatures (the real contract surface).

## Back-compat & inertness summary

- All new fields defaulted and tail-appended → existing constructors/tests unmodified (FR-009, D7).
- `similar_resolutions` inert, unguarded → zero plan/closure/execution change (FR-010, SC-004, D6).
- No transfer, diff, wizard page, or widget added (FR-010).
