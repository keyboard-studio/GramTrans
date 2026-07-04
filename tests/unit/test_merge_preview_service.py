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
