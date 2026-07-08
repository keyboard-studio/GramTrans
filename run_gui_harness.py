"""Dev harness — launch the GramTrans PyQt6 GUI outside FLExTools.

Run with FLExTools' interpreter (the `py` launcher = Python 3.13), NOT Anaconda:

    py run_gui_harness.py                       # preview-only (safe)
    py run_gui_harness.py --source "Ejagham Mini"
    py run_gui_harness.py --move                # enable writes (modifyAllowed=True)

It reproduces what FLExTools hands MainFunction:
  * flexicon.FLExInitialize()  -> boots the LCM/.NET runtime
  * opens the SOURCE project read-only (the GUI treats the host's open project
    as the source; you pick the target inside the dialog)
  * a console report sink (.Info/.Warning/.Error/.Blank)

NOTE: api.bind_target opens the TARGET you pick with writeEnabled=True even for
a preview, so the target must NOT be open in FieldWorks/FLEx at the same time.

Requires FLExTools' interpreter (Python 3.13 via `py`) with flexicon + PyQt6
installed. This is a dev convenience for driving the GUI against live LCM
without deploying into the FLExTools Modules directory.
"""
from __future__ import annotations

import argparse
import os
import sys
import traceback

# Make `src/` importable so `import gramtrans.gramtrans` resolves.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "src"))

from flexicon import (  # noqa: E402
    AllProjectNames,
    FLExCleanup,
    FLExInitialize,
    FLExProject,
)


class ConsoleReport:
    """Stand-in for the FlexTools report object (ASCII-only for Windows terms)."""

    def Info(self, msg: str = "") -> None:  # noqa: N802
        print(f"[INFO] {msg}")

    def Warning(self, msg: str = "") -> None:  # noqa: N802
        print(f"[WARN] {msg}")

    def Error(self, msg: str = "") -> None:  # noqa: N802
        print(f"[ERROR] {msg}")

    def Blank(self) -> None:  # noqa: N802
        print()


def main() -> int:
    ap = argparse.ArgumentParser(description="GramTrans standalone GUI harness")
    ap.add_argument(
        "--source",
        # default="Ejagham Mini",
        default="Mbugwe LizzieHC practice",
        help="source project, opened read-only (default: 'Ejagham Mini')",
    )
    ap.add_argument(
        "--move",
        action="store_true",
        help="enable writes (modifyAllowed=True); default is preview-only",
    )
    args = ap.parse_args()

    print("[INFO] === GramTrans standalone GUI harness ===")
    print(f"[INFO] Python: {sys.version.split()[0]}  ({sys.executable})")
    print(f"[INFO] Source project (read-only): {args.source!r}")
    print(f"[INFO] modifyAllowed: {args.move}")
    print("[WARN] The TARGET you pick is opened write-enabled by bind_target;")
    print("[WARN] make sure it is NOT open in FieldWorks/FLEx before you proceed.")
    print()

    print("[INFO] Booting LCM runtime (flexicon.FLExInitialize)...")
    FLExInitialize()
    try:
        available = list(AllProjectNames())
        if args.source not in available:
            print(f"[ERROR] Source project {args.source!r} not found. Available:")
            for name in available:
                print(f"          - {name}")
            return 2

        source = FLExProject()
        print(f"[INFO] Opening source {args.source!r} (read-only)...")
        source.OpenProject(projectName=args.source, writeEnabled=False)
        try:
            # Import after init so any addsitedir/flexlibs wiring is in place.
            from gramtrans.gramtrans import MainFunction

            print("[INFO] Handing control to MainFunction (GUI dialog will open)...")
            print()
            MainFunction(source, ConsoleReport(), args.move)
            print()
            print("[INFO] MainFunction returned (dialog closed).")
        finally:
            source.CloseProject()
            print("[INFO] Source project closed.")
    except Exception:  # noqa: BLE001
        print("[ERROR] Harness caught an exception:")
        traceback.print_exc()
        return 1
    finally:
        FLExCleanup()
        print("[INFO] LCM runtime shut down (FLExCleanup).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
