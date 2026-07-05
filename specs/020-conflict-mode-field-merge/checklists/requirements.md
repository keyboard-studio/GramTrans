# Specification Quality Checklist: Conflict-Mode UI & Field-Level Merge (020)

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-07-05
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs) — *note: this spec intentionally
      names existing internal model surfaces (`ConflictMode`, `conflict.py`, `GetSyncableProperties`)
      because it is a surface-and-wire feature over a documented in-repo machinery; the constitution's
      probe-before-claim discipline requires citing them. User-facing behavior is stated in FR/US terms.*
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders (user stories + acceptance scenarios lead)
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded (three tiers; MERGE-field-resolution and disposition model excluded to amendment)
- [x] Dependencies and assumptions identified (incl. plan-verified caveats + blocked categories)

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows (US1–US5)
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak beyond the sanctioned machinery references

## Notes

- Updated in place 2026-07-05 to match `/speckit-plan` verification (live FLExTools MCP probes +
  LEX crew): US2/FR-003 field-resolution is `OVERWRITE`-only; FR-012 split into uniform selector
  vs. conditional field-detection; FR-013 (field scope = scalar/text + atomic RA) and FR-014
  (Phonemes/Environments blocked by flexicon defect) added; Assumptions record the three surfaces
  to add (`allowed_modes_for`, `_OW_OPS` coverage, fail-closed `_is_protected`) and the post-020
  disposition-model amendment.
- Consider running `/speckit-clarify` only if the tier assignment for MorphRule (Tier A pending a
  live re-probe, plan R2a) needs to be pinned before `/speckit-tasks`.
