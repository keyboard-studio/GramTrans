# Phase 0 Research: Similar-Candidate Capture & Per-Item Resolution Data Model (011)

All decisions below were validated read-only against a **live** FLEx repository via the
FLExTools MCP (`flexlibs2` mode, `write_enabled=false`, project **Ejagham Full GT-Test** —
the validated target from `STATUS.md`). The MCP is the user's declared source of truth for
this plan. Where a decision rests on empirical data, the concrete probe result is quoted so a
later reader can see the ground truth without re-running the probe.

## Canonical definition — deterministic order (referenced by D2 and D3)

**Deterministic order = HVO ascending.** Every candidate tuple and every label-collision pick in
this feature resolves ties by the LCM object's `Hvo` (the sequential creation-order integer),
ascending. HVO was confirmed readable on 100% of probed objects (33/33 affixes; all probed
phonemes / natural classes / environments). This single rule is the normative source for
SC-001/SC-002 reproducibility; D2 and D3 both reference it rather than restating it.

Rationale for HVO over GUID-string: GUIDs are random (UUID v4), so GUID-string order is stable
but arbitrary; HVO order is stable **and** creation-ordered, so "first candidate = suggested
match" (FR-003) picks the earliest-created target entry — the linguistically more canonical one —
and matches FLEx's own default list ordering.

---

## D1 — Affix candidates are an *ordered tuple*, because form collisions are real

**Decision:** `_build_target_sets` produces `normalized_form → Tuple[SimilarCandidate, ...]`
(ordered, possibly length > 1), plus a flat deduped all-candidates collection. `SimilarCandidate`
is `(target_guid, form, gloss)` (FR-001).

**Rationale — LIVE EVIDENCE (Ejagham Full GT-Test):** multi-candidate collision is not
theoretical, it is pervasive. Of 33 affix entries yielding 21 distinct normalized forms, **7
forms collide** (map to ≥2 distinct affix GUIDs):

| normalized form | # distinct target GUIDs | glosses |
|-----------------|-------------------------|---------|
| `n`  | 5 | 1.n / 9pl.n / 3pl.n / 3sg.n / 9sg.n |
| `a`  | 3 | 3s:PFV / 6 / 2 |
| `ń~` | 3 | 1sg.COND / 1sg.HORT / 1sg.RET |
| `á`  | 2 | 6.num / 2.num |
| `í`  | 2 | 8.num / 8 |
| `n~` | 2 | 1sg.PFV / 1sg.NEUT |
| (1 more) | 2 | — |

A `dict[form → single guid]` would silently collapse 4 of the 5 `n`-candidates. The ordered-tuple
shape is therefore empirically required, not defensive speculation.

**Alternatives considered:** (a) single-best-match dict — rejected, loses real candidates;
(b) unordered set of candidates — rejected, breaks FR-003's "first candidate = suggested match".

## D2 — Candidate ordering and the suggested match

**Decision:** within each form's candidate tuple, candidates are sorted **deterministic order**
(see canonical definition — HVO ascending) **at build time**, before the tuple is frozen. The
suggested target GUID for a form (FR-003) is the first candidate's `target_guid`, or `None` when
the form has no candidates. Downstream consumers treat tuple order as canonical and MUST NOT
re-sort (see data-model.md contract on `target_affix_candidates`).

**Rationale:** the current `_build_target_sets` iterates
`target.Cache.LangProject.LexDbOA.Entries` whose order is not guaranteed stable across sessions,
so an explicit sort is required for SC-001. HVO is readable on all 33 live affixes, so the sort key
is always available; entries with an unreadable HVO (none observed) sort last deterministically.

## D3 — FR-006 phonology label→GUID is a collision-aware (many-to-one) resolution, not a naive map

**Decision:** `_phon_target_sets` gains, alongside its existing `(guids, labels)` sets, a
`label → target_guid` resolution whose **output is a single GUID** obtained by a deterministic
lowest-HVO pick **when the casefold label maps to multiple target objects**. Every collapse is
logged at `INFO` (naming the label + the chosen GUID) so the choice is auditable. `PhonologyRow.matched_target_guid`
is populated for SIMILAR rows by looking the row's casefold label up in this resolution; NEW rows
and the no-target case leave it `None`.

**Rationale — LIVE EVIDENCE (Ejagham Full GT-Test):** label collision within a single phonology
category is real:

| category | items | distinct nonblank labels | colliding labels |
|----------|-------|--------------------------|------------------|
| Phonemes | 64 | 32 | **0** |
| NaturalClasses | 10 | 5 | **5 (all)** — Consonants×2, Labials×2, Nasal Consonants×2, Syllabic Nasal×2 |
| Environments | 5 | 1 | 0 |

Every natural-class name in the live target maps to two distinct GUIDs. (This is exactly
GramTrans's real operating condition: the target may already carry partial/duplicate data from
prior transfers — GT-Test is a repeatedly-written throwaway target.) A naive `dict[label → guid]`
would be order-dependent; the lowest-HVO pick makes it reproducible. The map's **input is
many-to-one**; its **output is single-valued** — the plan deliberately avoids the unqualified
phrase "single-valued map" so as not to deny the documented collision.

**Alternatives considered:** (a) `frozenset`-valued map exposing all candidate GUIDs to the
PhonologyRow — rejected for 011: phonology gets no interactive merge/create workflow (spec
Assumptions), so a single deterministic match hint is sufficient and keeps the 012/014 consumer
simple; a frozenset would push ambiguity resolution into the UI with no phonology UI to resolve it.
(b) Skip `matched_target_guid` when a collision occurs — rejected, would leave the majority of
Ejagham NC SIMILAR rows with no diff anchor.

## D4 — `_build_target_sets` return-shape extension is contained to one caller

**Decision:** extend `_build_target_sets(target)` from returning `(target_guids, target_forms)` to
additionally returning the form→candidates map and the flat all-candidates collection. Update its
sole caller `build_pos_grouped_inventory` (selection.py:536) to consume the new shape and to set
`AffixRow.suggested_target_guid` (only when the row's status is SIMILAR).

**Rationale — STATIC EVIDENCE (lex-qc sweep):** grep confirms `_build_target_sets` has **exactly
one** active call site (selection.py:536); the only other hit (selection.py:1992) is a comment
reference. No hidden consumer depends on the 2-tuple shape, so the change is safe and localized.
See [contracts/target-set-builders.md](contracts/target-set-builders.md).

## D5 — `_phon_target_sets` gains a label→guid dict threaded to the PhonologyRow builder

**Decision:** `_phon_target_sets(target, accessor, *, phoneme=...)` returns, in addition to
`(guids, labels)`, the collision-aware `label → target_guid` resolution from D3.
`build_phonology_inventory` threads that dict per-category into the row build so a SIMILAR
`PhonologyRow` records the matched target GUID. Interactive re-linking for phonology stays out of
scope (spec Assumptions); only the match hint is captured.

**Rationale:** `_phon_target_sets` today returns only a `Set[str]` of labels (enough for the
existing SIMILAR *status*, insufficient for a *matched GUID*). D5 is the minimal extension that
makes FR-006 realizable without touching the status logic. See
[contracts/target-set-builders.md](contracts/target-set-builders.md).

## D6 — `similar_resolutions` follows the `leaf_item_picks` inert-when-off precedent exactly

**Decision:** `Selection.similar_resolutions: dict = field(default_factory=dict)` with **no**
`__post_init__` guard, plus `similar_resolution_for(guid)` returning `self.similar_resolutions.get(guid)`
(None on absence, no fabricated default). `SimilarResolution`'s own invariant — action ∈
`{overwrite, merge, create_new}`, with both `overwrite` and `merge` requiring a `target_guid` and
`create_new` requiring none — lives in `SimilarResolution.__post_init__`, not in
`Selection.__post_init__`.

**Action semantics (spec 2026-07-03 three-way split):** `overwrite` = source wins on every field
(import golden; this is the historical single-write behavior and the seeded default so the new
vocabulary changes nothing for an un-touched SIMILAR row); `merge` = target-preserving fill-the-gaps
(source written only where the target field is empty); `create_new` = fresh entry, no link. 011
defines and validates the vocabulary only — execution of each action is 013's concern (FR-010).

**Rationale — STATIC EVIDENCE (lex-qc, 91/100):** this mirrors `leaf_item_picks` (models.py
~291–303) whose deliberate no-guard comment explains that a stale key for an off category is
harmless because the dispatch gate fires first. Because no planner/closure code reads
`similar_resolutions` in 011, FR-010 inertness and SC-004 byte-identical plans hold by
construction. The guarded `affix_picks`/`template_picks`/`pos_picks` pattern is deliberately **not**
used (those couple to `categories`; `similar_resolutions` must not).

## D7 — Back-compat via tail-appended defaulted fields (FR-009)

**Decision:** append every new field at the tail of its frozen dataclass with a `= None` / `= ()` /
`default_factory` default: `AffixRow.suggested_target_guid = None` (after `status`);
`PhonologyRow.matched_target_guid = None` (after `runs`);
`PosGroupedAffixInventory.target_affix_candidates: Tuple[SimilarCandidate, ...] = ()` (after
`roots`/`junk`); `Selection.similar_resolutions = field(default_factory=dict)` (tail).

**Rationale — STATIC EVIDENCE (lex-qc back-compat sweep):** all existing constructors use keyword
args or the safe 7-positional-then-`status=`-keyword form; tail-appended defaults shift no
positional argument. `= ()`/`= None` match the file's existing convention (`ws_mapping_choices:
tuple = ()`). Sweep verdict: **SAFE**, no breakers across production or `tests/unit/`.

## D8 — Carry-forward defect: `_merge_row_glosses` must forward the new field (lex-qc P1)

**Decision:** `_merge_row_glosses` (selection.py:806–814), which reconstructs an `AffixRow` by
field name during gloss-merge, MUST add `suggested_target_guid=row.suggested_target_guid` to the
reconstruction. A regression fixture asserts a SIMILAR affix row surviving a gloss-merge retains
its suggestion.

**Rationale:** without the forward, a SIMILAR row whose entry contributes two MSAs to the same
POS/role (triggering the merge path) would silently reset `suggested_target_guid` to `None`,
dropping the very hint FR-004 exists to carry. Recorded here and as a discrete task so it does not
leak into implementation as an unnoticed regression.

---

## Resolved unknowns

All `NEEDS CLARIFICATION` items are resolved:

- Multi-candidate cardinality (affix) — RESOLVED: real, ordered tuple (D1).
- FR-006 label-map cardinality — RESOLVED: collision-aware, lowest-HVO pick, INFO log (D3).
- Ordering determinism — RESOLVED: HVO ascending, one canonical rule (D2/D3).
- Inert-pattern conformance — RESOLVED: `leaf_item_picks` precedent (D6).
- Back-compat safety — RESOLVED: tail-appended defaults, sweep clean (D7).
