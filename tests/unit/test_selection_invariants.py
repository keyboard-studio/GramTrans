"""T025: Selection invariants (data-model.md E2)."""

from __future__ import annotations

import pytest

from gramtrans.Lib.models import GrammarCategory, Selection


def test_affix_picks_require_affixes_category_on() -> None:
    with pytest.raises(ValueError, match="affix_picks non-empty requires"):
        Selection(
            categories={GrammarCategory.AFFIXES: False},
            affix_picks=frozenset({"some-guid"}),
        )


def test_template_picks_require_templates_category_on() -> None:
    with pytest.raises(ValueError, match="template_picks non-empty requires"):
        Selection(
            categories={GrammarCategory.AFFIX_TEMPLATES: False},
            template_picks=frozenset({"some-guid"}),
        )


def test_empty_picks_with_category_on_means_all_in_category() -> None:
    # Sentinel: AFFIXES=True + affix_picks=frozenset() → "all affixes".
    s = Selection(
        categories={GrammarCategory.AFFIXES: True},
        affix_picks=frozenset(),
    )
    assert s.affix_picks == frozenset()
    assert s.categories[GrammarCategory.AFFIXES] is True


def test_closure_defaults_to_on() -> None:
    s = Selection(categories={GrammarCategory.AFFIXES: True})
    assert s.include_closure is True
