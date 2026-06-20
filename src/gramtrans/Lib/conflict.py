"""Phase 2 — per-field conflict detection and resolution.

This module is the seam between the Preview-phase planner
(`Lib/preview.py`) and the user-interactive resolver
(`Lib/ui/conflict_dialog.py` in production, FakeConflictResolver in
tests).  Per constitution Principle III (Preview-Before-Mutate), every
ConflictPrompt is produced during planning, BEFORE any LCM mutation.

Public surface:
- `UserCancelled`: raised by `ConflictResolver.resolve` if the user
  dismisses the dialog. The caller MUST catch this and exit before any
  `transfer.execute()` call.
- `ConflictResolver`: Protocol — the interactive prompt's contract.
  Production impl: `Lib/ui/conflict_dialog.py.ConflictDialog`.
- `detect_conflicts(...)`: producer (T017, Phase 3 / US1).
- `_deterministic_merge(...)`: research.md R4 (T018, US1).
- `load_prior_decision(...)`: US3 prior-run recall (T040).
"""
from __future__ import annotations

from typing import Protocol


class UserCancelled(Exception):
    """The user dismissed an interactive dialog without completing it.

    Phase 2 (FR-213) requires this to be raised by ConflictResolver /
    WSResolver implementations.  The outermost MainFunction catches it
    and returns before any transfer.execute() call, so the target
    project is left bit-identical.
    """


class ConflictResolver(Protocol):
    """Production: PyQt ConflictDialog.  Tests: FakeConflictResolver.

    The protocol is structural -- any object exposing a compatible
    `resolve(...)` method satisfies it.  No runtime check is performed.
    """

    def resolve(self, prompts):
        """Block until the user has answered every prompt.

        Args:
            prompts: tuple[ConflictPrompt, ...].

        Returns:
            tuple[MergeDecision, ...] of the same length and order.

        Raises:
            UserCancelled: if the user dismisses the dialog.
        """
        ...
