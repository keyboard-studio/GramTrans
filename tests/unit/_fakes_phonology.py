"""Fake duck-typed handles for phonology-selector tests (spec 010, T001).

Lightweight stubs for the phonology object graph read by
`build_phonology_inventory` / `collapse_phonology` and the leaf-dispatch
`_phonology_simple_enumerate` filter.  No live LCM or Qt required.

GUID handling: every fake exposes BOTH `.guid` (lower-cased key read by
`_guid_str_from`'s fake fallback) and `.Guid` (the raw, possibly mixed-case /
braced form a live `str(obj.Guid)` would yield) so tests can exercise the
GUID-normalization invariant (spec 010 P0): the builder and the trim filter
must agree only after normalization.

Reference shapes (real LCM property names mirrored):
  phoneme.FeaturesOA.FeatureSpecsOC[*].FeatureRA   -> feature ref
  nc.SegmentsRC[*]                                 -> phoneme refs
  rule.StrucDescOS[*].FeatureStructureRA           -> NC or phoneme ref
  rule.RightHandSidesOS[*].LeftContextOA/RightContextOA.FeatureStructureRA
  rule.StratumRA                                   -> stratum ref
"""
from __future__ import annotations

from typing import Optional


class _Coll:
    """Wraps a list; exposes `.GetAll()` like a flexlibs2 Operations accessor."""

    def __init__(self, items):
        self._items = list(items)

    def GetAll(self):
        return list(self._items)


class _Name:
    def __init__(self, text):
        self.BestAnalysisAlternative = type("_T", (), {"Text": text})()


class _PhonObj:
    """Base fake: `.guid` (normalization key) + `.Guid` (raw) + `.Name`."""

    def __init__(self, guid: str, name: str = "", raw_guid: Optional[str] = None):
        self.guid = guid
        # raw_guid lets a test inject an un-normalized (mixed-case/braced) form;
        # defaults to the same value as guid.
        self.Guid = raw_guid if raw_guid is not None else guid
        self.name = name
        self.Name = _Name(name or guid[:8])


class FakeFeature(_PhonObj):
    pass


class FakeEnv(_PhonObj):
    pass


class FakeStratum(_PhonObj):
    pass


class _FeatSpec:
    def __init__(self, feature_ref):
        self.FeatureRA = feature_ref


class _FeatStruc:
    def __init__(self, feature_refs):
        self.FeatureSpecsOC = [_FeatSpec(f) for f in feature_refs]


class FakePhoneme(_PhonObj):
    def __init__(self, guid, name="", feature_refs=(), raw_guid=None):
        super().__init__(guid, name, raw_guid)
        self.FeaturesOA = _FeatStruc(feature_refs) if feature_refs else None


class FakeNC(_PhonObj):
    def __init__(self, guid, name="", segments=(), raw_guid=None):
        super().__init__(guid, name, raw_guid)
        self.SegmentsRC = list(segments)


class _Ctx:
    """IPhSimpleContext{NC,Seg} stand-in: `.FeatureStructureRA` -> NC or phoneme."""

    def __init__(self, ref):
        self.FeatureStructureRA = ref


class _RHS:
    def __init__(self, left=None, right=None):
        self.LeftContextOA = _Ctx(left) if left is not None else None
        self.RightContextOA = _Ctx(right) if right is not None else None


class FakeRule(_PhonObj):
    """PhSegmentRule stand-in.

    `class_name` mirrors the LCM concrete type so the KL-010-1 guard can spot
    PhMetathesisRule / PhReduplicationRule.
    """

    def __init__(self, guid, name="", struc_refs=(), rhs=(), stratum=None,
                 class_name="PhRegularRule", raw_guid=None):
        super().__init__(guid, name, raw_guid)
        self.StrucDescOS = [_Ctx(r) for r in struc_refs]
        self.RightHandSidesOS = list(rhs)
        self.StratumRA = stratum
        self.ClassName = class_name


def make_rhs(left=None, right=None):
    return _RHS(left, right)


class FakePhonSource:
    """Source/target handle exposing the six phonology accessors."""

    def __init__(self, *, features=(), phonemes=(), ncs=(), envs=(),
                 rules=(), strata=()):
        self.PhonFeatures = _Coll(features)
        self.Phonemes = _Coll(phonemes)
        self.NaturalClasses = _Coll(ncs)
        self.Environments = _Coll(envs)
        self.PhonRules = _Coll(rules)
        self.Strata = _Coll(strata)


class FakeContext:
    """Minimal enumerate context: `.source_handle` / `.target_handle`."""

    def __init__(self, source=None, target=None):
        self.source_handle = source
        self.target_handle = target
