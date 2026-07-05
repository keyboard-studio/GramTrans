"""Tests for feature 012 — User Story 4: MergePreviewService caching.

Covers T035–T039:
- Memoization: identical 4-tuple → zero recomputation.
- Re-link: different target_guid → distinct cache entry.
- Mode key regression guard (A1): same (cat, src, tgt) + different mode → cache miss.
- Invalidate: clears cache, forces recompute.
- No retained handles: cache holds dicts/MergePreview, not LCM objects.

All tests pure — no Qt, no LCM.
"""

from __future__ import annotations

from typing import Any

from gramtrans.Lib.merge_preview import (
    MERGE_KEEP,
    OVERWRITE,
    MergePreview,
    MergePreviewService,
    SegmentKind,
)

# ============================================================================
# Fake project handles for injection
# ============================================================================


class FakeProjectHandle:
    """Minimal duck-typed handle for service tests."""

    def __init__(self, props_by_guid: dict[str, dict[str, Any]]):
        self._props = props_by_guid

    def get_syncable_props(self, guid: str) -> dict[str, Any] | None:
        return self._props.get(guid)


def _make_table_for(handle: FakeProjectHandle, category: str = "entry"):
    """Build an injectable ops_table that uses FakeProjectHandle._props."""

    def _finder(target, guid):
        # Return a fake object whose _props is looked up from target
        if hasattr(target, "_props") and guid in target._props:

            class Obj:
                pass

            obj = Obj()
            obj._guid = guid
            return obj
        return None

    class FakeOps:
        def GetSyncableProperties(self, obj):
            return handle._props.get(obj._guid, {})

        def GetAll(self):
            return []

    class HandleWithOps:
        def __init__(self, inner):
            self._inner = inner
            self.LexEntry = FakeOps()

        @property
        def _props(self):
            return self._inner._props

    def _entry_finder(target, guid):
        if guid in target._props:

            class Obj:
                pass

            obj = Obj()
            obj._guid = guid
            return obj
        return None

    return {category: ("LexEntry", _entry_finder, False, False)}, HandleWithOps(handle)


# ============================================================================
# T035 — Memoization: same 4-tuple → zero recomputation (SC-006)
# ============================================================================


class TestMemoization:
    def test_second_call_returns_cached(self):
        """preview_for called twice with identical 4-tuple → same MergePreview object."""
        props = {"F": {"en": "v"}}
        src_handle = FakeProjectHandle({"src-guid": props})
        tgt_handle = FakeProjectHandle({"tgt-guid": props})
        table, wrapped_src = _make_table_for(src_handle)
        _, wrapped_tgt = _make_table_for(tgt_handle)

        svc = MergePreviewService(wrapped_src, wrapped_tgt, ops_table=table)
        r1 = svc.preview_for("entry", "src-guid", "tgt-guid", "similar", OVERWRITE)
        r2 = svc.preview_for("entry", "src-guid", "tgt-guid", "similar", OVERWRITE)
        assert r1 is r2, "Second call must return the SAME cached object"

    def test_compute_count_is_one(self):
        """Verify compute happens once by patching the internal cache."""
        props = {"F": "v"}
        src_handle = FakeProjectHandle({"src-2": props})
        tgt_handle = FakeProjectHandle({"tgt-2": props})
        table, wrapped_src = _make_table_for(src_handle)
        _, wrapped_tgt = _make_table_for(tgt_handle)

        svc = MergePreviewService(wrapped_src, wrapped_tgt, ops_table=table)
        svc.preview_for("entry", "src-2", "tgt-2", "similar", OVERWRITE)
        cache_size_after_first = len(svc._preview_cache)
        svc.preview_for("entry", "src-2", "tgt-2", "similar", OVERWRITE)
        cache_size_after_second = len(svc._preview_cache)
        assert cache_size_after_first == cache_size_after_second == 1


# ============================================================================
# T036 — Re-link: different target_guid → distinct cache entry (SC-006)
# ============================================================================


class TestReLink:
    def test_different_target_guid_distinct_result(self):
        """Same source, different target_guid → distinct MergePreview objects."""
        props1 = {"F": {"en": "target1"}}
        props2 = {"F": {"en": "target2"}}
        src_handle = FakeProjectHandle({"src-guid": {"F": {"en": "src"}}})
        tgt_handle = FakeProjectHandle({"tgt1": props1, "tgt2": props2})
        table, wrapped_src = _make_table_for(src_handle)
        _, wrapped_tgt = _make_table_for(tgt_handle)

        svc = MergePreviewService(wrapped_src, wrapped_tgt, ops_table=table)
        r1 = svc.preview_for("entry", "src-guid", "tgt1", "similar", OVERWRITE)
        r2 = svc.preview_for("entry", "src-guid", "tgt2", "similar", OVERWRITE)
        assert r1 is not r2, "Different target_guid must produce distinct cached entries"
        assert len(svc._preview_cache) == 2


# ============================================================================
# T037 — A1 regression guard: mode is part of the cache key (test cell 13)
# ============================================================================


class TestModeInCacheKey:
    def test_different_mode_is_cache_miss(self):
        """Same (cat, src, tgt) + different mode → distinct cache entry (A1)."""
        props = {"F": {"en": "value"}}
        src_handle = FakeProjectHandle({"src-dup": props})
        tgt_handle = FakeProjectHandle({"tgt-dup": {"F": {"en": "other"}}})
        table, wrapped_src = _make_table_for(src_handle)
        _, wrapped_tgt = _make_table_for(tgt_handle)

        svc = MergePreviewService(wrapped_src, wrapped_tgt, ops_table=table)
        r_ow = svc.preview_for("entry", "src-dup", "tgt-dup", "similar", OVERWRITE)
        r_mk = svc.preview_for("entry", "src-dup", "tgt-dup", "similar", MERGE_KEEP)

        # Different modes → different results (different semantics)
        assert r_ow is not r_mk, "Different mode must be a distinct cache key (A1)"
        assert len(svc._preview_cache) == 2

    def test_old_3tuple_key_would_have_been_stale(self):
        """Prove: if mode were excluded from key, the second call would return stale result."""
        # This test proves the fix: a 3-tuple key would have returned r_ow for r_mk call.
        props = {"F": {"en": "src_val"}}
        src_handle = FakeProjectHandle({"src-3t": props})
        tgt_handle = FakeProjectHandle({"tgt-3t": {"F": {"en": "tgt_val"}}})
        table, wrapped_src = _make_table_for(src_handle)
        _, wrapped_tgt = _make_table_for(tgt_handle)

        svc = MergePreviewService(wrapped_src, wrapped_tgt, ops_table=table)

        r_ow = svc.preview_for("entry", "src-3t", "tgt-3t", "similar", OVERWRITE)
        r_mk = svc.preview_for("entry", "src-3t", "tgt-3t", "similar", MERGE_KEEP)

        # OVERWRITE: differing value → REMOVED+ADDED
        # MERGE_KEEP: target has value → UNCHANGED+NOTE
        ow_kinds = {s.kind for fd in r_ow.fields for s in fd.segments}
        mk_kinds = {s.kind for fd in r_mk.fields for s in fd.segments}
        assert SegmentKind.REMOVED in ow_kinds, "OVERWRITE should have REMOVED"
        assert SegmentKind.NOTE in mk_kinds, "MERGE_KEEP should have NOTE"
        # They differ — a stale 3-tuple key would mask this difference
        assert ow_kinds != mk_kinds, "OVERWRITE and MERGE_KEEP must produce different segment kinds"


# ============================================================================
# T038 — Invalidate clears cache → next preview_for recomputes (SC-006)
# ============================================================================


class TestInvalidate:
    def test_invalidate_clears_preview_cache(self):
        """After invalidate(), next preview_for recomputes (new object)."""
        props = {"G": "val"}
        src_handle = FakeProjectHandle({"src-inv": props})
        tgt_handle = FakeProjectHandle({"tgt-inv": props})
        table, wrapped_src = _make_table_for(src_handle)
        _, wrapped_tgt = _make_table_for(tgt_handle)

        svc = MergePreviewService(wrapped_src, wrapped_tgt, ops_table=table)
        svc.preview_for("entry", "src-inv", "tgt-inv", "similar", OVERWRITE)
        svc.invalidate()
        assert len(svc._preview_cache) == 0, "Preview cache must be empty after invalidate()"
        r2 = svc.preview_for("entry", "src-inv", "tgt-inv", "similar", OVERWRITE)
        # After invalidate, it's a fresh computation — may be equal in value but is a new object
        assert isinstance(r2, MergePreview)

    def test_invalidate_clears_props_cache(self):
        """invalidate() also clears the props-dict cache."""
        props = {"H": "val"}
        src_handle = FakeProjectHandle({"src-pc": props})
        tgt_handle = FakeProjectHandle({"tgt-pc": props})
        table, wrapped_src = _make_table_for(src_handle)
        _, wrapped_tgt = _make_table_for(tgt_handle)

        svc = MergePreviewService(wrapped_src, wrapped_tgt, ops_table=table)
        svc.preview_for("entry", "src-pc", "tgt-pc", "similar", OVERWRITE)
        svc.invalidate()
        assert len(svc._props_cache) == 0, "Props cache must be empty after invalidate()"


# ============================================================================
# T039 — No retained handles: cache holds dicts/MergePreview only (FR-012)
# ============================================================================


class TestNoRetainedHandles:
    def test_preview_cache_holds_merge_preview(self):
        """Preview cache values are MergePreview instances, not LCM objects."""
        props = {"I": "val"}
        src_handle = FakeProjectHandle({"src-nr": props})
        tgt_handle = FakeProjectHandle({"tgt-nr": props})
        table, wrapped_src = _make_table_for(src_handle)
        _, wrapped_tgt = _make_table_for(tgt_handle)

        svc = MergePreviewService(wrapped_src, wrapped_tgt, ops_table=table)
        svc.preview_for("entry", "src-nr", "tgt-nr", "similar", OVERWRITE)

        for _k, v in svc._preview_cache.items():
            assert isinstance(
                v, MergePreview
            ), f"Preview cache must hold MergePreview, got {type(v)}"

    def test_props_cache_holds_dicts_or_none(self):
        """Props cache values are dicts (or None), never LCM objects (FR-012)."""
        props = {"J": "val"}
        src_handle = FakeProjectHandle({"src-pc2": props})
        tgt_handle = FakeProjectHandle({"tgt-pc2": props})
        table, wrapped_src = _make_table_for(src_handle)
        _, wrapped_tgt = _make_table_for(tgt_handle)

        svc = MergePreviewService(wrapped_src, wrapped_tgt, ops_table=table)
        svc.preview_for("entry", "src-pc2", "tgt-pc2", "similar", OVERWRITE)

        for _k, v in svc._props_cache.items():
            assert v is None or isinstance(
                v, dict
            ), f"Props cache must hold dict or None, got {type(v)}"

    def test_service_holds_handles_not_objects(self):
        """Service attributes: _source/_target are handles (not LCM objects cached)."""
        src_handle = FakeProjectHandle({})
        tgt_handle = FakeProjectHandle({})
        svc = MergePreviewService(src_handle, tgt_handle)
        assert svc._source is src_handle
        assert svc._target is tgt_handle


# ============================================================================
# T040-T043 — Value->key translation wired to the real _PROPS_TABLE (016-fix)
# ============================================================================

from gramtrans.Lib.merge_preview import (  # noqa: E402
    _CATEGORY_VALUE_TO_KEY,
    _PROPS_TABLE,
    _resolve_category_key,
    props_for,
)

_NINE_LIVE_VALUES_AND_EXPECTED_KEYS = [
    ("affixes", "entry"),
    ("stems", "entry"),
    ("phonemes", "phoneme"),
    ("natural_classes", "natural_class"),
    ("phonological_rules", "phon_rule"),
    ("inflection_features", "inflection_feature"),
    ("slots", "slot"),
    ("affix_templates", "template"),
    ("stem_names", "stem_name"),
]


class TestValueToKeyTranslation:
    """Regression guard: GrammarCategory.value -> _PROPS_TABLE key wiring."""

    # A) ------------------------------------------------------------------
    def test_all_nine_live_values_resolve_or_none(self):
        """Each live wizard value resolves to None OR an existing _PROPS_TABLE key."""
        for value, expected_key in _NINE_LIVE_VALUES_AND_EXPECTED_KEYS:
            resolved = _resolve_category_key(value)
            assert resolved is not None, f"{value!r} resolved to None unexpectedly"
            assert resolved in _PROPS_TABLE, (
                f"{value!r} -> {resolved!r} is not a key in _PROPS_TABLE"
            )
            assert resolved == expected_key, (
                f"{value!r} expected -> {expected_key!r}, got {resolved!r}"
            )

        # inflection_classes maps to None (no standalone preview — by design)
        assert _resolve_category_key("inflection_classes") is None

    # B) ------------------------------------------------------------------
    def test_every_mapped_nonNone_key_is_in_real_table(self):
        """Every non-None mapping in _CATEGORY_VALUE_TO_KEY targets a real table key."""
        for value, key in _CATEGORY_VALUE_TO_KEY.items():
            if key is not None:
                assert key in _PROPS_TABLE, (
                    f"_CATEGORY_VALUE_TO_KEY[{value!r}] = {key!r} "
                    f"but {key!r} is not in _PROPS_TABLE"
                )

    # C) ------------------------------------------------------------------
    def test_identity_passthrough(self):
        """Values absent from the map pass through as-is and exist in _PROPS_TABLE."""
        for identity_value in ("pos", "entry", "sense", "allomorph"):
            resolved = _resolve_category_key(identity_value)
            assert resolved == identity_value, (
                f"Identity value {identity_value!r} should pass through unchanged"
            )
            assert resolved in _PROPS_TABLE, (
                f"Identity value {identity_value!r} is not a real _PROPS_TABLE key"
            )

    # D) ------------------------------------------------------------------
    def test_props_for_translates_before_real_table_lookup(self):
        """props_for with category='affixes' uses real table via value->key translation."""

        _FAKE_GUID = "aaaabbbb-cccc-dddd-eeee-ffffaaaabbbb"
        _FAKE_PROPS = {"Gloss": {"en": "test_gloss"}}

        class _FakeEntry:
            guid = _FAKE_GUID

            def GetSyncableProperties(self, _obj):
                return _FAKE_PROPS

            def GetAll(self):
                return [self]

        class _FakeHandle:
            LexEntry = _FakeEntry()

        result = props_for(_FakeHandle(), category="affixes", guid=_FAKE_GUID)
        assert result == _FAKE_PROPS, (
            f"props_for('affixes', ...) should return props dict via entry path, got {result!r}"
        )

        # Bogus category: neither in map nor in table -> graceful None
        result_bogus = props_for(_FakeHandle(), category="definitely_not_a_category", guid=_FAKE_GUID)
        assert result_bogus is None, (
            f"Unmapped/unknown category should return None, got {result_bogus!r}"
        )


# ============================================================================
# T044 — DEFECT FIX: inflection_feature finder uses FeatureGetAll (not InflectionClassGetAll)
#
# Spec 017 MUST-FIX: InflectionClassGetAll() returns IMoInflClass objects
# (inflection CLASSES), not IFsClosedFeature objects (inflection FEATURES).
# The correct accessor is FeatureGetAll(), consistent with
# inflection_features_enumerate_source in categories.py.
# The previous test here was documenting the BUG — updated per spec 017.
# ============================================================================

from gramtrans.Lib.merge_preview import (  # noqa: E402
    _find_target_inflection_feature_by_guid,
    _filter_props,
    _is_excluded_key,
    _append_custom_fields,
    _find_gap_object,
    _direct_read_gap,
)


class TestInflectionFeatureFinderFix:
    """Regression: finder must call FeatureGetAll(), never InflectionClassGetAll() or GetAll().

    Spec 017 MUST-FIX DEFECT: the finder previously called InflectionClassGetAll()
    which returns inflection CLASSES (IMoInflClass), not inflection FEATURES
    (IFsClosedFeature).  Corrected to FeatureGetAll() per categories.py pattern.
    """

    def test_finder_uses_FeatureGetAll(self):
        """Finder resolves object via FeatureGetAll(), not InflectionClassGetAll()."""

        class _FakeInflFeat:
            guid = "aabb-ccdd"

        class _FakeInflFeatures:
            _getall_called = False
            _feature_getall_called = False
            _inflclass_getall_called = False

            def GetAll(self):
                self._getall_called = True
                raise AttributeError("GetAll does not exist on InflectionFeatures")

            def FeatureGetAll(self):
                self._feature_getall_called = True
                return [_FakeInflFeat()]

            def InflectionClassGetAll(self):
                self._inflclass_getall_called = True
                return []  # returns inflection CLASSES, not features

        class _FakeTarget:
            InflectionFeatures = _FakeInflFeatures()

        result = _find_target_inflection_feature_by_guid(_FakeTarget(), "aabb-ccdd")
        assert result is not None, "Finder should resolve the matching inflection feature"
        assert _FakeTarget.InflectionFeatures._feature_getall_called, (
            "FeatureGetAll() must be called to locate inflection features"
        )
        assert not _FakeTarget.InflectionFeatures._inflclass_getall_called, (
            "InflectionClassGetAll() must NOT be called — it returns inflection CLASSES, not features"
        )
        assert not _FakeTarget.InflectionFeatures._getall_called, (
            "GetAll() must NOT be called — it does not exist on InflectionFeatures"
        )

    def test_finder_returns_None_when_guid_not_found(self):
        """Finder returns None gracefully when no matching GUID exists."""

        class _FakeInflFeatures:
            def FeatureGetAll(self):
                return []

        class _FakeTarget:
            InflectionFeatures = _FakeInflFeatures()

        result = _find_target_inflection_feature_by_guid(_FakeTarget(), "no-such-guid")
        assert result is None


# ============================================================================
# T045 — DEFECT FIX: affix_template is a gap category — direct-read Name+Description
# ============================================================================


class TestTemplateGapPath:
    """Template is now is_gap=True; direct-read returns Name+Description."""

    def test_template_gap_returns_name_description(self):
        """props_for with category='affix_templates' reads Name+Description via gap path."""

        class _FakeTemplate:
            guid = "tmpl-guid-1234"
            Name = {"en": "Noun Template"}
            Description = {"en": "Template for nominal affixes"}

        class _FakePOS:
            guid = "pos-guid-5678"
            AffixTemplatesOS = [_FakeTemplate()]

        class _FakeHandle:
            class POS:
                @staticmethod
                def GetAll(recursive=False):
                    return [_FakePOS()]

            def get_gap_object(self, category, guid):
                if category == "template" and guid == "tmpl-guid-1234":
                    return _FakeTemplate()
                return None

        result = props_for(
            _FakeHandle(), category="affix_templates", guid="tmpl-guid-1234",
            owner_guid="pos-guid-5678"
        )
        assert result is not None, "Should return a dict for template gap path"
        assert "Name" in result, f"Name expected in result, got {result}"
        assert "Description" in result, f"Description expected in result, got {result}"
        # Abbreviation not present on templates — should not be required
        assert result["Name"] == {"en": "Noun Template"}

    def test_template_no_abbreviation_required(self):
        """Template gap-read succeeds even when Abbreviation is absent."""

        class _FakeTemplateNoAbbr:
            guid = "tmpl-no-abbr"
            Name = {"en": "Simple Template"}
            # no Abbreviation attribute

        class _FakeHandleNoAbbr:
            def get_gap_object(self, category, guid):
                return _FakeTemplateNoAbbr()

        result = props_for(
            _FakeHandleNoAbbr(), category="affix_templates", guid="tmpl-no-abbr"
        )
        assert result is not None
        assert "Name" in result
        assert "Abbreviation" not in result


# ============================================================================
# T046 — R-a: Custom-field extraction with namespaced child keys
# ============================================================================


class TestCustomFieldExtraction:
    """Custom fields appear in props dict with correct namespace prefixes."""

    def _make_handle_with_custom_fields(self):
        """Build a fake handle + entry with custom fields on object and children."""

        class _FakeExample:
            pass

        class _FakeSense:
            ExamplesOS = [_FakeExample()]

        class _FakeEntry:
            guid = "entry-guid-cf"
            SensesOS = [_FakeSense()]
            AlternateFormsOS = []

        class _FakeCFOps:
            def GetAllFields(self, owner_class):
                mapping = {
                    "LexEntry": [("1", "MyEntryField")],
                    "LexSense": [("2", "MySenseField")],
                    "MoForm": [],
                    "LexExampleSentence": [("3", "MyExampleField")],
                }
                return mapping.get(owner_class, [])

            def GetValue(self, obj, field_name):
                if field_name == "MyEntryField":
                    return {"en": "entry custom value"}
                if field_name == "MySenseField":
                    return {"en": "sense custom value"}
                if field_name == "MyExampleField":
                    return {"en": "example custom value"}
                return None

        class _FakeHandle:
            CustomFields = _FakeCFOps()

        return _FakeHandle(), _FakeEntry()

    def test_entry_custom_field_prefixed(self):
        """Object-level custom fields have 'CustomField.' prefix."""
        handle, entry = self._make_handle_with_custom_fields()
        props: dict = {}
        _append_custom_fields(handle, entry, "entry", props)
        assert "CustomField.MyEntryField" in props, f"Got keys: {list(props)}"
        assert props["CustomField.MyEntryField"] == {"en": "entry custom value"}

    def test_sense_custom_field_prefixed(self):
        """Child sense custom fields have 'Sense.' prefix."""
        handle, entry = self._make_handle_with_custom_fields()
        props: dict = {}
        _append_custom_fields(handle, entry, "entry", props)
        assert "Sense.MySenseField" in props, f"Got keys: {list(props)}"
        assert props["Sense.MySenseField"] == {"en": "sense custom value"}

    def test_example_custom_field_prefixed(self):
        """Grandchild example custom fields have 'Example.' prefix."""
        handle, entry = self._make_handle_with_custom_fields()
        props: dict = {}
        _append_custom_fields(handle, entry, "entry", props)
        assert "Example.MyExampleField" in props, f"Got keys: {list(props)}"

    def test_no_custom_fields_ops_graceful(self):
        """Handle without CustomFields attribute returns empty dict gracefully."""

        class _FakeHandleNoCF:
            pass

        props: dict = {}
        _append_custom_fields(_FakeHandleNoCF(), object(), "entry", props)
        assert props == {}

    def test_unknown_category_skipped_gracefully(self):
        """Category with no known owner_class produces no custom fields."""

        class _FakeHandleWithCF:
            class CustomFields:
                @staticmethod
                def GetAllFields(owner_class):
                    return []

        props: dict = {}
        _append_custom_fields(_FakeHandleWithCF(), object(), "slot", props)
        assert props == {}


# ============================================================================
# T047 — R-b: Empty-field suppression in _filter_props
# ============================================================================

from gramtrans.Lib.merge_preview import _is_empty_value  # noqa: E402


class TestRbEmptySuppression:
    """Fields with empty values are suppressed after filtering."""

    def test_none_value_suppressed(self):
        props = {"Name": None, "Description": {"en": "valid"}}
        result = _filter_props(props)
        assert "Name" not in result
        assert "Description" in result

    def test_empty_string_suppressed(self):
        props = {"Name": "", "Abbreviation": "  "}
        result = _filter_props(props)
        assert "Name" not in result
        assert "Abbreviation" not in result

    def test_empty_dict_suppressed(self):
        props = {"Name": {}, "Description": {"en": "has value"}}
        result = _filter_props(props)
        assert "Name" not in result
        assert "Description" in result

    def test_all_whitespace_multistring_suppressed(self):
        """A multistring dict whose every ws value is empty/whitespace is suppressed."""
        props = {"Name": {"en": "", "fr": "   "}, "Description": {"en": "ok"}}
        result = _filter_props(props)
        assert "Name" not in result
        assert "Description" in result

    def test_genuinely_changed_nonempty_kept(self):
        """A non-empty field value is never suppressed."""
        props = {"Name": {"en": "Real Name"}, "BasicIPASymbol": "p"}
        result = _filter_props(props)
        assert "Name" in result
        assert "BasicIPASymbol" in result

    def test_is_empty_value_helpers(self):
        assert _is_empty_value(None)
        assert _is_empty_value("")
        assert _is_empty_value("  ")
        assert _is_empty_value({})
        assert _is_empty_value({"en": "", "fr": "  "})
        assert not _is_empty_value({"en": "hello"})
        assert not _is_empty_value("x")
        assert not _is_empty_value(0)
        assert not _is_empty_value(False)


# ============================================================================
# T048 — R-c: Bookkeeping key exclusion
# ============================================================================


class TestRcBookkeepingExclusion:
    """Confirmed bookkeeping keys are excluded; user-content keys are retained."""

    _EXCLUDED = [
        "FeaturesGuid",
        "PhonemeGuids",
        "StratumGuid",
        "Guid",
        "Hvo",
        "DateCreated",
        "DateModified",
        "HomographNumber",
        "DoNotPublishInRC",
        "DoNotShowMainEntryInRC",
        "ImportResidue",
        "Direction",
        "SomeOtherGuid",          # ends in "Guid"
        "LastModifiedDateModified",  # contains "DateModified"
    ]

    _RETAINED = [
        "Name",
        "Description",
        "BasicIPASymbol",
        "Abbreviation",
        "CustomField.MyField",
        "Sense.MySense",
        "Allomorph.MyForm",
        "Example.MyEx",
        "LiteralMeaning",
        "Bibliography",
        "Comment",
    ]

    def test_excluded_keys_filtered(self):
        props = {k: {"en": "value"} for k in self._EXCLUDED}
        result = _filter_props(props)
        for k in self._EXCLUDED:
            assert k not in result, f"Bookkeeping key {k!r} should be excluded"

    def test_retained_keys_kept(self):
        props = {k: {"en": "value"} for k in self._RETAINED}
        result = _filter_props(props)
        for k in self._RETAINED:
            assert k in result, f"User-editable key {k!r} should be retained"

    def test_is_excluded_key_patterns(self):
        assert _is_excluded_key("FeaturesGuid")
        assert _is_excluded_key("PhonemeGuids")
        assert _is_excluded_key("StratumGuid")
        assert _is_excluded_key("HomographNumber")
        assert _is_excluded_key("DoNotPublishInRC")
        assert _is_excluded_key("ImportResidue")
        assert _is_excluded_key("Direction")
        assert _is_excluded_key("DateCreated")
        assert not _is_excluded_key("Name")
        assert not _is_excluded_key("Description")
        assert not _is_excluded_key("CustomField.MyGuidField")  # prefix not ending pattern
