"""Tests for preview enrichment of inflection features and natural classes.

These cover the fixes for:
- inflection-feature previews (empty before, because GetSyncableProperties
  targets inflection *classes*, not IFsClosedFeature / IFsSymFeatVal);
- natural-class members (were returned as bare-GUID "PhonemeGuids" and dropped
  by the key filter) and feature-based constraints;
- phoneme grapheme labels resolving via the vernacular alternative.

All fakes are duck-typed; ``_lcm_cast`` returns the object unchanged when
SIL.LCModel is unavailable (headless), so no LCM is required.
"""

from __future__ import annotations

from gramtrans.Lib.merge_preview import (
    _enrich_natural_class,
    _enrich_phoneme,
    _find_inflection_feature_or_value,
    _gather_entry_nested,
    _natural_class_members,
    _phoneme_feature_labels,
    _phoneme_label,
    _read_inflection_feature,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _Alt:
    def __init__(self, text):
        self.Text = text


class _Name:
    """Duck-typed IMultiUnicode with best-vernacular / best-analysis alternatives."""

    def __init__(self, vern="", anal=""):
        self.BestVernacularAlternative = _Alt(vern)
        self.BestAnalysisAlternative = _Alt(anal)


class _Phoneme:
    def __init__(self, guid, vern="", anal=""):
        self.Guid = guid
        self.Name = _Name(vern, anal)


class _NC:
    """Segment-based natural class fake (SegmentsRC of phonemes)."""

    def __init__(self, guid, phonemes):
        self.Guid = guid
        self.SegmentsRC = phonemes


class _Value:
    def __init__(self, guid, name, abbr):
        self.Guid = guid
        self.Name = {"en": name}
        self.Abbreviation = {"en": abbr}


class _Feature:
    def __init__(self, guid, name, abbr, values):
        self.Guid = guid
        self.Name = {"en": name}
        self.Abbreviation = {"en": abbr}
        self.Description = {}
        self.ValuesOC = values


class _InflOps:
    def __init__(self, feats):
        self._feats = feats

    def FeatureGetAll(self):
        return self._feats


class _Handle:
    def __init__(self, feats):
        self.InflectionFeatures = _InflOps(feats)


# ---------------------------------------------------------------------------
# Phoneme labelling
# ---------------------------------------------------------------------------


class TestPhonemeLabel:
    def test_prefers_vernacular_grapheme(self):
        # Grapheme in vernacular, empty analysis -> use vernacular ('bh').
        assert _phoneme_label(_Phoneme("g1", vern="bh", anal="")) == "bh"

    def test_falls_back_to_analysis(self):
        assert _phoneme_label(_Phoneme("g2", vern="", anal="x")) == "x"

    def test_empty_degrades_to_short_guid(self):
        label = _phoneme_label(_Phoneme("0911a1170000", vern="", anal=""))
        assert label == "0911a117"  # 8-char guid prefix, never blank


# ---------------------------------------------------------------------------
# Natural-class members / enrichment
# ---------------------------------------------------------------------------


class TestNaturalClassEnrichment:
    def _nc(self):
        return _NC("nc1", [
            _Phoneme("p1", vern="p"),
            _Phoneme("p2", vern="ny"),   # empty analysis -> vernacular grapheme
            _Phoneme("00abcdef0000", vern="", anal=""),  # unnamed -> guid prefix
        ])

    def test_members_resolved_in_order(self):
        assert _natural_class_members(self._nc()) == ["p", "ny", "00abcdef"]

    def test_enrich_replaces_phoneme_guids_with_members(self):
        raw = {"Name": {"en": "Consonants"}, "PhonemeGuids": ["p1", "p2"]}
        _enrich_natural_class(self._nc(), raw)
        assert "PhonemeGuids" not in raw          # raw-GUID key removed
        assert raw["Members"] == ["p", "ny", "00abcdef"]
        assert raw["Name"] == {"en": "Consonants"}  # standard fields untouched

    def test_enrich_no_members_leaves_no_members_key(self):
        raw = {"Name": {"en": "Empty"}, "PhonemeGuids": []}
        _enrich_natural_class(_NC("nc2", []), raw)
        assert "PhonemeGuids" not in raw
        assert "Members" not in raw


# ---------------------------------------------------------------------------
# Phoneme phonological-feature enrichment
# ---------------------------------------------------------------------------


class _FeatDefn:
    def __init__(self, abbr="", name=""):
        self.Abbreviation = {"en": abbr} if abbr else {}
        self.Name = {"en": name} if name else {}


class _ClosedValue:
    """Duck-typed IFsClosedValue: a ready LongName, or FeatureRA/ValueRA."""

    def __init__(self, long_name=None, feat_abbr=None, val_abbr=None):
        if long_name is not None:
            self.LongName = long_name
        if feat_abbr is not None:
            self.FeatureRA = _FeatDefn(abbr=feat_abbr)
        if val_abbr is not None:
            self.ValueRA = _FeatDefn(abbr=val_abbr)


class _FeatStruc:
    def __init__(self, specs):
        self.FeatureSpecsOC = specs


class _PhonemeWithFeatures:
    def __init__(self, specs):
        self.FeaturesOA = _FeatStruc(specs) if specs is not None else None


class TestPhonemeFeatureEnrichment:
    def test_labels_prefer_longname_and_sort(self):
        # LongName is FLEx's native "feature:value"; result sorts alphabetically
        # regardless of the (unordered) FeatureSpecsOC iteration order.
        ph = _PhonemeWithFeatures([
            _ClosedValue(long_name="voice:+"),
            _ClosedValue(long_name="back:-"),
            _ClosedValue(long_name="high:+"),
        ])
        assert _phoneme_feature_labels(ph) == ["back:-", "high:+", "voice:+"]

    def test_falls_back_to_abbreviations(self):
        # No LongName -> reconstruct "<feat-abbr>:<value-abbr>".
        ph = _PhonemeWithFeatures([_ClosedValue(feat_abbr="ATR", val_abbr="+")])
        assert _phoneme_feature_labels(ph) == ["ATR:+"]

    def test_no_feature_struct_returns_empty(self):
        assert _phoneme_feature_labels(_PhonemeWithFeatures(None)) == []

    def test_enrich_replaces_features_guid_specs_with_labels(self):
        ph = _PhonemeWithFeatures([
            _ClosedValue(long_name="high:+"),
            _ClosedValue(long_name="back:-"),
        ])
        raw = {
            "Name": {"mgz": "ee"},
            "FeaturesGuid": "abc-123",
            "Features": [
                {"FeatureGuid": "f1", "ValueGuid": "v1"},
                {"FeatureGuid": "f2", "ValueGuid": "v2"},
            ],
        }
        _enrich_phoneme(ph, raw)
        assert raw["Features"] == ["back:-", "high:+"]   # resolved + sorted
        assert "FeaturesGuid" not in raw                  # backward-compat scalar dropped
        assert raw["Name"] == {"mgz": "ee"}               # standard fields untouched

    def test_enrich_drops_features_when_unresolvable(self):
        # Feature struct present but every spec is unreadable -> drop the raw
        # GUID list rather than leak {"FeatureGuid":…} dicts into the pane.
        ph = _PhonemeWithFeatures([_ClosedValue()])  # no LongName, no FeatureRA/ValueRA
        raw = {"Features": [{"FeatureGuid": "f1", "ValueGuid": "v1"}]}
        _enrich_phoneme(ph, raw)
        assert "Features" not in raw

    def test_enrich_no_features_key_is_noop(self):
        raw = {"Name": {"mgz": "ee"}}
        _enrich_phoneme(_PhonemeWithFeatures(None), raw)
        assert raw == {"Name": {"mgz": "ee"}}


# ---------------------------------------------------------------------------
# Inflection features
# ---------------------------------------------------------------------------


class TestInflectionFeatureRead:
    def test_read_feature_includes_name_abbrev_and_values(self):
        feat = _Feature("f1", "BantuPl", "Bpl", [
            _Value("v1", "2", "2"), _Value("v2", "9pl", "9pl"),
        ])
        props = _read_inflection_feature(feat)
        assert props["Name"] == {"en": "BantuPl"}
        assert props["Abbreviation"] == {"en": "Bpl"}
        assert props["Values"] == ["2", "9pl"]  # abbreviation labels, in order

    def test_read_value_has_no_values_list(self):
        val = _Value("v1", "singular number", "sg")
        props = _read_inflection_feature(val)
        assert props["Name"] == {"en": "singular number"}
        assert props["Abbreviation"] == {"en": "sg"}
        assert "Values" not in props

    def test_read_none_returns_none(self):
        assert _read_inflection_feature(None) is None


class _MorphType:
    def __init__(self, abbr):
        self.Abbreviation = {"en": abbr}


class _Allo:
    def __init__(self, form, mt=None):
        self.Form = {"etu": form}
        self.MorphTypeRA = _MorphType(mt) if mt else None


class _Entry:
    def __init__(self, lexeme, lexeme_mt, alts):
        self.LexemeFormOA = _Allo(lexeme, lexeme_mt)
        self.AlternateFormsOS = alts
        self.SensesOS = []


class TestLexemeFormNotAnAllomorph:
    """The lexeme form must not be repeated as 'Allomorph 1' (it's the entry
    scalar 'Lexeme Form'); only its morph type is promoted to entry level."""

    def test_lexeme_morph_type_promoted_form_not_duplicated(self):
        entry = _Entry("fém", "ubd stem", [_Allo("bém", "sfx")])
        props, meta = _gather_entry_nested(object(), entry, [])
        # Lexeme morph type promoted to an entry-level field (indent 0, no group).
        lex_keys = [k for k, v in props.items() if v == "ubd stem"]
        assert lex_keys, f"lexeme morph type missing: {list(props)}"
        dn, _sk, indent, group = meta[lex_keys[0]]
        assert dn == "Morph Type" and indent == 0 and group == ""
        # The lexeme form 'fém' is NOT emitted again as an allomorph Form.
        assert not any(v == {"etu": "fém"} for v in props.values())

    def test_alternate_form_is_the_only_allomorph(self):
        entry = _Entry("fém", "ubd stem", [_Allo("bém", "sfx")])
        props, meta = _gather_entry_nested(object(), entry, [])
        alt_keys = [k for k, v in props.items() if v == {"etu": "bém"}]
        assert alt_keys, "alternate form should be gathered as an allomorph"
        assert meta[alt_keys[0]][3] == "Allomorph 1"


class TestInflectionFeatureFinder:
    def _handle(self):
        feat = _Feature("feat-guid", "number", "num", [
            _Value("val-guid-a", "singular number", "sg"),
            _Value("val-guid-b", "plural number", "pl"),
        ])
        return _Handle([feat]), feat

    def test_finds_feature_by_guid(self):
        handle, feat = self._handle()
        assert _find_inflection_feature_or_value(handle, "feat-guid") is feat

    def test_finds_value_by_guid(self):
        handle, feat = self._handle()
        found = _find_inflection_feature_or_value(handle, "val-guid-b")
        assert found is feat.ValuesOC[1]

    def test_missing_guid_returns_none(self):
        handle, _feat = self._handle()
        assert _find_inflection_feature_or_value(handle, "nope") is None
