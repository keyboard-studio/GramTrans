# Contract: Residue `merge=` Segment

Extends the Phase 1 `ImportResidueTag` wire format with an optional `merge=<base64>` segment carrying the `MergeDecisionLog` for the object.

## Wire format

```
GT|<run_id>|<source_project_name>|<iso_timestamp>[|snap=<base64>][|merge=<base64>]
```

- Segments 1–4 are unchanged from Phase 0.
- Segment 5 (optional) is the Phase 1 snapshot, prefix `snap=`.
- Segment 6 (optional, Phase 2) is the Phase 2 merge log, prefix `merge=`.
- If both optional segments are present, `snap=` MUST appear before `merge=`. Parsers MUST recognize segments by prefix, not column position.

## Encoding

```python
merge_json = log.to_json()          # stable JSON, sort_keys=True
merge_bytes = merge_json.encode("utf-8")
merge_b64 = base64.b64encode(merge_bytes).decode("ascii")
```

Decoding is the symmetric inverse. Errors during decode (corrupt base64, invalid JSON, schema mismatch) MUST cause `decode_merge_log()` to return None — not raise. Callers fall back to fresh-prompt behavior per FR-215.

## API additions (in `Lib/residue.py`)

```python
class ImportResidueTag:
    merge_b64: Optional[str] = None  # new field

    def serialize(self) -> str: ...
    @classmethod
    def parse(cls, s: str) -> Optional["ImportResidueTag"]: ...
    def with_merge_log(self, log: MergeDecisionLog) -> "ImportResidueTag": ...
    def decode_merge_log(self) -> Optional[MergeDecisionLog]: ...
```

## Round-trip invariant

For every `ImportResidueTag t` with `merge_b64` set:
```python
parsed = ImportResidueTag.parse(t.serialize())
assert parsed == t
assert parsed.decode_merge_log() == t.decode_merge_log()
```

For tags WITHOUT `merge_b64` (Phase 0 / Phase 1 tags), the round-trip MUST still hold and `decode_merge_log()` MUST return None.

## Backward compatibility

| Tag form           | Parses with Phase 0 parser | Parses with Phase 1 parser | Parses with Phase 2 parser |
|--------------------|----------------------------|----------------------------|----------------------------|
| 4-segment          | yes                        | yes                        | yes                        |
| 5-segment (`snap=`)  | no                         | yes                        | yes                        |
| 6-segment (`snap=` + `merge=`) | no              | no                         | yes                        |
| 5-segment (`merge=` only — `snap=` absent) | no  | no                         | yes                        |

Phase 2 parser MUST tolerate `merge=` appearing without `snap=` (e.g. when the interactive run targets a Phase 0 object that had no Phase 1 snapshot to begin with).

## Size budget

A `MergeDecisionLog` with 20 fields × ~200 bytes each compresses through base64 to roughly 5 KB. LiftResidue is Unicode-string-typed with no platform-imposed length cap up to LCM's general string limit (well over 1 MB). No practical pressure within Phase 2's expected scope.
