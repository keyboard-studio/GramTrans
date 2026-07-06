"""Per-item IsProtected gating helpers (Phase 3c, plan.md Refinement 4 section h).

Pure Python -- no LCM / PyQt6 imports at module level.  Safe to import in
both unit tests and the wizard.

Public surface:
- `_is_protected(lcm_obj)` -> bool
- `apply_isprotected_layer2(cat, lcm_item, current_mode)` -> ConflictMode
"""
from __future__ import annotations

if __package__:
    from .models import ConflictMode, GrammarCategory
else:
    from models import ConflictMode, GrammarCategory  # type: ignore


def _is_protected(lcm_obj) -> bool:
    """Cast-safe IsProtected read for an LCM item.

    Attempts the IsProtected attribute on the concrete object.  Supported
    types per spec (h): ILexEntryType, IPartOfSpeech, ICmSemanticDomain,
    IMoMorphType, ILexEntryInflType, ILexRefType.

    Guard: a failed cast / absent attribute -> return False (permissive),
    because protection cannot be proven.  This is the spec-mandated default.
    """
    if lcm_obj is None:
        return False
    try:
        val = lcm_obj.IsProtected
        if isinstance(val, bool):
            return val
        # pythonnet may return a .NET bool-like; coerce.
        return bool(val)
    except (AttributeError, TypeError, Exception):  # noqa: BLE001
        # Failed cast / absent attr -> permissive (cannot prove protection).
        return False


def apply_isprotected_layer2(
    cat: "GrammarCategory",
    lcm_item,
    current_mode: "ConflictMode",
) -> "ConflictMode":
    """Apply Layer-2 per-item IsProtected refinement.

    If the item is protected, downgrade to LINK (link-only, no field writes)
    regardless of category default.  Non-protected items keep `current_mode`.

    Failed cast / absent attribute -> permissive (return `current_mode` unchanged).
    """
    if _is_protected(lcm_item):
        return ConflictMode.LINK  # 022: was MERGE; renamed to LINK (same semantics)
    return current_mode
