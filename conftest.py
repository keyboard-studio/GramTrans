"""Pytest configuration: add `src/` to sys.path so `import gramtrans` works
without an editable install in the host environment.

Also adds `tests/unit` to sys.path so helper modules (e.g. _fakes_affix)
can be imported directly by test files without a package structure.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_TESTS_UNIT = Path(__file__).parent / "tests" / "unit"
if str(_TESTS_UNIT) not in sys.path:
    sys.path.insert(0, str(_TESTS_UNIT))
