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
    """Wraps a list; exposes `.GetAll()` like a flexicon Operations accessor."""

    def __init__(self, items):
        self._items = list(items)

    def GetAll(self):
        return list(self._items)


class _Name:
    def __init__(self, text, vern=None):
        self.BestAnalysisAlternative = type("_T", (), {"Text": text})()
        # Phonemes carry their grapheme in the vernacular alternative; only set
        # it when a test supplies one so non-phoneme fakes stay analysis-only.
        if vern is not None:
            self.BestVernacularAlternative = type("_T", (), {"Text": vern})()


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
    def __init__(self, guid, name="", feature_refs=(), raw_guid=None,
                 vernacular=None, ipa=None, description=None):
        super().__init__(guid, name, raw_guid)
        self.FeaturesOA = _FeatStruc(feature_refs) if feature_refs else None
        # FLEx phoneme fields, all distinct: 'Refer to as' -> Name (grapheme,
        # vernacular alternative; analysis alt is the '***' sentinel), 'IPA
        # Symbol' -> BasicIPASymbol, 'Description' -> Description (analysis).
        if vernacular is not None:
            self.Name = _Name("***", vern=vernacular)
        self.BasicIPASymbol = (
            type("_T", (), {"Text": ipa})() if ipa is not None else None)
        self.Description = _Name(description) if description is not None else None


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


# ---------------------------------------------------------------------------
# Spec 021 -- Lexical-Entry Types fakes
# ---------------------------------------------------------------------------

class FakeInflFeatSpec:
    """Stand-in for IFsFeatureSpecification: `.ValueRA` points to a value obj."""

    def __init__(self, value_ref):
        self.ValueRA = value_ref


class FakeInflFeatStruc:
    """Stand-in for IFsFeatStruc: `.FeatureSpecsOC` is a list of specs.

    Used as `InflFeatsOA` on FakeInflEntryType.
    """

    def __init__(self, specs=()):
        self.FeatureSpecsOC = list(specs)


class _SimpleName:
    """`.BestAnalysisAlternative.Text` mimic for entry-type label reads."""

    def __init__(self, text):
        self.BestAnalysisAlternative = type("_T", (), {"Text": text})()


class FakeEntryType:
    """Base ILexEntryType stand-in.

    Attributes
    ----------
    guid : str
        Normalized (lower-cased, no braces) GUID -- used by `_guid_str_from`
        fake fallback.
    Guid : str
        Raw form (may be mixed-case, braced) to exercise normalization.
    Name  : _SimpleName
    CatalogSourceId : str or None
        Non-empty => `_is_gold` returns True; None or "" => user-defined.
    SubPossibilitiesOS : list
        Child FakeEntryType objects (nesting mirrors real LCM hierarchy).
    """

    def __init__(self, guid: str, name: str = "", *,
                 catalog_source_id=None, raw_guid=None, sub_possibilities=()):
        self.guid = guid
        self.Guid = raw_guid if raw_guid is not None else guid
        self.Name = _SimpleName(name or guid[:8])
        self.CatalogSourceId = catalog_source_id
        self.SubPossibilitiesOS = list(sub_possibilities)


class FakeInflEntryType(FakeEntryType):
    """ILexEntryInflType stand-in: adds `.InflFeatsOA`.

    When `infl_feats` is empty, `InflFeatsOA` is None (base variant type).
    When `infl_feats` is a non-empty sequence of value objects, `InflFeatsOA`
    is a `FakeInflFeatStruc` wrapping `[FakeInflFeatSpec(v) for v in infl_feats]`.
    """

    def __init__(self, guid: str, name: str = "", *,
                 infl_feats=(), catalog_source_id=None, raw_guid=None,
                 sub_possibilities=()):
        super().__init__(guid, name, catalog_source_id=catalog_source_id,
                         raw_guid=raw_guid, sub_possibilities=sub_possibilities)
        if infl_feats:
            self.InflFeatsOA = FakeInflFeatStruc(
                [FakeInflFeatSpec(v) for v in infl_feats]
            )
        else:
            self.InflFeatsOA = None


class FakePossibilityList:
    """Stand-in for CmPossibilityList: `.PossibilitiesOS` is a list.

    `_walk_possibilities` accesses `.PossibilitiesOS` directly (not GetAll()).
    """

    def __init__(self, items=()):
        self.PossibilitiesOS = list(items)


class _FakeLangProject:
    def __init__(self, lex_db):
        self.LexDbOA = lex_db


class _FakeCache:
    def __init__(self, lex_db):
        self.LangProject = _FakeLangProject(lex_db)


class FakeLexDb:
    """Stand-in for LexDbOA: owns the two entry-type possibility lists."""

    def __init__(self, *, variant_entry_types=(), complex_entry_types=()):
        self.VariantEntryTypesOA = FakePossibilityList(variant_entry_types)
        self.ComplexEntryTypesOA = FakePossibilityList(complex_entry_types)


class FakeLexDbSource:
    """Source handle whose `.Cache.LangProject.LexDbOA` resolves to a FakeLexDb.

    Also exposes `.VariantEntryTypesOA` and `.ComplexEntryTypesOA` as direct
    shortcuts for tests that call the accessors without going through Cache.
    """

    def __init__(self, lex_db: FakeLexDb):
        self.Cache = _FakeCache(lex_db)
        self.VariantEntryTypesOA = lex_db.VariantEntryTypesOA
        self.ComplexEntryTypesOA = lex_db.ComplexEntryTypesOA
