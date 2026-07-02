# Specification Quality Checklist: Phonology Selector (Model-B Independent Block)

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-07-02
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- Model-B default state (ALL vs NONE) resolved during specification via user decision:
  **ALL-preselected**, recorded in FR-003 and Assumptions.
- Engine layer (spec 005) is pre-existing and live-verified; this spec is UI/selection only.
  Some references to `Lib/preview.py` / `Lib/transfer.py` / callback names appear in FR-008
  as *integration boundaries* (naming the existing engine seam the page feeds), not as
  prescribed implementation — acceptable per the "wire into existing system" pattern also
  used in spec 009.
- Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`.

## LEX crew review — cycle 1 (2026-07-02, verdict: READY-AFTER-EDITS, all edits applied)

Reviewed by lex-domain (LCM correctness), lex-author (completeness), Explore (cross-doc),
synthesized by lex-lead. Nine must-fix edits applied:

1. **FR-010 chain corrected** (domain): dropped the wrong `rules → environments` edge
   (`IPhEnvironment` is allomorph-side via `PhoneEnvRC`, not rule-side); added the missing
   direct `rule → phoneme` edge (`IPhSimpleContextSeg`). Chain now: rules → (inline context:
   NCs and/or phonemes) → phonemes → features.
2. **US5 "Why" para** rewritten to the corrected chain.
3. **US5 acceptance scenario 3** added for the direct rule→phoneme stranding case.
4. **FR-009 + US3 + SC-004 + Edge Cases**: strata now gated on a phonological RULE being in
   the plan (only `IPhPhonologicalRule.StratumRA` references strata), not on "any phonology."
5. **SC-006** reworded from "per stranded reference" → "per kept item with an unresolvable
   reference" (entry-centric, matching FR-010 and 009 SC-006).
6. **SC-007** added (page-order testability for FR-001).
7. **FR-008** untestable clause moved to Assumptions; SC-008 added for FR-012 (no conflict UI).
8. **Empty-block tristate** edge case added (toggle reads unchecked/disabled, not vacuously
   selected).
9. P2 folded in: shared-009-Move-gate dependency + no-target warning policy in Assumptions;
   cross-block-closure gap clarified.

Advisory / not blocking: 009's FR-013 page-order string omits Phonology (predates this page)
— track a one-line doc-consistency touch to 009 when 010 lands.
