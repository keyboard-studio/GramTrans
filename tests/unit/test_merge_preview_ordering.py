"""Tests for spec-023 nested-preview ordering & FieldWorks field order.

Covers the redesign that:
- orders entry-level scalars by the FieldWorks LexEntry detail/Normal layout
  (LexemeForm -> CitationForm -> Comment/Note -> LiteralMeaning -> Bibliography),
  not alphabetically;
- nests each sense's grammatical info (MSA) UNDER its own sense rather than in
  a detached trailing group;
- orders top-level groups entry(0) -> senses(1) -> allomorphs(2);
- renders one bold group header per child group with its fields indented.

All tests are pure -- no Qt, no LCM.
"""

from __future__ import annotations

from gramtrans.Lib.merge_preview import (
    NEW,
    OVERWRITE,
    DiffSegment,
    FieldDiff,
    MergePreview,
    SegmentKind,
    _entry_scalar_meta,
    _grammar_scalar_meta,
    diff_props,
    to_html,
)
from gramtrans.Lib.ws_fonts import WsFont, WsFontRegistry, WsRole


def _no_role(_wid):
    return None


US = "\x1f"  # unit separator used inside nested-child machine keys


def _mk(kind: str, tok: str, field: str) -> str:
    """Build a machine-key-shaped string (kind\\x1ftoken\\x1ffield)."""
    return f"{kind}{US}{tok}{US}{field}"


# ============================================================================
# _entry_scalar_meta — FieldWorks scalar order + labels + custom-field placement
# ============================================================================


class TestEntryScalarMeta:
    def test_standard_fields_get_fieldworks_order(self):
        # Deliberately reversed / shuffled input order.
        keys = ["Bibliography", "Comment", "LexemeForm", "LiteralMeaning", "CitationForm"]
        meta = _entry_scalar_meta(keys)
        # sort_key = ((0, 0), field_order); pull field_order for each.
        order = {k: meta[k][1][1] for k in keys}
        assert order["LexemeForm"] < order["CitationForm"] < order["Comment"]
        assert order["Comment"] < order["LiteralMeaning"] < order["Bibliography"]

    def test_labels_are_prettified(self):
        meta = _entry_scalar_meta(["LexemeForm", "CitationForm", "Comment"])
        assert meta["LexemeForm"][0] == "Lexeme Form"
        assert meta["CitationForm"][0] == "Citation Form"
        assert meta["Comment"][0] == "Note"  # FLEx entry-level label

    def test_scalars_are_entry_level_no_group(self):
        meta = _entry_scalar_meta(["LexemeForm"])
        _dn, sk, indent, group = meta["LexemeForm"]
        assert indent == 0
        assert group == ""
        assert sk[0] == (0, 0)  # kind_rank 0 -> sorts before any child group

    def test_object_custom_fields_sort_after_standard(self):
        meta = _entry_scalar_meta(["Bibliography", "CustomField.Tone"])
        std = meta["Bibliography"][1][1]
        cf = meta["CustomField.Tone"][1][1]
        assert cf > std
        # Label strips the CustomField. prefix, stays entry-level.
        assert meta["CustomField.Tone"][0] == "Tone"
        assert meta["CustomField.Tone"][3] == ""

    def test_nested_child_keys_are_skipped(self):
        # Keys containing the unit separator belong to _gather_entry_nested.
        meta = _entry_scalar_meta([_mk("sense", "abc", "Gloss"), "LexemeForm"])
        assert _mk("sense", "abc", "Gloss") not in meta
        assert "LexemeForm" in meta


# ============================================================================
# _grammar_scalar_meta — Name/Abbreviation/Description-first for grammar objects
# ============================================================================


class TestGrammarScalarMeta:
    def test_name_abbrev_description_lead(self):
        meta = _grammar_scalar_meta(["Description", "Name", "Abbreviation"])
        order = {k: meta[k][1][1] for k in meta}
        assert order["Name"] < order["Abbreviation"] < order["Description"]

    def test_members_and_values_after_description(self):
        meta = _grammar_scalar_meta(["Members", "Values", "Description", "Name"])
        order = {k: meta[k][1][1] for k in meta}
        assert order["Description"] < order["Members"]
        assert order["Description"] < order["Values"]

    def test_unknown_field_sorts_after_known(self):
        meta = _grammar_scalar_meta(["Zebra", "Name"])
        assert meta["Zebra"][1][1] > meta["Name"][1][1]

    def test_custom_field_label_stripped_and_last(self):
        meta = _grammar_scalar_meta(["CustomField.Tone", "Name"])
        assert meta["CustomField.Tone"][0] == "Tone"
        assert meta["CustomField.Tone"][1][1] > meta["Name"][1][1]

    def test_all_grammar_fields_are_entry_level(self):
        meta = _grammar_scalar_meta(["Name", "Members"])
        for _k, (_dn, _sk, indent, group) in meta.items():
            assert indent == 0 and group == ""


# ============================================================================
# diff_props — end-to-end ordering with a props_for-shaped meta map
# ============================================================================


def _entry_like():
    """A source-entry props dict + meta mimicking props_for's entry output.

    Two senses (sense 2 declared first to prove sort, not insertion order),
    each with Gloss + Grammatical Info, plus one allomorph, plus scalars.
    """
    s1 = "s1tok"
    s2 = "s2tok"
    a1 = "a1tok"
    props = {
        # scalars (reversed vs FieldWorks order on purpose)
        "Bibliography": {"en": "Smith 1999"},
        "LexemeForm": {"koh": "-ung"},
        "CitationForm": {"koh": "-ung"},
        # sense 2 first
        _mk("sense", s2, "Gloss"): {"en": "instrument"},
        _mk("sense", s2, "Grammatical Info"): "n",
        # sense 1
        _mk("sense", s1, "Gloss"): {"en": "act of X"},
        _mk("sense", s1, "Grammatical Info"): "n",
        # allomorph
        _mk("allomorph", a1, "Form"): {"koh": "-ung"},
    }
    meta = {}
    meta.update(_entry_scalar_meta(["Bibliography", "LexemeForm", "CitationForm"]))
    # nested meta (as _gather_entry_nested would emit): ((kind_rank, ordinal), field_order)
    meta[_mk("sense", s1, "Gloss")] = ("Gloss", ((1, 1), 0), 1, "Sense 1")
    meta[_mk("sense", s1, "Grammatical Info")] = ("Grammatical Info", ((1, 1), 2), 1, "Sense 1")
    meta[_mk("sense", s2, "Gloss")] = ("Gloss", ((1, 2), 0), 1, "Sense 2")
    meta[_mk("sense", s2, "Grammatical Info")] = ("Grammatical Info", ((1, 2), 2), 1, "Sense 2")
    meta[_mk("allomorph", a1, "Form")] = ("Form", ((2, 1), 0), 1, "Allomorph 1")
    return props, meta


class TestDiffPropsOrdering:
    def test_full_top_to_bottom_order(self):
        props, meta = _entry_like()
        result = diff_props(props, None, NEW, _no_role, meta=meta)
        seq = [(fd.group, fd.display_name) for fd in result.fields]
        assert seq == [
            ("", "Lexeme Form"),
            ("", "Citation Form"),
            ("", "Bibliography"),
            ("Sense 1", "Gloss"),
            ("Sense 1", "Grammatical Info"),
            ("Sense 2", "Gloss"),
            ("Sense 2", "Grammatical Info"),
            ("Allomorph 1", "Form"),
        ]

    def test_grammatical_info_nests_under_its_own_sense(self):
        # Regression: MSA must not float below other senses.
        props, meta = _entry_like()
        result = diff_props(props, None, NEW, _no_role, meta=meta)
        groups = [fd.group for fd in result.fields]
        first_sense2 = groups.index("Sense 2")
        # Every Sense 1 field (incl. its Grammatical Info) precedes any Sense 2 field.
        s1_positions = [i for i, g in enumerate(groups) if g == "Sense 1"]
        assert all(i < first_sense2 for i in s1_positions)

    def test_scalars_carry_entry_indent_children_indent_one(self):
        props, meta = _entry_like()
        result = diff_props(props, None, NEW, _no_role, meta=meta)
        for fd in result.fields:
            if fd.group == "":
                assert fd.indent == 0
            else:
                assert fd.indent == 1

    def test_target_only_child_key_is_labeled_not_raw(self):
        # Mirrors the OVERWRITE case where the target sense's gloss differs from
        # the source's, so it joins on a different token -> a target-only key.
        # With target meta merged in (as preview_for now does), it must render
        # with a proper group/label, never the raw "sense\x1f...\x1fGloss" key.
        s_src = _mk("sense", "srctok", "Gloss")
        s_tgt = _mk("sense", "tgttok", "Gloss")
        src_props = {"LexemeForm": {"etu": "e"}, s_src: {"en": "5.n"}}
        tgt_props = {"LexemeForm": {"etu": "e"}, s_tgt: {"en": "5"}}
        meta = {}
        meta.update(_entry_scalar_meta(["LexemeForm"]))
        meta[s_src] = ("Gloss", ((1, 1), 0), 1, "Sense 1")       # source meta
        meta[s_tgt] = ("Gloss", ((1, 1), 0), 1, "Sense 1")       # merged target meta
        result = diff_props(src_props, tgt_props, OVERWRITE, _no_role, meta=meta)
        by_key = {fd.field_name: fd for fd in result.fields}
        assert by_key[s_tgt].display_name == "Gloss"     # not the raw key
        assert by_key[s_tgt].group == "Sense 1"
        assert US not in (by_key[s_tgt].display_name or "")

    def test_no_meta_still_alphabetical(self):
        # Non-entry categories pass meta=None -> unchanged alphabetical behavior.
        props = {"Zeta": "z", "Alpha": "a"}
        result = diff_props(props, None, NEW, _no_role)
        assert [fd.field_name for fd in result.fields] == ["Alpha", "Zeta"]


# ============================================================================
# to_html — group-header rendering
# ============================================================================


def _registry():
    return WsFontRegistry(
        {
            WsRole.VERNACULAR: WsFont(ws_id="koh", font_name="Doulos SIL", size_pt=12.0, rtl=False),
            WsRole.ANALYSIS: WsFont(ws_id="en", font_name="Arial", size_pt=10.0, rtl=False),
        }
    )


class TestGroupHeaderRendering:
    def _grouped_preview(self):
        seg = (DiffSegment(text="x", kind=SegmentKind.UNCHANGED, ws_role=None),)
        fields = (
            FieldDiff("LexemeForm", seg, indent=0, display_name="Lexeme Form", sort_key=((0, 0), 0)),
            FieldDiff(_mk("sense", "s1", "Gloss"), seg, indent=1, display_name="Gloss",
                      sort_key=((1, 1), 0), group="Sense 1"),
            FieldDiff(_mk("sense", "s1", "Grammatical Info"), seg, indent=1,
                      display_name="Grammatical Info", sort_key=((1, 1), 2), group="Sense 1"),
        )
        return MergePreview(status="new", fields=fields)

    def test_group_header_emitted_once_per_group(self):
        html = to_html(self._grouped_preview(), _registry())
        assert html.count("<b>Sense 1</b>") == 1

    def test_entry_scalar_has_no_group_header(self):
        html = to_html(self._grouped_preview(), _registry())
        # The scalar's own label is bold, but no header row precedes it.
        assert html.index("<b>Lexeme Form</b>") < html.index("<b>Sense 1</b>")

    def test_child_fields_indented(self):
        html = to_html(self._grouped_preview(), _registry())
        assert "margin-left:16px" in html  # indent == 1 -> 16px

    def test_group_header_has_divider(self):
        html = to_html(self._grouped_preview(), _registry())
        assert "border-top" in html  # visual divider between sections

    def test_promoted_field_with_explicit_empty_group_has_no_header(self):
        # A machine-keyed field WITH a display_name but an explicit empty group
        # (e.g. the lexeme form's promoted Morph Type) must not get a fallback
        # "Lexeme" divider header.
        seg = (DiffSegment(text="ubd stem", kind=SegmentKind.UNCHANGED, ws_role=None),)
        key = _mk("lexeme", "lexeme_form", "Morph Type")
        prev = MergePreview(status="in_target", fields=(
            FieldDiff(key, seg, indent=0, display_name="Morph Type",
                      sort_key=((0, 0), 0.5), group=""),
        ))
        html = to_html(prev, _registry())
        assert "<b>Lexeme</b>" not in html   # no spurious fallback header
        assert "<b>Morph Type</b>" in html

    def test_machine_key_never_leaks_when_meta_missing(self):
        # A nested-child FieldDiff with no display_name/group (e.g. a target-only
        # key absent from source meta) must NOT render the raw "kind\x1ftoken\x1ffield".
        seg = (DiffSegment(text="5", kind=SegmentKind.UNCHANGED, ws_role=None),)
        key = _mk("sense", "ff96c412", "Gloss")
        prev = MergePreview(status="in_target", fields=(
            FieldDiff(key, seg, indent=1),  # no display_name, no group, no sort_key
        ))
        html = to_html(prev, _registry())
        assert US not in html                 # no unit-separator tofu
        assert "ff96c412" not in html         # no token leak
        assert "<b>Gloss</b>" in html         # falls back to the field segment
        assert "<b>Sense</b>" in html         # kind becomes the group header
