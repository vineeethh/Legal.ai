# Legal AI — Judgment Extraction Pipeline: Full Project Overview

> A production-grade Python system that ingests an Indian court judgment PDF and
> produces a **structured, provenance-backed, validated JSON record** of the case —
> its metadata, facts, statutes cited, both sides' arguments, and evidence — with a
> **deterministic confidence score** that routes each record to auto-save, review, or
> a human-in-the-loop interrupt.
>
> This is a from-scratch re-engineering of an original Flowise multi-agent workflow
> into a real, reproducible, auditable Python system. The guiding priority is
> **accuracy over speed**: minimize hallucination, and prefer `None` over a guess.

---

## 1. What this system does (in one pass)

```
PDF  →  structural safety scan (pikepdf — reject unsafe files before Docling)
     →  Docling parse (+OCR fallback)  →  hierarchical sections
     →  section-aware semantic chunking (provenance-carrying)
     →  prompt-injection pattern scan over chunk text (flag, never drop)
     →  structure-first routing to 6 isolated extraction agents
        (with embedding retrieval fallback when routing is thin)
     →  parallel extraction (LangGraph fan-out) — every field carries a verbatim quote
     →  per-agent span-grounded validation → blind retries as a real graph cycle
        (temperature-only; failing-field pruning once retries are exhausted)
     →  statute verification against a Postgres + Qdrant knowledge base
     →  deterministic document confidence scoring (no LLM)
     →  auto-save / needs-review / human-required routing
        (human_required pauses the graph for an approve / reject / edit decision)
     →  persist to PostgreSQL (structured JSON + confidence + validation/retry logs)
     →  durable checkpointing + full Langfuse tracing (one session per document)
```

Entry point: `python -m pipeline.run <judgment.pdf>` (see `pipeline/run.py`).

---

## 2. The core design invariants (enforced everywhere)

These are the non-negotiable rules the whole architecture is built to guarantee.
They are documented in `docs/architecture/data_flow.md` and enforced in code:

1. **Agents are isolated.** Each extraction agent receives *only* its own routed
   chunks + its own prompt. No agent ever reads another agent's output. Enforced
   structurally in `schemas/state.py` (each agent writes only its own slot) and
   `pipeline/agents/base.py` (an agent's only input is the context text built from
   its own chunks). The Petitioner and Respondent agents in particular never see
   each other's inputs or outputs, so one side's framing can't contaminate the other.

2. **RAG is verification-only.** The Qdrant knowledge base is used *only* by the
   statute verification step to check citations — never to generate or "enrich" any
   extraction. This is the single place RAG touches the pipeline
   (`statute_kb/lookup.py`).

3. **Every field carries provenance.** The `Sourced[T]` / `SourcedItem[T]` wrappers
   (`schemas/base.py`) force every extracted value to carry a `SourceRef`: page number
   + verbatim quote (+ optional char offsets, chunk id, section path). No quote ⇒
   cannot be validated ⇒ treated as unsupported. A `None` value must carry **no**
   sources; a non-`None` value must carry **at least one** — enforced by a Pydantic
   validator.

4. **Validation is a second, span-grounded LLM.** The validator (`pipeline/validation.py`)
   must cite a verbatim source span or the field FAILS. It uses **no RAG** and **no
   outside knowledge** — it only judges whether the quote entails the value.

5. **Retries are blind (strict isolation).** No validator feedback ever reaches a
   retried agent. Only the sampling temperature changes across attempts
   (`0.0 → 0.4 → 0.7`) so retries can actually recover instead of repeating the same
   deterministic output. After the retry budget is spent, still-failing fields are
   **pruned** (`pipeline/fallback.py`) rather than shipped as an unverified guess.

6. **Confidence is deterministic.** The score is computed from measurable signals
   (`pipeline/confidence.py`), never produced by an LLM.

7. **"None over guessing" applies end to end.** From the extraction prompts, through
   validation, to the retry-exhausted fallback — when the system isn't sure, it
   produces an explicit absence, never a fabricated value or source.

---

## 3. Repository layout

```
Legal.ai-main/
├── pyproject.toml              # Python ≥3.12; pydantic v2, langgraph(+postgres checkpoint),
│                               # docling, pikepdf, qdrant, langfuse, FlagEmbedding, …
├── Dockerfile                  # CPU-only torch; the supported way to run on this machine
├── docker-compose.yml          # app container + local Qdrant (Postgres is on Supabase)
├── .env.example                # every config var, documented
├── PROJECT_OVERVIEW.md         # this document
│
├── docs/architecture/
│   ├── data_flow.md            # canonical architecture doc; parts auto-generated from code
│   └── graph.png               # rendered image of the actual compiled LangGraph
│
├── schemas/                    # Pydantic contract layer (the backbone — import from here)
│   ├── base.py                 # Sourced[T], SourcedItem[T], SourcedList[T], SourceRef
│   ├── enums.py                # AgentName, StatuteAct, ActFamily, VerificationStatus, …
│   ├── metadata.py             # MetadataOutput (court, bench, judges, parties, …)
│   ├── facts.py                # FactsOutput (background, incident, key_facts, timeline)
│   ├── statutes.py             # StatuteOutput, StatuteReference, KBMatch
│   ├── arguments.py            # ArgumentsOutput (petitioner/respondent share this shape)
│   ├── evidence.py             # EvidenceOutput (witness/document/physical/digital)
│   ├── validation.py           # FieldValidation, AgentValidationResult
│   ├── confidence.py           # ConfidenceWeights, ConfidenceBreakdown (+ decide())
│   ├── final.py                # StructuredJudgment, ProcessingMetadata (the final record)
│   └── state.py                # PipelineState, RoutedInput (LangGraph shared state)
│
├── pipeline/                   # the runtime
│   ├── config.py               # central Settings singleton (all env parsing lives here)
│   ├── llm.py                  # OpenRouter access (LangChain ChatOpenAI + raw client)
│   ├── llm_config.py           # per-node LLM config (model, temp ladder, top_p, thresholds)
│   ├── prompt_spec.py          # PromptSpec dataclass (split out to avoid an import cycle)
│   ├── prompts.py              # prompt registry aggregating each agent's PromptSpec
│   ├── pdf_safety.py           # structural PDF safety scan (pikepdf) — runs before Docling
│   ├── injection_screen.py     # deterministic prompt-injection pattern scan over chunks
│   ├── docling_parse.py        # PDF → hierarchical sections, OCR fallback
│   ├── chunking.py             # section-aware semantic chunking + recursive split
│   ├── embeddings.py           # BGE-M3 embed + bge-reranker-v2-m3; ephemeral per-doc index
│   ├── router.py               # structure-first routing + retrieval fallback
│   ├── statute_verification.py # wires Statute Agent output → KB lookup
│   ├── validation.py           # span-grounded second-LLM validator
│   ├── fallback.py             # prunes fields that never passed after retries are exhausted
│   ├── confidence.py           # deterministic 5-signal confidence engine
│   ├── graph.py                # LangGraph supervisor (safety→parse→extract→retry→assemble→review)
│   ├── architecture_doc.py     # regenerates the graph diagram/table + graph.png from real code
│   ├── persistence.py          # writes the run to Postgres
│   ├── run.py                  # CLI entrypoint (incl. terminal human-review prompt)
│   └── agents/                 # the 7 agents
│       ├── base.py             # shared agent machinery + isolation-reminder prompt
│       ├── metadata.py, facts.py, statute.py, arguments.py, evidence.py   # 6 extractors
│       └── response.py         # assembly-only agent (no LLM, no extraction)
│
├── statute_kb/                 # the statute knowledge base (verification source of truth)
│   ├── acts.py                 # registry: one entry per act + effective dates
│   ├── parser.py               # bare-act PDF → sections (+ coverage report)
│   ├── ingest.py               # raw PDF → processed JSONL → Postgres + Qdrant
│   ├── mappings.py             # old-act → new-act crosswalk loader (IPC 302 → BNS 103)
│   └── lookup.py               # two-tier citation verification
│
├── db/
│   ├── schema.sql              # Postgres schema (KB tables + run-persistence tables)
│   └── apply_schema.py         # idempotent schema applier
│
├── scripts/
│   └── setup_checkpointer.py   # one-shot: create the LangGraph Postgres checkpointer tables
│
├── observability/
│   └── langfuse_client.py      # Langfuse tracing helpers (one session per document run)
│
└── data/
    ├── README.md               # sourcing rules for bare-act PDFs
    ├── raw/<act>/              # official PDFs (gitignored), one folder per act
    ├── judgments/             # input judgment PDFs (gitignored)
    └── processed/              # committed JSONL per act + coverage reports + mappings seed
```

---

## 4. The data contract layer (`schemas/`)

Everything in the system speaks Pydantic v2 models. This is the "backbone" — the
validator checks against it, the confidence engine scores it, the DB stores it.

### 4.1 Provenance primitives (`schemas/base.py`)

- **`SourceRef`** — a pointer back into the judgment for one value: `page` (≥1,
  required), `quote` (verbatim, required, min length 1), optional `char_start`/
  `char_end`, `chunk_id`, `section_path`. Frozen (immutable). Validates that
  `char_end ≥ char_start`.
- **`Sourced[T]`** — one extracted scalar + its provenance. `value=None` is a
  **first-class legitimate state** meaning "not confidently found" — never an error,
  never a fabrication. Invariant enforced by a validator: `None` ⇒ empty sources;
  non-`None` ⇒ ≥1 source. Has a self-reported `extraction_confidence` field that is
  explicitly **NOT** used for the deterministic score.
- **`SourcedList[T]` / `SourcedItem[T]`** — lists where each item carries its own
  provenance (each `SourcedItem` requires ≥1 source). An empty list means "the agent
  looked and found none", distinct from a scalar `None`.

### 4.2 Enums (`schemas/enums.py`)

- **`AgentName`** — `metadata, facts, statute, petitioner, respondent, evidence,
  response` (six extract, one assembles).
- **`StatuteAct`** — `IPC, CRPC, EVIDENCE_ACT, CONSTITUTION, BNS, BNSS, BSA, UNKNOWN`.
  Old and new acts coexist **indefinitely** — pre-2024 offenses are tried under the
  law in force at the time of the offense (Article 20(1)), so IPC/CrPC/Evidence Act
  citations remain valid for decades after BNS/BNSS/BSA. Never remove an act.
- **`ActFamily`** — groups an old act with its replacement: `criminal_substantive`
  (IPC↔BNS), `criminal_procedural` (CrPC↔BNSS), `evidence` (Evidence Act↔BSA),
  `constitutional` (no successor).
- **`VerificationStatus`** — `VERIFIED, NOT_FOUND, MISMATCH, SKIPPED`.
- **`ReviewDecision`** — `AUTO_SAVE (≥0.90), NEEDS_REVIEW (0.80–0.90), HUMAN_REQUIRED (<0.80)`.
- **`ValidationStatus`** — `PASS, FAIL, NOT_APPLICABLE`.
- **`EvidenceKind`** — `witness, document, physical, digital`.

### 4.3 Per-agent output schemas

| Schema | Key fields |
|--------|------------|
| `MetadataOutput` | court, bench, judges[], decision_date, case_number, petitioners[], respondents[], jurisdiction (all `Sourced`) |
| `FactsOutput` | background, incident_summary, key_facts[], timeline[] (`TimelineEvent` = date? + description) |
| `StatuteOutput` | references[] of `StatuteReference`; computed `verified_count` / `verification_rate` |
| `StatuteReference` | raw_citation, parsed_act, parsed_section, sources[]; + verification_status, kb_match, verification_note, current_equivalent |
| `KBMatch` | act, act_version, section_number, section_title, official_text, similarity_score |
| `ArgumentsOutput` | party_side + arguments[] (`Argument` = summary + optional `relied_on`) |
| `EvidenceOutput` | items[] of `EvidenceItem` (kind + description + optional label like "PW-1"/"Ext. P-12") |

### 4.4 Validation, confidence, final record, state

- **`FieldValidation` / `AgentValidationResult`** — per-field PASS/FAIL/N/A plus
  helpers: `failed_fields`, `overall`, `pass_rate` (fraction of applicable fields
  that passed).
- **`ConfidenceWeights`** — the five signal weights, **validated to sum to 1.0**.
- **`ConfidenceBreakdown`** — the five signals + final `score` + `decision`, with a
  static `decide(score)` implementing the threshold logic.
- **`StructuredJudgment`** — the final artifact: all six agent outputs + confidence
  + review_decision + `ProcessingMetadata` (document_id, schema_version, llm_model,
  prompt_versions hash map, retry_counts, processed_at, duration).
- **`PipelineState` / `RoutedInput`** — the LangGraph shared state container and the
  per-agent "what this agent is allowed to see" object. `PipelineState` also carries
  the two guardrail fields used for logic: `injection_matches` (chunk_id → matched
  pattern names) and `pdf_safety_reasons`.

---

## 5. The pipeline runtime (`pipeline/`)

### 5.1 Configuration (`config.py`)

A single frozen `Settings` dataclass, built lazily as a process-wide singleton. Every
module reads config from here, **never `os.environ` directly**. Required vars fail at
startup with a clear message. Defaults include: LLM model `openai/gpt-4o-mini`,
embeddings `BAAI/bge-m3`, reranker `BAAI/bge-reranker-v2-m3`, autosave threshold 0.90,
review threshold 0.80, max retries 3, temperature ladder `(0.0, 0.4, 0.7)`, and the PDF
guardrails `pdf_max_size_mb` (50) and `pdf_max_pages` (600).

### 5.2 LLM access (`llm.py`, `llm_config.py`)

**OpenRouter only**, by project decision. `get_chat_model()` returns a LangChain
`ChatOpenAI` pointed at OpenRouter, accepting `model`, `temperature`, `top_p`, and
`max_tokens`; `get_traced_client()` returns the raw OpenAI-compatible client,
Langfuse-wrapped, for direct calls. Structured output goes through
`get_chat_model(...).with_structured_output(Schema)`.

**Per-node sampling** lives in `llm_config.py`: `DEFAULT_NODE_LLM_CONFIG` maps each
agent to a `NodeLLMConfig` (`model`, `temperature_ladder`, `top_p`, `max_tokens`, and a
per-agent `confidence_threshold`). The threshold is the pass-rate an agent must reach
to stop retrying — `1.0` (default) means every field must pass; lowering it for a node
lets that node accept a partial pass rather than burning all retries chasing one
stubborn field. This replaces any single global temperature list.

### 5.3 PDF safety scan (`pdf_safety.py`)

Runs **first, before Docling ever touches the file**. Uses **pikepdf** to check
*structure only* (no antivirus/byte scanning): file size vs `pdf_max_size_mb`, page
count vs `pdf_max_pages`, document-level `/OpenAction` and `/AA` auto-actions, embedded
`/JavaScript`, embedded files, per-page auto-actions and file-attachment annotations,
plus password-protected and malformed PDFs. It **rejects** an unsafe file outright
(collecting *all* failed reasons, not just the first) rather than trying to sanitize
it — this pipeline's job is extraction, not disarming malicious documents.

### 5.4 PDF parsing (`docling_parse.py`)

Uses **Docling** with `do_ocr=True, force_full_page_ocr=False` — OCR is applied only
to pages/regions where the native text layer is insufficient, not forced on every
page. Produces a `ParsedDocument` of heading-delimited `ParsedSection`s, each keeping
its heading breadcrumb (`section_path`, e.g. `"ORDER > Held"`) and page number so
provenance can be traced back to page + section. Table structure extraction is on.

### 5.5 Chunking (`chunking.py`)

**Section boundaries are the primary chunk boundary** — this keeps each chunk's
`section_path` meaningful for structure-first routing. Sections longer than
`chunk_size` (default 1200, overlap 150) are recursively split via
`RecursiveCharacterTextSplitter`. Every resulting `Chunk` carries a UUID, its text,
`section_path`, page, and parent section index.

### 5.6 Prompt-injection screen (`injection_screen.py`)

A deterministic regex scan over every chunk's text for phrasing aimed at an LLM reading
the chunk as an instruction — e.g. "ignore all previous instructions", "disregard the
system prompt", role reassignment, fake `system:`/`assistant:` markers, `### system`
directive blocks, prompt-exfiltration ("reveal your prompt"), and "always mark this as
verified". It **flags, never blocks**: court documents legitimately contain
adversarial-sounding quoted text, so dropping matched chunks would risk silently
losing real case text. Matches are stored on `PipelineState.injection_matches` and a
flagged document can never auto-save — it is floored to at least `needs_review`.

### 5.7 Embeddings + reranking (`embeddings.py`)

`BAAI/bge-m3` (dense, 1024-dim) for embeddings, `bge-reranker-v2-m3` for reranking,
both run **locally** (lazy singletons). Two distinct uses:
- **Persistent**: statute-KB embeddings written to Qdrant.
- **Ephemeral per-run**: `JudgmentChunkIndex` — an in-memory cosine index over one
  document's own chunks, used by the retrieval-fallback path. Small, no persistence,
  no lifecycle to manage.

### 5.8 Routing (`router.py`)

**Structure-first**: match heading keywords against each section's `section_path`
(cheap, deterministic, no embeddings). Keyword tables per agent, e.g. Facts →
`FACTS, BACKGROUND, BRIEF FACTS, CASE OF THE PROSECUTION`; Evidence → `EVIDENCE,
WITNESS, EXHIBIT, TESTIMONY`. If an agent gets fewer than `MIN_STRUCTURE_CHUNKS` (3),
`apply_retrieval_fallback` pulls more chunks via semantic recall (top-8) → rerank
(top-5) using a per-agent fallback query, and **merges** them in (never removes
structure-routed chunks). The `routed_by` field records `structure` / `hybrid` /
`retrieval` for auditability.

### 5.9 The agents (`pipeline/agents/`)

All six extractors share `base.py`: `build_context_text()` prefixes every chunk with
a `[[page:P chunk:ID]]` marker, and `run_structured_agent()` calls the LLM with
structured output (accepting the per-node `model`/`temperature`/`top_p`/`max_tokens`).
Every agent's system prompt is appended with the **isolation reminder**: "You only
have access to the excerpt below… every value must carry a verbatim quote… if you
can't confidently find a field, leave it None — never guess." Each agent module also
exports a `PROMPT_SPECS` entry so `prompts.py` can register its prompt centrally for
the architecture-doc generator.

- **Metadata Agent** — court, bench, judges, decision date, case number, parties,
  jurisdiction.
- **Facts Agent** — background, incident summary, key facts, timeline. (Relies most
  on retrieval fallback since facts rarely sit under one clean heading.)
- **Statute Agent** — extracts **raw citations only** (section/article numbers, the
  act as named/implied, verbatim citation text). Leaves `parsed_act=UNKNOWN` rather
  than guessing. **Does not verify** — that's a separate step.
- **Petitioner + Respondent Agents** — same shape (`ArgumentsOutput`), run in complete
  isolation from each other, driven by one templated prompt (`side`). Extract only
  arguments attributed to their own side, with optional `relied_on` (statute/precedent).
- **Evidence Agent** — every piece of evidence classified as witness/document/physical/
  digital, with the label as written ("PW-1", "Ext. P-12").
- **Response Agent** (`response.py`) — **assembly only, no LLM, no extraction.**
  Composes the already-validated outputs + confidence into `StructuredJudgment`.
  Fields left `None` after retries pass through as `None` — it never fills gaps.

### 5.10 Validation (`validation.py`)

Two gates per field, in order:
1. **Deterministic quote-existence check** (free, no LLM): the `SourceRef.quote` must
   be an **exact substring** of the chunk it claims to come from. A fabricated or
   paraphrased quote fails here immediately.
2. **LLM entailment check**: for fields passing gate 1, a second LLM (temperature 0,
   structured output) confirms the quote actually **entails** the value — catching
   quotes that exist verbatim but don't support the claim. No RAG, no outside
   knowledge.

`walk_sourced_fields()` recursively walks any output model to find every sourced value
(scalars, list items, and statute references) with its dotted field path.

### 5.11 Retry-exhausted fallback (`fallback.py`)

When an agent's *final* attempt still has failing fields, `apply_fallback()` prunes
exactly those fields rather than returning a low-confidence guess as fact — the same
"None over guessing" rule applied to the retry-exhausted case:
- **`Sourced[T]`** has a legitimate empty state → nulled out (`value=None, sources=[]`).
- **`SourcedItem[T]` / `StatuteReference`** have no valid empty state (value/citation
  is required) → the failing item is **dropped from its list** entirely.

Its traversal mirrors `walk_sourced_fields` exactly so the pruned paths line up with
the validator's `field_path`s.

### 5.12 Statute verification (`statute_verification.py` + `statute_kb/lookup.py`)

Runs after the Statute Agent, before scoring. **Two-tier**:
- **Tier 1 (primary, deterministic)**: exact Postgres lookup on `(act, section_number)`,
  optionally filtered to the version **in force on the judgment's decision date**
  (`effective_from ≤ date < effective_to`). Drives `VERIFIED` / `NOT_FOUND`.
- **Tier 2 (secondary, semantic)**: used only to (a) confirm the quoted section text
  actually matches canonical text via the reranker — a divergence below the 0.55
  threshold becomes `MISMATCH`; or (b) attempt a fuzzy Qdrant match when a citation
  didn't parse cleanly — reported as `NOT_FOUND` with a note, **never** silently
  upgraded to `VERIFIED` (embedding similarity is not proof of citation correctness).

It also attaches the **`current_equivalent`** from the crosswalk (e.g. IPC 302 → BNS
103) for convenience — but the citation is **always verified against the act actually
cited**, never substituted.

### 5.13 Confidence (`confidence.py`)

Deterministic, no LLM. Five signals in `[0,1]`, weighted:

| Signal | Weight | What it measures |
|--------|--------|------------------|
| `validation_pass_rate` | 0.35 | mean of per-agent field pass rates |
| `statute_verification_rate` | 0.20 | fraction of citations VERIFIED against the KB |
| `provenance_coverage` | 0.20 | fraction of present fields with a traceable SourceRef (chunk_id + page) |
| `schema_completeness` | 0.15 | fraction of core expected fields present (court, decision_date, case_number) |
| `cross_agent_consistency` | 0.10 | deterministic cross-checks (e.g. no timeline event postdates the decision date) |

`score = Σ signal × weight` → `decide(score)` → `AUTO_SAVE (≥0.90)` /
`NEEDS_REVIEW (0.80–0.90)` / `HUMAN_REQUIRED (<0.80)`. Consistency defaults to 1.0
(no penalty) when data is absent — it only penalizes a **detected** contradiction,
never an absence (that's `schema_completeness`'s job). As a guardrail, a document with
any injection matches is floored to at least `needs_review` even if it otherwise scores
into auto-save.

### 5.14 Orchestration (`graph.py`) — the LangGraph supervisor

The pipeline is a single compiled LangGraph state machine. Parsing and chunking happen
**inside** the graph so an unsafe file is never handed to Docling. The node topology:

1. **`pdf_safety_gate`** → routes to `rejected` (terminal) if the structural scan
   found anything, else to `parse_and_chunk`. `run_document()` raises `PdfSafetyError`
   for a rejected file.
2. **`parse_and_chunk`** → Docling parse + chunk + structure-routing; populates the
   run context and `agent_inputs`.
3. **`injection_screen`** → pattern scan; writes `injection_matches`.
4. **Fan-out**: the 6 extraction agents are independent branches (edges from
   `injection_screen`), so LangGraph's Pregel executor runs them concurrently.
5. **Retry as a real graph cycle**: each agent node runs exactly **one** attempt (at
   `temperature_ladder[attempt]`), then flows into its own **`<agent>_confidence`**
   node. That node runs span-grounded validation and compares the deterministic
   pass-rate to the node's `confidence_threshold`:
   - below threshold with retries left → loops **back** to the agent node (a visible
     cycle in the compiled graph / `graph.png`), incrementing the attempt;
   - below threshold with retries exhausted → applies `fallback.apply_fallback()` to
     prune failing fields and marks the agent done;
   - at/above threshold → marks the agent done.
   Retries stay blind — only temperature changes, no validator feedback is fed back.
6. **`fan_in_gate`** — an explicit manual barrier. LangGraph fires a multi-predecessor
   node on *every* trigger rather than waiting for all predecessors, so the graph
   tracks an `agents_done` map and only proceeds to `assemble` once all six agents
   have truly finished; otherwise it waits.
7. **`assemble`** → runs statute verification (as-of the decision date).
8. **`confidence`** → computes the document-level `ConfidenceBreakdown`, applies the
   injection-match floor, builds `ProcessingMetadata`, and calls the Response Agent to
   assemble the final `StructuredJudgment`.
9. **Routing**: `auto_save` / `needs_review` end the graph (persisted normally);
   **`human_required`** routes to the **`human_review`** node.
10. **`human_review`** → calls LangGraph's `interrupt()` with a payload (document id,
    decision, score, flagged fields, and a result preview), **pausing the graph** for a
    human. The reviewer's resume decision is one of **approve** (keep as-is),
    **reject** (mark `human_required`), or **edit** (apply a JSON patch of top-level
    field overrides, re-validated into a `StructuredJudgment`).

**Concurrency-safe state**: `GraphState` extends `PipelineState` with `operator.or_`
merge reducers on the dicts multiple nodes write (`validations`, `retry_counts`,
`retry_decision`, `agents_done`) so concurrent writes merge rather than clobber.
Run-scoped, non-serializable data (chunks, the embedding index) lives in a separate
`RunContext`, kept out of the checkpoint-serializable graph state.

**Durable checkpointing**: the graph compiles with a **`PostgresSaver`** checkpointer,
so state is persisted per step — a crash mid-run resumes rather than reprocessing the
document, and a paused (interrupted) run can be resumed from a *different* process.
(The checkpointer's tables are created once via `scripts/setup_checkpointer.py`.)

`run_document(document_id, source_path, *, run_config, on_human_review)` returns
`(final_state, human_review_decision)`. The `on_human_review` callback receives the
interrupt payload and returns the resume decision; without it, a run that pauses raises
`RuntimeError`.

### 5.15 Persistence (`persistence.py`) + CLI (`run.py`)

`save_run()` writes three tables in one transaction: `documents` (filename, ocr_used),
`processing_runs` (the full structured JSON, confidence score, review decision, model,
prompt versions, retry counts, the **human-review decision payload**, Langfuse session
id, timings), and one `validation_logs` row per validated field (agent, attempt, field
path, status, quote, reason).

`run.py` is the CLI: `python -m pipeline.run <pdf> [--no-save] [--out result.json]`.
It mints a document UUID, verifies the Langfuse connection, runs the graph under a
Langfuse session keyed to the document id, prints the structured JSON + confidence →
decision, and (unless `--no-save`) persists the run. It supplies a default terminal
`on_human_review` callback that prints flagged fields + a result preview and asks the
reviewer to **approve / reject / edit** (edit via a JSON patch file). A file rejected
by the safety scan exits with the collected reasons.

### 5.16 Architecture-doc generator (`architecture_doc.py`)

`python -m pipeline.architecture_doc` regenerates the graph-derived parts of
`docs/architecture/data_flow.md` — the Mermaid diagram (between `GRAPH:START/END`
markers) and the per-node table (between `NODES:START/END`) — directly from the actual
compiled `StateGraph`, the prompt registry, and the per-node LLM config, so the doc
can't drift from the code. It also writes `docs/architecture/graph.png` (rendered via
LangGraph's `draw_mermaid_png()`, which needs network access for the mermaid.ink
backend; the Mermaid source is still regenerated if that's unavailable). The
hand-written parts of the doc (design invariants, overview, limitations) are untouched.

---

## 6. The statute knowledge base (`statute_kb/` + `db/`)

The KB is the **source of truth for citation verification**. Postgres is authoritative;
Qdrant only supplies semantic recall/rerank, never the final verdict.

### 6.1 Act registry (`acts.py`)

One `ActEntry` per act with **effective dates** — the load-bearing legal facts for
verification. Registered: IPC-1860 (superseded 2024-07-01), CrPC-1973 (superseded),
Evidence Act-1872 (superseded), Constitution-1950 (active), and BNS / BNSS / BSA
(active from 2024-07-01). Effective dates are updated here, never by editing PDF text.

### 6.2 Ingestion (`ingest.py` + `parser.py`)

`python -m statute_kb.ingest [--acts …] [--skip-qdrant] [--embed-only]`:
`raw/<act>/*.pdf` → Docling parse → `parser.split_into_sections()` (regex on the
`"<number>. <Title>.—<body>"` pattern) → `data/processed/<act>.jsonl` → upsert into
Postgres (on `(act, act_version, section_number)`) and Qdrant (deterministic UUID5
point ids). Every run writes a **coverage report** flagging gaps in the section-number
sequence for human spot-check before the data is trusted. An `--embed-only` mode loads
Qdrant from existing JSONL separately, because Docling's models + BGE-M3 together can
exceed a constrained container's memory.

### 6.3 Crosswalk (`mappings.py`)

Loads the old→new act concordance (IPC 302 → BNS 103) from
`data/processed/statute_mappings_seed.csv`. **Deliberately not** LLM-generated or
embedding-inferred — renumbering isn't 1:1 (splits, merges, net-new offenses, dropped
provisions), so it must come from the official MHA concordance tables. `mapping_type` ∈
`exact | split | merged | renumbered | new_provision | no_equivalent`.

### 6.4 Database schema (`db/schema.sql`)

- **KB tables**: `statute_sections` (one row per act/version/section, append-only with
  `effective_from`/`effective_to` versioning, unique on `(act, act_version,
  section_number)`), `statute_aliases` (alternate citation spellings), `statute_mappings`
  (the crosswalk).
- **Run-persistence tables**: `documents`, `processing_runs` (JSONB structured judgment
  + confidence + decision + `human_review_decision` + audit fields), `validation_logs`.
  Applied idempotently via `db/apply_schema.py`.
- **Checkpointer tables**: created separately by `scripts/setup_checkpointer.py` (they
  are LangGraph's own DDL, not part of `schema.sql`).

---

## 7. Observability (`observability/langfuse_client.py`)

Langfuse tracing. `traced_run_config(session_id=…)` builds the LangGraph run config with
a `CallbackHandler` and trace attributes wired in, using **one session per document
run** so all agents + validator + every retry cycle land under a single trace.
`verify_langfuse_connection()` auth-checks credentials at startup (logs and returns
`False` rather than raising, so a bad key fails loudly before a long run instead of
silently dropping traces). LangGraph nodes are traced via the callback handler; any
direct OpenRouter call uses the Langfuse-wrapped `get_openrouter_client()` — both report
to the same trace.

Reproducibility is designed in: temperature-0 baseline, versioned prompts (a prompt
hash is stored per output in `ProcessingMetadata.prompt_versions`), full Langfuse
tracing, and the auto-generated architecture doc that stays pinned to the real graph.

---

## 8. Deployment (`Dockerfile`, `docker-compose.yml`)

- **Dockerfile**: `python:3.12-slim` + `libgl1`/`libglib2.0-0` (needed by an OpenCV
  transitive dep of Docling at import time). Installs **CPU-only** torch/torchvision
  from PyTorch's CPU index (avoids ~2GB of unused CUDA packages).
- **docker-compose**: an `app` service (the pipeline) + a local `qdrant` service.
  Postgres is **hosted on Supabase**, not run locally. HuggingFace model weights are
  cached on a bind-mounted volume (`HF_HOME=/app/.hf_cache`) to survive `--rm` runs.
  Running via Docker is the supported path on this machine because `docling-parse` is a
  C++ extension with no prebuilt wheel for the local Python/arch, forcing a slow
  from-source CMake build otherwise.

Config surface (`.env.example`): `OPENROUTER_API_KEY`, Supabase/`DATABASE_URL`,
optional model overrides, embedding/reranker models, Qdrant URL/collection, Langfuse
keys, OCR density threshold, confidence thresholds, and max retries. (The PDF
guardrails `PDF_MAX_SIZE_MB` / `PDF_MAX_PAGES` are also env-tunable, defaulting to
50 MB / 600 pages in `config.py`.)

---

## 9. Current state of the data

- **Ingested & processed** (committed JSONL + coverage reports in `data/processed/`):
  - `IPC-1860.jsonl` — **201 sections** parsed (numeric range 76–502; the coverage
    report flags many gaps — the section-splitter is heuristic and needs human
    spot-checking against the source PDF before this is trusted for verification).
  - `CrPC-1973.jsonl` — **458 sections** parsed (range 1–484, with flagged gaps).
- **Not yet ingested**: Evidence Act, Constitution, BNS, BNSS, BSA (registry entries
  exist; `data/raw/<act>/` folders are placeholders with `.gitkeep`; raw PDFs are
  gitignored and must be sourced from India Code / e-Gazette).
- **Crosswalk**: `statute_mappings_seed.csv` currently has **only the header row** — no
  mappings loaded yet (awaiting the official MHA concordance tables).

### Known, accepted limitation

The KB currently emphasizes IPC (plus CrPC). Judgments citing acts not yet ingested
won't verify until those acts are loaded. The schema already stores `act` +
`act_version` + effective dates, so adding an act is **configuration, not a rewrite**,
and a section number is always matched against the *correct* act rather than blindly.

---

## 10. How to run it

```bash
# 0. Configure
cp .env.example .env    # fill in OPENROUTER_API_KEY, DATABASE_URL, Supabase, Langfuse

# 1. Bring up local Qdrant (Postgres is on Supabase)
docker compose up -d qdrant

# 2. Apply the DB schema + create the checkpointer tables (both idempotent, run once)
python -m db.apply_schema
python -m scripts.setup_checkpointer

# 3. Ingest bare-act PDFs into the KB (drop PDFs into data/raw/<act>/ first)
python -m statute_kb.ingest --acts IPC-1860,CrPC-1973
python -m statute_kb.mappings          # load the old→new crosswalk (once seeded)

# 4. Run the pipeline on a judgment
python -m pipeline.run path/to/judgment.pdf --out result.json
#   → prints structured JSON + "Confidence: 0.xxx -> auto_save|needs_review|human_required"
#   → on human_required, prompts on the terminal to approve / reject / edit
#   → persists to Postgres unless --no-save

# On this machine, prefer Docker (docling has no local prebuilt wheel):
docker compose run --rm app python -m pipeline.run path/to/judgment.pdf

# Optional: regenerate the architecture diagram + graph.png from the real graph
python -m pipeline.architecture_doc
```

---

## 11. Design philosophy summary

Everything above serves one goal: **an auditable legal record you can trust or
knowingly distrust — never one that quietly guesses.**

- Unsafe or malformed PDFs are rejected before any model sees them; injection-style
  text is flagged and can never silently auto-save.
- Every value is traceable to a verbatim span a lawyer can click back to.
- Nothing is asserted that a second, span-grounded LLM can't confirm — and anything
  still unconfirmed after retries is pruned, not shipped as fact.
- Nothing is "verified" against the law unless it exactly matches the KB for the act
  actually cited, in force on the decision date.
- The confidence number is a deterministic function of measurable signals — no LLM
  gets to grade its own homework.
- When the system isn't sure, it says `None`, and low-confidence records pause for a
  human to approve, reject, or edit before they're saved.
- The whole run is durably checkpointed and fully traced, and the architecture doc is
  regenerated from the real compiled graph so it can't drift from the code.
