"""Coverage report: copy EVERYTHING from a source project into a target and log
per-category GAPS (selected types whose source items did not land in target).

Runnable CLI (NOT a pytest -- run it directly). It:
  1. restores the target baseline from the newest backups/*.fwbackup (skip with
     --no-restore),
  2. inventories the target (before) and the source,
  3. runs a full transfer (all categories except STEMS) -- run #1,
  4. re-inventories the target (after),
  5. runs a second transfer with no restore to check idempotency (skip: --once),
  6. writes a per-category table + an explicit GAPS section to
     tests/integration/_snapshots/coverage_report.txt and prints it.

Usage (PowerShell), from the repo root:
    $env:GRAMTRANS_SOURCE = "Ejagham Mini"    # optional; this is the default
    $env:GRAMTRANS_TARGET = "Target"           # optional; this is the default
    python debug/coverage_report.py
    #   --no-restore   use the target as-is (no baseline restore)
    #   --once         skip the idempotency second run

Prerequisites: flexicon installed; the source and target projects present under
C:\\ProgramData\\SIL\\FieldWorks\\Projects; the target CLOSED in FLEx; and a
*.fwbackup in the repo backups/ folder (its .fwdata is renamed to the target).
ASCII-only output (Windows-terminal safe). Reuses the live harness under
tests/integration/harness/ (restore + full_run).
"""
from __future__ import annotations

import os
import sys
from collections import OrderedDict
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent          # debug/
_REPO = _THIS_DIR.parent                              # repo root
sys.path.insert(0, str(_REPO / "src" / "gramtrans" / "Lib"))
sys.path.insert(0, str(_REPO / "tests" / "integration"))  # harness package

SOURCE = os.environ.get("GRAMTRANS_SOURCE", "Ejagham Mini")
TARGET = os.environ.get("GRAMTRANS_TARGET", "Target")
PROJECTS_ROOT = os.environ.get(
    "GRAMTRANS_PROJECTS_ROOT", r"C:\ProgramData\SIL\FieldWorks\Projects")
TARGET_PATH = os.path.join(PROJECTS_ROOT, TARGET)
_LOG = _THIS_DIR / "logs" / "coverage_report.txt"

# Categories that are GOLD/canonical: the target normally already has these, so
# a zero delta is EXPECTED (not a gap) as long as the target already holds them.
_GOLD_CANONICAL = {"semantic_domains"}


def _inventory(p):
    """Comprehensive per-category count for an open flexicon project."""
    import categories as C  # local: Lib on sys.path
    lp = p.Cache.LangProject
    inv = OrderedDict()

    def _try(label, fn):
        try:
            inv[label] = fn()
        except Exception as e:  # noqa: BLE001
            inv[label] = "ERR:%s" % (str(e)[:36])

    _try("pos", lambda: len(list(p.POS.GetAll(recursive=True))))
    entries = list(C._iter_lex_entries(p))
    inv["lex_entries"] = len(entries)
    inv["senses"] = sum(len(list(getattr(e, "SensesOS", None) or [])) for e in entries)
    inv["msas"] = sum(len(list(getattr(e, "MorphoSyntaxAnalysesOC", None) or [])) for e in entries)
    inv["allomorphs"] = sum(
        (1 if getattr(e, "LexemeFormOA", None) is not None else 0)
        + len(list(getattr(e, "AlternateFormsOS", None) or []))
        for e in entries)
    _try("phonemes", lambda: len(list(p.Phonemes.GetAll())))
    _try("natural_classes", lambda: len(list(p.NaturalClasses.GetAll())))
    _try("environments", lambda: lp.PhonologicalDataOA.EnvironmentsOS.Count)
    _try("phon_rules", lambda: lp.PhonologicalDataOA.PhonRulesOS.Count)
    _try("strata", lambda: lp.MorphologicalDataOA.StrataOS.Count)
    _try("compound_rules", lambda: lp.MorphologicalDataOA.CompoundRulesOS.Count)
    _try("adhoc_prohib", lambda: lp.MorphologicalDataOA.AdhocCoProhibitionsOC.Count)
    _try("infl_classes", lambda: sum(
        getattr(getattr(x, "concrete", x), "InflectionClassesOC").Count
        for x in p.POS.GetAll(recursive=True)))
    _try("stem_names", lambda: sum(
        getattr(getattr(x, "concrete", x), "StemNamesOC").Count
        for x in p.POS.GetAll(recursive=True)))
    _try("variant_types", lambda: lp.LexDbOA.VariantEntryTypesOA.PossibilitiesOS.Count)
    _try("complex_types", lambda: lp.LexDbOA.ComplexEntryTypesOA.PossibilitiesOS.Count)
    _try("semantic_domains", lambda: lp.SemanticDomainListOA.PossibilitiesOS.Count)

    def _cf():
        from SIL.LCModel.Infrastructure import IFwMetaDataCacheManaged
        mdc = IFwMetaDataCacheManaged(p.Cache.MetaDataCacheAccessor)
        tot = 0
        for clsid in (5002, 5016, 5035, 5049):  # LexEntry, LexSense, Example, MoForm
            try:
                tot += sum(1 for f in mdc.GetFields(clsid, False, -1) if mdc.IsCustom(f))
            except Exception:  # noqa: BLE001
                pass
        return tot
    _try("custom_fields", _cf)
    return inv


def _snap(name):
    from flexicon import FLExProject
    p = FLExProject()
    p.OpenProject(projectName=name, writeEnabled=False)
    try:
        return _inventory(p)
    finally:
        try:
            p.CloseProject()
        except Exception:  # noqa: BLE001
            pass


def _plan_by_category(plan):
    from collections import Counter
    c = Counter()
    for a in plan.actions:
        cat = getattr(a, "category", None)
        c[getattr(cat, "value", None) or str(cat)] += 1
    return c


def main(argv):
    do_restore = "--no-restore" not in argv
    do_idem = "--once" not in argv

    from harness import restore, full_run

    import flexicon
    flexicon.FLExInitialize()

    # SLDR offline: LCM's WS save/commit path calls
    # SIL.WritingSystems.Sldr.Initialize(offlineTestMode=False, ...), which makes
    # a BLOCKING HTTP call to the SLDR server. Offline / proxied / slow-server ->
    # CloseProject() hangs forever while persisting (e.g. the AddCustomField
    # schema write in api._ensure_custom_fields). There is NO Sldr.OfflineMode
    # property in this libpalaso build; the lever is Cleanup() + Initialize(True).
    # FLExInitialize already initialized SLDR *online*, so we must re-init offline
    # here, after FLExInitialize (assemblies loaded) and before any OpenProject.
    try:
        from SIL.WritingSystems import Sldr  # type: ignore
        if Sldr.IsInitialized:
            Sldr.Cleanup()
        Sldr.Initialize(True)  # offlineTestMode=True -> local SldrCache, no network
        print("[INFO] SLDR forced offline (Sldr.Initialize(True))")
    except Exception as exc:  # noqa: BLE001
        print("[WARN] could not force SLDR offline: %r" % (exc,))

    lines = []

    def out(s=""):
        print(s)
        lines.append(s)

    out("GramTrans coverage report")
    out("  source = %r" % SOURCE)
    out("  target = %r  (%s)" % (TARGET, TARGET_PATH))
    out("")

    if do_restore:
        out("[STEP] restore target baseline from newest backup")
        restore.restore_target(TARGET, projects_root=PROJECTS_ROOT)

    before = _snap(TARGET)
    src = _snap(SOURCE)

    out("[STEP] transfer run #1 (all categories except STEMS)")
    plan1, _ = full_run.run_full_transfer(SOURCE, TARGET, TARGET_PATH)
    after = _snap(TARGET)
    plan1_cats = _plan_by_category(plan1)

    plan2 = None
    if do_idem:
        out("[STEP] transfer run #2 (no restore) -- idempotency")
        plan2, _ = full_run.run_full_transfer(SOURCE, TARGET, TARGET_PATH)

    keys = list(dict.fromkeys(list(src) + list(before) + list(after)))
    out("")
    out("%-18s %8s %10s %9s %7s %9s" %
        ("category", "SOURCE", "tgt-before", "tgt-after", "delta", "run1-plan"))
    out("-" * 66)
    gaps = []
    for k in keys:
        s = src.get(k, "-")
        b = before.get(k, "-")
        a = after.get(k, "-")
        d = (a - b) if isinstance(a, int) and isinstance(b, int) else "-"
        planned = plan1_cats.get(k, 0)
        out("%-18s %8s %10s %9s %7s %9s" % (k, s, b, a, d, planned))
        # GAP heuristic: source has items, but the target neither already held
        # them nor gained them (delta 0 and after < source), excluding canonical
        # GOLD lists the target is expected to already contain.
        if (isinstance(s, int) and s > 0 and isinstance(a, int) and isinstance(b, int)
                and d == 0 and a < s and k not in _GOLD_CANONICAL):
            gaps.append((k, s, a))

    out("")
    out("=== GAPS (source has items that did not land in target) ===")
    if not gaps:
        out("  none -- every category with source data was reflected in the target.")
    else:
        for k, s, a in gaps:
            out("  %-18s source=%d  target-after=%d  MISSING" % (k, s, a))

    out("")
    out("[RESULT] run #1 planned actions: %d" % len(plan1.actions))
    if plan2 is not None:
        n2 = len(plan2.actions)
        out("[RESULT] run #2 planned actions: %d  (%s)" %
            (n2, "IDEMPOTENT" if n2 == 0 else "NOT IDEMPOTENT -- see below"))
        if n2:
            for k, n in _plan_by_category(plan2).most_common():
                out("           re-planned: %-18s %d" % (k, n))

    _LOG.parent.mkdir(parents=True, exist_ok=True)
    _LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out("")
    out("[LOG] written to %s" % _LOG)


if __name__ == "__main__":
    main(sys.argv[1:])
