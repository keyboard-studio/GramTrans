"""Tests for feature 012 — User Story 2: to_html rendering.

Covers T018–T021:
- Escaping: HTML metacharacters escaped; repr() output not mangled.
- Per-role font + RTL: RTL font → dir='rtl'; LTR → no rtl attr.
- Color + strike + indent: added green, removed red+strike, note gray italic.
- Chrome path: ws_role=None → default font (no font span attributes).

All tests pure — no Qt, no LCM.
"""

from __future__ import annotations

from gramtrans.Lib.merge_preview import (
    OVERWRITE,
    DiffSegment,
    FieldDiff,
    MergePreview,
    SegmentKind,
    diff_props,
    to_html,
)
from gramtrans.Lib.ws_fonts import WsFont, WsFontRegistry, WsRole

# ============================================================================
# Helpers — fabricated registries
# ============================================================================


def _make_registry(vern_rtl=False, anal_rtl=False, ipa_rtl=False) -> WsFontRegistry:
    return WsFontRegistry(
        {
            WsRole.VERNACULAR: WsFont(
                ws_id="koh", font_name="Doulos SIL", size_pt=12.0, rtl=vern_rtl
            ),
            WsRole.ANALYSIS: WsFont(ws_id="en", font_name="Arial", size_pt=10.0, rtl=anal_rtl),
            WsRole.IPA: WsFont(
                ws_id="koh-fonipa", font_name="Charis SIL", size_pt=11.0, rtl=ipa_rtl
            ),
        }
    )


def _make_preview(
    field_name: str,
    segments: list,
    indent: int = 0,
    status: str = "similar",
    notes=(),
) -> MergePreview:
    return MergePreview(
        status=status,
        fields=(FieldDiff(field_name=field_name, segments=tuple(segments), indent=indent),),
        notes=tuple(notes),
    )


# ============================================================================
# T018 — Escaping
# ============================================================================


class TestEscaping:
    def test_html_metacharacters_escaped(self):
        """<, >, &, " in text must be escaped in output."""
        seg = DiffSegment(
            text='<script>alert("xss")</script> & more',
            kind=SegmentKind.ADDED,
            ws_role=None,
        )
        preview = _make_preview("Danger", [seg])
        html_out = to_html(preview, WsFontRegistry.empty())
        assert "<script>" not in html_out
        assert "&lt;script&gt;" in html_out
        assert "&amp;" in html_out

    def test_repr_fallback_not_mangled(self):
        """repr() output (e.g. '<Weird>') is escaped; no stray < or > survive."""
        src = {"Obj": object()}  # repr produces something with angle-like text
        tgt = {"Obj": object()}

        def _no_role(_wid):
            return None

        preview = diff_props(src, tgt, OVERWRITE, _no_role)
        html_out = to_html(preview, WsFontRegistry.empty())
        # All angle brackets must be escaped
        import re

        re.findall(r"(?<!&lt;)(?<!&gt;)(?<![a-z])(<[^!]|>)", html_out)
        # The only < > allowed are from HTML tags themselves
        # We check that no raw < or > appears INSIDE a span's content
        # by verifying that the text content of spans doesn't contain unescaped chars
        # Simple check: after stripping HTML tags, no < or > in text nodes
        tag_stripped = re.sub(r"<[^>]+>", "", html_out)
        assert "<" not in tag_stripped, f"Unescaped '<' in text node: {tag_stripped}"
        assert ">" not in tag_stripped, f"Unescaped '>' in text node: {tag_stripped}"

    def test_field_name_escaped(self):
        """Field names with HTML chars are escaped."""
        seg = DiffSegment(text="value", kind=SegmentKind.UNCHANGED, ws_role=None)
        fd = FieldDiff(field_name="Field<b>", segments=(seg,))
        preview = MergePreview(status="", fields=(fd,), notes=())
        html_out = to_html(preview, WsFontRegistry.empty())
        assert "Field<b>" not in html_out
        assert "Field&lt;b&gt;" in html_out


# ============================================================================
# T019 — Per-role font + RTL direction
# ============================================================================


class TestFontAndRtl:
    def test_rtl_role_gets_rtl_attr(self):
        """RTL role → dir='rtl' in the rendered span (A2)."""
        registry = _make_registry(vern_rtl=True)
        seg = DiffSegment(text="arabic text", kind=SegmentKind.UNCHANGED, ws_role=WsRole.VERNACULAR)
        preview = _make_preview("Form", [seg])
        html_out = to_html(preview, registry)
        assert "dir='rtl'" in html_out

    def test_ltr_role_no_rtl_attr(self):
        """LTR role → no rtl direction attribute."""
        registry = _make_registry(vern_rtl=False, anal_rtl=False)
        seg = DiffSegment(text="english", kind=SegmentKind.UNCHANGED, ws_role=WsRole.ANALYSIS)
        preview = _make_preview("Gloss", [seg])
        html_out = to_html(preview, registry)
        assert "dir='rtl'" not in html_out

    def test_font_family_in_span(self):
        """Segment with a role → font-family in span style."""
        registry = _make_registry()
        seg = DiffSegment(text="form", kind=SegmentKind.UNCHANGED, ws_role=WsRole.VERNACULAR)
        preview = _make_preview("Form", [seg])
        html_out = to_html(preview, registry)
        assert "Doulos SIL" in html_out

    def test_font_size_in_span(self):
        """Font size appears in span style."""
        registry = _make_registry()
        seg = DiffSegment(text="form", kind=SegmentKind.UNCHANGED, ws_role=WsRole.VERNACULAR)
        preview = _make_preview("Form", [seg])
        html_out = to_html(preview, registry)
        assert "12.0pt" in html_out

    def test_ipa_rtl_not_set_when_false(self):
        """IPA role with rtl=False → no rtl attribute."""
        registry = _make_registry(ipa_rtl=False)
        seg = DiffSegment(text="/pʰ/", kind=SegmentKind.UNCHANGED, ws_role=WsRole.IPA)
        preview = _make_preview("IPA", [seg])
        html_out = to_html(preview, registry)
        assert "dir='rtl'" not in html_out


# ============================================================================
# T020 — Color, strike-through, indent, field names bold
# ============================================================================


class TestColorStrikeIndent:
    def test_added_is_green(self):
        seg = DiffSegment(text="new text", kind=SegmentKind.ADDED, ws_role=None)
        preview = _make_preview("F", [seg])
        html_out = to_html(preview, WsFontRegistry.empty())
        assert "color:#1a7f1a" in html_out

    def test_removed_is_red_with_strikethrough(self):
        seg = DiffSegment(text="old text", kind=SegmentKind.REMOVED, ws_role=None)
        preview = _make_preview("F", [seg])
        html_out = to_html(preview, WsFontRegistry.empty())
        assert "color:#cc0000" in html_out
        assert "line-through" in html_out

    def test_note_is_gray_italic(self):
        seg = DiffSegment(text="(note)", kind=SegmentKind.NOTE, ws_role=None)
        preview = _make_preview("F", [seg])
        html_out = to_html(preview, WsFontRegistry.empty())
        assert "color:#888888" in html_out
        assert "italic" in html_out

    def test_indent_produces_margin(self):
        """FieldDiff.indent > 0 produces a concrete asserted indentation (test cell 12)."""
        seg = DiffSegment(text="indented", kind=SegmentKind.UNCHANGED, ws_role=None)
        preview = _make_preview("Nested", [seg], indent=2)
        html_out = to_html(preview, WsFontRegistry.empty())
        assert "margin-left:32px" in html_out  # 2 * 16 = 32

    def test_zero_indent_no_margin(self):
        seg = DiffSegment(text="top", kind=SegmentKind.UNCHANGED, ws_role=None)
        preview = _make_preview("Top", [seg], indent=0)
        html_out = to_html(preview, WsFontRegistry.empty())
        assert "margin-left:0px" in html_out

    def test_field_name_is_bold(self):
        seg = DiffSegment(text="v", kind=SegmentKind.UNCHANGED, ws_role=None)
        preview = _make_preview("MyField", [seg])
        html_out = to_html(preview, WsFontRegistry.empty())
        assert "<b>MyField</b>" in html_out

    def test_preview_notes_rendered(self):
        seg = DiffSegment(text="v", kind=SegmentKind.UNCHANGED, ws_role=None)
        preview = MergePreview(
            status="",
            fields=(FieldDiff(field_name="F", segments=(seg,)),),
            notes=("A top-level note",),
        )
        html_out = to_html(preview, WsFontRegistry.empty())
        assert "A top-level note" in html_out


# ============================================================================
# T021 — Chrome path: ws_role=None → default font, no font span attrs
# ============================================================================


class TestWsCodeAndReplacement:
    """WS codes render as grey subscripts (shown once); changing fields render
    as a single old -> new replacement."""

    def test_ws_code_is_subscript_not_brackets(self):
        seg = DiffSegment(text="[en] hello", kind=SegmentKind.UNCHANGED, ws_role=WsRole.ANALYSIS)
        html_out = to_html(_make_preview("Gloss", [seg]), _make_registry())
        assert ">en</sub>" in html_out       # WS code is a subscript
        assert "[en]" not in html_out        # the bracket form is gone
        assert "hello" in html_out

    def test_replacement_shows_one_ws_code_and_arrow(self):
        rem = DiffSegment(text="[etu] old", kind=SegmentKind.REMOVED, ws_role=WsRole.VERNACULAR)
        add = DiffSegment(text="[etu] new", kind=SegmentKind.ADDED, ws_role=WsRole.VERNACULAR)
        html_out = to_html(_make_preview("Form", [rem, add]), _make_registry())
        assert html_out.count(">etu</sub>") == 1   # WS code NOT duplicated
        assert "→" in html_out                 # replacement arrow
        assert "line-through" in html_out           # old struck through
        assert "color:#1a7f1a" in html_out          # new is green
        assert "old" in html_out and "new" in html_out

    def test_plain_str_replacement_has_arrow_no_ws_code(self):
        rem = DiffSegment(text="ubd stem", kind=SegmentKind.REMOVED, ws_role=None)
        add = DiffSegment(text="prefix", kind=SegmentKind.ADDED, ws_role=None)
        html_out = to_html(_make_preview("Morph Type", [rem, add]), WsFontRegistry.empty())
        assert "→" in html_out
        assert "<sub" not in html_out

    def test_two_distinct_ws_each_shown_once(self):
        a = DiffSegment(text="[etu] fém", kind=SegmentKind.UNCHANGED, ws_role=WsRole.VERNACULAR)
        b = DiffSegment(text="[en] stool", kind=SegmentKind.UNCHANGED, ws_role=WsRole.ANALYSIS)
        html_out = to_html(_make_preview("LexemeForm", [a, b]), _make_registry())
        assert ">etu</sub>" in html_out and ">en</sub>" in html_out


class TestChromePath:
    def test_none_role_no_font_family(self):
        """ws_role=None → registry returns None → no font-family in span (test cell 11)."""
        registry = _make_registry()
        seg = DiffSegment(text="chrome text", kind=SegmentKind.UNCHANGED, ws_role=None)
        preview = _make_preview("Chrome", [seg])
        html_out = to_html(preview, registry)
        # The span for 'chrome text' should not have a font-family style
        # (The field name is bold but that's separate)
        # We check: no Doulos/Arial/Charis in the span containing 'chrome text'
        # by checking the full output doesn't inject a font for None-role
        import re

        # Find span containing 'chrome text'
        spans = re.findall(r"<span[^>]*>chrome text</span>", html_out)
        assert len(spans) == 1
        span = spans[0]
        assert "font-family" not in span

    def test_empty_registry_renders(self):
        """Empty registry renders without error and without font styles."""
        seg = DiffSegment(text="plain", kind=SegmentKind.ADDED, ws_role=WsRole.VERNACULAR)
        preview = _make_preview("F", [seg])
        html_out = to_html(preview, WsFontRegistry.empty())
        # No font-family since registry is empty (font_for returns None for all roles)
        import re

        spans = re.findall(r"<span[^>]*>plain</span>", html_out)
        assert len(spans) == 1
        span = spans[0]
        # The span may have color style (green for ADDED) but not font-family
        assert "font-family" not in span
