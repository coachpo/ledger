# RETIRED PORTFOLIO PAGES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/pages/AGENTS.md`.

## OVERVIEW

`src/pages/portfolios/` is retired migration residue pending Task 4.2 deletion. It is not a live routed surface, not a sidebar destination, and must not be treated as product scope.

Portfolio bookkeeping, balances, positions, trades, and the `/portfolios` routes were removed from live SignalDeck scope. Do not add new work here except deletion cleanup required by the migration plan.

## CONVENTIONS

- Prefer deleting code in this directory over updating it.
- Do not re-add `/portfolios` route metadata, navigation, API calls, tests, or Finance Workspace gates.
- Do not document portfolio bookkeeping as a live workflow, route family, or extension surface.

## VALIDATION

Use the migration task validation from the parent frontend guide after deleting remaining files.
