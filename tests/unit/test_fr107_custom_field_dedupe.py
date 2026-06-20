"""FR-107: custom-field deduplication in overwrite executor.

The helper `_dedupe_custom_fields` filters `src_props` so that custom
fields whose value already matches the target's pre-overwrite value are
NOT re-written (no-op optimization).  Same key + different value -> kept
(source wins, FR-109).  Target-only keys -> preserved by virtue of
ApplySyncableProperties only touching keys it receives (not exercised
here; that's the caller's responsibility).
"""
from __future__ import annotations

from gramtrans.Lib.transfer import _dedupe_custom_fields


def test_identical_custom_field_dropped():
    src = {"Custom_Topic": "verbs", "CitationForm": "ko"}
    tgt = {"Custom_Topic": "verbs", "CitationForm": "ko-old"}
    out = _dedupe_custom_fields(src, tgt)
    assert "Custom_Topic" not in out
    assert out["CitationForm"] == "ko"  # non-custom always kept


def test_differing_custom_field_kept():
    src = {"Custom_Topic": "verbs"}
    tgt = {"Custom_Topic": "nouns"}
    out = _dedupe_custom_fields(src, tgt)
    assert out["Custom_Topic"] == "verbs"  # source wins


def test_target_only_custom_field_does_not_appear_in_src():
    src = {"Custom_A": "x"}
    tgt = {"Custom_A": "x", "Custom_B": "preserved-in-target"}
    out = _dedupe_custom_fields(src, tgt)
    assert "Custom_B" not in out  # not in src -> not in apply set; target keeps it
    assert "Custom_A" not in out  # identical -> dropped


def test_non_custom_keys_always_kept_even_when_identical():
    src = {"CitationForm": "ko", "HomographNumber": 0}
    tgt = {"CitationForm": "ko", "HomographNumber": 0}
    out = _dedupe_custom_fields(src, tgt)
    assert out == src  # FR-109 source-wins applies to non-custom regardless


def test_empty_target_pre_props():
    src = {"Custom_A": "x", "Comment": "hi"}
    out = _dedupe_custom_fields(src, {})
    assert out == src  # nothing to dedup against


def test_empty_source_props():
    out = _dedupe_custom_fields({}, {"Custom_A": "x"})
    assert out == {}


def test_non_dict_src_passes_through():
    """Robustness: non-dict src returned unchanged (no crash)."""
    sentinel = object()
    assert _dedupe_custom_fields(sentinel, {}) is sentinel


def test_non_dict_tgt_passes_through():
    src = {"Custom_A": "x"}
    assert _dedupe_custom_fields(src, None) is src


def test_returns_new_dict_does_not_mutate_src():
    src = {"Custom_A": "x", "Comment": "hi"}
    tgt = {"Custom_A": "x"}
    out = _dedupe_custom_fields(src, tgt)
    assert out is not src
    assert "Custom_A" in src  # input unchanged


def test_value_equality_uses_eq():
    """Lists, dicts, tuples should dedup on structural equality."""
    src = {"Custom_Tags": ["a", "b"]}
    tgt = {"Custom_Tags": ["a", "b"]}
    out = _dedupe_custom_fields(src, tgt)
    assert "Custom_Tags" not in out


def test_value_inequality_keeps_value():
    src = {"Custom_Tags": ["a", "b", "c"]}
    tgt = {"Custom_Tags": ["a", "b"]}
    out = _dedupe_custom_fields(src, tgt)
    assert out["Custom_Tags"] == ["a", "b", "c"]
