"""
GramTrans — additive grammar-piece transfer between FLEx projects.

FlexTools entry point (FLExTrans-style: docs dict + MainFunction). Helpers
live under sibling `Lib/`, loaded via `site.addsitedir(r"Lib")`.

Phase 0 (Additive) — see specs/001-phase0-additive-transfer/. Copies grammar
pieces (POS, affix templates, slots, affix entries with MSAs + allomorphs +
environments, ...) from a SOURCE project to the currently-open TARGET project.
FR-009 explicitly permits duplicates. New target objects are tagged with a
structured residue marker (`[GT-Tag]: GT|<run_id>|<source>|<iso_ts>`) for
later audit.

T-Spike (constitution v5.0.0 Principle III closing clause, 2026-06-19):
the inline Move logic that lived in the previous version of this file is now
split into:
  - Lib/preview.py   — plan builder (never mutates target)
  - Lib/transfer.py  — plan executor (the only Move-mode writer)
  - Lib/residue.py   — Import Residue tag + Carrier A/B dispatchers
  - Lib/report.py    — RunReport aggregation
  - Lib/types.py     — dataclasses (RunContext, RunPlan, RunReport, ...)
"""
from flextoolslib import *  # noqa: F401,F403 — FlexTools host names

import datetime
import os
import site
import sys

# Make `Lib/` importable per the FLExTrans module convention. `Lib/ui/` is
# added too so the PyQt widgets load flat (top-level module names), which keeps
# their `if __package__:` dual-mode guards on the flat branch at runtime.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
site.addsitedir(os.path.join(_THIS_DIR, "Lib"))
site.addsitedir(os.path.join(_THIS_DIR, "Lib", "ui"))

# ============================================================================
# CRITICAL: explicit flexlibs2 imports (template-mandatory)
#
# FlexTools loads stable flexlibs by default; without explicit flexlibs2
# imports, FieldWorks silently uses the wrong (stable) wrappers and grammar
# coverage falls off. Requires the patched MattGyverLee/flexlibs2 fork — see
# CLAUDE.md "flexlibs2 fork dependency".
# ============================================================================
from flexlibs2 import (  # noqa: F401 — pinned for the patched fork
    FLExProject,
    POSOperations,
    MorphRuleOperations,
    LexEntryOperations,
    LexSenseOperations,
    AllomorphOperations,
    EnvironmentOperations,
    InflectionFeatureOperations,
)

# Helpers under Lib/ (resolved via site.addsitedir above).
from preview import build_run_plan
from transfer import execute
from residue import ImportResidueTag
from report import render_text_summary, to_snapshot_json
from models import (
    GrammarCategory,
    RunContext,
    RunMode,
    Selection,
    WSMapping,
)
from conflict import (
    UserCancelled,
    build_session_from_resolutions,
    collect_overwrite_conflicts,
)
from ws_mapping import detect_ws_mismatches, fold_choices_into_ws_mapping


__version__ = "0.1.0"


# ============================================================================
# Module metadata (FLExTrans convention — FlexTools reads this dict to render
# the module list entry)
# ============================================================================

docs = {
    FTM_Name       : "GramTrans — Additive Grammar Transfer",
    FTM_Version    : __version__,
    FTM_ModifiesDB : True,
    FTM_Synopsis   : "Copy grammar pieces from a toy source project into the host target.",
    FTM_Help       : "",
    FTM_Description:
"""
Phase 0 (Additive) of GramTrans. Reads the configured SOURCE project
(currently hard-coded to 'Ejagham Mini' — FR-002 target picker arrives in a
future iteration) and copies its Verb POS + affix templates + slots into the
currently-open TARGET project. New objects preserve source GUIDs and are
tagged with a structured residue marker of the form
`GT|<run_id>|<source>|<iso_ts>` — look in Residue (Lex* classes) or the
object's Description ([GT-Tag]: line) to find this run's additions.

Phase 0 is additive only: duplicates are permitted (FR-009). FLEx's Ctrl+Z
undoes the entire run.

See CLAUDE.md for the flexlibs2 fork install instructions and STATUS.md for
the latest session's validated work.
""",
}


# Hard-coded source project for the MVP. The PyQt picker (FR-002) replaces
# this in a future iteration.
DEFAULT_SOURCE_PROJECT = "Ejagham Mini"


# ============================================================================
# Entry point
# ============================================================================

def MainFunction(project, report, modifyAllowed):
    """Standard FlexTools entry.

    Args:
        project: FLExProject connected to the host's currently-open project.
            In the GUI flow this is the SOURCE (Clarification Q2: open=source,
            picker=target). In the headless fallback it is the TARGET and the
            source is `DEFAULT_SOURCE_PROJECT`.
        report: report.Info / .Warning / .Error / .Blank for log output.
        modifyAllowed: True when FlexTools is running write-enabled.

    Primary path (T057): opens the GramTrans PyQt main window dialog (FR-002
    picker + category toggles + Preview/Move). The host's open project is the
    source; the user picks the target from the dialog.

    Headless fallback (PyQt unavailable): runs the additive verb-vertical from
    `DEFAULT_SOURCE_PROJECT` into the host's open project directly.

    Phase 0 semantics: additive only. Each source piece becomes a new
    target object with the same GUID (FR-012). Duplicates allowed (FR-009).
    The FlexTools host wraps this call in a UOW (research.md R10), so
    `Ctrl+Z` once in FLEx undoes the entire run.
    """
    QtWidgets = _try_import_qt()
    if QtWidgets is None:
        report.Warning(
            "[GramTrans] PyQt6 not available; running headless Phase-0 "
            "fallback (source={0!r}).".format(DEFAULT_SOURCE_PROJECT)
        )
        _headless_phase0(project, report, modifyAllowed)
        return

    try:
        _run_gui(project, report, modifyAllowed, QtWidgets)
    except Exception as e:  # noqa: BLE001 — FlexTools silences raw exceptions
        report.Error(f"[GramTrans] GUI fatal: {e}")
        import traceback
        report.Error(traceback.format_exc())


def _try_import_qt():
    """Return the PyQt6 QtWidgets module, or None if PyQt6 is not importable —
    the caller falls back to the headless path. PyQt6 is the project's mandated
    toolkit (initial design constraint); there is no PyQt5/PySide fallback."""
    try:
        from PyQt6 import QtWidgets
        return QtWidgets
    except ImportError:
        return None


def _run_gui(project, report, modifyAllowed, QtWidgets):
    """Launch the GramTrans PyQt main window. The host's open project is the
    source; the user picks the target inside the dialog.

    FlexTools' own GUI is wxPython, so there is normally no live QApplication;
    we reuse an existing instance if present, otherwise create one for the
    lifetime of the modal dialog. The target project opened by the dialog's
    target-picker is closed here after the dialog returns, to release its lock.
    """
    # Phase 3c: use the SelectionWizard (replaces main_window.MainWindow).
    # Flat import (Lib/ui on sys.path) so the dual-mode guard takes its flat
    # branch; fall back to the package path for non-addsitedir hosts.
    try:
        from selection_wizard import SelectionWizard
    except ImportError:
        from gramtrans.Lib.ui.selection_wizard import SelectionWizard

    source_name = project.ProjectName()
    report.Info("[GramTrans] Launching Selection Wizard (Phase 3c).")
    report.Info(f"  Source (open project): {source_name!r}")
    report.Info(f"  Mode: {'MOVE-enabled' if modifyAllowed else 'PREVIEW-only'}")

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv[:1])

    wizard = SelectionWizard(
        project,
        report,
        modifyAllowed,
        source_project_name=source_name,
    )
    try:
        wizard.exec()
    finally:
        ctx = wizard.context()
        target = getattr(ctx, "target_handle", None) if ctx is not None else None
        if target is not None:
            try:
                target.CloseProject()
                report.Info("[GramTrans] Target project closed.")
            except Exception as exc:  # noqa: BLE001
                report.Warning(f"[GramTrans] Could not close target project: {exc}")
    report.Info("[GramTrans] Selection Wizard closed.")


def _headless_phase0(project, report, modifyAllowed):
    """Headless additive verb-vertical (original MVP path). Source is
    `DEFAULT_SOURCE_PROJECT`; the host's open project is the target."""
    try:
        run_id, started_at = _make_run_id()
        source_name = DEFAULT_SOURCE_PROJECT
        tag = ImportResidueTag.make(
            run_id=run_id,
            source_project_name=source_name,
            timestamp=started_at,
        )

        report.Info(f"[GramTrans] Phase 0 additive transfer  run_id={run_id}")
        report.Info(f"  Source: {source_name!r}")
        report.Info(f"  Target: {project.ProjectName()!r}")
        report.Info(f"  Mode:   {'MOVE' if modifyAllowed else 'PREVIEW (read-only)'}")
        report.Info(f"  Tag:    {tag.serialize()}")
        report.Blank()

        source = FLExProject()
        source.OpenProject(projectName=source_name, writeEnabled=False)
        try:
            context = RunContext(
                source_handle=source,
                source_project_name=source_name,
                source_project_path=_safe_project_path(source),
                target_handle=project,
                target_project_name=project.ProjectName(),
                target_project_path=_safe_project_path(project),
                run_id=run_id,
                started_at=started_at,
            )

            # MVP: the Selection / WSMapping UI doesn't exist yet (T055, T057).
            # For the T-Spike parity run we hard-code the equivalent of the
            # spike's "all-Verb-vertical" selection.
            selection = Selection(
                categories={
                    GrammarCategory.POS: True,
                    GrammarCategory.AFFIX_TEMPLATES: True,
                    GrammarCategory.SLOTS: True,
                },
                include_closure=True,
            )
            ws_mapping = WSMapping(entries=())  # identity-only until FR-011 lands

            # Preview (never mutates target) — Principle III gate.
            plan = build_run_plan(context, selection, ws_mapping, source, project)
            report.Info(f"[Preview]  actions={len(plan.actions)}  skips={len(plan.skips)}")
            for a in plan.actions:
                report.Info(f"  + {a.category.value:10s} {a.source_guid}  {a.summary}")
            for s in plan.skips:
                report.Info(f"  - {s.category.value:10s} {s.source_guid}  {s.reason.value}: {s.detail}")
            report.Blank()

            if not modifyAllowed:
                report.Info("(Preview-only run: no writes performed.)")
                return

            # Move — the only mutating call path.
            run_report = execute(plan, source, project, report, tag)

            report.Blank()
            for line in render_text_summary(run_report):
                report.Info(line)

        finally:
            source.CloseProject()

    except Exception as e:  # noqa: BLE001 — FlexTools silences raw exceptions
        report.Error(f"[GramTrans] Fatal: {e}")
        import traceback
        report.Error(traceback.format_exc())


# ============================================================================
# Phase 2 interactive entry helper
# ============================================================================

def phase2_interactive_move(
    project,
    report,
    modifyAllowed,
    source_project_name=DEFAULT_SOURCE_PROJECT,
    pos_picks=None,
    ws_resolver=None,
    conflict_resolver=None,
    categories=None,
):
    """Phase 2 entry point that drives the full interactive flow:

        WS-wizard -> build_run_plan -> ConflictDialog -> execute(session)

    Designed for either FlexTools host invocation (production: PyQt
    WSWizard + ConflictDialog) or live MCP testing (resolver doubles).
    The standard `MainFunction` continues to expose the Phase 0
    additive flow unchanged.

    Args:
        project: FLExProject target (FlexTools host's bound project).
        report: FlexTools report sink (.Info / .Warning / .Error / .Blank).
        modifyAllowed: True if the host permits writes.
        source_project_name: name of the source project to open (default
            "Ejagham Mini").
        pos_picks: frozenset[str] of POS GUIDs to drive overwrite.  When
            None, every POS in source is in scope.
        ws_resolver: WSResolver implementation.  When None, the wizard
            opens only if mismatches exist AND PyQt is importable;
            otherwise the function falls back to identity WSMapping.
        conflict_resolver: ConflictResolver implementation.  When None,
            the dialog opens only if conflicts exist AND PyQt is
            importable; otherwise the function falls back to Phase 1
            source-wins (FR-109).
        categories: dict[GrammarCategory, bool] for Selection.  When
            None, all eight Phase-0 categories are enabled.

    Returns:
        RunReport on success.  Returns None on UserCancelled (no writes
        occur).
    """
    import datetime, time
    report.Info(f"[GramTrans Phase 2] interactive move start")
    source = FLExProject()
    source.OpenProject(projectName=source_project_name, writeEnabled=False)
    try:
        now = datetime.datetime.now()
        run_id = now.strftime("GT-%Y%m%d-%H%M%S")
        started_at = now.strftime("%Y-%m-%dT%H:%M:%S")
        context = RunContext(
            source_handle=source,
            source_project_name=source_project_name,
            source_project_path="",
            target_handle=project,
            target_project_name=project.ProjectName(),
            target_project_path=_safe_project_path(project),
            run_id=run_id,
            started_at=started_at,
        )

        # 1. WS-mapping wizard (FR-209..212)
        mismatches = detect_ws_mismatches(source, project)
        ws_choices = ()
        ws_mapping = WSMapping(entries=())
        if mismatches:
            report.Info(f"[Phase 2] {len(mismatches)} writing-system mismatch(es) detected.")
            if ws_resolver is None:
                ws_resolver = _build_default_ws_resolver(mismatches, project)
            if ws_resolver is None:
                report.Warning(
                    "[Phase 2] No WS resolver available; falling back to "
                    "identity mapping (Phase 0 behavior)."
                )
            else:
                try:
                    ws_choices = ws_resolver.resolve(mismatches)
                except UserCancelled:
                    report.Info("[Phase 2] WS wizard cancelled; aborting transfer.")
                    return None
                ws_mapping = fold_choices_into_ws_mapping(ws_choices, ws_mapping)
                report.Info(f"[Phase 2] WS wizard resolved {len(ws_choices)} mismatch(es).")
        else:
            report.Info("[Phase 2] No WS mismatches; WS wizard not invoked.")

        # 2. Build plan (interactive_merge=True gates Phase 2 path)
        if categories is None:
            categories = {c: True for c in (
                GrammarCategory.POS, GrammarCategory.AFFIX_TEMPLATES, GrammarCategory.SLOTS,
                GrammarCategory.ENTRY, GrammarCategory.SENSE, GrammarCategory.MSA,
                GrammarCategory.ALLOMORPH, GrammarCategory.PH_ENVIRONMENT,
            )}
        selection = Selection(
            categories=categories,
            include_closure=True,
            pos_picks=frozenset(pos_picks) if pos_picks else frozenset(),
            enable_overwrite=True,
            interactive_merge=True,
            ws_mapping_choices=ws_choices,
        )
        plan = build_run_plan(context, selection, ws_mapping, source, project)
        report.Info(
            f"[Phase 2] Plan: actions={len(plan.actions)} "
            f"overwrites={len(plan.overwrites)} skips={len(plan.skips)}"
        )

        # 3. Conflict detection + resolver
        prompts = collect_overwrite_conflicts(plan, source, project)
        session = None
        if prompts:
            report.Info(f"[Phase 2] {len(prompts)} conflict prompt(s) collected.")
            if conflict_resolver is None:
                conflict_resolver = _build_default_conflict_resolver(prompts)
            if conflict_resolver is None:
                report.Warning(
                    "[Phase 2] No conflict resolver available; falling "
                    "back to source-wins (FR-109)."
                )
            else:
                try:
                    decisions = conflict_resolver.resolve(prompts)
                except UserCancelled:
                    report.Info("[Phase 2] Conflict dialog cancelled; aborting transfer.")
                    return None
                session = build_session_from_resolutions(prompts, decisions)
                report.Info(f"[Phase 2] {len(decisions)} decisions captured.")
        else:
            report.Info("[Phase 2] No conflicts in plan; conflict dialog not invoked.")

        if not modifyAllowed:
            report.Info("[Phase 2] modifyAllowed=False; preview-only run, no writes.")
            return None

        # 4. Execute with the resolved session
        tag = ImportResidueTag.make(
            run_id=run_id,
            source_project_name=source_project_name,
            timestamp=started_at,
        )
        t0 = time.time()
        run_report = execute(plan, source, project, report, tag, interactive_session=session)
        elapsed = time.time() - t0
        report.Blank()
        report.Info(f"[Phase 2] Move done in {elapsed:.3f}s")
        for line in render_text_summary(run_report):
            report.Info(line)
        return run_report
    finally:
        source.CloseProject()


def _build_default_ws_resolver(mismatches, target_project):
    """Lazily import PyQt WSWizard; return None if PyQt is unavailable
    (headless contexts) so the caller can fall back."""
    try:
        from ui.ws_wizard import WSWizard
    except ImportError:
        return None
    try:
        return WSWizard(mismatches, target_project=target_project)
    except Exception:
        return None


def _build_default_conflict_resolver(prompts):
    """Lazily import PyQt ConflictDialog; return None on import error."""
    try:
        from ui.conflict_dialog import ConflictDialog
    except ImportError:
        return None
    try:
        return ConflictDialog(prompts)
    except Exception:
        return None


# ============================================================================
# Utilities
# ============================================================================

def _make_run_id() -> "tuple[str, str]":
    now = datetime.datetime.now()
    return (
        "GT-" + now.strftime("%Y%m%d-%H%M%S"),
        now.strftime("%Y-%m-%dT%H:%M:%S"),
    )


def _safe_project_path(flex_project) -> str:
    """Best-effort retrieval of a FLExProject's on-disk path. flexlibs2 doesn't
    expose this directly; fall back to an empty string so RunContext construction
    doesn't blow up when introspection isn't available."""
    for attr in ("ProjectPath", "ProjectFilename", "ProjectFolder"):
        try:
            v = getattr(flex_project, attr)
            return v() if callable(v) else str(v)
        except Exception:
            continue
    return ""
