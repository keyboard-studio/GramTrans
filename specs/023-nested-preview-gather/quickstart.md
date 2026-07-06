# Quickstart: Nested Preview Field Gathering

Validation guide. Confirms the preview pane represents an affix's full nested structure and that no
MultiString custom field is silently dropped. See [data-model.md](data-model.md) and
[contracts/](contracts/) for shapes; do not duplicate implementation here.

## Prerequisites

- flexicon (pyflexicon) installed per repo README; test pair `Ejagham Mini` (source) →
  `Ejagham Full GT-Test` (target).
- Reference object: affix entry `n-1` (Lexeme Form `n`, morph type `prefix`), sense gloss `1.n`,
  grammatical info `n:NC`, two allomorphs (`m` with comment "before b, p, f, w?" + one more),
  MultiString custom field `Plural` (flid 5002502).

## Unit validation (Qt-free, no LCM)

Run: `python -m pytest tests/unit/test_merge_preview_service.py tests/unit/test_merge_preview_diff.py -q`

Expected coverage:
1. **Nested gather** — a fake entry with two senses + two allomorphs yields child fields under
   distinct join keys; both allomorphs and both senses appear (no collapse). (SC-002)
2. **Fingerprint join** — source & target fakes whose allomorph forms match share a key → per-field
   status computed; a source-only allomorph → all ADDED; a target-only allomorph → target-only. (FR-011)
3. **Ordering** — `display_name` = "Sense 1 ▸ Gloss", "Allomorph 1 ▸ Form", … in source order;
   scalar-only categories still render alphabetically (feature 012 SC-003 unregressed). (FR-005)
4. **MultiString CF fallback** — a fake CF ops whose `GetValue` raises the ITsMultiString
   AttributeError falls back to a `{ws: text}` read; a populated value appears; an empty one is
   suppressed; an unrecoverable one yields a read-failure note. (SC-004, FR-007)
5. **ITsString coercion** — child standard string fields render as text, never an object repr. (SC-003)
6. **Containment** — a child whose one field raises still contributes its other fields; the entry
   never blanks. (SC-005, FR-012)

## Live validation (FLExToolsMCP, read-only)

Against `Ejagham Full GT-Test`, gather affix `n-1` and assert the preview dict contains:
- `MorphType = prefix`; `Sense 1 ▸ Gloss = 1.n`; `Sense 1 ▸ Grammatical Info = n:NC`;
- `Allomorph 1 ▸ Form` and `Allomorph 2 ▸ Form` both present (distinct);
- `Allomorph … ▸ Comment = before b, p, f, w?`;
- `Slots`/`Category` from the MSA;
- `Plural` custom field present with a value **or** a visible read-failure note — never absent.

Sweep: over all affixes + stems, assert **zero** values render as `"<… object at 0x…>"` (SC-003) and
**zero** populated MultiString CFs are missing (SC-004).

## Preview-vs-Move parity (SC-006)

For an affix that already exists in the target, take a Move **preview** (plan-builder) and the nested
gather **pane** preview of the same entry; confirm the set of child fields shown equals the set Move
writes (no field shown that Move does not transfer; no non-empty field Move transfers omitted), and
that the child pairing (which allomorph maps to which) agrees.

## Expected outcome

Selecting affix `n-1` shows its Morph Type, Sense (gloss + grammatical info), MSA slots/category, and
**both** allomorphs with their forms/comments — matching the FLEx view — instead of only the Lexeme
Form. No MultiString custom field silently disappears.
