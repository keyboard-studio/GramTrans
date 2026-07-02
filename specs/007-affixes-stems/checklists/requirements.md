# Specification Quality Checklist: Phase 3c — Affixes / Stems / Templates Block

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-06-22
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

- FR-331..341 reference `GrammarCategory` enum members and module paths
  (`Lib/preview.py`, `Lib/transfer.py`, `_LEAF_DISPATCH_CATEGORIES`,
  `_create_with_guid`). Same precedent as Phase 3a/3b — these are
  contract-level names inherited from the leaf-dispatch pattern, not new
  implementation details.
- LCM class names (`IMoMorphType.IsAffixType`, `IMoEndoCompound`,
  `IMoExoCompound`, `IMoInflAffMsa`, `IMoStemMsa`, `LexEntryRef.ComponentLexemesRS`)
  appear in FRs because the affix/stem partition and compound-rule
  subclass dispatch are domain semantics, not implementation choices.
  This is the same posture Phase 3a took for phonology classes.
- Acceptance scenarios are encoded compactly in the user-story
  one-liners + the dependency column of the categories table; explicit
  Given/When/Then scenarios will be expanded by `/speckit-plan`'s
  quickstart.md against the live Ejagham Mini → Ejagham Full GT-Test
  fixture (matching the Phase 3a/3b precedent).
- Edge cases are covered by the named `Skip(...)` reasons in FR-332
  (`DEPENDENCY_UNRESOLVED`), FR-333 (deferred MSA-slot wiring),
  FR-334 (`ALREADY_PRESENT_BY_GUID` collision guard), FR-335 / FR-340
  (`DEPENDENCY_UNRESOLVED` on unresolved refs), and FR-341
  (`NEEDS_MANUAL` on unknown compound subclasses).
- SC-301 carries a forward-looking entity-count estimate. Actual
  Ejagham Mini counts will be refined by `/speckit-plan` MCP probes
  before `/speckit-tasks` fans out.
