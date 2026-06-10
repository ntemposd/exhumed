# Speaker Sources Catalog

Reference for every council speaker, the on-disk source file, and the **citation fields written into Upstash Vector metadata** (`source_title`, optional `source_volume`, optional `source_chapter`) via `backend/scripts/ingest_agent_knowledge.py`.

**Legend**

| Column | Meaning |
|---|---|
| **`source_title`** | Primary work or document name (full title, no trailing `.`, no `...`) |
| **`source_volume`** | Volume label when applicable (e.g. `Vol. II`); empty string otherwise |
| **`source_chapter`** | Chapter, note, or section label when applicable; empty string otherwise |
| **Display** | UI composes `title - volume - chapter`, then truncates to 48 characters + `...` |
| **Source file** | Path under repo root (`data/<agent-id>.txt` unless noted) |
| **Ingest status** | Whether an `AgentIngestPlan` exists and the speaker is selectable in the UI |

**Storage rules** (`backend/utils/source_titles.py`):

- Stored fields strip trailing `.` / `;` / `:` and any literal `...`
- Display composes parts with ` - `, truncates the **title only**, and keeps volume/chapter visible in footers
- Does **not** rename sources beyond mechanical normalization at ingest

---

## Live Upstash Vector snapshot

**What this is:** Ground truth for what the backend retrieves today — not what ingest *intends* to write, but what is actually stored in the index pointed at by `UPSTASH_VECTOR_REST_URL` in `.env`.

**How to refresh:**

```powershell
.\.venv\Scripts\python.exe backend\scripts\query_vector_stats.py --all-agents --json > docs\vector-snapshot.json
```

**Last scan:** 2026-06-09 (full index walk via `index.range`, `scan_limit=100`)

| Field | Value |
|---|---|
| **Total chunks** | 5,694 |
| **Agents in index** | 13 (`agt_001`–`agt_009`, `agt_011`–`agt_014`; no `agt_010`) |
| **Complete JSON result** | [`docs/vector-snapshot.json`](./vector-snapshot.json) |

The JSON file is the **complete query result** — every agent block includes all `source_stats` rows (one row per distinct `source_slug` in the index) with `source_title`, `source_volume`, `source_chapter`, `source_slug`, and chunk length stats. Napoleon alone has **122** `source_slug` rows sharing one series title and `Vol. I`–`Vol. IV` volume labels.

### Index summary by agent

| Agent | Speaker | Chunks | Distinct `source_slug` rows | Notable live metadata |
|---|---|---:|---:|---|
| agt_001 | Socrates | 155 | 2 | `Apology`, `Crito` |
| agt_002 | Steve Jobs | 202 | 5 | Titles from file headers (no trailing `.`); e.g. `Stanford Commencement Address 2005` |
| agt_003 | Sun Tzu | 366 | 1 | `The Art of War` |
| agt_004 | Napoleon Bonaparte | 1,318 | 122 | Full series title + `source_volume`: `Vol. I`–`Vol. IV` |
| agt_005 | Marcus Aurelius | 149 | 2 | `Meditations` + `source_chapter`: `Second Book`, `Fourth Book` |
| agt_006 | Cleopatra | 207 | 1 | `Life of Antony - Cleopatra arc` |
| agt_007 | Leonardo da Vinci | 649 | 1 | `Thoughts on Art and Life` |
| agt_008 | Ada Lovelace | 79 | 2 | `Notes on the Analytical Engine` + chapter per note |
| agt_009 | Marie Curie | 137 | 3 | Split title/chapter (Pierre Curie + Autobiographical Notes) |
| agt_011 | Leon Trotsky | 292 | 1 | `My Life` |
| agt_012 | Friedrich Nietzsche | 491 | 1 | `The Twilight of the Idols` |
| agt_013 | Nikola Tesla | 210 | 1 | `My Inventions` |
| agt_014 | Marie Antoinette | 1,439 | 6 | Hybrid corpus (5 curated docs + Campan memoir body) |

**Semantic query example** (top-k retrieval, not a full scan):

```powershell
.\.venv\Scripts\python.exe backend\scripts\query_vector_stats.py --query "Waterloo campaign" --agent-id agt_004 --top-k 20 --json
```

---

## Catalog vs live index

The per-speaker sections below describe the **ingest catalog** (what `ingest_agent_knowledge.py` assigns at extraction time). For the authoritative live state, use the [Live Upstash Vector snapshot](#live-upstash-vector-snapshot) and [`docs/vector-snapshot.json`](./vector-snapshot.json).

Minor catalog/live differences to expect:

- **Steve Jobs** — live index uses file-header titles (e.g. `Stanford Commencement Address 2005`, slug `stanford_commencement_address_2005`); the catalog may list a shorter hand-set title for the leading speech block.
- **Napoleon** — live index lists one row per anchor-window `source_slug` (122 rows); footers dedupe by `(title, volume, chapter)` so many slugs collapse to fewer displayed citations.

---

## Ingested speakers (catalog)

### agt_001 — Socrates

| Current `source_title` | `source_slug` | Notes |
|---|---|---|
| Apology | `apology` | Plato, *Apology* (Jowett) |
| Crito | `crito` | Plato, *Crito* (Jowett) |

- **Source file:** `data/agt_001.txt`
- **Ingest status:** Ingested
- **Extractor:** `extract_socrates_source_documents`

---

### agt_002 — Steve Jobs

| Current `source_title` | `source_volume` | `source_chapter` | `source_slug` | Raw section header in `agt_002.txt` |
|---|---|---|---|---|
| Stanford Commencement Address | | | `stanford_commencement` | `Stanford Commencement Address 2005.` |
| The Lost Interview 1995 | | | `the_lost_interview_1995` | `The Lost Interview 1995.` |
| Thoughts on Flash 2010 | | | `thoughts_on_flash_2010` | `Thoughts on Flash 2010.` |
| iPhone introduction 2007 | | | `iphone_introduction_2007` | `iPhone introduction 2007.` |
| Think Different era 1997 | | | `think_different_era_1997` | `Think Different era 1997.` |

- **Source file:** `data/agt_002.txt`
- **Ingest status:** Ingested
- **Extractor:** `extract_jobs_source_documents` — leading speech block + dash-delimited sections; section titles taken verbatim from file headers (slug = `slugify(title)`)
- **Note:** First document uses a hand-set title (`Stanford Commencement Address`); later sections use the raw header line including trailing periods.

---

### agt_003 — Sun Tzu

| Current `source_title` | `source_slug` | Notes |
|---|---|---|
| The Art of War | `art_of_war` | Single treatise body (Giles translation) |

- **Source file:** `data/agt_003.txt`
- **Ingest status:** Ingested
- **Extractor:** `extract_sun_tzu_source_documents` — one document, default config title

---

### agt_004 — Napoleon Bonaparte

| Current `source_title` | `source_volume` | `source_chapter` | `source_slug` pattern | Underlying ebook (Project Gutenberg) |
|---|---|---|---|---|
| Memoirs of the life, exile, and conversations of the Emperor Napoleon | `Vol. I`–`Vol. IV` | | `memoirs_of_the_life_vol_{1-4}_{anchor}_{NNNN}` | See volume list below |

**All Napoleon anchor windows share one series `source_title` and a per-volume `source_volume`.**

**Four source volumes in one file:**

1. *Memoirs of the life, exile, and conversations of the Emperor Napoleon. (Vol. I)*
2. *Memoirs of the life, exile, and conversations of the Emperor Napoleon. (Vol. II)*
3. *Memoirs of the life, exile, and conversations of the Emperor Napoleon. (Vol. III)*
4. *Memoirs of the life, exile, and conversations of the Emperor Napoleon. (Vol. IV)*

**Anchor windows extracted per volume** (regex hits → paragraph context windows; each match becomes its own document with a unique `source_slug`):

| Anchor slug | Match pattern (summary) |
|---|---|
| `austerlitz` | Austerlitz |
| `waterloo` | Waterloo |
| `campaign_of_italy` | Campaign of Italy / Cisalpine |
| `russian_campaign` | Moscow / Borodino / Russian campaign |
| `marengo` | Marengo |
| `civil_code` | My Code / Civil Code / Napoleonic Code |
| `institutions` | My institutions / University / Legion of Honour |
| `united_states_of_europe` | United States of Europe / European association |
| `unification_of_europe` | Unification of Europe / Universal law |

- **Source file:** `data/agt_004.txt` (expected by ingest; not always present in a minimal checkout)
- **Ingest status:** Ingested (~1,318 chunks)
- **Extractor:** `extract_napoleon_source_documents` → `extract_anchor_context_documents`

---

### agt_005 — Marcus Aurelius

| Current `source_title` | `source_volume` | `source_chapter` | `source_slug` | Notes |
|---|---|---|---|---|
| Meditations | | Second Book | `meditations_second_book` | Selected book II |
| Meditations | | Fourth Book | `meditations_fourth_book` | Selected book IV |

- **Source file:** `data/agt_005.txt`
- **Ingest status:** Ingested
- **Extractor:** `extract_meditations_source_documents`

---

### agt_006 — Cleopatra

| Current `source_title` | `source_slug` | Notes |
|---|---|---|
| Life of Antony - Cleopatra arc | `life_of_antony_cleopatra_arc` | Plutarch, *Life of Antony* (Cleopatra narrative slice) |

- **Source file:** `data/agt_006.txt`
- **Ingest status:** Ingested
- **Extractor:** `extract_cleopatra_source_documents` — single document, default config title

---

### agt_007 — Leonardo da Vinci

| Current `source_title` | `source_slug` | Notes |
|---|---|---|
| Thoughts on Art and Life | `thoughts_on_art_and_life` | *Thoughts on Art and Life* (Baring translation), notebook fragments |

- **Source file:** `data/agt_007.txt`
- **Ingest status:** Ingested
- **Extractor:** `extract_leonardo_source_documents` — single document

---

### agt_008 — Ada Lovelace

| Current `source_title` | `source_volume` | `source_chapter` | `source_slug` | Notes |
|---|---|---|---|---|
| Notes on the Analytical Engine | | Note A - Analytical Engine Scope | `note_a_analytical_engine_scope` | Note A only |
| Notes on the Analytical Engine | | Note G - Engine Limits and Bernoulli Method | `note_g_engine_limits_bernoulli_method` | Note G only |

- **Source file:** `data/agt_008.txt`
- **Ingest status:** Ingested (~79 chunks)
- **Extractor:** `extract_lovelace_source_documents` — Notes A and G only; formulas/diagrams normalized to prose/LaTeX summaries

---

### agt_009 — Marie Curie

| Current `source_title` | `source_volume` | `source_chapter` | `source_slug` | Source work / section |
|---|---|---|---|---|
| Pierre Curie | | The Discovery of Radium | `pierre_curie_discovery_of_radium` | *Pierre Curie*, Chapter V |
| Autobiographical Notes | | Discovery and Old Shed Years | `autobiographical_notes_discovery_old_shed_years` | *Autobiographical Notes*, Chapter II |
| Autobiographical Notes | | War Years | `autobiographical_notes_war_years` | *Autobiographical Notes*, Chapter III |

- **Source file:** `data/agt_009.txt` (Pierre Curie omnibus volume)
- **Ingest status:** Ingested
- **Extractor:** `extract_curie_source_documents`

---

### agt_011 — Leon Trotsky

| Current `source_title` | `source_slug` | Notes |
|---|---|---|
| My Life | `my_life_selected` | Selected chapters from *My Life* memoir |

- **Source file:** `data/agt_011.txt`
- **Ingest status:** Ingested
- **Extractor:** `extract_trotsky_source_documents` — single document, default config title

---

### agt_012 — Friedrich Nietzsche

| Current `source_title` | `source_slug` | Notes |
|---|---|---|
| The Twilight of the Idols | `twilight_of_the_idols_selected` | Selected sections from *Twilight of the Idols* (Ludovici) |

- **Source file:** `data/agt_012.txt`
- **Ingest status:** Ingested
- **Extractor:** `extract_nietzsche_source_documents` — single document, default config title

---

### agt_013 — Nikola Tesla

| Current `source_title` | `source_slug` | Notes |
|---|---|---|
| My Inventions | `my_inventions` | *My Inventions* autobiography body |

- **Source file:** `data/agt_013.txt`
- **Ingest status:** Ingested
- **Extractor:** `extract_tesla_source_documents` — single document

---

### agt_014 — Marie Antoinette

| Current `source_title` | `source_slug` | Document type |
|---|---|---|
| Letter to Maria Theresa (1773) | `letter_to_maria_theresa_1773` | Primary letter |
| Mercy-Argenteau Report (1776) | `mercy_argenteau_report_1776` | Ambassador report |
| Campan Court Record | `campan_court_record` | Historical record excerpt |
| Trial Indictment (1793) | `trial_indictment_1793` | Revolutionary tribunal |
| Last Letter to Madame Elisabeth | `last_letter_to_madame_elisabeth_1793` | Primary letter |
| Memoirs of the Court of Marie Antoinette | `memoirs_of_the_court_of_marie_antoinette` | Madame Campan memoir body (PG) |

- **Source file:** `data/agt_014.txt` (hybrid corpus: curated front-matter + Campan PG text)
- **Ingest status:** Ingested (~1,439 chunks)
- **Extractor:** `extract_marie_antoinette_source_documents`

---

## Pending speakers (no ingest plan yet)

These appear in the UI legend registry but are **not selectable** and have **no** `AgentIngestPlan` entry.

| Agent ID | Speaker | Source file | Status |
|---|---|---|---|
| agt_010 | Jorge Luis Borges | `data/agt_010.txt` (placeholder) | Pending |
| agt_015 | Frida Kahlo | `data/agt_015.txt` (placeholder) | Pending |
| agt_016 | Salvador Dali | `data/agt_016.txt` (placeholder) | Pending |

---

## Related files

| File | Role |
|---|---|
| `backend/scripts/query_vector_stats.py` | Query or full-scan Upstash Vector; emit human report or JSON |
| `docs/vector-snapshot.json` | Complete `--all-agents --json` snapshot (regenerate after re-ingest) |
| `backend/scripts/ingest_agent_knowledge.py` | Source extraction, citation metadata, vector upsert |
| `backend/utils/source_titles.py` | Citation compose + display formatting |
| `data/agt_*.txt` | Raw speaker corpora |
| `docs/adding-speakers.md` | How to add a new speaker |
| `docs/architecture.md` | Ingest status summary |

---

## Review checklist

When changing citation rules, re-run the vector snapshot and diff `docs/vector-snapshot.json`:

- [ ] Stored titles have no trailing `.` and no literal `...`
- [ ] Volume/chapter fields populated where ingest splits documents (Napoleon, Meditations, Curie, Lovelace)
- [ ] Footer display preserves volume/chapter after title truncation
- [ ] Re-ingest affected agents, then refresh the snapshot
