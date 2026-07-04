"""Fake duck-typed handles for custom-fields tests (spec 016, T001).

Lightweight stubs for the custom-fields object graph used by
`custom_fields_enumerate_source`, `classify_custom_field`, and related
016 helpers.  No live LCM or pythonnet required.

Real LibLCM signatures (from live MCP probe, 2026-07-04):

  GetAllFields(className) -> Iterable[(field_id, name, field_type, list_root_guid)]

  Cache.MetaDataCacheAccessor:
    GetFieldType(flid) -> int (CellarPropertyType)
    GetFieldName(flid) -> str
    GetFieldListRoot(flid) -> Guid
    AddCustomField(className, fieldName, fieldType: int, destinationClass: int)
        -> int (flid, nonzero on success)
    AddCustomField(className, fieldName, fieldType, destinationClass,
                   fieldHelp, fieldWs, fieldListRoot: Guid)
        -> int (7-arg extended overload)

  IMPORTANT: The 4th positional arg is destinationClass (Int32), NOT
  list_root_guid.  list_root is the 7th arg in the extended overload.

  GetClassId returns:
    LexEntry            = 5002
    LexSense            = 5016
    LexExampleSentence  = 5004
    MoForm              = 5035

Owner levels exposed by _CUSTOM_FIELD_OWNER_CLASSES:
  ("LexEntry", "LexSense", "LexExampleSentence", "MoForm")
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Class-id constants (real LCM values from live probe)
# ---------------------------------------------------------------------------

CLASS_ID = {
    "LexEntry": 5002,
    "LexSense": 5016,
    "LexExampleSentence": 5004,
    "MoForm": 5035,
}


# ---------------------------------------------------------------------------
# MetaDataCacheAccessor fake (source side -- read-only)
# ---------------------------------------------------------------------------

class FakeSourceMDC:
    """Read-only MDC stub for the source handle.

    Backed by the same field registry that FakeSourceCustomFields reads from;
    keyed by flid.
    """

    def __init__(self, flid_map: Dict[int, Tuple[str, int, str]]):
        # flid_map: {flid: (name, field_type, list_root_guid)}
        self._map = flid_map

    def GetFieldType(self, flid: int) -> int:
        return self._map[flid][1]

    def GetFieldName(self, flid: int) -> str:
        return self._map[flid][0]

    def GetFieldListRoot(self, flid: int) -> str:
        return self._map[flid][2]


# ---------------------------------------------------------------------------
# CustomFields accessor fakes (source side)
# ---------------------------------------------------------------------------

# Field spec as stored per owner class:
#   (field_id, name, field_type, list_root_guid)
_FieldTuple = Tuple[int, str, int, str]


class FakeSourceCustomFields:
    """Duck-typed CustomFields accessor (read side).

    Mirrors flexicon CustomFieldOperations.GetAllFields().
    GetAllFields(className) -> list of (field_id, name, field_type, list_root_guid)
    """

    def __init__(self, fields_by_class: Dict[str, List[_FieldTuple]]):
        # fields_by_class: {"LexEntry": [(5100, "Noun class", 13, ""), ...], ...}
        self._fields = fields_by_class

    def GetAllFields(self, owner_class: str) -> List[_FieldTuple]:
        return list(self._fields.get(owner_class, []))

    def FindField(self, owner_class: str, name: str) -> int:
        for fid, label, _ftype, _root in self._fields.get(owner_class, []):
            if label == name:
                return fid
        return 0


class FakeSourceCache:
    """Fake source Cache object exposing MetaDataCacheAccessor."""

    def __init__(self, flid_map: Dict[int, Tuple[str, int, str]]):
        self.MetaDataCacheAccessor = FakeSourceMDC(flid_map)


class FakeSourceHandle:
    """Full fake source handle with CustomFields + Cache.MetaDataCacheAccessor.

    Covers all four owner levels plus supports empty levels (by omission).

    Parameters
    ----------
    fields_by_class:
        Dict mapping owner class name to a list of
        (field_id, name, field_type, list_root_guid) tuples.
        Omit a class key entirely to simulate zero fields for that level.
    """

    def __init__(self, fields_by_class: Optional[Dict[str, List[_FieldTuple]]] = None):
        fields_by_class = fields_by_class or {}
        self.CustomFields = FakeSourceCustomFields(fields_by_class)
        # Build the flid -> (name, field_type, list_root_guid) map for MDC.
        flid_map: Dict[int, Tuple[str, int, str]] = {}
        for tuples in fields_by_class.values():
            for fid, name, ftype, root in tuples:
                flid_map[fid] = (name, ftype, root)
        self.Cache = FakeSourceCache(flid_map)


# ---------------------------------------------------------------------------
# MetaDataCacheAccessor fake (target side -- mutable)
# ---------------------------------------------------------------------------

class FakeTargetMDC:
    """Mutable MDC stub for the target handle.

    Supports the real AddCustomField signatures:
      4-arg: (className, fieldName, fieldType, destinationClass)
      7-arg: (className, fieldName, fieldType, destinationClass,
               fieldHelp, fieldWs, fieldListRoot)

    By default returns a nonzero flid on each call.  Set
    `fail_next_add = True` to make the next AddCustomField return 0
    (simulates schema-write failure; used by the fail-loud test).
    """

    def __init__(self):
        # {flid: (owner_class, name, field_type, destination_class, list_root)}
        self._registry: Dict[int, Tuple[str, str, int, int, str]] = {}
        self._next_flid = 9001
        self.fail_next_add: bool = False

    # -- read surface --

    def GetFieldType(self, flid: int) -> int:
        return self._registry[flid][2]

    def GetFieldName(self, flid: int) -> str:
        return self._registry[flid][1]

    def GetFieldListRoot(self, flid: int) -> str:
        return self._registry[flid][4]

    # -- write surface --

    def AddCustomField(
        self,
        class_name: str,
        field_name: str,
        field_type: int,
        destination_class: int,
        field_help: str = "",
        field_ws: int = 0,
        field_list_root: str = "",
    ) -> int:
        """Create a custom field in the in-memory registry.

        4-arg call:  AddCustomField(class_name, field_name, field_type, destination_class)
        7-arg call:  AddCustomField(class_name, field_name, field_type, destination_class,
                                    field_help, field_ws, field_list_root)

        Returns 0 if fail_next_add is True (simulates creation failure).
        """
        if self.fail_next_add:
            self.fail_next_add = False
            return 0
        flid = self._next_flid
        self._next_flid += 1
        self._registry[flid] = (class_name, field_name, field_type, destination_class, field_list_root)
        return flid

    def get_registered_flid(self, class_name: str, field_name: str) -> int:
        """Test-helper: look up the flid assigned to a (class, name) pair."""
        for flid, (cls, name, *_) in self._registry.items():
            if cls == class_name and name == field_name:
                return flid
        return 0


# ---------------------------------------------------------------------------
# CustomFields accessor fake (target side)
# ---------------------------------------------------------------------------

class FakeTargetCustomFields:
    """Duck-typed CustomFields accessor (target/write side).

    FindField delegates to an in-memory registry; initial fields can be
    pre-seeded to simulate a target that already has some custom fields.

    Parameters
    ----------
    preseeded:
        Dict mapping owner class -> list of (field_id, name, field_type, list_root_guid).
        Represents fields that exist in the target before any AddCustomField calls.
    mdc:
        Shared FakeTargetMDC so FindField and AddCustomField see the same state.
    """

    def __init__(
        self,
        preseeded: Optional[Dict[str, List[_FieldTuple]]] = None,
        mdc: Optional[FakeTargetMDC] = None,
    ):
        # Pre-seeded {class -> [(fid, name, ftype, root), ...]} for FindField.
        self._preseeded: Dict[str, List[_FieldTuple]] = preseeded or {}
        self._mdc = mdc

    def FindField(self, owner_class: str, name: str) -> int:
        """Return nonzero flid if (owner_class, name) is present; else 0."""
        for fid, label, _ftype, _root in self._preseeded.get(owner_class, []):
            if label == name:
                return fid
        # Also check what has been dynamically created via AddCustomField.
        if self._mdc is not None:
            return self._mdc.get_registered_flid(owner_class, name)
        return 0

    def GetAllFields(self, owner_class: str) -> List[_FieldTuple]:
        """Return pre-seeded fields for the given owner class."""
        return list(self._preseeded.get(owner_class, []))


class FakeTargetCache:
    """Fake target Cache object exposing a mutable MetaDataCacheAccessor."""

    def __init__(self, mdc: FakeTargetMDC):
        self.MetaDataCacheAccessor = mdc


class FakeTargetHandle:
    """Full fake target handle with mutable CustomFields + Cache.MetaDataCacheAccessor.

    Parameters
    ----------
    preseeded:
        Fields already present in the target before the run, by owner class.
        Each entry is (field_id, name, field_type, list_root_guid).
    fail_add:
        If True, the first AddCustomField call returns 0 (fail-loud test).
    """

    def __init__(
        self,
        preseeded: Optional[Dict[str, List[_FieldTuple]]] = None,
        fail_add: bool = False,
    ):
        self._mdc = FakeTargetMDC()
        if fail_add:
            self._mdc.fail_next_add = True
        preseeded = preseeded or {}
        # Pre-populate the MDC registry from pre-seeded fields so that
        # GetFieldType(flid) works for fields that exist before any AddCustomField.
        for cls_name, rows in preseeded.items():
            for fid, name, ftype, root in rows:
                self._mdc._registry[fid] = (cls_name, name, ftype, 0, root)
        self.CustomFields = FakeTargetCustomFields(preseeded, self._mdc)
        self.Cache = FakeTargetCache(self._mdc)

    @property
    def mdc(self) -> FakeTargetMDC:
        """Direct access to the MDC for test assertions."""
        return self._mdc


# ---------------------------------------------------------------------------
# Convenience factory functions
# ---------------------------------------------------------------------------

def make_source(
    entry_fields: Optional[List[_FieldTuple]] = None,
    sense_fields: Optional[List[_FieldTuple]] = None,
    example_fields: Optional[List[_FieldTuple]] = None,
    moform_fields: Optional[List[_FieldTuple]] = None,
) -> FakeSourceHandle:
    """Build a FakeSourceHandle populated with fields on any of the four levels.

    Each level list is a list of (field_id, name, field_type, list_root_guid).
    Omit or pass None to leave that level empty.

    Example::

        src = make_source(
            entry_fields=[(5100, "Noun class", 13, "")],
            sense_fields=[(5101, "Tone melody", 16, "")],
        )
    """
    by_class: Dict[str, List[_FieldTuple]] = {}
    if entry_fields:
        by_class["LexEntry"] = entry_fields
    if sense_fields:
        by_class["LexSense"] = sense_fields
    if example_fields:
        by_class["LexExampleSentence"] = example_fields
    if moform_fields:
        by_class["MoForm"] = moform_fields
    return FakeSourceHandle(by_class)


def make_target(
    entry_fields: Optional[List[_FieldTuple]] = None,
    sense_fields: Optional[List[_FieldTuple]] = None,
    example_fields: Optional[List[_FieldTuple]] = None,
    moform_fields: Optional[List[_FieldTuple]] = None,
    fail_add: bool = False,
) -> FakeTargetHandle:
    """Build a FakeTargetHandle with optional pre-seeded fields.

    Pass `fail_add=True` to make the next AddCustomField return 0.

    Example::

        tgt = make_target(
            entry_fields=[(7001, "Noun class", 13, "")],  # already present
        )
        tgt_fresh = make_target()                          # nothing pre-seeded
        tgt_fail  = make_target(fail_add=True)             # AddCustomField -> 0
    """
    preseeded: Dict[str, List[_FieldTuple]] = {}
    if entry_fields:
        preseeded["LexEntry"] = entry_fields
    if sense_fields:
        preseeded["LexSense"] = sense_fields
    if example_fields:
        preseeded["LexExampleSentence"] = example_fields
    if moform_fields:
        preseeded["MoForm"] = moform_fields
    return FakeTargetHandle(preseeded, fail_add=fail_add)
