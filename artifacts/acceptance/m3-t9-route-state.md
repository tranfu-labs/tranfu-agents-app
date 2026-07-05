# m3-t9-route-state acceptance evidence

## Automated verification

- `npm --prefix frontend run test:unit` passed: 56 tests, 56 passed.
- `npm --prefix frontend run build` passed.

## Acceptance mapping

1. `/skills/bogus-route-test` Not Found:
   - `frontend/src/App.tsx` wildcard route renders `NotFoundRoute`.
   - `frontend/src/App.tsx` invalid `/skills/clues/:clueKind` also renders `NotFoundRoute`.
   - Unit guard: `unknown and invalid skills routes render NotFoundRoute`.

2. `/skills?sel=` refresh restores drawer:
   - `frontend/src/views/Skills.tsx` derives `drawerSkill` from URL-selected `sel` plus current `data.table`.
   - Invalid or missing `sel` does not render `SkillDrawer`.
   - Unit guard: `frontend/src/lib/skillsSelection.test.ts` (`skills drawer restores from selected URL state instead of local-only state`), imported by `frontend/src/lib/run-tests.ts`.

3. View-record link and KPI URL semantics:
   - `frontend/src/components/skills/RankBars.tsx` uses React Router `Link` for the `↗` record action.
   - `frontend/src/lib/skillsEvidence.ts` canonicalizes generated links to `w` and drops legacy `win`.
   - Unit guards: `rank view-record action is implemented as a router anchor link`, `skill links output canonical w and drop legacy win`, `total evidence and newly published skill KPI paths stay semantically distinct`, and `skills drilldown views do not append raw location.search`.

## Browser note

The in-app browser plugin reported no available browser instances (`agent.browsers.list()` returned `[]`), so no acceptance screenshot was generated in this run.
