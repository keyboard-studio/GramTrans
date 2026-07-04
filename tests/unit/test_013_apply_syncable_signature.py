"""T-S3c: Regression guard -- ApplySyncableProperties fill_gaps parameter drift.

Asserts that every one of the six flexicon fork classes that declares
ApplySyncableProperties carries a ``fill_gaps`` parameter (with any default).

Strategy: AST-based inspection of the source files.
Rationale: importing the Operations classes pulls in SIL.FieldWorks LCM
assemblies (pythonnet / clr) that are unavailable in headless CI.  Parsing
the .py sources with the stdlib ``ast`` module requires no runtime -- but we
still resolve the fork's ``code/`` directory via ``importlib`` (which only
touches the light ``flexicon`` package ``__init__``, not the heavy Operations
submodules) so the test survives the fork being moved or re-cloned.

Note: the distribution is ``pyflexicon`` and the import package is
``flexicon`` (formerly ``flexicon``; that name is now a deprecated
compat-shim alias).

The test fails if:
  - the flexicon package cannot be located (fork not installed), OR
  - a source file is missing, OR
  - ApplySyncableProperties is not defined in that file, OR
  - the definition lacks a ``fill_gaps`` parameter.

That is exactly the bug class this test closes (spec 013 fork-completeness).
"""
import ast
import importlib.util
import pathlib
import pytest

# ---------------------------------------------------------------------------
# Fork ``code/`` root -- resolved from the installed ``flexicon`` package so
# this stays correct if the fork directory is renamed or moved. Falls back to
# the known checkout path if the package is not importable in this environment.
# ---------------------------------------------------------------------------
def _resolve_fork_code_dir() -> pathlib.Path:
    spec = importlib.util.find_spec("flexicon")
    if spec is not None and spec.origin:
        return pathlib.Path(spec.origin).parent / "code"
    return pathlib.Path("D:/Github/_Projects/_LEX/flexicon/flexicon/code")


_FORK_CODE = _resolve_fork_code_dir()

# Six (file-relative-to-code-root, human label) pairs.
_TARGETS = [
    ("BaseOperations.py",                   "BaseOperations"),
    ("Grammar/StratumOperations.py",        "Grammar.StratumOperations"),
    ("Lexicon/EtymologyOperations.py",      "Lexicon.EtymologyOperations"),
    ("Lexicon/ExampleOperations.py",        "Lexicon.ExampleOperations"),
    ("Lexicon/LexEntryOperations.py",       "Lexicon.LexEntryOperations"),
    ("Lexicon/LexSenseOperations.py",       "Lexicon.LexSenseOperations"),
]

# Build parametrize IDs from the human labels.
_IDS = [label for _, label in _TARGETS]
_PATHS = [_FORK_CODE / rel for rel, _ in _TARGETS]


def _find_fill_gaps_in_file(src_path: pathlib.Path) -> bool:
    """Return True iff src_path defines ApplySyncableProperties with fill_gaps."""
    source = src_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(src_path))

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name != "ApplySyncableProperties":
            continue
        # Collect all argument names (positional, kw-only, etc.)
        all_args = (
            [a.arg for a in node.args.args]
            + [a.arg for a in node.args.kwonlyargs]
            + ([node.args.vararg.arg] if node.args.vararg else [])
            + ([node.args.kwarg.arg] if node.args.kwarg else [])
        )
        if "fill_gaps" in all_args:
            return True
    return False


@pytest.mark.parametrize("src_path,label", zip(_PATHS, _IDS), ids=_IDS)
def test_apply_syncable_has_fill_gaps(src_path, label):
    """ApplySyncableProperties in {label} must declare a fill_gaps parameter."""
    if not src_path.exists():
        pytest.fail(
            f"Source file not found -- fork may not be cloned at expected path.\n"
            f"  Expected: {src_path}"
        )

    found = _find_fill_gaps_in_file(src_path)
    assert found, (
        f"{label}: ApplySyncableProperties is missing the 'fill_gaps' parameter.\n"
        f"  File: {src_path}"
    )
