<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan
at specs/012-merge-preview-diff-engine/plan.md
<!-- SPECKIT END -->

## flexicon dependency

GramTrans runtime depends on **flexicon** (dist name `pyflexicon`), a standalone
independent package — it is NOT a fork or patch of stock flexlibs2. flexicon natively
provides both the `GetSyncableProperties` writing-system enumeration (via
`project.WritingSystems.GetAll()`) and the `ApplySyncableProperties(item, props,
ws_map=None)` method on `BaseOperations`.

The 8 Grammar Operations subclasses each declare an override of `ApplySyncableProperties`
for MCP-indexer visibility (the indexer's static analysis doesn't follow inheritance):

- `Grammar/POSOperations.py`
- `Grammar/MorphRuleOperations.py`
- `Grammar/GramCatOperations.py`
- `Grammar/InflectionFeatureOperations.py`
- `Grammar/NaturalClassOperations.py`
- `Grammar/EnvironmentOperations.py`
- `Grammar/PhonologicalRuleOperations.py`
- `Grammar/PhonemeOperations.py`

### Install

`pyproject.toml` declares `pyflexicon>=4.1`. Install from the local directory:

```powershell
pip install -e D:/Github/_Projects/_LEX/flexlibs2
```

> **Editor note:** The disk directory is literally named `flexlibs2` and MUST NOT be
> renamed to `flexicon` — the install command above references it by that exact path.

### Constitution authority

Per [constitution v5.1.0 Principle II](.specify/memory/constitution.md), module code
imports flexicon modules **directly**. There is no `flavors/` adapter contract in this
repo. The LibLCM-direct implementation is a separate post-Phase-2 sibling repository,
not an in-tree deliverable. See the constitution Sync Impact Report for the v4.0.0 →
v5.0.0 rationale.

## Session handoff

See [STATUS.md](STATUS.md) for the most recent session's validated work (Layer 1+2
done against the Ejagham Mini → Ejagham Full GT-Test pair) and the pickup checklist.
The next session's blocking task is **T-Spike** in
[specs/001-phase0-additive-transfer/tasks.md](specs/001-phase0-additive-transfer/tasks.md):
refactor `gramtrans.py.transfer_verb_vertical()` into the `Lib/preview.py` +
`Lib/transfer.py` Preview/Move split required by constitution v5.1.0 Principle III
closing clause before Layer 3 begins.

## Rules

When working and referencing flexicon or liblcm, ALWAYS use FLExToolsMCP instead of using direct code inspection. This allows lookup and testing.
