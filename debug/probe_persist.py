"""Minimal live probe for the persist-without-close checkpoint.

Isolates the wedge seen in coverage_report run #2: does an
End -> usm.Save() -> Begin checkpoint complete on the MAIN thread when the
ambient non-undoable task holds (a) nothing, (b) one object write, and does
the XML backend's CommitThread actually write the fwdata afterward?

Run:  python debug/probe_persist.py
ASCII-only output (Windows-terminal safe).
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "src" / "gramtrans" / "Lib"))

TARGET = os.environ.get("GRAMTRANS_TARGET", "Target")
FWDATA = Path(r"C:\ProgramData\SIL\FieldWorks\Projects") / TARGET / f"{TARGET}.fwdata"


def mtime() -> str:
    return time.strftime("%H:%M:%S", time.localtime(FWDATA.stat().st_mtime))


def main() -> None:
    import flexicon
    flexicon.FLExInitialize()
    try:
        from SIL.WritingSystems import Sldr  # type: ignore
        if Sldr.IsInitialized:
            Sldr.Cleanup()
        Sldr.Initialize(True)
        print("[INFO] SLDR offline")
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] SLDR: {exc!r}")

    from flexicon import FLExProject
    from SIL.LCModel import IUndoStackManager

    source = None
    if os.environ.get("PROBE_CO_OPEN_SOURCE"):
        source = FLExProject()
        source.OpenProject(projectName=os.environ.get("GRAMTRANS_SOURCE", "Ejagham Mini"),
                           writeEnabled=False)
        print("[OK] source project co-opened read-only (mirrors full_run)")

    print(f"[STEP] fwdata mtime before open: {mtime()}")
    proj = FLExProject()
    proj.OpenProject(projectName=TARGET, writeEnabled=True)
    print("[OK] opened write-enabled (ambient NonUndoableTask held)")

    mca = proj.project.MainCacheAccessor
    usm = proj.ObjectRepository(IUndoStackManager)

    # --- checkpoint A: AddCustomField then persist (mirrors the schema checkpoint)
    t0 = time.time()
    if os.environ.get("PROBE_ADD_CUSTOM_FIELD"):
        from SIL.LCModel.Infrastructure import IFwMetaDataCacheManaged
        from SIL.LCModel.Core.Cellar import CellarPropertyType
        mdc = IFwMetaDataCacheManaged(proj.Cache.MetaDataCacheAccessor)
        name = f"ProbeField{int(time.time()) % 100000}"
        flid = mdc.AddCustomField("LexEntry", name, CellarPropertyType(13), 0)
        print(f"[OK] AddCustomField {name} -> flid={flid}")
    mca.EndNonUndoableTask()
    usm.Save()
    mca.BeginNonUndoableTask()
    print(f"[OK] checkpoint A in {time.time()-t0:.2f}s")
    for _ in range(20):
        time.sleep(0.5)
        try:
            if "AdditionalFields" in FWDATA.read_text(encoding="utf-8", errors="ignore")[:4000]:
                break
        except OSError:
            pass
    has_af = "AdditionalFields" in FWDATA.read_text(encoding="utf-8", errors="ignore")[:4000]
    print(f"[STEP] AdditionalFields on disk after checkpoint A: {has_af}  (mtime {mtime()})")

    # --- one real object write inside the ambient task
    t0 = time.time()
    lp = proj.project.LangProject
    from SIL.LCModel import ICmPossibilityFactory
    factory = proj.ObjectRepository(ICmPossibilityFactory)
    poss = factory.Create()
    lp.ConfidenceLevelsOA.PossibilitiesOS.Add(poss)
    print(f"[OK] created one CmPossibility in {time.time()-t0:.2f}s")

    # --- checkpoint B: with a gathered change (mirrors the post-transfer wedge)
    t0 = time.time()
    mca.EndNonUndoableTask()
    print("[STEP] End done; calling usm.Save() with 1 change ...")
    usm.Save()
    print(f"[OK] Save returned in {time.time()-t0:.2f}s")
    mca.BeginNonUndoableTask()
    print("[OK] checkpoint B complete")

    # --- did the CommitThread actually write?
    for i in range(20):
        time.sleep(0.5)
        if FWDATA.stat().st_mtime > time.time() - 15:
            break
    print(f"[STEP] fwdata mtime after checkpoint B: {mtime()}")

    t0 = time.time()
    proj.CloseProject()
    print(f"[OK] CloseProject in {time.time()-t0:.2f}s")
    print(f"[STEP] fwdata mtime after close: {mtime()}")
    print("[DONE]")


if __name__ == "__main__":
    main()
