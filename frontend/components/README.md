# Components

Single-feature composition root. Hooks own behaviour; view-models derive display state; renderers paint pixels.

```
components/
│
├── chat-workbench.tsx          # App composition root
├── types.ts                    # Shared view-layer contracts
├── utils.ts                    # Pure helpers and derivations
│
├── hooks/
│   ├── use-debate-controller.ts  # SSE stream + debate lifecycle
│   ├── use-workbench-data.ts     # Agents + services cache fetching
│   ├── use-topic-editor-state.ts # Topic textarea with persistence
│   ├── use-theme.ts              # Dark/light mode toggle
│   └── index.ts                  # Re-exports
│
├── view-models/
│   ├── use-workbench-view-state.ts  # Async phase states for panels
│   ├── use-telemetry-view-model.tsx # All sidebar display values
│   └── index.ts                     # Re-exports
│
└── renderers/
    ├── app-navbar.tsx                  # Logo, title, theme button
    ├── app-navbar.module.css           # Navbar layout and brand
    ├── discussion-panel.tsx            # Topic, council, type, transcript
    ├── discussion-panel.module.css     # Controls deck and transcript frame
    ├── discussion-transcript.tsx       # Message bubbles and round dividers
    ├── discussion-transcript.module.css # Bubble and round header styles
    ├── telemetry-sidebar.tsx           # Status, tables, cost, diversity
    ├── telemetry-sidebar.module.css    # Table, card, and track styles
    └── index.ts                        # Re-exports
```

## Layer rules

- **Hooks** fetch, stream, and own side effects. No JSX.
- **View-models** consume hook output and derive render-ready state. No JSX.
- **Renderers** are pure display. No fetch, no localStorage.
- **chat-workbench** is the only file allowed to cross all three layers.
