"""Unit tests for the exclusive-backend guard (_disable_project_sharing).

LibLCM silently upgrades a plain-XML open to the SharedXML multi-process
backend whenever SharedSettings/LexiconSettings.plsx carries
projectSharing="true". That peer protocol (global commit-log mutex,
cross-peer reconciliation, UI marshals on the writer thread) deadlocks a
pump-less headless host -- observed live as an unbounded Save() after a
large transfer. bind_target flips the flag off before opening the target,
forcing the proven exclusive XML backend.
"""
from __future__ import annotations

from gramtrans.Lib.api import _disable_project_sharing

_SHARED_PLSX = """<?xml version="1.0"?>
<ProjectLexiconSettings projectSharing="true">
  <WritingSystems addToSldr="true">
    <WritingSystem id="en">
      <Abbreviation>Eng</Abbreviation>
    </WritingSystem>
  </WritingSystems>
</ProjectLexiconSettings>
"""


def _make_project(tmp_path, plsx_text=None):
    proj = tmp_path / "Proj"
    (proj / "SharedSettings").mkdir(parents=True)
    if plsx_text is not None:
        (proj / "SharedSettings" / "LexiconSettings.plsx").write_text(
            plsx_text, encoding="utf-8"
        )
    return proj


def test_flips_sharing_true_to_false(tmp_path):
    proj = _make_project(tmp_path, _SHARED_PLSX)
    assert _disable_project_sharing(str(proj), "Proj") is True
    text = (proj / "SharedSettings" / "LexiconSettings.plsx").read_text(encoding="utf-8")
    assert 'projectSharing="false"' in text
    assert 'projectSharing="true"' not in text
    # The rest of the document is untouched.
    assert "<WritingSystem id=\"en\">" in text
    assert "addToSldr=\"true\"" in text  # unrelated attrs must survive


def test_noop_when_sharing_already_false(tmp_path):
    plsx = _SHARED_PLSX.replace('projectSharing="true"', 'projectSharing="false"')
    proj = _make_project(tmp_path, plsx)
    assert _disable_project_sharing(str(proj), "Proj") is False
    text = (proj / "SharedSettings" / "LexiconSettings.plsx").read_text(encoding="utf-8")
    assert text == plsx


def test_noop_when_settings_file_missing(tmp_path):
    proj = _make_project(tmp_path, plsx_text=None)
    assert _disable_project_sharing(str(proj), "Proj") is False


def test_noop_when_project_folder_missing(tmp_path):
    assert _disable_project_sharing(str(tmp_path / "nope"), "nope") is False


def test_only_the_root_element_attribute_is_touched(tmp_path):
    """A projectSharing-looking string elsewhere in the doc must not match."""
    plsx = _SHARED_PLSX.replace(
        "</ProjectLexiconSettings>",
        "<Note>projectSharing=\"true\" quoted in prose</Note></ProjectLexiconSettings>",
    )
    proj = _make_project(tmp_path, plsx)
    assert _disable_project_sharing(str(proj), "Proj") is True
    text = (proj / "SharedSettings" / "LexiconSettings.plsx").read_text(encoding="utf-8")
    assert text.count('projectSharing="true"') == 1  # only the prose copy remains
    assert '<ProjectLexiconSettings projectSharing="false">' in text
