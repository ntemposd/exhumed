# Adding a New Speaker Source

This guide describes the workflow for adding a new speaker to Vector-backed retrieval.

## What You Need

To make a speaker work well at runtime, you need all of the following aligned:

1. an agent id and display identity already registered in Redis
2. a source text in `data/`
3. a named `AgentIngestPlan` entry in `backend/scripts/ingest_agent_knowledge.py`
4. a source extraction strategy that removes boilerplate and preserves the real content
5. a Vector upsert for that speaker
6. a retrieval smoke test after ingestion

## Step-by-Step Checklist

### 1. Register the agent in Redis

The agent must exist in the registry before it can receive turns. Register it via the API or directly through the admin tooling:

```bash
curl -X POST http://localhost:8000/agents/register \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agt_017",
    "display_name": "Virginia Woolf",
    "system_prompt": "You are Virginia Woolf...",
    "temperature": 0.7,
    "max_tokens": 512
  }'
```

### 2. Add the source file

Place the source material in `data/`, for example:

- `data/agt_017.txt`

Choose the file content carefully:

- remove copyright-problematic material if needed
- prefer public-domain or clearly reusable source text
- include the real speech, dialogue, essay, or letters — not only summaries
- the file is read as a single UTF-8 text block; the extractor function handles internal structure

### 3. Inspect the source boundaries

Before editing the ingestion script, determine:

- where boilerplate starts and ends (title page, Project Gutenberg header/footer, editors' notes)
- whether there are section markers or end markers to detect
- whether the text is clean enough to chunk directly or needs a custom extractor

The goal is to ingest the actual speaker material, not archive headers or license text.

### 4. Add a metadata config entry to `AGENT_SOURCE_CONFIG`

```python
"agt_017": {
    "speaker_name": "Virginia Woolf",
    "source_title": "A Room of One's Own",
    "author": "Virginia Woolf",
    "translator": "",
    "source_type": "essay",
    "voice_type": "primary",
    "source_slug": "a_room_of_ones_own",
    "section": "main_text",
}
```

### 5. Write a source extractor

If the file contains boilerplate, add a helper that strips it and returns the body text:

```python
def extract_woolf_source_documents(text: str) -> List[SourceDocument]:
    body = extract_project_gutenberg_work_body(text, ebook_title="A Room of One's Own")
    return [
        build_source_document(
            "agt_017",
            body,
            source_title="A Room of One's Own",
            source_slug="a_room_of_ones_own",
            voice_type="primary",
        )
    ]
```

For simple cases, `extract_project_gutenberg_work_body()` handles standard PG formatting. For complex multi-volume or anchor-window sources, see the Napoleon extractor as a reference.

### 6. Add an `AgentIngestPlan` entry

```python
"agt_017": AgentIngestPlan(
    speaker_name="Virginia Woolf",
    extraction_summary="Extract the main essay body, excluding the PG header and license.",
    chunking_summary="Paragraph-first chunking preserving essay section boundaries.",
    document_extractor=extract_woolf_source_documents,
    chunking_policy=ChunkingPolicy(950, 12, 60, 1.2, ()),
),
```

**Chunking policy guidance:**

| Parameter | Meaning | Typical value |
|---|---|---|
| `target_chunk_size` | Target chars per chunk | 900–1000 |
| `overlap_percent` | Overlap between adjacent chunks | 10–15 |
| `min_chunk_chars` | Discard chunks shorter than this | 60 |
| `max_merge_ratio` | How aggressively to merge short paragraphs | 1.2 |
| `boundary_patterns` | Regex patterns to prefer as chunk boundaries | `()` for prose |

Larger chunks (950 chars) keep paragraphs and arguments intact. Smaller chunks (500 chars) increase recall at the cost of fragmenting context. The current default (950) is well-suited to prose sources.

### 7. Dry-run the ingestion

```bat
.\.venv\Scripts\python.exe backend\scripts\ingest_agent_knowledge.py --agent-id agt_017 --dry-run
```

Check:

- the chunk count looks reasonable (a full-length book: 200–600 chunks; a short essay or speech: 20–80 chunks)
- the first chunk preview starts at the real text, not the intro or archive header
- the source breakdown shows the expected documents
- average chunk length is near the target (850–1050 chars)

### 8. Upsert to Upstash Vector

When the dry run looks correct:

```bat
.\.venv\Scripts\python.exe backend\scripts\ingest_agent_knowledge.py --agent-id agt_017
```

The script reports total chunks and a per-source breakdown on completion.

### 9. Smoke-test retrieval

```bat
.\.venv\Scripts\python.exe -c "
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path('.env'))
from backend.services.database import create_database_service
svc = create_database_service()
results = svc.get_agent_context('What does solitude mean for creative work?', 'agt_017', top_k=3)
print(len(results), 'matches')
for r in results:
    print(r.get('score'), (r.get('data') or '')[:180].replace('\n', ' '))
"
```

What you want to see:

- nonzero results
- scores in the 0.65–0.82 range (scores below this suggest a mismatch between query and corpus)
- text that's clearly from the source material, not boilerplate

### 10. Verify in the live app

After ingestion and backend restart:

- run a turn for that speaker on a relevant topic
- check backend logs for retrieval matches
- check the `VECTOR USAGE` section in the telemetry panel — it should show the source slug and chunk count

---

## Chunking Guidance

The current script uses paragraph-first chunking with a sentence-level fallback when a paragraph exceeds the target size. Overlap is applied between adjacent chunks so a concept that spans a paragraph boundary appears in both.

Keep sources in medium-sized semantic chunks rather than tiny sentences. At ~950 chars, each chunk covers 2–3 paragraphs and is self-contained enough for the LLM to use without neighbor enrichment.

Boundary patterns (`boundary_patterns` in `ChunkingPolicy`) are regex strings matched at the start of a line. They tell the chunker to prefer breaking at chapter headings, numbered sections, or act/scene markers. Leave the tuple empty `()` for continuous prose.

---

## Corpus Size Guidelines

The source diversity filter (max 2 chunks per source slug per retrieval) means corpus size is less critical than it used to be — a large corpus no longer floods retrieval. That said:

- **Thin corpus (< 100 chunks):** retrieval is weaker on broad topics. Consider adding a second source if available.
- **Normal corpus (100–600 chunks):** good coverage across themes.
- **Large corpus (600+ chunks):** fine with diversity filter in place. No need to re-ingest at a larger chunk size unless chunks are too short to be self-contained.

---

## Prompt Behavior Reminder

Retrieved source text is used as background grounding, not as a scene to continue directly. The backend prompt instructs the speaker to apply retrieved ideas to the current topic without reproducing courtroom exchanges, named interlocutors, or scene-specific address forms from the source material.

---

## Current Caveats

- the ingestion pipeline requires a named `AgentIngestPlan` per speaker; there is no fully generic path
- some speakers need source-specific extraction logic (Napoleon's anchor-window approach, Socrates' multi-work handling)
- retrieval is topic-driven — vague or very broad topics retrieve broader, less focused chunks
- adding a speaker source is necessary but not sufficient for good runtime behavior; the system prompt voice and persona quality matters equally
