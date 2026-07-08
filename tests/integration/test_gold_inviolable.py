"""GOLD invariant integration scaffold (Ejagham Mini -> Ejagham Full GT-Test).

Constitution v7.0.0 (GOLD unlock) RETIRED the old byte-identical rule that this
module used to encode. GOLD / catalog / reserved objects are now ORDINARY items:
their fields (Name, Abbreviation, Description, LiftResidue, ...) MAY change and
merge/update like any custom item. The former assertion -- that every GOLD object
is byte-for-byte identical before and after a Move -- is therefore WRONG under
v7.0.0 and has been removed.

The single protected invariant is now the ontology concept<->object-GUID binding
(a closest-match assertion): a created target object must be bound to its
concept's canonical GUID and must never carry a GUID naming a non-matching
concept. Enforcing that binding via GUID remapping at target-object CREATION is
"GOLD unlock Half 2" and is NOT part of the Half 1 field-unlock. Until Half 2
lands there is no creation-time binding machinery to exercise here, so this
scaffold is skipped rather than asserting either the retired byte-identical rule
or an as-yet-unbuilt invariant.

See the source rework https://github.com/MattGyverLee/GramTrans/issues/22
(Parts 2 & 3) and the "GOLD unlock Half 2" tracking issue for the binding-
enforcement design.
"""
from __future__ import annotations

import pytest

# All integration tests are marked so unit-only runs skip them:
#   pytest -m 'not integration'
# The marker is registered in pyproject.toml.
pytestmark = pytest.mark.integration


def test_gold_concept_guid_binding_preserved_after_move() -> None:
    """NEW invariant (constitution v7.0.0): after a Move, each GOLD/ontology
    object on the target must still be bound to its concept's canonical GUID
    (closest-match). GOLD *fields* MAY differ before/after -- only the
    concept<->GUID binding is protected.

    Deferred: the creation-time GUID-remapping/binding step that this test would
    assert is "GOLD unlock Half 2" and is not yet implemented. The old
    byte-identical assertion is retired under v7.0.0 and must NOT be reinstated.
    """
    pytest.skip(
        "GOLD unlock Half 2 not yet implemented: the concept<->GUID binding is "
        "enforced by GUID remapping at target-object creation, which does not "
        "exist yet. The retired v6.x byte-identical GOLD rule is intentionally "
        "not asserted here (constitution v7.0.0). Track: GOLD unlock Half 2 / "
        "https://github.com/MattGyverLee/GramTrans/issues/22 (Parts 2 & 3)."
    )
