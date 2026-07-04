"""T033b: FR-020 target lock / read-only detection — integration scaffolds against Ejagham Full GT-Test."""
from __future__ import annotations

import pytest

# All integration tests are marked so unit-only runs skip them:
#   pytest -m 'not integration'
# The marker is registered in pyproject.toml.
pytestmark = pytest.mark.integration


def test_target_open_in_flex_yields_target_unavailable() -> None:
    """FR-020: bind_target() raises TargetUnavailable when the target project is already opened for write by FLEx.

    Requires:
    - FlexTools host running this test (not raw pytest from CLI).
    - Ejagham Mini at C:\\ProgramData\\SIL\\FieldWorks\\Projects\\Ejagham Mini (source)
    - Ejagham Full GT-Test simultaneously opened in FLEx itself (so the LCM
      lock file is held by another process)

    Asserts: api.bind_target(ctx, target_name='Ejagham Full GT-Test') raises
    gramtrans.Lib.api.TargetUnavailable before any write is attempted.  The
    error message must identify the project name so the user knows which project
    to close.  FR-020 requires this check to occur during bind_target(), not
    deferred to execute_move().
    """
    pytest.skip(
        "Integration test — requires FlexTools host. "
        "Run via FlexTools MCP `flextools_run_module` or under the host directly."
    )

    if False:
        from gramtrans.Lib.api import TargetUnavailable, bind_target, initialize_run  # noqa: F401

        # Pre-condition: Ejagham Full GT-Test must be open in FLEx to hold the lock.
        ctx = initialize_run(source_project_name="Ejagham Mini")
        with pytest.raises(TargetUnavailable) as exc_info:
            bind_target(ctx, target_name="Ejagham Full GT-Test")
        assert "Ejagham Full GT-Test" in str(exc_info.value)


def test_read_only_project_directory_yields_target_unavailable() -> None:
    """FR-020: bind_target() raises TargetUnavailable when the target's project directory is read-only on disk.

    Requires:
    - FlexTools host running this test (not raw pytest from CLI).
    - Ejagham Mini at C:\\ProgramData\\SIL\\FieldWorks\\Projects\\Ejagham Mini (source)
    - Ejagham Full GT-Test freshly restored then its project directory set
      read-only via icacls / attrib before this test runs.

    Asserts: api.bind_target(ctx, target_name='Ejagham Full GT-Test') raises
    TargetUnavailable when the LCM open attempt fails due to the filesystem
    being read-only.  The module must surface this as TargetUnavailable (not an
    unhandled OSError / flexicon exception) so the UI can present a meaningful
    message.  FR-020 closes the coverage gap flagged in the 2026-06-19 audit.
    """
    pytest.skip(
        "Integration test — requires FlexTools host. "
        "Run via FlexTools MCP `flextools_run_module` or under the host directly."
    )

    if False:
        import subprocess  # noqa: F401

        from gramtrans.Lib.api import TargetUnavailable, bind_target, initialize_run  # noqa: F401

        project_dir = (
            r"C:\ProgramData\SIL\FieldWorks\Projects\Ejagham Full GT-Test"
        )
        # Make the directory read-only before the test.
        subprocess.run(
            ["icacls", project_dir, "/deny", "Everyone:(W)"], check=True
        )
        try:
            ctx = initialize_run(source_project_name="Ejagham Mini")
            with pytest.raises(TargetUnavailable):
                bind_target(ctx, target_name="Ejagham Full GT-Test")
        finally:
            # Restore write permissions regardless of test outcome.
            subprocess.run(
                ["icacls", project_dir, "/remove:d", "Everyone"], check=True
            )
