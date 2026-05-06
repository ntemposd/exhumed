# Components Architecture

This folder holds React entry points and feature folders used to assemble the
frontend UI.

## Structure

- `chat-workbench.tsx` is the composition root for the main product surface.
- `hooks/` contains behavioral hooks and side-effect owners.
- `view-models/` contains derived UI-state hooks.
- `renderers/` contains presentational React components and UI primitives.
- `types.ts` and `utils.ts` hold shared component-layer contracts and helpers.

## Why It Is Flat Now

Because there is only one major feature surface right now, an extra feature
folder added more ceremony than clarity. The current structure keeps the same
architectural separation, but makes `components/` itself the feature root.

Keeping them together does three useful things:

1. It keeps the composition root close to the hooks, view-models, and renderers it orchestrates.
2. It keeps related files physically close, which makes refactoring and code navigation cheaper.
3. It preserves role-based organization without an unnecessary extra directory layer.

If the frontend grows into multiple feature slices later, introducing feature
folders again would make sense. Right now, the flatter structure is simpler.