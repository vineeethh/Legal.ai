# Legal.ai — Judgment Extraction Pipeline

Turn an Indian court judgment PDF into a **structured, provenance-backed, validated
JSON record** — metadata, facts, statutes (verified against a knowledge base),
both sides' arguments, and evidence — with a **deterministic confidence score**
and a human-in-the-loop review gate. Every extracted value carries a **verbatim
quote** you can click back to in the source PDF.

> Design principle: *an auditable legal record you can trust or knowingly
> distrust — never one that quietly guesses.* When the system isn't sure, it
> returns an explicit `None`, not a fabrication. Full architecture:
> [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md).

## Quickstart

Requirements: Docker Desktop, a Postgres database (a free [Supabase](https://supabase.com)
project works — use the **Session pooler** connection string, port 5432), and an
LLM (see [Bring your own model](#bring-your-own-model)).

```bash
cp .env.example .env          # fill in DATABASE_URL (+ OPENROUTER_API_KEY if using OpenRouter)

docker compose up -d qdrant   # local vector store
docker compose run --rm app python -m db.apply_schema
docker compose run --rm app python -m scripts.setup_checkpointer

# Load the statute KB from the committed section data (IPC + CrPC)
docker compose run --rm app python -m statute_kb.ingest --acts IPC-1860,CrPC-1973 --postgres-only
docker compose run --rm app python -m statute_kb.ingest --acts IPC-1860,CrPC-1973 --embed-only

docker compose up -d api web  # the local web app
```

Open **http://localhost:3000** — upload a judgment PDF, watch the six agents work
live, review low-confidence records, and click any extracted field to see its
verbatim span highlighted in the source PDF. (First `web` start runs `npm install`
inside the container; give it a couple of minutes.)

Prefer the CLI? `docker compose run --rm app python -m pipeline.run path/to/judgment.pdf`

## Bring your own model

You run this with **your own key on your own machine** — nothing is shared.
Configure in the web UI (Settings) or `.env`:

| Path | Config | Honest tradeoff |
|---|---|---|
| **OpenRouter** (default) | `OPENROUTER_API_KEY`, `LLM_MODEL` | One key, every model. **Free models are for testing the plumbing only** — they're rate-limited (50 req/day without credit) and rarely survive this system's verbatim-quote validation, so they produce *empty* records, not wrong ones. A capable model (e.g. `openai/gpt-4o`) costs pennies per judgment. |
| **Ollama / any OpenAI-compatible server** | `LLM_BASE_URL=http://host.docker.internal:11434/v1`, no key | Free, unlimited, fully private. Quality depends on your hardware — use a strong *instruct* model with tool-calling support. |

Optional: set `VALIDATOR_LLM_MODEL` to a *different* model family so the
extractor never grades its own homework, and `PIPELINE_MAX_CONCURRENCY=1` on
rate-limited tiers.

## What makes it trustworthy

- **Provenance is mandatory** — a value without a verbatim source span cannot pass validation.
- **A second, span-grounded LLM validates every field**; failing fields are retried blind, then pruned — never shipped as fact.
- **Statute citations verify against a real KB** (Postgres + Qdrant), as of the judgment's decision date, with the old→new act crosswalk (IPC → BNS).
- **Confidence is deterministic** — five measurable signals, no self-grading; low scores pause the run for human approve/reject/edit.
- **Unsafe PDFs are rejected** by a structural scan before any parser or model touches them; injection-style text is flagged and can never auto-save.

## Repository map

```
pipeline/     the runtime: safety → parse → route → 6 agents → validate → verify → score
schemas/      Pydantic contract layer (Sourced[T] provenance backbone)
statute_kb/   statute knowledge base: registry, ingestion, two-tier verification
api/          local FastAPI server (upload, SSE progress, review, settings)
web/          local Next.js UI (dashboard, live timeline, record ⇆ PDF review)
db/           Postgres schema + idempotent applier
tests/        deterministic unit tests (run: python -m pytest)
```
