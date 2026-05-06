# Adding a New Speaker Source

This guide describes the current workflow for adding a new speaker to Vector-backed retrieval.

## What You Need

To make a speaker work well at runtime, you need all of the following aligned:

1. an agent id and display identity already recognized by the app
2. a source text in `data/`
3. an ingestion config entry in `backend/scripts/ingest_agent_knowledge.py`
4. a source extraction strategy that removes boilerplate and preserves the real content
5. a Vector upsert for that speaker
6. a retrieval smoke test after ingestion

## Current Pattern

The ingestion script is currently speaker-aware rather than fully generic.

That means each new speaker usually needs:

- a metadata config entry in `AGENT_SOURCE_CONFIG`
- a body extractor in `extract_body()` or a new helper it dispatches to

## Step-by-Step Checklist

### 1. Add the source file

Place the source material in `data/`, for example:

- `data/agt_003.txt`

Choose the file content carefully:

- remove copyright-problematic material if needed
- prefer public-domain or clearly reusable source text
- include the real speech, dialogue, essay, or letters, not only summaries

### 2. Inspect the source boundaries

Before editing the ingestion script, determine:

- where boilerplate starts and ends
- whether the first line is an intro that should be removed
- whether there are section markers or end markers
- whether the text is already clean enough to chunk directly

The goal is to ingest the actual speaker material, not title pages, editors' notes, or archive headers.

### 3. Add metadata to `AGENT_SOURCE_CONFIG`

Add a new config entry in `backend/scripts/ingest_agent_knowledge.py`.

Required fields in the current pattern:

- `speaker_name`
- `source_title`
- `author`
- `translator`
- `source_type`
- `voice_type`
- `source_slug`
- `section`

Example shape:

```python
"agt_003": {
    "speaker_name": "Sun Tzu",
    "source_title": "The Art of War",
    "author": "Sun Tzu",
    "translator": "",
    "source_type": "treatise",
    "voice_type": "primary",
    "source_slug": "art_of_war",
    "section": "main_text",
}
```

### 4. Add or update the body extractor

If the file contains boilerplate, add a source-specific extraction helper.

Examples already in the repo:

- `extract_apology_body()` for Socrates
- `extract_stanford_speech_body()` for Steve Jobs

Then wire it into `extract_body(agent_id, text)`.

### 5. Dry-run the ingestion

Run the script without writing to Vector first.

Windows:

```bat
.\.venv\Scripts\python.exe backend\scripts\ingest_agent_knowledge.py --agent-id agt_003 --source-file data\agt_003.txt --dry-run
```

Check:

- the chunk count looks reasonable
- the first chunk preview starts at the real text, not the intro or archive header
- the text is coherent and not over-split

### 6. Upsert the source

When the dry run looks correct:

```bat
.\.venv\Scripts\python.exe backend\scripts\ingest_agent_knowledge.py --agent-id agt_003 --source-file data\agt_003.txt
```

### 7. Smoke-test retrieval

Use the same backend retrieval path the app uses:

```bat
.\.venv\Scripts\python.exe -c "from pathlib import Path; from dotenv import load_dotenv; load_dotenv(Path('.env')); from backend.services.database import create_database_service; svc=create_database_service(); results=svc.get_agent_context('What strategic principle matters most in conflict?', 'agt_003', top_k=3); print(len(results)); [print((r.get('score'), (r.get('data') or '')[:180].replace('\n',' '))) for r in results]"
```

What you want to see:

- nonzero results
- source-consistent text excerpts
- relevance scores that are not obviously random

### 8. Verify in the live app

After ingestion and restart:

- run a turn for that speaker
- check backend logs for retrieval matches
- check the `VECTOR USAGE` box in the Next.js telemetry panel

## Chunking Guidance

The current script uses:

- paragraph-first chunking
- sentence fallback when a paragraph is too large
- overlap between chunks

Keep sources in medium-sized semantic chunks rather than tiny sentences. The current defaults are a reasonable baseline unless a source is unusually dense or repetitive.

## Prompt Behavior Reminder

Retrieved source text is used as background grounding, not as a scene to continue directly.

That means if the source contains named interlocutors, courtroom exchanges, or address forms, the backend prompt tries to prevent those from leaking directly into unrelated debates.

## Current Caveats

- the ingestion pipeline is not yet fully generic
- some speakers may need source-specific cleaning logic
- retrieval is currently topic-driven, so vague topics can still retrieve broad chunks
- adding a speaker source is necessary but not always sufficient for good runtime behavior; the base system prompt still matters