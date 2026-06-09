# Lib Architecture

This folder holds frontend-wide shared contracts and configuration that should
not depend on feature-level React components.

## Current Files

- `config.ts` exposes the browser-facing backend base path (`/api/backend`). The real backend URL and API key live in server-only env vars (`BACKEND_URL`, `BACKEND_API_KEY`) read by `app/api/backend/[...path]/route.ts`.
- `legends.ts` contains the local presentation registry for the historical figures.
- `types.ts` contains shared backend contract types used across the frontend.

## Rule Of Thumb

Put a file in `lib/` when it is:

1. Shared across features.
2. Not tied to one React screen.
3. Safe to import from hooks, view-models, or renderers without pulling UI concerns along with it.

If a file only exists for the current main UI surface, it should usually stay
under `components/` instead of being promoted to `lib/` too early.