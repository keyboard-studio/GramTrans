"""Import Residue tag (data-model.md E5, spec.md FR-010 / Q5).

Dual-carrier strategy per research.md R7:
- Carrier A: `LiftResidue` field on Lex* / MoForm / MoMorphSynAnalysis classes.
- Carrier B: append to inherited `Description` multistring with `[GT-Tag]:` marker
  prefix on classes that lack a residue field.

The dispatcher `apply_residue(obj, ws, tag, residue_class_table)` picks A or B
by consulting the Carrier-A class-name lookup table (passed in by the caller so
this module stays decoupled from LCM imports).

Tag wire format: `GT|<run_id>|<source_project_name>|<iso_timestamp>`.
"""
from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Optional


_GT_TAG_LINE_MARKER = "[GT-Tag]: "
_RUN_ID_PATTERN = re.compile(r"^GT-\d{8}-\d{6}$")
_SNAP_PREFIX = "snap="
_MERGE_PREFIX = "merge="


# Carrier-A class names (research.md R7 — validated 2026-06-19).
# These LCM interfaces expose a `LiftResidue` multistring; everything else
# routes to Carrier B (Description-append).
CARRIER_A_CLASSES = frozenset({
    "LexEntry",
    "LexSense",
    "LexEntryRef",
    "LexEtymology",
    "LexExampleSentence",
    "LexPronunciation",
    "LexReference",
    "MoStemAllomorph",
    "MoAffixAllomorph",
    "MoAffixProcess",
    "MoStemMsa",
    "MoInflAffMsa",
    "MoDerivAffMsa",
    "MoUnclassifiedAffixMsa",
    "MoDerivStepMsa",
})


@dataclass(frozen=True)
class ImportResidueTag:
    """Structured per-object tag (data-model.md E5).

    `prefix` defaults to "GT" and MUST always be "GT"; it is exposed as a
    field so that Carrier-A round-trip parsing can reconstruct an identical
    object, but callers may omit it when constructing directly.
    """
    run_id: str
    source_project_name: str
    timestamp: str
    prefix: str = "GT"
    snapshot_b64: Optional[str] = None  # FR-106: base64(json) of target's
    # pre-overwrite syncable props; absent on additive (Phase 0) runs.
    merge_b64: Optional[str] = None  # Phase 2 (FR-206): base64(json) of the
    # MergeDecisionLog for this object; absent on non-interactive runs.

    def __post_init__(self) -> None:
        if self.prefix != "GT":
            raise ValueError(f"prefix must be 'GT', got {self.prefix!r}")
        if not _RUN_ID_PATTERN.match(self.run_id):
            raise ValueError(f"run_id must match GT-YYYYMMDD-HHMMSS, got {self.run_id!r}")
        # E5 invariant: run_id must match timestamp
        try:
            expected_run_id = datetime.fromisoformat(self.timestamp).strftime("GT-%Y%m%d-%H%M%S")
        except ValueError as exc:
            raise ValueError(f"timestamp is not valid ISO-8601: {self.timestamp!r}") from exc
        if self.run_id != expected_run_id:
            raise ValueError(
                f"run_id {self.run_id!r} does not match timestamp {self.timestamp!r} "
                f"(expected {expected_run_id!r})"
            )

    @classmethod
    def make(cls, run_id: str, source_project_name: str, timestamp: str) -> "ImportResidueTag":
        return cls(run_id=run_id, source_project_name=source_project_name, timestamp=timestamp)

    def serialize(self) -> str:
        parts = [
            f"{self.prefix}|{self.run_id}|{self.source_project_name}|{self.timestamp}"
        ]
        if self.snapshot_b64:
            parts.append(f"{_SNAP_PREFIX}{self.snapshot_b64}")
        if self.merge_b64:
            parts.append(f"{_MERGE_PREFIX}{self.merge_b64}")
        return "|".join(parts)

    def with_snapshot(self, props: dict) -> "ImportResidueTag":
        """FR-106: return a tag clone with `props` encoded as base64(json)
        into snapshot_b64. JSON serialization is lossy — non-stringifiable
        values are coerced to repr() so the snapshot is best-effort audit
        trail rather than a reversible undo."""
        try:
            raw = json.dumps(props, default=repr, sort_keys=True).encode("utf-8")
        except (TypeError, ValueError):
            raw = json.dumps({"_snapshot_error": "unserializable_props"}).encode("utf-8")
        b64 = base64.b64encode(raw).decode("ascii")
        return replace(self, snapshot_b64=b64)

    def decode_snapshot(self) -> Optional[dict]:
        """Recover the snapshot dict from snapshot_b64, or None if absent."""
        if not self.snapshot_b64:
            return None
        try:
            raw = base64.b64decode(self.snapshot_b64.encode("ascii"))
            return json.loads(raw.decode("utf-8"))
        except (ValueError, json.JSONDecodeError):
            return None

    def with_merge_log(self, log) -> "ImportResidueTag":
        """Phase 2 (FR-206): return a tag clone with `log.to_json()` encoded
        as base64 into merge_b64.  `log` is a MergeDecisionLog (typed
        loosely to avoid an import cycle with models)."""
        raw = log.to_json().encode("utf-8")
        b64 = base64.b64encode(raw).decode("ascii")
        return replace(self, merge_b64=b64)

    def decode_merge_log(self):
        """Recover the MergeDecisionLog from merge_b64, or None if absent /
        corrupted.  FR-215: a corrupted tag returns None rather than raising
        so callers fall back to fresh-prompt behaviour.
        """
        if not self.merge_b64:
            return None
        try:
            raw = base64.b64decode(self.merge_b64.encode("ascii"))
            s = raw.decode("utf-8")
            # Lazy import to avoid cycle with models.py.
            if __package__:
                from .models import MergeDecisionLog
            else:
                from models import MergeDecisionLog
            return MergeDecisionLog.from_json(s)
        except (ValueError, json.JSONDecodeError, KeyError, TypeError):
            return None

    @classmethod
    def parse(cls, s: Optional[str]) -> Optional["ImportResidueTag"]:
        """Recover an ImportResidueTag from either Carrier A (raw tag string)
        or Carrier B (multi-line Description with the `[GT-Tag]:` marker line).
        Returns None if no GramTrans tag is detectable."""
        if not s:
            return None
        marker_idx = s.rfind(_GT_TAG_LINE_MARKER)
        if marker_idx >= 0:
            start = marker_idx + len(_GT_TAG_LINE_MARKER)
            end = s.find("\n", start)
            line = (s[start:end] if end >= 0 else s[start:]).strip()
        else:
            lines = s.splitlines() or [s]
            line = lines[0].strip()
        parts = line.split("|")
        # Phase 2: accept 4, 5, or 6 segments.  Optional segments 5+ are
        # recognised by prefix, not column position; `snap=` MUST precede
        # `merge=` if both are present.
        if len(parts) < 4 or len(parts) > 6 or parts[0] != "GT":
            return None
        if not _RUN_ID_PATTERN.match(parts[1]):
            return None
        snapshot_b64 = None
        merge_b64 = None
        seen_merge = False
        for seg in parts[4:]:
            if seg.startswith(_SNAP_PREFIX):
                if snapshot_b64 is not None or seen_merge:
                    return None  # snap= must appear at most once, before merge=
                snapshot_b64 = seg[len(_SNAP_PREFIX):] or None
            elif seg.startswith(_MERGE_PREFIX):
                if merge_b64 is not None:
                    return None  # merge= must appear at most once
                seen_merge = True
                merge_b64 = seg[len(_MERGE_PREFIX):] or None
            else:
                return None  # unknown segment prefix
        try:
            return cls(prefix="GT", run_id=parts[1],
                       source_project_name=parts[2], timestamp=parts[3],
                       snapshot_b64=snapshot_b64,
                       merge_b64=merge_b64)
        except ValueError:
            return None


# ============================================================================
# Carrier dispatchers — these import the LCM cast helpers lazily so the module
# remains import-safe outside FlexTools (unit tests can exercise serialize/parse
# without flexlibs2 / pythonnet on the path).
# ============================================================================

def class_uses_carrier_a(class_name: str) -> bool:
    """Pure-Python dispatch helper. Callers pass the LCM ClassName string
    (e.g. obj.ClassName) and we look it up. No LCM import required."""
    return class_name in CARRIER_A_CLASSES


def apply_carrier_a(obj, ws, tag: ImportResidueTag) -> bool:
    """Carrier A: write `tag.serialize()` to `obj.LiftResidue` at writing
    system `ws`. `obj` MUST be a concrete-typed LCM object exposing
    `LiftResidue` (Lex*, MoForm, IMo*Msa classes).

    Handles five observable LiftResidue shapes:
    - attribute absent on object   -> returns False (let Carrier B handle)
    - attribute is None            -> returns False (let Carrier B handle)
    - attribute is str (empty)     -> setattr path, returns True
    - attribute is str (populated) -> setattr overwrites, returns True
    - attribute is ITsMultiString  -> set_String path, returns True

    In LCM 9.x, ILexEntry / IMoAffixAllomorph / IMoInflAffMsa expose
    LiftResidue as a plain Unicode single-string, not an ITsMultiString.
    The old code called lift.set_String() unconditionally, which silently
    failed (AttributeError swallowed) on those types.  The fix checks for
    set_String before calling it, and falls back to setattr otherwise.

    Returns True if the write succeeded, False if LiftResidue was absent
    or None (uninitialized) -- callers can fall through to Carrier B in that
    case.
    """
    _MISSING = object()
    lift = getattr(obj, "LiftResidue", _MISSING)
    if lift is _MISSING:
        return False  # attribute absent entirely
    if hasattr(lift, "set_String"):
        from SIL.LCModel.Core.Text import TsStringUtils  # lazy -- only when needed
        lift.set_String(ws, TsStringUtils.MakeString(tag.serialize(), ws))
        return True
    # lift is None, str (empty or populated), or some other non-multistring
    # value.  For Unicode single-string properties (ILexEntry /
    # IMoAffixAllomorph / IMoInflAffMsa expose LiftResidue this way in LCM
    # 9.x), None means "not yet set" -- setattr is the correct write.  Try
    # setattr; bail to Carrier B only if it raises (e.g. truly read-only).
    try:
        setattr(obj, "LiftResidue", tag.serialize())
        return True
    except Exception:
        return False


def apply_carrier_b(obj, ws, tag: ImportResidueTag, strict: bool = True) -> bool:
    """Carrier B with a `strict` flag. Set strict=False to make the
    no-Description case a warning instead of an error (used by the residue
    dispatcher's fallback path)."""
    desc = getattr(obj, "Description", None)
    if desc is None:
        if strict:
            raise TypeError(
                f"Carrier B object {type(obj).__name__} has no Description attribute; "
                "either use Carrier A (LiftResidue) or extend the residue dispatcher."
            )
        return False
    existing = desc.get_String(ws).Text or ""
    if existing and not existing.endswith("\n"):
        existing = existing + "\n"
    desc.set_String(
        ws,
        f"{existing}\n{_GT_TAG_LINE_MARKER}{tag.serialize()}",
    )
    return True




def apply_residue(obj, ws, tag: ImportResidueTag, class_name: Optional[str] = None) -> None:
    """Dispatch to Carrier A or B based on the object's LCM class name.

    If `class_name` is not provided, we read it from `obj.ClassName` (cheap
    in LCM). Carrier-A classes use LiftResidue; everything else falls through
    to Carrier B (Description-append).
    """
    if class_name is None:
        from SIL.LCModel import ICmObject  # lazy
        class_name = ICmObject(obj).ClassName
    if class_uses_carrier_a(class_name):
        if apply_carrier_a(obj, ws, tag):
            return
        # Carrier A's LiftResidue multistring was None (uninitialized on a
        # freshly-created object). Try Carrier B (Description) but don't
        # raise if that's also unavailable — Layer 3 LCM types (ILexEntry,
        # ILexSense, IMoMorphSynAnalysis) expose neither LiftResidue nor
        # Description on a freshly-created object; the residue trail for
        # those objects is recovered from per-allomorph data and the run
        # report.
        apply_carrier_b(obj, ws, tag, strict=False)
        return
    apply_carrier_b(obj, ws, tag)
