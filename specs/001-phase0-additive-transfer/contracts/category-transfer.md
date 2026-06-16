# Contract: Category Transfer Interface

**Plan**: [../plan.md](../plan.md)
**Data Model**: [../data-model.md](../data-model.md)

Every file in `src/gramtrans/categories/*.py` MUST expose this interface (implemented
as a module-level class or a set of module functions — either is acceptable so long
as the call sites in `core/` see the same signatures).

This contract is **internal** to the module. It is the boundary between the engine
(`core/`) and per-category semantics (`categories/`), and the boundary between
per-category semantics and the flavor adapters (`flavors/`).

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
        piece. Used by `core/closure.py`.

        - Empty iterable for leaf categories (e.g., inflection features).
        - Refs name (target_category, target_source_guid) so the walker can dedup.
        """

    def required_writing_systems(
        self,
        piece: SourcePiece,
    ) -> Iterable[tuple[str, WSKind]]:
        """
        Return (ws_id, kind) pairs for every writing system this piece's strings
        live in. Used by `core/ws_mapping.py` to compute the mandatory mapping
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
        - Reasons for a Skip include: UNMAPPED_WS (defensive — `core/preview.py`
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
        `core/transfer.py.execute()`.

        - MUST set the target object's Import Residue field to
          `residue_tag.serialize()` before returning success.
        - MUST set GUID-on-create where LCM permits, per R6 / FR-012.
        - MUST be a no-op if `context` carries Preview mode (defensive — Preview
          should never reach this method).
        - Returns ExecutionResult with either `added=True` (and the actual
          target_guid, which equals intended_target_guid except in the remap
          case) or `failed=True` (with reason string).
        """
```

## Wiring conventions

- Each `CategoryTransfer` instance defaults to **`flavor=FLEXLIBS1`** per constitution
  v3.0.0 Principle II. A category MAY declare `flavor=LIBLCM` for the write path
  ONLY if flexlibs1 cannot express the operation; that exception MUST be documented
  on the class itself (a one-line comment naming what flexlibs1 cannot do) AND
  surfaced in the plan's Constitution Check.
- Per-action mixed flavors are permitted (e.g., reads via flexlibs1, a single
  GUID-on-create call via LibLCM for one specific object class) but each LibLCM
  primitive invoked MUST satisfy the same justification rule.
- The flavor adapters expose primitives (`create_object`, `set_field`,
  `set_residue`, `set_guid`, `open_undo_unit`, etc.). Category code calls these
  primitives, never raw flexlibs1 / LibLCM imports. The flexlibs1 adapter
  implements every primitive; the LibLCM adapter implements only those that flexlibs1
  cannot satisfy.
- `core/transfer.py` opens a single `UndoableUnitOfWork` (R10) around the entire
  loop over `actions`. Each `execute_action` call runs inside that unit.

## Per-category notes

- **`writing_systems.py`** does NOT participate as a normal transfer category. Its
  job is to materialize the user's `WSMapping` into the target (creating WSs flagged
  with `create_in_target=True`). It runs as a pre-step in `core/transfer.py` before
  the main `actions` loop.
- **`affixes.py`** is the most complex: its `dependencies()` returns refs to
  inflection features, classes, stem names, exception features (FR-005), plus its
  allomorphs (which carry their own environment refs). Its `enumerate_source`
  honors `selection.affix_picks` (Q4 tree-picker output).
- **`templates.py`** depends on slots and on the affixes filling those slots
  (FR-006). Its `dependencies()` walks template → slot → filling-affix.
- **`gram_categories.py`** and **`inflection_features.py`** check the GOLD bit in
  `plan_action`: a piece that *is* a GOLD object yields a Skip with
  `GOLD_INVIOLABLE`. References to GOLD objects are NOT skips — they are normal
  resolved refs and the closure walker treats GOLD objects as present-in-both.
