# Contract: Category Transfer Interface

**Plan**: [../plan.md](../plan.md)
**Data Model**: [../data-model.md](../data-model.md)
**Constitution**: v5.1.0 (no flavor-adapter contract — flexicon imported directly; flexicon is the standalone `pyflexicon>=4.1` package)

Every category implementation under `src/gramtrans/Lib/` MUST expose the following
interface — either as module-level functions sharing the same signatures or as a class
with these methods. Concretely:

- **`Lib/categories.py`** — one set of functions per leaf category
  (`gram_categories`, `inflection_features`, `custom_fields`, `inflection_classes`,
  `stem_names`, `exception_features`, `variant_types`, `complex_form_types`,
  `adhoc_rules`, `compound_rules`).
- **`Lib/categories_affixes.py`** — affixes (FR-005).
- **`Lib/categories_templates.py`** — templates + slots (FR-006).
- **`Lib/categories_msas.py`** — MSA wiring (entry → senses → MSAs → allomorphs).

Writing-system materialization is NOT a normal category — it runs as a pre-step inside
`Lib/transfer.py` (see Per-category notes below).

This contract is **internal** to the module. It is the boundary between the engine
(`Lib/preview.py`, `Lib/transfer.py`) and per-category semantics. Each category file
imports flexicon directly (e.g.,
`from flexicon.Grammar.POSOperations import POSOperations`) — there is no adapter
layer between category code and flexicon.

```python
# Pseudocode — actual Python signatures land in code.

class CategoryTransfer(Protocol):
    """One implementation per FR-004 grammar piece category."""

    category: GrammarCategory  # which category this implementation handles

    def enumerate_source(
        self,
        context: RunContext,
        selection: Selection,
    ) -> Iterable[SourcePiece]:
        """
        Yield every source-side piece in this category that the user has selected.

        - If `selection.categories[self.category]` is False, yield nothing.
        - For AFFIXES / TEMPLATES, honor `selection.affix_picks` /
          `selection.template_picks`. Empty set = all in category.
        - This is a READ-ONLY operation on the source project. It MUST NOT touch
          the target.
        """

    def dependencies(
        self,
        piece: SourcePiece,
    ) -> Iterable[Ref]:
        """
        Return the outgoing references the closure walker should follow from this
        piece. Used by `Lib/closure.py`.

        - Empty iterable for leaf categories (e.g., inflection features).
        - Refs name (target_category, target_source_guid) so the walker can dedup.
        """

    def required_writing_systems(
        self,
        piece: SourcePiece,
    ) -> Iterable[tuple[str, WSKind]]:
        """
        Return (ws_id, kind) pairs for every writing system this piece's strings
        live in. Used by `Lib/ws_mapping.py` to compute the mandatory mapping
        before any transfer.

        - VERNACULAR and ANALYSIS WSs are both reported.
        - A piece with no string fields returns an empty iterable.
        """

    def plan_action(
        self,
        piece: SourcePiece,
        context: RunContext,
        ws_mapping: WSMapping,
    ) -> PlannedAction | Skip:
        """
        Decide whether this piece can be transferred under the current context +
        WS mapping, and produce either a PlannedAction (will transfer) or a Skip
        (with reason).

        - MUST NOT mutate the target.
        - Reasons for a Skip include: UNMAPPED_WS (defensive — `Lib/preview.py`
          already enforces this), GOLD_INVIOLABLE (the piece IS a GOLD object
          that we never modify, but a GOLD reference is fine), GUID_CONFLICT_NO_-
          OVERRIDE (Phase 1; never returned in Phase 0), UNSUPPORTED_LCM_TYPE.
        """

    def execute_action(
        self,
        action: PlannedAction,
        context: RunContext,
        ws_mapping: WSMapping,
        residue_tag: ImportResidueTag,
    ) -> ExecutionResult:
        """
        Perform the actual add against the target project. ONLY called by
        `Lib/transfer.py.execute()`.

        - MUST set the target object's Import Residue carrier to
          `residue_tag.serialize()` before returning success — Carrier A
          (`LiftResidue`) where the LCM class exposes it, Carrier B
          (`Description`-append with `[GT-Tag]: ` prefix) otherwise.
        - MUST set GUID-on-create where LCM permits, per R6 / FR-012. Some
          flexicon factory wrappers DO accept a `Guid` parameter on `Create()`;
          where they don't, the pattern is `factory.Create()` → assign `obj.Guid`.
        - MUST be a no-op if `context` carries Preview mode (defensive — Preview
          should never reach this method).
        - Returns ExecutionResult with either `added=True` (and the actual
          target_guid, which equals intended_target_guid except in the remap
          case) or `failed=True` (with reason string).
        """
```

## Wiring conventions

- Categories call flexicon directly. No adapter indirection. Per constitution v5.1.0
  Principle II there is no `flavors/` directory in this repo.
- The FlexTools runner already wraps each `MainFunction` invocation in an
  `UndoableUnitOfWork` (per [research.md R10](../research.md) + STATUS.md MCP-validator
  quirks). `Lib/transfer.py` does NOT nest its own UOW — the iteration over `actions`
  runs inside the runner's outer unit.
- The dual-carrier residue strategy is uniform across categories (Carrier A LCM
  classes vs Carrier B `Description`-append); helpers live in `Lib/residue.py`.

## Per-category notes

- **Writing-system materialization** is NOT a normal transfer category. It runs as a
  pre-step inside `Lib/transfer.py` before the main `actions` loop, materializing the
  user's `WSMapping` into the target (creating WSs flagged with
  `create_in_target=True`).
- **`Lib/categories_affixes.py`** is the most complex: its `dependencies()` returns refs
  to inflection features, classes, stem names, exception features (FR-005), plus its
  allomorphs (which carry their own environment refs). Its `enumerate_source` honors
  `selection.affix_picks` (Q4 tree-picker output).
- **`Lib/categories_templates.py`** depends on slots and on the affixes filling those
  slots (FR-006). Its `dependencies()` walks template → slot → filling-affix. Slot
  transfer is implemented inline in this same file (no separate `slots.py`).
- **`Lib/categories_msas.py`** wires MSAs: entry → senses → MSAs → allomorphs.
  MSA `SlotsRC` and allomorph `PhoneEnvRC` cross-references are resolved by GUID lookup
  per STATUS.md Layer 3 outline.
- **`gram_categories` and `inflection_features`** (inside `Lib/categories.py`) check the
  GOLD bit in `plan_action`: a piece that *is* a GOLD object yields a Skip with
  `GOLD_INVIOLABLE`. References to GOLD objects are NOT skips — they are normal resolved
  refs and the closure walker treats GOLD objects as present-in-both.
