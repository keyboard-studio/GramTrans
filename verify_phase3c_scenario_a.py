"""Phase 3c Scenario A Live Verification Script

Run via FlexTools MCP:
    flextools_run_module(
        project_name="Ejagham Mini",
        code=<this file>,
        write_enabled=True
    )

Target: Freshly restored Ejagham Full GT-Test
Goal: Verify US1+US2 MVP (affixes + slots + templates + 17.1 wiring)
"""
import time
from pathlib import Path

def Main(project, report, modifyAllowed):
    """Phase 3c US1+US2 MVP verification against Ejagham Mini → GT-Test."""

    if not modifyAllowed:
        report.Error("Scenario A requires write mode (modifyAllowed=True)")
        return

    report.Info("=" * 70)
    report.Info("Phase 3c Scenario A — MVP Full Chain (Empty Target, US1+US2)")
    report.Info("=" * 70)

    # Import gramtrans API after FlexTools host loads
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

    from gramtrans.Lib import api
    from gramtrans.Lib.models import GrammarCategory, Selection, RunContext, WSMapping

    # Source: Ejagham Mini (current project handle from FlexTools)
    # Target: Ejagham Full GT-Test
    target_name = "Ejagham Full GT-Test"
    target_path = Path(r"C:/ProgramData/SIL/FieldWorks/Projects") / target_name

    if not target_path.exists():
        report.Error(f"Target not found: {target_path}")
        report.Error("Please restore 'Ejagham Full GT-Test' from backups first.")
        return

    report.Info(f"Source: {project.ProjectName}")
    report.Info(f"Target: {target_name}")
    report.Info("")

    # Build selection: AFFIXES + SLOTS + AFFIX_TEMPLATES (US1+US2 MVP)
    selection = Selection(
        categories={
            GrammarCategory.AFFIXES: True,
            GrammarCategory.SLOTS: True,
            GrammarCategory.AFFIX_TEMPLATES: True,
        },
        enable_overwrite=False,
        enable_merge=False,
    )

    # Build RunContext
    try:
        # Open target project
        from flexlibs2 import OpenProject
        target_handle = OpenProject(str(target_path))
    except Exception as e:
        report.Error(f"Failed to open target project: {e!r}")
        return

    try:
        context = RunContext(
            source_handle=project,
            source_project_name=project.ProjectName,
            source_project_path=str(Path(r"C:/ProgramData/SIL/FieldWorks/Projects") / project.ProjectName),
            target_handle=target_handle,
            target_project_name=target_name,
            target_project_path=str(target_path),
            run_id=f"GT-{time.strftime('%Y%m%d-%H%M%S')}",
            started_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )

        # PHASE 1: Preview (plan generation)
        report.Info("--- PHASE 1: Preview (Planning) ---")
        start_preview = time.time()

        try:
            ws_mapping = WSMapping(entries=())  # identity mapping for now
            plan = api.compute_preview(context, selection, ws_mapping)
        except Exception as e:
            report.Error(f"Preview failed: {e!r}")
            import traceback
            report.Error(traceback.format_exc())
            return

        preview_elapsed = time.time() - start_preview

        report.Info(f"Preview completed in {preview_elapsed:.2f}s")
        report.Info("")

        # Extract plan metrics
        affixes_count = sum(1 for a in plan.actions if a.category == GrammarCategory.AFFIXES)
        slots_count = sum(1 for a in plan.actions if a.category == GrammarCategory.SLOTS)
        templates_count = sum(1 for a in plan.actions if a.category == GrammarCategory.AFFIX_TEMPLATES)
        total_actions = len(plan.actions)
        total_skips = len(plan.skips)

        report.Info(f"AFFIXES planned: {affixes_count}")
        report.Info(f"SLOTS planned: {slots_count}")
        report.Info(f"AFFIX_TEMPLATES planned: {templates_count}")
        report.Info(f"Total actions: {total_actions}")
        report.Info(f"Total skips: {total_skips}")
        report.Info("")

        # Expected: T012 probe found 88 total affixes in Ejagham Mini (not 13)
        # But we're only testing a subset for MVP
        if affixes_count < 10 or affixes_count > 100:
            report.Warning(f"Expected 10-100 affixes, got {affixes_count}")
        if slots_count < 5 or slots_count > 15:
            report.Warning(f"Expected 5-15 slots, got {slots_count}")
        if templates_count < 3 or templates_count > 10:
            report.Warning(f"Expected 3-10 templates, got {templates_count}")

        # PHASE 2: Move (execution)
        report.Info("--- PHASE 2: Move (Execution) ---")
        start_move = time.time()

        try:
            move_report = api.execute_move(context, plan)
        except Exception as e:
            report.Error(f"Move failed: {e!r}")
            import traceback
            report.Error(traceback.format_exc())
            return

        move_elapsed = time.time() - start_move
        total_elapsed = preview_elapsed + move_elapsed

        report.Info(f"Move completed in {move_elapsed:.2f}s")
        report.Info(f"Total elapsed: {total_elapsed:.2f}s")
        report.Info("")

        # Extract execution metrics
        added_count = move_report.added_count
        skipped_count = move_report.skipped_count

        report.Info(f"Items added: {added_count}")
        report.Info(f"Items skipped: {skipped_count}")
        report.Info("")

        # Validate SC-301 performance gate (< 30s)
        if total_elapsed >= 30.0:
            report.Warning(f"SC-301 FAIL: Total time {total_elapsed:.2f}s >= 30s target")
        else:
            report.Info(f"SC-301 PASS: Total time {total_elapsed:.2f}s < 30s target")

        # PHASE 3: Post-execution inspection (17.1 MSA-slot wiring)
        report.Info("")
        report.Info("--- PHASE 3: Post-Execution Inspection ---")

        # Check 17.1 sub-pass results (MSA slot bindings)
        msa_slot_bindings = getattr(plan, 'msa_slot_bindings', {})
        report.Info(f"MSA-slot bindings stashed: {len(msa_slot_bindings)}")

        # T012: 247 MSAs (83 InflAff + 164 Stem), but not all have slots
        # Expected: some number of bindings (exact count TBD from live run)
        if len(msa_slot_bindings) > 0:
            report.Info(f"PASS: {len(msa_slot_bindings)} MSA-slot bindings detected")
        else:
            report.Warning("No MSA-slot bindings found (expected some)")

        # Summary
        report.Info("")
        report.Info("=" * 70)
        report.Info("SCENARIO A COMPLETE")
        report.Info("=" * 70)
        report.Info(f"Wall-clock: {total_elapsed:.2f}s")
        report.Info(f"Affixes: {affixes_count} planned → {added_count} (subset) added")
        report.Info(f"Slots: {slots_count} planned")
        report.Info(f"Templates: {templates_count} planned")
        report.Info(f"MSA-slot bindings: {len(msa_slot_bindings)}")
        report.Info("")

        if total_elapsed < 30.0 and affixes_count > 0 and slots_count > 0:
            report.Info("VERDICT: PASS — MVP verification successful")
        else:
            report.Warning("VERDICT: REVIEW — Some metrics outside expected range")

        report.Info("")
        report.Info("Next: Record results to specs/007-affixes-stems/verification-log.md")
        report.Info("      Run Scenario B (re-run idempotency)")

    finally:
        # Close target project
        if 'target_handle' in locals():
            try:
                target_handle.Close()
            except Exception:
                pass
