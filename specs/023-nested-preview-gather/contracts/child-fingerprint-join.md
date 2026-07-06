# Contract: Child Fingerprint Join

**Module**: `src/gramtrans/Lib/fingerprints.py` (new, Qt-free, no Move-execution imports).

## Interface

```
child_join_token(kind: str, obj: Any, *, ws_handle=None) -> tuple
# kind in {"allomorph", "sense", "msa"}; returns a hashable content-derived token.

token_hash(token: tuple) -> str      # stable short digest for machine-key construction
```

`preview.py` / `matcher.py` fingerprints SHOULD compose their GUID-bearing fingerprints from the same
content token so preview and Move discriminate on the same content (research R2).

## Guarantees

- **G1 (cross-project stability)**: the token contains **no** project-specific GUID that differs
  across the source/target pair (no `owner_entry_guid`, no raw `pos_guid`). Allomorph token uses form
  text + global morph-type id (GUID if globally stable else name); sense uses gloss text; MSA uses the
  label (POS abbrev + slot names).
- **G2 (Move agreement)**: for the common case (POS transferred GUID-first / already aligned), the
  pairing induced by `child_join_token` equals the pairing computed by
  `preview._match_allomorphs_by_fingerprint` / `_match_msas_by_fingerprint` (SC-006).
- **G3 (determinism on collision)**: identical tokens among source children are disambiguated by
  first-unused ordinal in source order (spec Edge Case "ambiguous fingerprint").
- **G4 (containment)**: unreadable discriminators degrade the token (empty component) rather than
  raising; a fully unreadable child still gets a stable fallback token from its ordinal.

## Divergence (documented)

If a target child differs from its source counterpart only in a field **outside** the token (e.g. two
allomorphs share form + morph type but differ in environments), the preview pairs them anyway
(first-unused-wins) — matching Move's own fingerprint behavior, which also excludes environments from
the allomorph fingerprint.

## Acceptance

- SC-006; spec Edge Cases "child count mismatch", "ambiguous fingerprint match".
