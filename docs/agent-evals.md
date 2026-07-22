# Agent Evals (MVP)

EXHUMED uses evaluation to ask a hard question in plain language: **when a historical persona answers, how grounded and in-character is that answer?**

One sentence: we generate fixed debate turns with the live RAG pipeline, have a second LLM score each answer 1–5 for faithfulness and persona, and can optionally run a script that proposes (and applies) a better system prompt from failing cases.

This doc is both an operator guide and an AI-literacy walkthrough of what “eval” means here.

---

## Why evaluate at all?

Large language models do not come with a built-in grade. Without evals you only have vibes: “this sounded like Socrates today.”

Evals turn vibes into a **repeatable check**:

1. Fix the inputs (same speakers, topics, prior turns)
2. Generate answers the same way production does
3. Score them against a written rubric
4. Compare runs over time (did a prompt change help or hurt?)

That is the literacy point: **measurement is a design choice**, not magic. What you measure, how you score it, and what you ignore all shape what “better” means.

---

## Two layers (do not confuse them)

| Layer | What it is | Trust it for |
|---|---|---|
| **Telemetry proxies** (sidebar: Source relevance, Shared wording, Diversity) | Cheap math on scores/words already available | Rough live signals; easy to misread |
| **LLM-as-judge evals** (offline suite + optional online judge) | Second model call with a rubric + retrieved evidence | Prompt tuning and regression; still imperfect |

The sidebar bars are **not** the eval. The JSON reports under `backend/evals/reports/` are.

---

## What we evaluate

Two dimensions only (MVP):

### Faithfulness

**Question:** Are the reply’s substantive claims supported by the **retrieved speaker chunks** for that turn?

This is *grounding in what we fetched*, not “historically true in the absolute sense.” If retrieval missed a relevant passage, a true claim can still score low.

### Persona

**Question:** Does the reply sound like that historical figure—voice, values, rhetorical style, era-appropriate reasoning?

This is *character fidelity*, not lexical overlap with sources. Paraphrasing in-character can score high on persona and low on Shared wording in the sidebar.

---

## The rubric (1–5)

Source of truth in code: [`backend/evals/judge.py`](../backend/evals/judge.py) (`JUDGE_SYSTEM_PROMPT`).

### Faithfulness

| Score | Meaning |
|---|---|
| **5** | Nearly all substantive claims are supported by the retrieved context |
| **4** | Mostly supported; minor unsupported flourish |
| **3** | Mixed; some important claims lack support |
| **2** | Largely unsupported or invents material |
| **1** | Ignores sources / fabricates freely |

**Empty retrieval rule:** score at most **2** unless the answer clearly hedges or abstains from source-backed claims.

### Persona

| Score | Meaning |
|---|---|
| **5** | Strongly sounds like the named figure (voice, values, style, era-appropriate reasoning) |
| **4** | Clearly in character with small slips |
| **3** | Partially in character / generic with some flavor |
| **2** | Weak persona; modern chatbot tone or wrong values dominate |
| **1** | Not in character |

**Extra judge instructions:** punish modern anachronism and generic assistant phrasing; **do not** reward word overlap alone—judge character fidelity.

### What the judge returns

```json
{
  "faithfulness": 1-5,
  "persona": 1-5,
  "faithfulness_notes": "...",
  "persona_notes": "...",
  "unsupported_claims": ["..."]
}
```

For the UI, scores are normalized to 0–1 with `(score - 1) / 4` (so 1→0%, 3→50%, 5→100%).

---

## Pipeline (one fixture case)

```text
Fixture (agent + topic + optional prior turn)
    → retrieve speaker chunks (same Vector path as live debate)
    → build prompt + generate answer (same LLM path as live debate)
    → second LLM call: judge with rubric + evidence
    → store scores, notes, unsupported claims
```

Evidence the judge sees:

- speaker id / display name  
- system prompt  
- retrieved context text  
- previous debate turn (if any)  
- candidate answer  

It does **not** see the whole corpus—only what retrieval returned for that topic.

---

## Offline suite (source of truth)

Fixtures: [`backend/evals/fixtures/persona_faithfulness_v1.json`](../backend/evals/fixtures/persona_faithfulness_v1.json)  
(~8 cases across Socrates, Sun Tzu, Napoleon, Marcus Aurelius; mix of opening and rebuttal turns.)

```bat
.\.venv\Scripts\python.exe -m backend.scripts.run_eval_suite
```

Optional filters:

```bat
.\.venv\Scripts\python.exe -m backend.scripts.run_eval_suite --agent-id agt_001
.\.venv\Scripts\python.exe -m backend.scripts.run_eval_suite --case-id socrates_virtue_opening
```

Reports land in `backend/evals/reports/` (gitignored JSON).

### Pass thresholds (MVP)

A run **passes** if all of these hold:

- mean faithfulness ≥ **3.5**
- mean persona ≥ **3.5**
- no case with persona ≤ **2**

On fail: the report is still written and the process exits non-zero. **Nothing auto-changes** prompts or blocks the app. Improvement is a separate, deliberate step.

### How to read a report

1. **`summary`** — suite means, pass/fail, threshold list  
2. Per **`cases[]`** — the actual `answer`, retrieval size, and `judge` block  
3. Read **`persona_notes` / `faithfulness_notes`** before trusting the number  
4. Use **`unsupported_claims`** as concrete fix targets (prompt or corpus)

Literacy habit: **notes over numbers**. A “4” without reading why is cargo-cult metrics.

---

## Optimize loop (eval → prompt → re-eval)

```bat
.\.venv\Scripts\python.exe -m backend.scripts.optimize_agent_prompt --agent-id agt_001
```

What it does:

1. Load latest report (or `--report path`)
2. Collect cases for that agent below a score ceiling (default 3.5; use `--below 5` to tighten soft spots)
3. Ask an LLM to revise the `system_prompt` from those failures + notes
4. Re-run that agent’s fixtures with old vs new prompt
5. Write an `*-optimize-*.json` artifact  
6. With `--apply`: write the new prompt to the Redis agent registry **only if** combined means improved

```bat
.\.venv\Scripts\python.exe -m backend.scripts.optimize_agent_prompt --agent-id agt_001 --apply
```

Literacy point: this is **closed-loop prompting**, not model fine-tuning. You are changing instructions, then measuring whether the same fixtures score better.

---

## Online judge (optional)

Default **off** (extra LLM call per turn).

```bat
set EVAL_ONLINE_JUDGE=on
```

Restart the backend. Live turns can attach judge scores to telemetry (**Stays with the sources** / **Sounds like them** in **How this round reads**).

Use for interactive iteration; keep offline suite as the comparable record.

---

## How legit is this? (honest limits)

**Strong enough for:** regression checks, prompt diffs, teaching how RAG systems get graded.

**Not strong enough for:** claiming scientific proof of historical authenticity.

Known soft spots:

| Limit | Why it matters |
|---|---|
| Same provider/model family often generates and judges | Shared biases; judge may prefer fluent answers |
| Subjective rubric | “Sounds like Napoleon” is not a fact; humans would disagree |
| Small fixture set | Easy to overfit prompts to 8 scenarios |
| No human calibration | Numbers are not anchored to expert ratings |
| Retrieval-bounded faithfulness | Missed chunks → harsh or odd faithfulness scores |
| Run-to-run noise | Temperature-0 helps; non-determinism remains |

**AI literacy takeaway:** an eval is a **contract**—inputs, rubric, judge, thresholds—not a truth machine. Document the contract, know its failure modes, and improve the contract (more fixtures, human spot-checks, stronger judge model) as the product matures.

---

## Suggested learning path

1. Open one report in `backend/evals/reports/` and walk a single case end-to-end  
2. Compare sidebar **Shared wording** vs judge **Sounds like them** on the same turn  
3. Change one agent’s system prompt, re-run `--agent-id …`, read before/after  
4. Skim `JUDGE_SYSTEM_PROMPT` in `backend/evals/judge.py` and ask: what would *you* change in the rubric?

---

## File map

| Path | Role |
|---|---|
| `backend/evals/judge.py` | Rubric + judge call + JSON parse |
| `backend/evals/suite.py` | Fixture run, thresholds, reports |
| `backend/evals/fixtures/persona_faithfulness_v1.json` | Fixed scenarios |
| `backend/evals/reports/` | Run outputs (local) |
| `backend/scripts/run_eval_suite.py` | CLI entry for the suite |
| `backend/scripts/optimize_agent_prompt.py` | Prompt optimize loop |
| Telemetry “How this round reads” | Live proxies (+ optional judge rows) |
