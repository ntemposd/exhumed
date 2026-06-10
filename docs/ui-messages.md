# UI Messages

This document lists all user-facing status messages in the frontend, their EXHUMED-themed copy, and what triggers each one.

The canonical theming layer is `frontend/components/status-messages.ts`. Backend stream payloads may still carry technical strings (for example `Rate limit hit. Retrying in 2.0s`); the frontend rewrites those before they reach the system-message line or thinking bubbles.

---

## Debate Controller (`use-debate-controller.ts`)

| New message | Old message | Trigger |
|---|---|---|
| `The chamber awaits.` | `Standby.` | Initial state on load |
| `The dead are summoned.` | `Round armed.` | PLAY pressed, starting a fresh round |
| `The séance resumes.` | `Round resumed.` | PLAY pressed, resuming a paused mid-round queue |
| `Raising {name}...` | `Running {name}...` | A speaker's turn begins (LLM request fires) |
| `{name} stirs slowly. Still channeling...` | `{name} is taking longer than usual. Waiting on the backend...` | Turn has not completed after 12 seconds |
| `{name} awaits the call.` | `Queued {name}.` | A turn completes; next speaker is queued |
| `The round is interred.` | `Round complete.` | Last speaker of the round finishes |
| `Sealing the vault after this voice.` | `Pausing after current speaker.` | PAUSE pressed while a turn is in flight |
| `The voices fall silent.` | `Debate paused.` | Debate pauses (mid-round or after current turn) |
| `The record expunged.` | `Debate cleared.` | Session wipe completes successfully |
| `A new séance prepared.` | `New session armed.` | New session created (renew button) |
| `New topic. A fresh séance begins.` | `Topic changed. Started a fresh session.` | Topic changed after messages already exist |
| `Summon at least one legend.` | `Draft at least one legend.` | PLAY pressed with no speakers selected |
| `Transcribing the séance...` | `Preparing PDF...` | PDF export starts |
| `The transcript surfaces.` | `Print dialog opened.` | PDF export succeeds, print dialog opens |
| `Nothing to transcribe.` | `No messages to export.` | PDF export attempted with no messages |
| `The séance was interrupted.` | `Turn execution failed` | Default fallback when a turn errors |
| `The voice did not return.` | `Agent failed to produce a response.` | Displayed in the transcript bubble on turn failure |

---

## Throttle / Rate Limit (`status-messages.ts`, `discussion-transcript.tsx`, `use-debate-controller.ts`)

| Surface | Message | Trigger |
|---|---|---|
| **Thinking bubble** | `The ether is congested. Retrying in {n}s` (live countdown) | Groq 429 during an in-flight turn; ticks in the bubble only |
| **Transcript header** | *(hidden during retry)* — stays on the prior line e.g. `Raising {name}...` | Header does not mirror the countdown; bubble owns throttle detail |
| **Transcript header** | `The ether is congested` | Static throttle copy when surfaced outside an active thinking bubble |
| **Transcript header** | `The ether is exhausted. The daily quota is spent.` | Daily token quota exhausted; backend fails fast |

Legacy mapping (backend → themed):

| New message | Old message | Trigger |
|---|---|---|
| Bubble: `The ether is congested. Retrying in {n}s` | `Rate limit hit. Retrying in {n}s` / `Request throttled. Retrying in {n}s` | Groq returns 429 with a short retry-after (≤ 60s); backend retries and streams countdown |
| Header/bubble: `The ether is congested` | `Request throttled` | 429 detected without an active bubble countdown |
| Header: `The ether is exhausted. The daily quota is spent.` | `LLM rate limit: quota exhausted, retry after {n}s` | Daily token quota exhausted |

> **Note on long countdowns:** If `retry-after > 60s` the backend now fails fast instead of sleeping. This surfaces when Groq's **daily token quota (TPD)** is exhausted — retrying would just hit the same wall immediately after the sleep.

> **Header vs bubble:** Live retry countdown appears **only** in the active speaker's thinking bubble. The transcript header keeps the prior lifecycle line (`Raising {name}...`) or hides throttle copy while a turn is running. Turn errors show in the header only (not duplicated in the command footer).

---

## Workbench State (`use-workbench-view-state.ts`)

| New message | Old message | Trigger |
|---|---|---|
| `Unearthing the registry...` | `Recovering legend registry...` | Agent list is loading for the first time |
| `The vault is sealed.` | `Legend registry unavailable.` | Agent list failed to load and no cached agents exist |
| `The vault is empty.` | `No legends available.` | Agent list loaded but returned zero agents |
| `Surveying the ether...` | `Checking services...` | Service health check loading for the first time |
| `The chamber fell silent.` | `The chamber stalled before the first response. Adjust the council or topic and try again.` | Error state before any message has appeared |

---

## Messages not changed (technical / instructional)

These were kept verbatim because they carry precise technical instructions the user needs to act on:

| Message | Reason kept |
|---|---|
| `Popup blocked — allow popups and try again.` | Actionable browser instruction |
| `Topic is too long ({n}/255 characters).` | Precise validation feedback |
| `Debate cleared locally, but backend cleanup failed.` | Distinguishes partial failure |
| `Open services to run live checks.` | Instructional, not a status |
| `Assemble the Council, define the Topic, and press PLAY.` | Idle onboarding instruction (already themed) |
| `The chamber is assembling. First responses will appear here as the round begins.` | Already themed |
