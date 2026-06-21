# Phase 3a Foundational MCP Probes (T004–T009)

Discovery findings against `Ejagham Full GT-Test` via `flextools-mcp` on
2026-06-20. All Phase 3a factory probes return a **`Create(Guid guid)`
overload alongside the no-arg `Create()`** — GUID preservation is
universally supported, identity_remap fallback is needed only as a
runtime safety net.

## Per-factory results

| Factory | `Create()` | `Create(Guid)` | Status |
|---------|-----------|----------------|--------|
| `IPhPhonemeFactory` | ✓ | ✓ | GUID-preservable |
| `IPhNCSegmentsFactory` | ✓ | ✓ | GUID-preservable |
| `IPhNCFeaturesFactory` | ✓ | ✓ | GUID-preservable |
| `IMoStratumFactory` | ✓ | ✓ | GUID-preservable |
| `IPhEnvironmentFactory` | (already verified Phase 0) | ✓ | GUID-preservable (existing Phase 0 code) |
| `IPhRegularRuleFactory` / `IPhSegmentRuleFactory` / `IPhMetathesisRuleFactory` | not yet probed | likely yes (LCM 9.x convention) | Implementation-time probe at T026 |
| `IFsClosedFeatureFactory` (phon subsystem) | (already verified Phase 0 IF) | ✓ | GUID-preservable |

All probed factories also expose `CreateInternal()` (returns `ICmObject`),
which is the LCM-internal hook the public `Create()` wraps — not used
by GramTrans.

## Implication for tasks

- **T016 / T021 / T032**: planner can call `factory.Create(Guid)` per
  the existing Phase 0 IF / IPhEnvironment pattern. No identity_remap
  fallback needed at plan time.
- **T026 (Phon Rules)**: probe the specific rule-subtype factory at
  implementation time; if any subtype's `Create(Guid)` is absent, fall
  back to identity_remap per Phase 1 FR-012 (MSA / Allomorph pattern).
- **flexlibs#196 (Strata Operations)**: independent of this finding —
  the issue still adds value by giving strata an Operations-class
  surface (`project.Strata.GetAll()`, `Find()`, `Create(name)`,
  `GetSyncableProperties()`). Whether or not it lands before Phase 3a
  ships, the GUID-preservable factory is already usable via
  `project.GetService(IMoStratumFactory)`.

## Runtime safety net (unchanged)

Phase 1's `identity_remap` mechanism remains the documented fallback
for any factory whose `Create(Guid)` raises at runtime (e.g., the
target's GUID space already contains the source's GUID with a
conflicting type). The implementation should catch the LCM exception
and route to remap on a per-object basis, not preemptively.

## Probe commands used

```python
flextools_get_object_api(object_type='PhPhonemeFactory')
flextools_get_object_api(object_type='PhNCSegmentsFactory')
flextools_get_object_api(object_type='PhNCFeaturesFactory')
flextools_get_object_api(object_type='MoStratumFactory')
```

Output schema: `methods[].signature` carries the Guid-overload variant
explicitly when present.
