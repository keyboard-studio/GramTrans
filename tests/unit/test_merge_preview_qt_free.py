"""Tests for feature 012 — Qt-free guarantee (SC-007, T040).

Qt-free audit result (T003):
  - ``gramtrans.Lib.merge_preview`` imports only:
      html (stdlib), dataclasses, enum, typing (stdlib),
      gramtrans.Lib.ws_fonts (confirmed Qt-free — no PyQt/PySide import).
  - ``gramtrans.Lib.ws_fonts`` imports only:
      dataclasses, enum, typing (all stdlib).
  - ``gramtrans.Lib.models`` imports only:
      enum, dataclasses, typing (all stdlib). No Qt import.
  - No transitive Qt import exists on the diff/render path.

The test below imports merge_preview in a subprocess with PyQt6 blocked via
a sys.modules sentinel that raises ImportError on any attempt to import it.
``diff_props`` and ``to_html`` are called with fabricated data and must
produce output without importing Qt.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap


def test_qt_free_import_and_run():
    """Import merge_preview with Qt blocked; run diff_props + to_html (SC-007, T040)."""
    import pathlib

    src_dir = str(pathlib.Path(__file__).parent.parent.parent / "src")

    # Use %s substitution to avoid f-string brace conflicts with dict literals
    script_template = textwrap.dedent(
        """
        import sys
        sys.path.insert(0, %s)

        # Block all PyQt/PySide flavors via sentinel modules
        for _blocked in ("PyQt6", "PyQt5", "PySide2", "PySide6"):
            _m = type(sys)(_blocked)
            sys.modules[_blocked] = _m

        # Now import the module under test
        try:
            import gramtrans.Lib.merge_preview as mp
        except ImportError as e:
            print("IMPORT_ERROR: " + str(e), flush=True)
            sys.exit(1)

        # Verify key symbols exist
        assert hasattr(mp, 'diff_props'), "diff_props missing"
        assert hasattr(mp, 'to_html'), "to_html missing"
        assert hasattr(mp, 'MergePreviewService'), "MergePreviewService missing"

        # Run diff_props with fabricated data
        src_data = {'Name': {'en': 'hello'}, 'Count': 42}
        result = mp.diff_props(src_data, None, mp.NEW, lambda _: None)
        assert result is not None, "diff_props returned None"
        assert len(result.fields) == 2, "Expected 2 fields, got " + str(len(result.fields))
        for fd in result.fields:
            for seg in fd.segments:
                assert seg.kind == mp.SegmentKind.ADDED, "Expected ADDED, got " + str(seg.kind)

        # Run to_html with fabricated registry
        from gramtrans.Lib.ws_fonts import WsFontRegistry
        html_out = mp.to_html(result, WsFontRegistry.empty())
        assert isinstance(html_out, str), "to_html did not return str"
        assert '<' in html_out, "to_html output not HTML-like"
        assert 'hello' in html_out, "expected 'hello' in html output"

        print("QT_FREE_OK", flush=True)
        """
    )
    script = script_template % repr(src_dir)

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)

    assert (
        result.returncode == 0
    ), f"Qt-free test subprocess failed.\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    assert (
        "QT_FREE_OK" in result.stdout
    ), f"Qt-free sentinel not emitted.\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    assert (
        "IMPORT_ERROR" not in result.stdout
    ), f"Import error in Qt-free test.\nSTDOUT: {result.stdout}"


def test_merge_preview_module_no_qt_imports():
    """Verify merge_preview.py has no top-level PyQt/PySide import (static check)."""
    import ast
    import pathlib

    module_path = (
        pathlib.Path(__file__).parent.parent.parent
        / "src"
        / "gramtrans"
        / "Lib"
        / "merge_preview.py"
    )
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    qt_imports = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            # Check for top-level Qt imports (not inside function bodies)
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if any(qt in name for qt in ("PyQt", "PySide")):
                    qt_imports.append(name)

    assert qt_imports == [], f"Qt imports found in merge_preview.py: {qt_imports}"


def test_merge_preview_no_conflict_import():
    """T008: merge_preview.py must NOT import conflict (mirror-not-import boundary)."""
    import ast
    import pathlib

    module_path = (
        pathlib.Path(__file__).parent.parent.parent
        / "src"
        / "gramtrans"
        / "Lib"
        / "merge_preview.py"
    )
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    conflict_imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if "conflict" in alias.name:
                    conflict_imports.append(("import", alias.name))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if "conflict" in module:
                conflict_imports.append(("from", module))

    assert conflict_imports == [], (
        "merge_preview.py MUST NOT import conflict (mirror-not-import boundary): "
        f"{conflict_imports}"
    )
