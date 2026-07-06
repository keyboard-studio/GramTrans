"""End-to-end orchestration helpers (no pytest asserts; reusable).

Drives the api.py engine facade against a live FLEx project pair:

    source (read-only) --compute_preview--> RunPlan --execute_move--> RunReport

All FLEx / flexicon calls are made lazily inside functions so this module
imports cleanly on a host without flexicon (the test module skips in that case).
ASCII-only console output.

Public API
----------
build_full_selection(exclude=frozenset({GrammarCategory.STEMS})) -> Selection
    Every GrammarCategory member set True except those in ``exclude``. All
    pick-sets left empty (engine walks all POSes / transfer-all leaf items).

run_full_transfer(source_name, target_name, target_path) -> (RunPlan, RunReport)
    Opens source RO, binds target, compute_preview, execute_move. Sets the
    GRAMTRANS_DEBUG env var first so export/persist diagnostics fire.

reopen_and_count(target_name) -> dict[str, int]
    Reopens the target fresh (read-only) and returns a few cheap, robust
    inventory counts to prove persistence. Defensive: a missing accessor is
    simply omitted from the returned dict.
"""
from __future__ import annotations

import os
from typing import Optional, Tuple

from gramtrans.Lib import api
from gramtrans.Lib.debuglog import DEBUG_ENV
from gramtrans.Lib.models import GrammarCategory, RunPlan, RunReport, Selection


# ---------------------------------------------------------------------------
# Selection builder
# ---------------------------------------------------------------------------

def build_full_selection(
    exclude: frozenset = frozenset({GrammarCategory.STEMS}),
) -> Selection:
    """Build a Selection with EVERY GrammarCategory True except ``exclude``.

    Pick-sets (pos_picks / affix_picks / stem_picks / leaf_item_picks) are left
    empty so the engine walks all POSes and transfers all leaf items.
    Custom Fields is included (it is a normal GrammarCategory member), which is
    what exercises the PATH-CLOSE-REBIND persist branch in execute_move.
    """
    categories = {
        cat: True
        for cat in GrammarCategory
        if cat not in exclude
    }
    return Selection(categories=categories)


# ---------------------------------------------------------------------------
# Project open helpers (lazy flexicon import)
# ---------------------------------------------------------------------------

_FLEX_INITIALIZED = False


def _ensure_flex_initialized() -> None:
    """Call flexicon.FLExInitialize() exactly once per process.

    Standalone (non-FlexTools-host) processes MUST initialize the FieldWorks
    libraries before any OpenProject; the host normally does this at startup.
    Skipping it surfaces as ``RegistryHelper.get_CompanyKey()`` throwing
    ArgumentNullException on the first open. Idempotent + safe to re-call.
    """
    global _FLEX_INITIALIZED
    if _FLEX_INITIALIZED:
        return
    from flexicon import FLExInitialize  # lazy -- absent on hosts without flexicon

    FLExInitialize()
    _FLEX_INITIALIZED = True


def _open_source_readonly(source_name: str):
    """Open the source project read-only and return the flexicon handle.

    Raises RuntimeError with an actionable message on failure (caller turns
    this into a pytest.skip).
    """
    from flexicon import FLExProject  # lazy -- absent on hosts without flexicon

    _ensure_flex_initialized()
    proj = FLExProject()
    try:
        proj.OpenProject(projectName=source_name, writeEnabled=False)
    except Exception as exc:  # noqa: BLE001 -- LCM raises a variety of types
        raise RuntimeError(
            "[ERROR] Could not open source project %r read-only: %s"
            % (source_name, exc)
        ) from exc
    return proj


def _dump_plan_composition(plan) -> None:
    """Print per-category actions/skips + duplicate-(category,guid) detection
    for the plan produced by the REAL api path. ASCII-only."""
    from collections import Counter

    def _cat(x):
        c = getattr(x, "category", None)
        return getattr(c, "value", None) or str(c)

    acts = Counter(_cat(a) for a in plan.actions)
    skps = Counter(_cat(s) for s in plan.skips)
    seen = Counter((_cat(a), a.source_guid) for a in plan.actions)
    dups = {k: n for k, n in seen.items() if n > 1}
    print("[PLAN] === actions by category (total=%d) ===" % len(plan.actions))
    for k, n in acts.most_common():
        print("[PLAN]   %-22s %4d" % (k, n))
    print("[PLAN] === skips by category (total=%d) ===" % len(plan.skips))
    for k, n in skps.most_common():
        print("[PLAN]   %-22s %4d" % (k, n))
    print("[PLAN] === duplicate (category,guid) action rows: %d distinct ==="
          % len(dups))
    for (k, g), n in sorted(dups.items(), key=lambda kv: -kv[1])[:8]:
        print("[PLAN]   %dx  %-14s %s" % (n, k, g))


# ---------------------------------------------------------------------------
# Full transfer orchestration
# ---------------------------------------------------------------------------

def run_full_transfer(
    source_name: str,
    target_name: str,
    target_path: str,
) -> Tuple[RunPlan, RunReport]:
    """Run a full (all-categories-except-STEMS) transfer end to end.

    Sets GRAMTRANS_DEBUG=1 (so export/persist diagnostics fire), opens the
    source read-only, binds the target for write, computes the preview plan,
    and executes the move. Returns ``(plan, report)``.

    The source handle is closed in a finally block; the target handle is owned
    by the engine (execute_move's PATH-CLOSE-REBIND branch closes it for the
    custom-field path).
    """
    # Ensure the export/persist diagnostics fire for this run.
    os.environ.setdefault(DEBUG_ENV, "1")

    context = None
    source_handle = _open_source_readonly(source_name)
    try:
        stub = api.initialize_run(
            source_handle,
            source_project_name=source_name,
            source_project_path="",
        )
        choice = api.TargetCandidate(
            project_name=target_name,
            project_path=target_path,
        )
        context = api.bind_target(stub, choice)

        selection = build_full_selection()
        state, plan = api.compute_preview(context, selection, ws_mapping=None)
        if state is not api.PreviewState.PREVIEW_READY:
            raise RuntimeError(
                "[ERROR] compute_preview did not return PREVIEW_READY; got %r"
                % (state,)
            )
        _dump_plan_composition(plan)

        report = api.execute_move(context, plan)
        return plan, report
    finally:
        # The harness IS the host here: FLEx only persists writes on
        # CloseProject(). api.execute_move deliberately leaves closing the
        # target to the caller on the non-custom-field path (in production
        # gramtrans._run_gui does it), so we MUST close the target handle to
        # flush writes to disk before any reopen/count. On the custom-field
        # PATH-CLOSE-REBIND path execute_move already closed this handle
        # internally, so this is a safe no-op there.
        if context is not None:
            try:
                context.target_handle.CloseProject()
            except Exception:  # noqa: BLE001
                pass
        try:
            source_handle.CloseProject()
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# Persistence-proof inventory counts
# ---------------------------------------------------------------------------

# (label, accessor-chain) pairs. Each accessor chain is applied against the
# open flexicon project; a chain that raises / is absent is skipped (defensive).
# These are intentionally cheap, top-level owning collections that a full
# transfer is expected to grow.
_COUNT_ACCESSORS = (
    ("pos", lambda p: p.lp.PartsOfSpeechOA.PossibilitiesOS.Count),
    ("phonemes", lambda p: p.lp.PhonologicalDataOA.PhonemeSetsOS[0].PhonemesOC.Count),
    ("entries", lambda p: p.lexicon.LexiconNumberOfEntries()),
)


def reopen_and_count(target_name: str) -> dict:
    """Reopen ``target_name`` fresh (read-only) and return inventory counts.

    Returns a dict of ``{label: int}`` for each accessor that resolves without
    error. A missing / renamed accessor is silently omitted so the harness
    survives flexicon API drift. The project is always closed before returning.
    """
    from flexicon import FLExProject  # lazy

    _ensure_flex_initialized()
    proj = FLExProject()
    try:
        proj.OpenProject(projectName=target_name, writeEnabled=False)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "[ERROR] Could not reopen target %r for counting: %s"
            % (target_name, exc)
        ) from exc

    counts: dict = {}
    try:
        for label, accessor in _COUNT_ACCESSORS:
            try:
                value = accessor(proj)
            except Exception:  # noqa: BLE001 -- accessor absent / shape differs
                continue
            try:
                counts[label] = int(value)
            except (TypeError, ValueError):
                continue
    finally:
        try:
            proj.CloseProject()
        except Exception:  # noqa: BLE001
            pass
    return counts


def total_count(counts: dict) -> int:
    """Sum of all inventory counts in a ``reopen_and_count`` result."""
    return sum(counts.values())
