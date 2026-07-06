"""FieldWorks restore helper (standalone; not a pytest module).

Restores the target project from a ``.fwbackup`` so each end-to-end run starts
from a known-clean baseline. HEADLESS by default: a ``.fwbackup`` is a plain zip
archive, so we extract it directly into the project directory instead of shelling
out to ``FieldWorks.exe -restore`` (which launches the full GUI -- About window,
etc. -- and blocks unattended runs). Fails loud with actionable, ASCII-only
messages (no emoji -- Windows terminal safe).

Public API
----------
newest_backup(backups_dir) -> Path
    Return the most-recently-modified ``*.fwbackup`` under ``backups_dir``.

restore_target(project_name, backup_path=None, projects_root=None) -> None
    Headlessly restore ``project_name`` from ``backup_path`` (default: newest
    backup in the repo ``backups/`` dir) by extracting the zip into
    ``<projects_root>/<project_name>/`` and renaming the archived ``*.fwdata`` to
    match ``project_name``. Raises RestoreError on any problem.
"""
from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path
from typing import Optional

# Env overrides.
FW_EXE_ENV = "GRAMTRANS_FW_EXE"          # legacy GUI-restore fallback exe
PROJECTS_ROOT_ENV = "GRAMTRANS_PROJECTS_ROOT"

# Repo root = three levels up from this file (tests/integration/harness/).
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_BACKUPS_DIR = _REPO_ROOT / "backups"

# Standard FieldWorks projects location on Windows.
_DEFAULT_PROJECTS_ROOT = r"C:\ProgramData\SIL\FieldWorks\Projects"

# Zip top-level folders that are backup metadata, not live project files.
_SKIP_TOP_DIRS = frozenset({"BackupSettings"})

# Common FieldWorks 9 install locations (legacy GUI-restore fallback only).
_FW_EXE_CANDIDATES = (
    r"C:\Program Files\SIL\FieldWorks 9\FieldWorks.exe",
    r"C:\Program Files (x86)\SIL\FieldWorks 9\FieldWorks.exe",
)


class RestoreError(RuntimeError):
    """Raised when the FieldWorks restore cannot be performed or fails."""


def newest_backup(backups_dir: os.PathLike | str = _DEFAULT_BACKUPS_DIR) -> Path:
    """Return the newest ``*.fwbackup`` under ``backups_dir`` (by mtime).

    Raises RestoreError if the directory is missing or has no backups.
    """
    d = Path(backups_dir)
    if not d.is_dir():
        raise RestoreError(
            "[ERROR] Backups directory not found: %s. "
            "Expected .fwbackup files under the repo 'backups/' folder." % d
        )
    backups = sorted(d.glob("*.fwbackup"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not backups:
        raise RestoreError(
            "[ERROR] No .fwbackup files in %s. "
            "Create a FieldWorks backup of the target project first." % d
        )
    return backups[0]


def _resolve_fw_exe(fw_exe: Optional[str]) -> Path:
    """Resolve the FieldWorks.exe path from argument, env, then a location scan."""
    if fw_exe:
        p = Path(fw_exe)
        if not p.is_file():
            raise RestoreError(
                "[ERROR] fw_exe argument points to a missing file: %s" % p
            )
        return p

    env_exe = os.environ.get(FW_EXE_ENV)
    if env_exe:
        p = Path(env_exe)
        if not p.is_file():
            raise RestoreError(
                "[ERROR] %s is set to a missing file: %s" % (FW_EXE_ENV, p)
            )
        return p

    for cand in _FW_EXE_CANDIDATES:
        p = Path(cand)
        if p.is_file():
            return p

    raise RestoreError(
        "[ERROR] Could not locate FieldWorks.exe. "
        "Set the %s environment variable to its full path, or install "
        "FieldWorks 9 in a standard location. Scanned: %s"
        % (FW_EXE_ENV, ", ".join(_FW_EXE_CANDIDATES))
    )


def _resolve_projects_root(projects_root: Optional[str]) -> Path:
    """Resolve the FLEx projects root from arg, env, then the Windows default."""
    root = projects_root or os.environ.get(PROJECTS_ROOT_ENV) or _DEFAULT_PROJECTS_ROOT
    p = Path(root)
    if not p.is_dir():
        raise RestoreError(
            "[ERROR] FLEx projects root not found: %s. "
            "Set %s to override." % (p, PROJECTS_ROOT_ENV)
        )
    return p


def _dest_for_member(member: str, proj_dir: Path, project_name: str) -> Optional[Path]:
    """Map a zip member path to its destination under ``proj_dir``.

    - Skips backup-metadata top dirs and directory entries.
    - Renames the archived root ``*.fwdata`` to ``<project_name>.fwdata`` so a
      backup taken under a different project name restores correctly (this is
      the rename the FieldWorks GUI restore performs).
    - Preserves every other member's relative path.
    Returns None for members that should be skipped.
    """
    norm = member.replace("\\", "/")
    if norm.endswith("/"):
        return None
    top = norm.split("/", 1)[0]
    if top in _SKIP_TOP_DIRS:
        return None
    if "/" not in norm and norm.lower().endswith(".fwdata"):
        return proj_dir / ("%s.fwdata" % project_name)
    return proj_dir / norm


def restore_target(
    project_name: str,
    backup_path: Optional[os.PathLike | str] = None,
    projects_root: Optional[str] = None,
) -> None:
    """Headlessly restore ``project_name`` from ``backup_path``.

    A ``.fwbackup`` is a zip archive; this extracts it directly into
    ``<projects_root>/<project_name>/`` -- no FieldWorks.exe, no GUI, no About
    window. The archived ``*.fwdata`` is renamed to ``<project_name>.fwdata``.

    Parameters
    ----------
    project_name:
        The FLEx project name to restore into (e.g. "Ejagham Full GT-Test").
    backup_path:
        Path to a .fwbackup file. Defaults to the newest backup in the repo
        ``backups/`` directory.
    projects_root:
        FLEx projects root dir. Defaults to env GRAMTRANS_PROJECTS_ROOT then the
        Windows standard location.

    Raises
    ------
    RestoreError
        On a missing/invalid backup, a locked target, or an extraction failure.

    Notes
    -----
    The target project MUST NOT be open (in FLEx or via a live flexicon handle);
    a locked ``.fwdata`` cannot be overwritten and raises RestoreError.
    """
    if backup_path is None:
        backup = newest_backup()
    else:
        backup = Path(backup_path)
        if not backup.is_file():
            raise RestoreError("[ERROR] Backup file not found: %s" % backup)
    if not zipfile.is_zipfile(backup):
        raise RestoreError(
            "[ERROR] Backup is not a valid zip/.fwbackup archive: %s" % backup
        )

    root = _resolve_projects_root(projects_root)
    proj_dir = root / project_name

    print("[INFO] Restoring target project '%s' (headless zip extract)" % project_name)
    print("[INFO]   backup:   %s" % backup)
    print("[INFO]   proj dir: %s" % proj_dir)

    # Clean the live files we are about to replace (leave unrelated files alone).
    try:
        proj_dir.mkdir(parents=True, exist_ok=True)
        # Remove any stale lock so a prior crash doesn't block the overwrite.
        for lock in proj_dir.glob("*.lock"):
            lock.unlink()
        old_fwdata = proj_dir / ("%s.fwdata" % project_name)
        if old_fwdata.exists():
            old_fwdata.unlink()
        for sub in ("WritingSystemStore", "ConfigurationSettings", "SharedSettings"):
            d = proj_dir / sub
            if d.is_dir():
                shutil.rmtree(d)
    except PermissionError as exc:
        raise RestoreError(
            "[ERROR] Could not clear the target project dir (is '%s' open in "
            "FLEx or held by a live flexicon handle?): %s" % (project_name, exc)
        ) from exc

    extracted = 0
    try:
        with zipfile.ZipFile(backup) as z:
            for member in z.namelist():
                dest = _dest_for_member(member, proj_dir, project_name)
                if dest is None:
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                with z.open(member) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)
                extracted += 1
    except PermissionError as exc:
        raise RestoreError(
            "[ERROR] Could not write restored files (target locked?): %s" % exc
        ) from exc
    except (OSError, zipfile.BadZipFile) as exc:
        raise RestoreError("[ERROR] Extraction of %s failed: %s" % (backup, exc)) from exc

    fwdata = proj_dir / ("%s.fwdata" % project_name)
    if not fwdata.is_file():
        raise RestoreError(
            "[ERROR] Restore completed but %s is missing -- the backup had no "
            "root .fwdata member. Extracted %d files." % (fwdata, extracted)
        )

    print("[DONE] Restore of '%s' completed (%d files)." % (project_name, extracted))
