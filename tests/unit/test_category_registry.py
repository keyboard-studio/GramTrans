"""Lock the `Lib/categories.LEAF_CATEGORIES` registry shape.

Even before the per-category bodies are filled in (T039), the registry's
contract is fixed. These tests catch accidental signature drift.
"""
from __future__ import annotations

import pytest

from gramtrans.Lib import categories
from gramtrans.Lib.models import GrammarCategory


REQUIRED_KEYS = {
    "enumerate_source",
    "dependencies",
    "required_writing_systems",
    "plan_action",
    "execute_action",
}

LEAF_CATEGORIES = {
    GrammarCategory.GRAM_CATEGORIES,
    GrammarCategory.INFLECTION_FEATURES,
    GrammarCategory.CUSTOM_FIELDS,
    GrammarCategory.INFLECTION_CLASSES,
    GrammarCategory.STEM_NAMES,
    GrammarCategory.EXCEPTION_FEATURES,
    GrammarCategory.VARIANT_TYPES,
    GrammarCategory.COMPLEX_FORM_TYPES,
    GrammarCategory.ADHOC_COMPOUND_RULES,  # Phase 3c: unified per FR-341 (was ADHOC_RULES + COMPOUND_RULES)
    # Phase 3a (memo steps 2-5 + 4b + 5b) -- phonology block + strata.
    GrammarCategory.PHONOLOGICAL_FEATURES,
    GrammarCategory.PHONEMES,
    GrammarCategory.NATURAL_CLASSES,
    GrammarCategory.PH_ENVIRONMENT,  # relocated from HEAVY in Phase 3a
    GrammarCategory.PHONOLOGICAL_RULES,
    GrammarCategory.STRATA,
    # Phase 3b (memo step 13b) -- semantic domains; other 8 Phase 3b
    # categories already listed above.
    GrammarCategory.SEMANTIC_DOMAINS,
    # Phase 3c (memo steps 14-18) — registered as stubs; real callbacks
    # land in Phase 3c US1-US4. AFFIXES / AFFIX_TEMPLATES / SLOTS moved
    # from HEAVY to LEAF as part of the Phase 3c migration plan. STEMS is
    # new in Phase 3c.
    GrammarCategory.AFFIXES,
    GrammarCategory.SLOTS,
    GrammarCategory.AFFIX_TEMPLATES,
    GrammarCategory.STEMS,
}

# Heavy categories (MSAs, ALLOMORPH, ENTRY, SENSE, POS, WRITING_SYSTEMS_CHECK)
# live in inline verb-vertical / Layer-3 paths and are absent from the leaf
# registry. AFFIXES / AFFIX_TEMPLATES / SLOTS migrated to LEAF in Phase 3c
# (still served by inline paths during the migration window; leaf stubs
# raise NotImplementedError so duplicate planning does not occur).
HEAVY_CATEGORIES = {
    GrammarCategory.MSA,
    GrammarCategory.ALLOMORPH,
    # PH_ENVIRONMENT moved to LEAF_CATEGORIES in Phase 3a (memo step 4b).
    GrammarCategory.ENTRY,
    GrammarCategory.SENSE,
    GrammarCategory.POS,
    GrammarCategory.WRITING_SYSTEMS_CHECK,
}


def test_registry_contains_every_leaf_category() -> None:
    assert set(categories.LEAF_CATEGORIES.keys()) == LEAF_CATEGORIES


def test_each_entry_has_the_required_keys() -> None:
    for cat, bundle in categories.LEAF_CATEGORIES.items():
        assert set(bundle.keys()) == REQUIRED_KEYS, f"{cat.name} missing keys"


def test_dependencies_returns_empty_for_pure_leaves() -> None:
    """Pure leaf categories (no closure refs) MUST return empty tuples for
    dependencies. Non-pure leaves are allowed to raise NotImplementedError
    (they DO carry cross-references that the per-category callback must
    walk):
    - VARIANT_TYPES: references inflection features (FR-004)
    - NATURAL_CLASSES: IPhNCSegments.SegmentsRC references phonemes (Phase 3a)
    - PHONOLOGICAL_RULES: references phonemes + NCs + envs + stratum (FR-304)
    """
    non_pure = {
        GrammarCategory.VARIANT_TYPES,
        GrammarCategory.NATURAL_CLASSES,
        GrammarCategory.PHONOLOGICAL_RULES,
    }
    pure_leaves = LEAF_CATEGORIES - non_pure
    for cat in pure_leaves:
        bundle = categories.LEAF_CATEGORIES[cat]
        assert tuple(bundle["dependencies"](piece=object())) == ()


def test_for_category_dispatch_matches_registry() -> None:
    for cat in LEAF_CATEGORIES:
        assert categories.for_category(cat) is categories.LEAF_CATEGORIES[cat]


def test_for_category_raises_keyerror_for_heavy_categories() -> None:
    for cat in HEAVY_CATEGORIES:
        with pytest.raises(KeyError):
            categories.for_category(cat)


def test_unimplemented_body_raises_not_implemented_with_task_pointer() -> None:
    """Still-unimplemented bodies raise NotImplementedError with the task ID.

    Phase 3b shipped detect-and-skip for custom_fields (US2) and full
    implementations for variant_types / complex_form_types /
    semantic_domains (US3). The remaining stub category is
    adhoc_compound_rules (Phase 3c US4 — implementation lands at T056-T060).
    """
    bundle = categories.for_category(GrammarCategory.ADHOC_COMPOUND_RULES)
    with pytest.raises(NotImplementedError, match="Phase 3c T056"):
        bundle["enumerate_source"](context=object(), selection=object())
