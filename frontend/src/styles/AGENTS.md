# STYLES GUIDE

> Inherits `/AGENTS.md` and `/frontend/AGENTS.md`. This directory owns global CSS entrypoints and theme tokens.

## OVERVIEW
Global styling is split into Tailwind setup, theme tokens, and the app CSS entrypoint. Component styling should stay in components through Tailwind classes and shared UI variants unless it truly belongs to the global layer.

## STRUCTURE
```text
src/styles/
|-- fonts.css
|-- index.css
|-- tailwind.css
`-- theme.css
```

## CONVENTIONS
- `index.css` imports `tailwind.css` before `theme.css`.
- `tailwind.css` uses Tailwind v4 CSS imports with explicit `@source '../**/*.{js,ts,jsx,tsx}'` scanning.
- `tailwind.css` imports `tw-animate-css` and registers `@tailwindcss/typography`.
- `theme.css` owns `@custom-variant dark`, CSS variables, `@theme inline` mapping, and base element styles.
- `fonts.css` is intentionally empty and currently unreferenced.
- Avoid global CSS for one-off feature layout.
