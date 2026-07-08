# RETIRED PORTFOLIO COMPONENTS GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/components/AGENTS.md`.

## OVERVIEW

`src/components/portfolios/` is retired migration residue pending Task 4.2 deletion. It no longer supports live routed pages, navigation, API calls, or Finance Workspace scope.

Portfolio bookkeeping, balances, positions, trades, and related dialogs are outside the mini-Jenkins product. Do not add new behavior here; remove remaining references when executing the frontend deletion task.

## CONVENTIONS

- Prefer deletion over maintenance in this directory.
- Do not reintroduce portfolio APIs, hooks, route metadata, navigation, or tests.
- Do not describe portfolio bookkeeping as a live feature surface.

## VALIDATION

Use the migration task validation from the parent frontend guide after deleting remaining files.
