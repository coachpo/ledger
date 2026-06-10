# Review Findings

## Approved Decisions

- Slice 1 starts with contract/test hardening so later deletions do not preserve dead paths “temporarily.”
- GAP-003 is now handled explicitly through `S04A` before launch/runtime cleanup.
- GAP-004 remains investigation-before-fix inside `S06`; the plan does not assume a runtime bug without proof.
- GAP-002 is treated in two stages: early retired-table/live-upgrade guards in `S01`, then final destructive startup-repair/model cleanup in `S13` after dependencies are removed.
- Finance remains extension-owned, Digital Oracle remains tool-only, and `/api/extensions` stays slim.
- Memory remains explicit-scope, package-contextual, and single-route on the frontend.

## Required Changes Before Implementation

- Keep `S01` green throughout all later slices; do not weaken removed-route or retired-surface absence assertions to make deletions easier.
- Treat `S04A` as a contract decision slice, not a compatibility-preservation slice. Choose one export rule and delete the losing path immediately.
- In `S06`, do not change terminal-write ownership until targeted lease/finalization tests prove a real defect or ambiguity that needs consolidation.
- In `S13`, do not delete startup-repair ballast before `S01`, `S02`, `S03`, and `S11` have already removed route, import, and extension dependencies on retired surfaces.

## Anti-Patterns To Avoid

- Temporary dual paths, route aliases, compatibility DTOs, or compatibility imports.
- Preserving old table names, old repair branches, or legacy cleanup logic “just in case.”
- Reintroducing global authoring roots through frontend type names, backend parsers, or hidden route/nav metadata.
- Folding Finance-owned behavior into platform core without an explicit shared-contract decision.
- Adding Digital Oracle pages, navigation, provider bundles, or lifecycle ownership.
- Expanding memory into global CRUD/search, namespace-grant authoring, or multi-route detail pages.
- Turning runtime precision questions into speculative queue rewrites without evidence.

## Final Go/No-Go For Slice 1

**Decision**: GO

**Reason**: Slice 1 is the safest and most necessary starting point because it locks the live contract, removed-route absence, and retired-table/live-upgrade guards before any destructive cleanup begins. Its verification commands are concrete, it does not require compatibility-preserving decisions, and later slices depend on its negative tests staying intact.
