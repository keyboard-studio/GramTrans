<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan
at specs/020-conflict-mode-field-merge/plan.md
<!-- SPECKIT END -->

## Git Workflow Protocol (specs → main, work → worktree)

**Spec artifacts are committed directly to `main`.** Anything under a `specs/`
feature folder — `spec.md`, `plan.md`, `research.md`, `data-model.md`,
`contracts/`, `quickstart.md`, `probe-results.md`, `checklists/`, `tasks.md`,
amendments, and any other planning doc — goes straight to `main`, not onto a
feature branch.

- **Why:** spec files on a feature branch are invisible to other agents/sessions
  until merged. That created a backlog where the specs that most needed work
  could not be seen. Keeping them on `main` means every session sees the full,
  current queue of what needs doing.
- Spec artifacts are additive-per-feature (each lives in its own `specs/NNN-*/`
  folder), so committing them to `main` should **not conflict** with other
  branches. Keep it that way: do not edit another feature's spec files from an
  unrelated worktree.
- The `.specify/feature.json` pointer and the `<!-- SPECKIT -->` block in this
  file are spec-adjacent bookkeeping and also commit to `main`.
- This applies to `/speckit-specify`, `/speckit-plan`, `/speckit-tasks`,
  `/speckit-clarify`, `/speckit-analyze`, and any manual spec edits.

**Implementation / work files are committed on a worktree**, not `main`.
Once a feature is actually being *implemented* (source under `src/`, tests under
`tests/`, and any non-spec change), do that work in a dedicated git worktree on a
feature branch (e.g. `../GramTrans-NNN-<short-name>` on branch `NNN-<short-name>`),
and merge back to `main` when the work is validated.

- Rule of thumb: **if it lives under `specs/`, commit it to `main`; otherwise
  commit it on the feature worktree.**
- A single `/speckit-plan` run may create the worktree *and* write spec files —
  commit the spec files to `main` and keep code changes on the worktree.

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

When working and referencing flexicon or liblcm, ALWAYS use FLExToolsMCP instead of using direct code inspection. This allows lookup and testing. `Ejagham Mini` and `Esperanto`, `Mbugwe Lizzie HCPractice` are good (read-only) test projects for many phenomena.
