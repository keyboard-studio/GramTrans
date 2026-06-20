<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan
at D:\Github\_Projects\_LEX\GramTrans\specs\003-phase2-interactive-merge\plan.md
<!-- SPECKIT END -->

## flexlibs2 fork dependency

GramTrans runtime depends on the **MattGyverLee/flexlibs2 fork**, not stock flexlibs2.
The fork lives locally at `D:/Github/_Projects/_LEX/flexlibs2` and carries two patches
that the module relies on:

1. **`GetSyncableProperties` writing-system enumeration fix.** Stock flexlibs2 reads
   `ws_factory.WritingSystems`, which does not exist on `ILgWritingSystemFactory` in
   the LCM 9.x runtime — every `GetSyncableProperties` call crashes. The fork enumerates
   via `self.project.WritingSystems.GetAll()`, which returns `CoreWritingSystemDefinition`
   objects with `.Id` and `.Handle`.
2. **New `ApplySyncableProperties(item, props, ws_map=None)` method on `BaseOperations`.**
   Symmetric inverse of `GetSyncableProperties`; generic dict → multistring / string apply,
   handles bool fields via the setattr branch, accepts an optional WS map (currently
   identity-only in GramTrans; FR-011 will populate it).

**Patched files (9 total)** — all syntactic, no behaviour change beyond
`ApplySyncableProperties`:

- `BaseOperations.py`
- `Grammar/POSOperations.py`
- `Grammar/MorphRuleOperations.py`
- `Grammar/GramCatOperations.py`
- `Grammar/InflectionFeatureOperations.py`
- `Grammar/NaturalClassOperations.py`
- `Grammar/EnvironmentOperations.py`
- `Grammar/PhonologicalRuleOperations.py`
- `Grammar/PhonemeOperations.py`

The 8 Grammar Operations subclasses each declare an override of `ApplySyncableProperties`
for MCP-indexer visibility (the indexer's static analysis doesn't follow inheritance).

### Install

`pyproject.toml` declares `flexlibs2>=2.0`. The fork is installed manually:

```powershell
pip install -e D:/Github/_Projects/_LEX/flexlibs2
```

Or — once the patches are published on a fork remote — pin to a git URL in
`pyproject.toml`. Upstreaming to `cdfarrow/flexlibs2` is tracked separately.

### Constitution authority

Per [constitution v5.0.0 Principle II](.specify/memory/constitution.md), module code
imports flexlibs2 modules **directly**. There is no `flavors/` adapter contract in this
repo. The LibLCM-direct implementation is a separate post-Phase-2 sibling repository,
not an in-tree deliverable. See the constitution Sync Impact Report for the v4.0.0 →
v5.0.0 rationale.

## Session handoff

See [STATUS.md](STATUS.md) for the most recent session's validated work (Layer 1+2
done against the Ejagham Mini → Ejagham Full GT-Test pair) and the pickup checklist.
The next session's blocking task is **T-Spike** in
[specs/001-phase0-additive-transfer/tasks.md](specs/001-phase0-additive-transfer/tasks.md):
refactor `gramtrans.py.transfer_verb_vertical()` into the `Lib/preview.py` +
`Lib/transfer.py` Preview/Move split required by constitution v5.0.0 Principle III
closing clause before Layer 3 begins.
