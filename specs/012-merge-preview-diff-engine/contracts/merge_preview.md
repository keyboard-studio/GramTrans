# Contract: `Lib/merge_preview.py` public API (012)

This is the interface contract the preview pane (014) and transfer threading (013) consume.
Everything here is **Qt-free** and holds **no LCM handle** in returned values.

## Types (see [data-model.md](../data-model.md))

- `SegmentKind` — `{added, unchanged, removed, note}`
- `DiffSegment(text: str, kind: SegmentKind, ws_role: Optional[WsRole] = None)` — **`rtl` is
  resolved at render time by `to_html` from the `WsFontRegistry`, NOT stored on the segment.**
  `diff_props` stays pure against plain dicts (no registry dependency); the registry is a
  `to_html` concern only.
- `FieldDiff(field_name: str, segments: Tuple[DiffSegment, ...], indent: int = 0)`
- `MergePreview(status: str, fields: Tuple[FieldDiff, ...], notes: Tuple[str, ...] = ())`
- Mode constants: `NEW`, `LINK_ONLY`, `OVERWRITE`, `MERGE_KEEP`

## `diff_props(src_props, tgt_props, mode, ws_role_of) -> MergePreview`

Pure. No I/O.

- `src_props: dict[str, Any]` — source syncable-props dict.
- `tgt_props: Optional[dict[str, Any]]` — target props, or `None` for NEW.
- `mode` — one of the four mode constants.
- `ws_role_of: Callable[[str], Optional[WsRole]]` — ws id → role (from `ws_role_map`).

**Guarantees**
- `tgt_props is None` → every field/value emitted `added` (FR-002, SC-001).
- LINK-ONLY → target fields `unchanged`; source-only fields carry a not-transferred `note` (FR-003).
- OVERWRITE → per union key: equal `unchanged`; source-only `added`; target-only `unchanged`;
  differing → value-shape dispatch, source wins (FR-004).
- MERGE-KEEP → per union key: equal `unchanged`; source-only/empty-target `added`; target-only
  `unchanged`; differing-with-nonempty-target → target `unchanged` + `note` (FR-004a).
- Value-shape dispatch (FR-005): multistring dict (recurse per ws; differing ws → removed+added),
  plain str (removed+added), list/tuple/set (union: common unchanged, source-only added,
  target-only unchanged), scalar int/bool/None (removed+added), other object (repr then treat
  as str).
- `fields` sorted **alphabetically** by `field_name` (FR-006, SC-003).
- Mirrors — never imports — `conflict._deterministic_merge` (FR-006).

## `props_for(handle, category, guid, *, index=None, owner_guid="") -> Optional[dict]`

Runtime (imports flexlibs2). Returns a comparable `{field: value}` dict.

**Guarantees**
- Covered category → `GetSyncableProperties(obj)` dict; builds the GUID `index` once, reuses it (FR-007).
- Template/slot category → uses `owner_guid` to resolve the owner-scoped wrapper (FR-007).
- Fork-gap category (Slots, Phonological Features, Stem Names) → direct guarded multistring read
  of Name/Abbreviation/Description per ws (+ optional slot bool) into `{field: {ws_id: text}}`;
  `None` + caller-visible note on hard failure — **never raises** to the caller (FR-008, SC-005).

## `ws_role_map(project) -> dict[str, WsRole]`

Runtime. Classifies each ws id → `VERNACULAR` / `IPA` / `ANALYSIS`, guarded against edge/missing
ws (FR-009). `IPA` when `"fonipa"` in the ws tag; `VERNACULAR` when in the vernacular list;
`ANALYSIS` otherwise.

## `to_html(preview, registry) -> str`

Pure. `registry: WsFontRegistry`.

**Guarantees** (FR-010, SC-004)
- 100% of text is HTML-escaped.
- `added` green; `removed` red + strike-through; `note` gray italic.
- Each value span uses the registry's font-family + point size for its `WsRole`.
- `dir="rtl"` (or equivalent) where the role's `WsFont.rtl` is true.
- Indentation reflects `FieldDiff.indent`; field names bold.
- A segment with `ws_role is None` renders in the default font (chrome).

## `MergePreviewService` (FR-011, FR-012)

Qt-free cache/orchestrator. Holds source/target handles, the ws-role classifier, and a lazy
target-GUID index.

- `preview_for(category, source_guid, target_guid, status, mode, owner_guid="") -> MergePreview`
  — computes lazily; memoizes on `(category, source_guid, target_guid, mode)`; re-link
  (different `target_guid`) AND resolution change (different `mode`) are each distinct keys
  (SC-006). **`mode` MUST be part of the key** — a resolution flip in-page does not fire
  `invalidate()`, so a 3-tuple key would return a stale diff. Features 014/015 MUST use this
  4-tuple key shape.
- `invalidate() -> None` — clears the cache for page re-entry.
- Caches property **dicts**, never live LCM objects; re-fetches by GUID on first click (FR-012).

## Cross-feature constraints (FR-013)

- MUST NOT import Qt (SC-007) or add any widget / wizard page / transfer behavior.
- Depends on feature 011's `SimilarResolution` action vocabulary.
- Consumed by feature 014 (pane) and 013 (transfer threading).
