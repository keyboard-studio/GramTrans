@echo off
REM Launch the GramTrans PyQt6 GUI outside FLExTools using the same interpreter
REM FLExTools uses (the `py` launcher = Python 3.13).
REM
REM Usage:
REM   run_gui_harness.cmd                 (preview-only, safe)
REM   run_gui_harness.cmd --move          (enable writes)
REM   run_gui_harness.cmd --source "Ejagham Mini"
cd /d "%~dp0"
py "%~dp0run_gui_harness.py" %*
pause
