# Legal.ai — Tech Stack, Auth Flow, HLD & LLD

> Written from a full read of the code (~3,600 lines), not just the README. Where the docs and the
> code disagree, this document follows the code — the differences are listed in
> [§6](#6-where-the-docs-and-the-code-disagree).
>
> **Updated** after adding the FastAPI layer, the React UI and the evaluation framework
> (§1, §2, §3, §4.1, §5.9–5.10, §6).
>
> **Viewing the diagrams:** they are Mermaid. GitHub renders them automatically. In VS Code, install
> the *Markdown Preview Mermaid Support* extension (`bierner.markdown-mermaid`) and open the preview.

## Contents

1. [What this system is](#1-what-this-system-is)
2. [Tech stack](#2-tech-stack)
3. [Auth flow](#3-auth-flow)
4. [High-level design (HLD)](#4-high-level-design-hld)
5. [Low-level design (LLD)](#5-low-level-design-lld)
6. [Where the docs and the code disagree](#6-where-the-docs-and-the-code-disagree)

---

## 1. What this system is

A **document-intelligence pipeline with a web app on top**. You give it one court-judgment PDF; it
returns a structured JSON record in which every extracted value cites the exact text it came from.
It can be driven from the CLI, over HTTP (FastAPI), or from the React UI, and an evaluation framework
scores its output against hand-labelled judgments. There is no CI yet.

| Command | When | What it does |
|---|---|---|
| `python -m db.apply_schema` | once | Creates the Postgres tables in [db/schema.sql](../../db/schema.sql) |
| `python -m scripts.setup_checkpointer` | once | Creates LangGraph's checkpoint tables |
| `python -m statute_kb.ingest` | once per act | **Offline:** builds the statute knowledge base from bare-act PDFs |
| `python -m pipeline.run judgment.pdf` | per document | **Online:** processes one judgment end to end |
| `uvicorn api.main:app` / `docker compose up api ui` | always on | **API + web app:** upload, live progress, review, results |
| `python -m evaluation.run_eval` | after labelling | **Evaluation:** scores predictions against gold labels |
| `pytest` | any time | API (demo mode) + evaluation tests; no Docling/LLM needed |

The pipeline commands run inside the `app` container: `docker compose run --rm app python -m ...`.
The API, UI and tests also run outside Docker in **demo mode** (`LEGAL_AI_DEMO_MODE=1`), which swaps
the pipeline for a scripted one that returns a clearly-labelled synthetic result.

---

## 2. Tech stack

```mermaid
flowchart TB
    subgraph WEB["Web layer"]
        UI["React + Vite + TypeScript<br/>served by nginx"]
        FA["FastAPI + Uvicorn<br/>jobs · review · results"]
    end

    subgraph RT["Runtime"]
        PY["Python 3.12"]
        DK["Docker + docker-compose<br/>python:3.12-slim, CPU-only torch"]
    end

    subgraph ORCH["Orchestration"]
        LG["LangGraph StateGraph<br/>parallel fan-out · retry cycles · interrupt()"]
        CP["langgraph-checkpoint-postgres<br/>PostgresSaver"]
    end

    subgraph DOC["Document processing"]
        PK["pikepdf<br/>structural safety scan"]
        DL["Docling<br/>layout · tables · OCR on demand"]
        TS["langchain-text-splitters<br/>1200-char chunks, 150 overlap"]
        RX["Regex prompt-injection screen"]
    end

    subgraph AI["AI / ML"]
        OR["OpenRouter LLM API<br/>via langchain-openai ChatOpenAI"]
        BG["FlagEmbedding (local CPU)<br/>BAAI/bge-m3 · bge-reranker-v2-m3"]
        PD["Pydantic v2<br/>Sourced[T] data contracts"]
    end

    subgraph DATA["Data stores"]
        PG[("PostgreSQL on Supabase<br/>psycopg 3, raw SQL")]
        QD[("Qdrant<br/>collection: statutes")]
    end

    subgraph OBS["Observability"]
        LF["Langfuse v3<br/>LangChain CallbackHandler"]
    end

    UI --> FA
    FA --> ORCH
    RT --> ORCH
    ORCH --> DOC
    ORCH --> AI
    ORCH --> DATA
    AI --> DATA
    ORCH -.-> OBS
```

| Layer | Technology | What it does here | Where |
|---|---|---|---|
| Runtime | Python 3.12, Docker (`python:3.12-slim`, CPU-only torch), docker-compose | Two containers, `app` and `qdrant`. Postgres is hosted externally on Supabase | [Dockerfile](../../Dockerfile), [docker-compose.yml](../../docker-compose.yml) |
| Orchestration | **LangGraph** `StateGraph`, conditional edges, `interrupt()` / `Command(resume=)` | Main control graph: runs agents in parallel, loops retries, pauses for human review | [pipeline/graph.py](../../pipeline/graph.py) |
| Checkpointing | `langgraph-checkpoint-postgres` (`PostgresSaver`) | Saves graph state to Postgres after each step | [graph.py:409](../../pipeline/graph.py#L409) |
| LLM | **OpenRouter** (OpenAI-compatible API) via `langchain-openai` `ChatOpenAI` + `.with_structured_output(PydanticModel)` | 6 extraction agents and 1 validator. Default model `anthropic/claude-sonnet-5` | [pipeline/llm.py](../../pipeline/llm.py), [agents/base.py](../../pipeline/agents/base.py) |
| Data contracts | **Pydantic v2** (generic `Sourced[T]`, model validators) | Defines every agent output, the graph state and the final JSON | [schemas/](../../schemas/) |
| PDF safety | **pikepdf** | Checks structure: JavaScript, auto-actions, embedded files, size, page count | [pdf_safety.py](../../pipeline/pdf_safety.py) |
| Parsing / OCR | **Docling** (layout and table models; OCR only where the text layer is thin) | Turns the PDF into sections that follow its headings | [docling_parse.py](../../pipeline/docling_parse.py) |
| Chunking | `RecursiveCharacterTextSplitter` (1200 chars, 150 overlap) | Splits text into chunks that stay inside one section | [chunking.py](../../pipeline/chunking.py) |
| Embeddings / rerank | **FlagEmbedding**: `BAAI/bge-m3` (1024-d dense) + `bge-reranker-v2-m3` cross-encoder, local CPU, NumPy cosine | Routing fallback, statute ingestion, MISMATCH check | [embeddings.py](../../pipeline/embeddings.py) |
| Vector DB | **Qdrant** (collection `statutes`, cosine, 1024-d) | Similarity search over statutes, used **only** as a fallback | [statute_kb/](../../statute_kb/) |
| Relational DB | **PostgreSQL on Supabase** via **psycopg 3**, raw SQL | Statute data (source of truth), run results, validation logs, checkpoints | [db/schema.sql](../../db/schema.sql), [persistence.py](../../pipeline/persistence.py) |
| Observability | **Langfuse v3** `CallbackHandler` on the LangGraph run | One trace session per document | [observability/](../../observability/) |
| Config | `python-dotenv` + frozen `Settings` dataclass | Loads env vars; stops at startup if required ones are missing | [config.py](../../pipeline/config.py) |
| Guardrail | Regex prompt-injection screen | Flags suspicious chunks and blocks auto-save | [injection_screen.py](../../pipeline/injection_screen.py) |
| Docs tooling | LangGraph `draw_mermaid()` → mermaid.ink | Regenerates the graph diagram in `data_flow.md` | [architecture_doc.py](../../pipeline/architecture_doc.py) |
| HTTP API | **FastAPI** + **Uvicorn**, `python-multipart` | Upload, status/progress, human review, results, evaluation reports | [api/](../../api/) |
| Web UI | **React 18 + Vite + TypeScript** (no UI library) | Upload, live pipeline view, click-through to sources, review screen, evaluation dashboard | [ui/](../../ui/) |
| UI serving | **nginx** | Serves the built UI and proxies `/api` to the API container | [ui/nginx.conf](../../ui/nginx.conf) |
| Evaluation | Pure Python + Pydantic | Gold labels → accuracy, abstention, P/R/F1, calibration reports | [evaluation/](../../evaluation/) |
| Tests | **pytest** + FastAPI `TestClient` | API flows in demo mode and the scoring rules | [tests/](../../tests/) |

**Listed in [pyproject.toml](../../pyproject.toml) but never imported:** `supabase`, `sqlalchemy`,
`sentence-transformers` (FlagEmbedding may still pull it in) and `langchain` (core). Where the README
says "OpenAI", it means the OpenAI-compatible client pointed at OpenRouter.

---

## 3. Auth flow

There are **no user accounts**: no login, users table, JWT, OAuth or session. Two kinds of auth exist:

1. **Client → API (new):** an optional shared API key. When `API_KEY` is set, every `/api` route
   except `/api/health` requires a matching `X-API-Key` header (constant-time comparison). The UI
   stores the key in the browser and sends it on every request. Unset = open, for local demos.
2. **App → outside services:** the pipeline signs in to OpenRouter, Postgres, Qdrant and Langfuse
   with keys from `.env` (table below).

| Service | Credential | How it's sent | If missing or wrong |
|---|---|---|---|
| OpenRouter | `OPENROUTER_API_KEY` | `Authorization: Bearer` header via `ChatOpenAI(api_key, base_url)` ([llm.py:30](../../pipeline/llm.py#L30-L37)) | `RuntimeError` at startup |
| Supabase Postgres | `DATABASE_URL` (password inside the URI) | Postgres protocol via psycopg / PostgresSaver | `RuntimeError` at startup |
| Qdrant | `QDRANT_URL` + optional `QDRANT_API_KEY` | `api-key` header if set; local dev has none | URL required, key optional |
| Langfuse | `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | The Langfuse SDK reads them from env itself | `auth_check()` logs a warning; the run continues without tracing ([langfuse_client.py:27](../../observability/langfuse_client.py#L27)) |
| HuggingFace Hub | none | Anonymous model download, cached in `.hf_cache` | — |

### 3.1 Credential flow for one run

```mermaid
sequenceDiagram
    autonumber
    actor Op as Operator
    participant Env as .env file
    participant CLI as pipeline.run
    participant Cfg as Settings
    participant LF as Langfuse
    participant PG as Supabase Postgres
    participant OR as OpenRouter
    participant QD as Qdrant

    Op->>CLI: docker compose run app python -m pipeline.run x.pdf
    Env-->>CLI: env_file loads secrets into the process environment
    CLI->>LF: auth_check() with public and secret key
    alt keys valid
        LF-->>CLI: OK, tracing enabled
    else keys missing or invalid
        LF-->>CLI: failure, warning logged, tracing becomes a no-op
    end
    CLI->>Cfg: get_settings()
    alt OPENROUTER_API_KEY, QDRANT_URL or DATABASE_URL missing
        Cfg-->>CLI: RuntimeError, run stops before any PDF work
    else all present
        Cfg-->>CLI: Settings singleton
    end
    CLI->>PG: PostgresSaver.from_conn_string(DATABASE_URL)
    Note over CLI,PG: the DB password travels inside the connection URI
    loop every agent and validator call
        CLI->>OR: POST /chat/completions with Authorization Bearer key
        OR-->>CLI: structured JSON
    end
    CLI->>PG: exact statute lookup with the same DATABASE_URL
    opt citation could not be parsed
        CLI->>QD: query_points, api-key header if QDRANT_API_KEY is set
    end
    opt confidence below 0.80
        CLI->>Op: human review prompt (approve, reject, edit)
        Op-->>CLI: decision typed at the terminal, no identity recorded
    end
    CLI->>PG: save_run() writes documents, processing_runs, validation_logs
```

### 3.2 API key flow (web app → API)

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant UI as React UI
    participant API as FastAPI
    participant Dep as require_api_key()

    U->>UI: Settings page - paste the server's API key
    UI->>UI: store it in localStorage
    UI->>API: GET /api/health (always open)
    API-->>UI: mode, auth_required, version
    U->>UI: upload a PDF
    UI->>API: POST /api/documents with X-API-Key header
    API->>Dep: dependency on every /api router route
    alt API_KEY unset
        Dep-->>API: allow
    else header matches (secrets.compare_digest)
        Dep-->>API: allow
    else missing or wrong
        Dep-->>UI: 401 Missing or invalid X-API-Key header
    end
    API-->>UI: 202 Accepted + job id
    Note over UI,API: The PDF viewer fetches /pdf with the same header and shows it as a blob URL, so the key never appears in a URL
```

### 3.3 Things to know

- **`SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` and `SUPABASE_SECRET_KEY` are never read.** The app
  skips Supabase's API and Row-Level Security and connects straight to Postgres with the database
  password. That one login is used for everything: reading statutes, writing results and creating
  tables.
- **The Langfuse fields in `Settings` are unused** — the SDK reads the env vars directly.
- **Human review is the only approval step, and it doesn't record who approved.** Whoever is at the
  terminal types `a`, `r` or `e`. The decision is stored in `processing_runs.human_review_decision`.
  `traced_run_config` accepts a `user_id`, but the CLI never passes one.
- **A shared API key is not per-user auth.** Everyone with the key has the same access, and API
  reviews don't record who approved either. The next step is: Supabase Auth issues a JWT → FastAPI
  verifies it in the same dependency slot → a `user_id` column on `documents` / `processing_runs`,
  protected by RLS → the same `user_id` passed into `traced_run_config`.

---

## 4. High-level design (HLD)

### 4.1 System context

Blue = runs locally in Docker (`ui`, `api`, `app` and `qdrant` containers). Green = external hosted service.

```mermaid
flowchart LR
    USER(["User<br/>in a browser"])
    UI["ui (nginx)<br/>React app · port 3000"]
    API["api (FastAPI)<br/>port 8000 · job threads"]
    OP(["Operator<br/>at the terminal"])
    RUN["pipeline.run<br/>LangGraph main graph"]
    ING["statute_kb.ingest<br/>offline, once per act"]
    OR["OpenRouter<br/>LLM API"]
    LF["Langfuse Cloud<br/>traces"]
    LOCAL["Local models<br/>pikepdf · Docling<br/>BGE-M3 · reranker<br/>cached in .hf_cache"]
    PG[("Supabase Postgres<br/>KB · runs · logs<br/>checkpoints")]
    QD[("Qdrant<br/>port 6333 · statutes")]

    USER --> UI
    UI -->|"/api proxy"| API
    API -->|"run_document()"| RUN
    OP -->|"judgment PDF (CLI)"| RUN
    OP -->|"bare-act PDFs"| ING
    RUN -->|"extract + validate"| OR
    RUN -.->|"traces"| LF
    RUN --> LOCAL
    RUN -->|"statute lookup,<br/>checkpoints, save run"| PG
    RUN -->|"semantic fallback only"| QD
    ING --> LOCAL
    ING -->|"upsert sections"| PG
    ING -->|"upsert vectors"| QD

    classDef local fill:#dbeafe,stroke:#2563eb,color:#111
    classDef ext fill:#dcfce7,stroke:#16a34a,color:#111
    class UI,API,RUN,ING,LOCAL,QD local
    class OR,LF,PG ext
```

### 4.2 Offline flow — building the statute knowledge base

```mermaid
flowchart LR
    A["Bare-act PDF<br/>data/raw/act/"] --> B["Docling parse"]
    B --> C["Regex section splitter<br/>matches: 302. Murder.— body"]
    C --> D["JSONL per act version<br/>data/processed/"]
    C --> E["Coverage report<br/>gaps in section numbering"]
    D --> F[("Postgres statute_sections<br/>upsert on act + version + section")]
    D --> G["BGE-M3 embedding<br/>1024-d"]
    G --> H[("Qdrant statutes<br/>deterministic UUID5 point ids")]
    I["statute_mappings_seed.csv<br/>old act to new act"] --> J[("Postgres statute_mappings")]
```

Code: [statute_kb/ingest.py](../../statute_kb/ingest.py), [parser.py](../../statute_kb/parser.py),
[mappings.py](../../statute_kb/mappings.py), [acts.py](../../statute_kb/acts.py). The `--embed-only`
flag runs the Qdrant step in a separate process because Docling's models and BGE-M3 together can
exceed container memory.

### 4.3 Online flow — processing one judgment

```mermaid
flowchart LR
    A["Judgment PDF"] --> B{"Safety scan"}
    B -->|unsafe| X["Rejected"]
    B -->|safe| C["Parse · chunk · route"]
    C --> D["Injection screen"]
    D --> E["6 agents in parallel"]
    E --> F["Validate + retry"]
    F --> G["Statute verification"]
    G --> H{"Confidence score"}
    H -->|"0.80 and above"| S[("Postgres")]
    H -->|"below 0.80"| R["Human review"]
    R --> S
```

### 4.4 Design rules the code enforces

1. **Agents are isolated.** Each sees only its own routed chunks, never another agent's output.
2. **Every value carries a source** — page, chunk id and an exact quote (`SourceRef`).
3. **The statute KB only checks citations.** It never feeds extraction.
4. **Confidence is calculated in code**, never self-reported by the LLM.
5. **None over guessing.** A field that fails validation is set to `None` or dropped, never shipped.

---

## 5. Low-level design (LLD)

### 5.1 The compiled LangGraph

Amber nodes call the LLM. Diamond nodes make a routing decision.

```mermaid
flowchart TD
    ST(["Start"]) --> SAFE["pdf_safety_gate<br/>pikepdf structural scan"]
    SAFE -->|unsafe| REJ["rejected<br/>raises PdfSafetyError"]
    REJ --> FIN(["End"])
    SAFE -->|safe| PARSE["parse_and_chunk<br/>Docling → chunks → route_document"]
    PARSE --> INJ["injection_screen<br/>regex, flags only"]

    INJ --> M["metadata"]
    INJ --> F["facts"]
    INJ --> S["statute"]
    INJ --> P["petitioner"]
    INJ --> R["respondent"]
    INJ --> E["evidence"]

    M --> MC{"metadata_confidence"}
    F --> FC{"facts_confidence"}
    S --> SC{"statute_confidence"}
    P --> PC{"petitioner_confidence"}
    R --> RC{"respondent_confidence"}
    E --> EC{"evidence_confidence"}

    MC -->|retry| M
    FC -->|retry| F
    SC -->|retry| S
    PC -->|retry| P
    RC -->|retry| R
    EC -->|retry| E

    MC -->|done| GATE{"fan_in_gate<br/>all 6 agents done?"}
    FC -->|done| GATE
    SC -->|done| GATE
    PC -->|done| GATE
    RC -->|done| GATE
    EC -->|done| GATE

    GATE -->|"wait: this branch ends"| FIN
    GATE -->|ready| ASM["assemble<br/>statute KB verification"]
    ASM --> CONF{"confidence<br/>5-signal score"}
    CONF -->|"auto_save or needs_review"| FIN
    CONF -->|human_required| HR["human_review<br/>interrupt() for a / r / e"]
    HR --> FIN

    classDef llm fill:#fef3c7,stroke:#d97706,color:#111
    class M,F,S,P,R,E,MC,FC,SC,PC,RC,EC llm
```

**Why `fan_in_gate` exists:** LangGraph runs a node every time *any* incoming branch finishes, not
once all of them have. Without the gate, `assemble` fired early on an agent's mid-retry output. Each
`<agent>_confidence` node sets `agents_done[agent] = True` only when that agent is truly finished, and
the gate proceeds only once all six are in.

| Node | Calls LLM? | Reads | Writes |
|---|---|---|---|
| `pdf_safety_gate` | no | `source_path` | `pdf_safety_reasons` |
| `parse_and_chunk` | no | `source_path` | `chunk_count`, `ocr_used`, `agent_inputs` (+ chunks in `RunContext`) |
| `injection_screen` | no | chunks | `injection_matches` |
| `<agent>` ×6 | **yes** — 1 extraction call | `agent_inputs[agent]`, `retry_counts[agent]` | its own output slot (`metadata`, `facts`, `statutes`, …) |
| `<agent>_confidence` ×6 | **yes** — 1 batched validator call | that agent's output | `validations`, `retry_counts`, `retry_decision`, `agents_done`; pruned output when retries run out |
| `fan_in_gate` | no | `agents_done` | — |
| `assemble` | no (local reranker) | `statutes`, `metadata.decision_date` | `statutes` with verification results |
| `confidence` | no | all outputs, `validations`, `injection_matches` | `confidence`, `result` |
| `human_review` | no | `validations`, `confidence`, `result` | `result` (if edited or rejected) |

**State merging:** the six branches write to the same dict fields (`validations`, `retry_counts`,
`retry_decision`, `agents_done`). Those are declared `Annotated[dict, operator.or_]` so parallel
writes merge instead of overwriting each other. Chunks and the embedding index live in `RunContext`,
outside the checkpointed state, because they aren't serializable.

### 5.2 Sequence for one document

```mermaid
sequenceDiagram
    autonumber
    participant CLI as pipeline.run
    participant G as LangGraph
    participant L as Local models
    participant OR as OpenRouter
    participant PG as Postgres
    participant QD as Qdrant
    participant LF as Langfuse

    CLI->>G: invoke(initial_state, thread_id = document_id)
    Note over G,PG: state is checkpointed to Postgres after every step
    G->>L: pikepdf structural scan
    G->>L: Docling parse, OCR only where needed
    G->>G: chunk, route by heading, regex injection scan
    par one branch per agent, 6 in parallel
        opt fewer than 3 routed chunks
            G->>L: bge-m3 top 8, then reranker top 5
        end
        loop until all fields pass or 3 retries are used
            G->>OR: extract (temperature 0, then 0.4, then 0.7)
            OR-->>G: structured output
            G->>G: gate 1 - is each quote an exact substring of its chunk?
            G->>OR: gate 2 - batched entailment check
            OR-->>G: pass or fail per field
        end
    end
    G->>PG: exact statute lookup as of the decision date
    G->>L: reranker compares quote with official text
    opt citation not parseable
        G->>QD: semantic top-1
    end
    G->>G: confidence score in plain Python
    alt score below 0.80
        G-->>CLI: interrupt payload (flagged fields + preview)
        CLI->>CLI: operator chooses approve, reject or edit
        CLI->>G: Command(resume = decision)
    end
    G-->>CLI: final state
    CLI->>PG: insert documents, processing_runs, validation_logs
    G-)LF: callbacks stream traces throughout the run
```

**LLM calls per document:** about 12 at best (6 extractions + up to 6 validator calls), up to 48 at
worst (4 attempts × 12).

### 5.3 Routing — which chunks each agent sees

```mermaid
flowchart TD
    A["Docling sections with heading paths<br/>e.g. JUDGMENT > FACTS"] --> B["Match heading keywords for this agent"]
    B --> C{"At least 3 chunks<br/>for this agent?"}
    C -->|yes| D["routed_by = structure"]
    C -->|no| E["Fixed fallback query for this agent<br/>e.g. witnesses, exhibits, evidence produced"]
    E --> F["In-memory bge-m3 index of this document<br/>cosine top 8"]
    F --> G["bge-reranker-v2-m3<br/>top 5"]
    G --> H["Merge with structure chunks<br/>never replace them"]
    H --> I["routed_by = hybrid or retrieval"]
    D --> J["Agent context:<br/>chunks prefixed with page and chunk id markers"]
    I --> J
```

| Agent | Heading keywords ([router.py](../../pipeline/router.py)) |
|---|---|
| metadata | IN THE, CORAM, BENCH, JUDGMENT, ORDER, CASE NO |
| facts | FACTS, BACKGROUND, BRIEF FACTS, CASE OF THE PROSECUTION |
| statute | STATUTE, PROVISION, SECTION, CHARGE |
| petitioner | PETITIONER, APPELLANT, PLAINTIFF, SUBMISSION OF THE APPELLANT |
| respondent | RESPONDENT, STATE, DEFENDANT, SUBMISSION OF THE RESPONDENT |
| evidence | EVIDENCE, WITNESS, EXHIBIT, TESTIMONY |

### 5.4 Agent → validate → retry cycle

```mermaid
stateDiagram-v2
    state "Agent node - 1 LLM extraction call" as Extract
    state "Gate 1 - exact-substring quote check (free)" as Gate1
    state "Gate 2 - batched entailment LLM call" as Gate2
    state "Compute pass_rate" as Scored
    state "Retry - same chunks, same prompt, higher temperature" as Retry
    state "Fallback - null Sourced fields, drop failing list items" as Fallback
    state decide <<choice>>

    [*] --> Extract
    Extract --> Gate1
    Gate1 --> Gate2 : quote found in its chunk
    Gate1 --> Scored : quote missing, field FAILS
    Gate2 --> Scored : pass or fail per field
    Scored --> decide
    decide --> Done : pass_rate reaches 1.0
    decide --> Retry : below threshold, retries left
    decide --> Fallback : below threshold, 3 retries used
    Retry --> Extract
    Fallback --> Done
    Done --> [*]
```

| Attempt | Temperature | Notes |
|---|---|---|
| 0 | 0.0 | first run |
| 1 | 0.4 | retry 1 |
| 2 | 0.7 | retry 2 |
| 3 | 0.7 | retry 3 (ladder index is capped at 2) |

Retries are **blind**: no validator feedback reaches the agent; only the temperature changes. The
threshold is per agent (`NodeLLMConfig.confidence_threshold`, default 1.0 = every field must pass) in
[llm_config.py](../../pipeline/llm_config.py). Code: [validation.py](../../pipeline/validation.py),
[fallback.py](../../pipeline/fallback.py), [graph.py:214-244](../../pipeline/graph.py#L214-L244).

### 5.5 Statute verification

```mermaid
flowchart TD
    A["StatuteReference<br/>parsed_act · parsed_section · quote"] --> B{"Section parsed<br/>and act known?"}
    B -->|no| C{"Quote present?"}
    C -->|no| SK["SKIPPED"]
    C -->|yes| Q["Qdrant top-1<br/>filtered by act when known"]
    Q --> Q2{"Score 0.55 or higher?"}
    Q2 -->|yes| NF1["NOT_FOUND<br/>with closest-match note"]
    Q2 -->|no| SK
    B -->|yes| PGL["Postgres exact lookup<br/>act + section in force on decision_date"]
    PGL --> R{"Row found?"}
    R -->|no| NF2["NOT_FOUND"]
    R -->|yes| RR{"Quote present and<br/>reranker score below 0.55?"}
    RR -->|yes| MM["MISMATCH"]
    RR -->|no| V["VERIFIED"]
    MM --> CW["statute_mappings crosswalk<br/>sets current_equivalent, info only"]
    V --> CW

    classDef ok fill:#dcfce7,stroke:#16a34a,color:#111
    classDef bad fill:#fee2e2,stroke:#dc2626,color:#111
    classDef warn fill:#fef3c7,stroke:#d97706,color:#111
    classDef skip fill:#f3f4f6,stroke:#6b7280,color:#111
    class V ok
    class MM bad
    class NF1,NF2 warn
    class SK skip
```

Postgres is the source of truth. Vector similarity from Qdrant **never** produces `VERIFIED` — at
most a `NOT_FOUND` with a hint. Code: [statute_kb/lookup.py](../../statute_kb/lookup.py),
[pipeline/statute_verification.py](../../pipeline/statute_verification.py).

### 5.6 Confidence scoring and routing

```mermaid
flowchart LR
    S1["validation_pass_rate<br/>weight 0.35"] --> SUM(("weighted<br/>sum"))
    S2["statute_verification_rate<br/>weight 0.20"] --> SUM
    S3["provenance_coverage<br/>weight 0.20"] --> SUM
    S4["schema_completeness<br/>weight 0.15"] --> SUM
    S5["cross_agent_consistency<br/>weight 0.10"] --> SUM
    SUM --> D{"score"}
    D -->|"0.90 and above"| AS["auto_save"]
    D -->|"0.80 to 0.90"| NR["needs_review"]
    D -->|"below 0.80"| HR["human_required<br/>graph pauses"]
    AS --> INJ{"Injection<br/>matches?"}
    INJ -->|yes| NR
    INJ -->|no| SAVE[("Saved to Postgres")]
    NR --> SAVE
    HR --> REV["Human review<br/>approve · reject · edit"]
    REV --> SAVE
```

| Signal | Weight | How it's computed |
|---|---|---|
| `validation_pass_rate` | 0.35 | Mean of each agent's field pass rate |
| `statute_verification_rate` | 0.20 | VERIFIED citations ÷ all citations (1.0 if none) |
| `provenance_coverage` | 0.20 | Share of present fields whose source has a chunk id and page |
| `schema_completeness` | 0.15 | Share of `court`, `decision_date`, `case_number` that are present |
| `cross_agent_consistency` | 0.10 | Penalises timeline events dated after the decision date |

Code: [pipeline/confidence.py](../../pipeline/confidence.py),
[schemas/confidence.py](../../schemas/confidence.py).

### 5.7 Data model — Pydantic contracts

**Provenance building blocks** ([schemas/base.py](../../schemas/base.py)). Every extracted value in
the system is wrapped in one of these:

```mermaid
classDiagram
    direction LR

    class SourceRef {
        +int page
        +str quote
        +str chunk_id
        +str section_path
        +int char_start
        +int char_end
    }
    class Sourced~T~ {
        +T value
        +list~SourceRef~ sources
        +is_present() bool
    }
    class SourcedItem~T~ {
        +T value
        +list~SourceRef~ sources
    }
    class StatuteReference {
        +str raw_citation
        +list~SourceRef~ sources
    }
    note for Sourced "Single fields. value is None exactly when sources is empty. Failing field is set to None."
    note for SourcedItem "List items. value required, at least 1 source. Failing item is dropped."

    Sourced o-- SourceRef
    SourcedItem o-- SourceRef
    StatuteReference o-- SourceRef
```

**The final record** ([schemas/final.py](../../schemas/final.py)) — what gets stored in
`processing_runs.structured_json`:

```mermaid
classDiagram
    direction TB

    class StructuredJudgment {
        +MetadataOutput metadata
        +FactsOutput facts
        +StatuteOutput statutes
        +ArgumentsOutput petitioner
        +ArgumentsOutput respondent
        +EvidenceOutput evidence
        +ConfidenceBreakdown confidence
        +ReviewDecision review_decision
        +ProcessingMetadata processing
    }
    class MetadataOutput {
        +Sourced court
        +Sourced bench
        +Sourced decision_date
        +Sourced case_number
        +Sourced jurisdiction
        +list~SourcedItem~ judges
        +list~SourcedItem~ petitioners
        +list~SourcedItem~ respondents
    }
    class FactsOutput {
        +Sourced background
        +Sourced incident_summary
        +list~SourcedItem~ key_facts
        +list~SourcedItem~ timeline
    }
    class StatuteOutput {
        +list~StatuteReference~ references
        +verification_rate() float
    }
    class StatuteReference {
        +str raw_citation
        +StatuteAct parsed_act
        +str parsed_section
        +list~SourceRef~ sources
        +VerificationStatus verification_status
        +KBMatch kb_match
        +KBMatch current_equivalent
    }
    class ArgumentsOutput {
        +str party_side
        +list~SourcedItem~ arguments
    }
    class EvidenceOutput {
        +list~SourcedItem~ items
    }
    class ConfidenceBreakdown {
        +float validation_pass_rate
        +float statute_verification_rate
        +float provenance_coverage
        +float schema_completeness
        +float cross_agent_consistency
        +float score
        +ReviewDecision decision
    }
    class ProcessingMetadata {
        +str document_id
        +str llm_model
        +dict prompt_versions
        +dict retry_counts
        +datetime processed_at
    }

    StructuredJudgment *-- MetadataOutput
    StructuredJudgment *-- FactsOutput
    StructuredJudgment *-- StatuteOutput
    StructuredJudgment *-- ArgumentsOutput
    StructuredJudgment *-- EvidenceOutput
    StructuredJudgment *-- ConfidenceBreakdown
    StructuredJudgment *-- ProcessingMetadata
    StatuteOutput *-- StatuteReference
```

### 5.8 Data model — Postgres tables

```mermaid
erDiagram
    STATUTE_SECTIONS ||--o{ STATUTE_ALIASES : "has (table unused)"
    DOCUMENTS ||--o{ PROCESSING_RUNS : has
    PROCESSING_RUNS ||--o{ VALIDATION_LOGS : has

    STATUTE_SECTIONS {
        bigserial id PK
        text act UK "StatuteAct value"
        text act_family
        text act_version UK "e.g. IPC-1860"
        text section_number UK
        text section_title
        text chapter_path
        text content "official section text"
        text status "active, repealed or superseded"
        date effective_from
        date effective_to "NULL while in force"
        text source_citation
        uuid qdrant_point_id
    }
    STATUTE_ALIASES {
        bigserial id PK
        bigint statute_section_id FK
        text alias
    }
    STATUTE_MAPPINGS {
        bigserial id PK
        text old_act
        text old_section
        text new_act
        text new_section
        text mapping_type "exact, split, merged, renumbered, ..."
        text notes
    }
    DOCUMENTS {
        uuid id PK
        text source_filename
        timestamptz uploaded_at
        int page_count
        boolean ocr_used
    }
    PROCESSING_RUNS {
        uuid id PK
        uuid document_id FK
        jsonb structured_json "full StructuredJudgment"
        float confidence_score
        text review_decision
        text llm_model
        jsonb prompt_versions
        jsonb retry_counts
        jsonb human_review_decision
        text langfuse_session_id
        timestamptz started_at
        timestamptz completed_at
    }
    VALIDATION_LOGS {
        bigserial id PK
        uuid processing_run_id FK
        text agent
        int attempt
        text field_path
        text status "pass, fail or not_applicable"
        text supporting_quote
        text reason
    }
```

`statute_mappings` has no foreign key; it is joined on act and section values. LangGraph's own
checkpoint tables (created by [scripts/setup_checkpointer.py](../../scripts/setup_checkpointer.py))
live in the same database.

### 5.9 API layer ([api/](../../api/))

The API never re-implements the pipeline. Each upload becomes a **job**; a background thread calls the
same `run_document()` the CLI uses, with two callbacks: `on_progress` (fed by streaming the graph
node by node) and `on_human_review` (blocks the thread until a reviewer answers over HTTP).

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant UI as React UI
    participant API as FastAPI routes
    participant S as JobStore
    participant W as Job thread (JobRunner)
    participant G as run_document()

    U->>UI: drop a PDF
    UI->>API: POST /api/documents (multipart)
    API->>API: check .pdf + %PDF- header, stream to disk with a size cap
    API->>S: add job (queued), write data/api_jobs/id.json
    API->>W: submit(job id)
    API-->>UI: 202 Accepted + job
    W->>W: wait for a free slot (API_MAX_CONCURRENT_JOBS)
    W->>G: run_document(id, pdf, on_progress, on_human_review)
    loop every graph node that finishes
        G-->>W: on_progress(node, update)
        W->>S: update progress (agent status, attempts)
    end
    loop every second until a final state
        UI->>API: GET /api/documents/{id}
        API-->>UI: status + progress
    end
    alt confidence below 0.80
        G-->>W: on_human_review(payload)
        W->>S: status awaiting_review + payload, then free the slot and wait
        UI->>API: GET /api/documents/{id}/review
        API-->>UI: flagged fields + result preview
        U->>UI: approve, reject or edit
        UI->>API: POST /api/documents/{id}/review
        API->>API: validate edit patches against StructuredJudgment (422 if invalid)
        API->>W: hand the decision to the waiting thread
        W-->>G: return decision, graph resumes from the checkpoint
    end
    G-->>W: final state
    W->>S: status completed + result (+ save_run to Postgres)
    UI->>API: GET /api/documents/{id}/result
    API-->>UI: StructuredJudgment JSON
```

```mermaid
stateDiagram-v2
    [*] --> queued : POST /documents
    queued --> running : slot free
    running --> awaiting_review : confidence below 0.80
    awaiting_review --> running : POST /review
    running --> completed : result saved
    running --> rejected : PDF safety scan failed
    running --> failed : exception
    awaiting_review --> failed : API restarted while waiting
    completed --> [*]
    rejected --> [*]
    failed --> [*]
```

**Why a thread waits for the reviewer instead of resuming from the checkpoint later:** the run's
chunks and embedding index live only in that call's memory (`RunContext`, not checkpointed), so a
different process could not resume it. Keeping the run alive avoids changing the pipeline; the
documented trade-off is that a paused run does not survive an API restart (it is marked `failed`).
The waiting thread releases its concurrency slot, so a pending review never blocks new uploads.

| Piece | File | Responsibility |
|---|---|---|
| Routes, upload checks, auth | [main.py](../../api/main.py) | `create_app(settings, pipeline)` factory, so tests inject temp dirs and demo mode |
| Settings | [config.py](../../api/config.py) | Env vars; starts without pipeline credentials in demo mode |
| Jobs | [jobs.py](../../api/jobs.py) | `Job` model + thread-safe store, mirrored to JSON on disk (atomic rename) |
| Worker | [worker.py](../../api/worker.py) | Threads, concurrency slots, review hand-off, progress folding |
| Pipeline adapters | [pipelines.py](../../api/pipelines.py), [demo.py](../../api/demo.py) | `RealPipeline` (LangGraph, imported lazily) and `DemoPipeline` (synthetic) |

### 5.10 Evaluation ([evaluation/](../../evaluation/))

```mermaid
flowchart LR
    G["Gold labels<br/>evaluation/gold/*.json<br/>hand-written"] --> SC["score_document()<br/>per field outcome<br/>list P/R/F1"]
    PDF["Judgment PDFs"] -->|"--run"| PIPE["run_document()<br/>review auto-approved"]
    PIPE --> P["Predictions<br/>evaluation/predictions/*.json"]
    CLI["pipeline.run --out"] --> P
    P --> SC
    SC --> AGG["aggregate()<br/>accuracy · wrong-when-answered<br/>abstention · calibration"]
    AGG --> R["Report<br/>reports/name.json + .md"]
    R --> UIE["UI Evaluation page<br/>via /api/eval/reports"]
```

Each labelled single-value field gets one of five outcomes — `correct`, `correct_absent`, `missed`,
`wrong`, `spurious` — so the report can separate "wrong when it answered" from "declined to answer".
Calibration compares the confidence score with per-document accuracy: if the score is meaningful,
auto-saved documents should be more accurate than ones sent for review.

---

## 6. Where the docs and the code disagree

1. **The validator uses the same model as the extractors.** `VALIDATOR_LLM_MODEL` is read but never
   used ([validation.py:112](../../pipeline/validation.py#L112)).
2. **The `<agent>_confidence` nodes do call the LLM.** The generated node table in
   [data_flow.md](data_flow.md) says "no LLM call", but these nodes run the validator. The text is
   hardcoded in [architecture_doc.py:64](../../pipeline/architecture_doc.py#L64).
3. **Some env vars do nothing.** `CONFIDENCE_AUTOSAVE_THRESHOLD`, `CONFIDENCE_REVIEW_THRESHOLD` and
   `DOCLING_OCR_DENSITY_THRESHOLD` have no effect; the thresholds are hardcoded in
   [schemas/confidence.py:60-65](../../schemas/confidence.py#L60-L65).
4. **`prompt_versions` is never filled in**, so it's always saved as `{}`, even though the docs say a
   prompt hash is stored with every result.
5. **A crashed run can't actually resume.** Every CLI run gets a new `uuid4` thread id
   ([run.py:66](../../pipeline/run.py#L66)), and chunks aren't saved in checkpoints
   ([graph.py:123](../../pipeline/graph.py#L123)). In practice, checkpointing only supports the
   human-review pause. The API works around this by keeping a paused run alive in its thread (§5.9).
6. **The statute data in the repo is much smaller than the docs say.** IPC has 201 sections, numbered
   76–502, with 245 numbers missing in that range. CrPC has 458 sections. There is no Constitution,
   BNS, BNSS or BSA data, and the old-to-new mapping CSV has only a header row, so
   `current_equivalent` is always `None`. (What's loaded in the live databases may differ.)
7. **The MISMATCH check may wrongly flag correct citations — worth testing.** It compares the
   judgment's quoted sentence (e.g. "convicted under Section 302 IPC") with the full official section
   text and flags anything scoring below 0.55 ([lookup.py:157](../../statute_kb/lookup.py#L157)).
8. **`validation_logs` keeps only each agent's last attempt**, not the full retry history.
   `documents.page_count` is always NULL.
9. **Human review edits skip quote validation.** An edit replaces top-level fields without
   re-checking the quotes, and a reject still saves the run. (The API at least validates an edit
   against the schema before resuming, so a malformed edit is a 422 instead of a crashed run.)
10. **The embedding index is built for every agent call, even when unused.** `ctx.index` is passed as
    an argument to `apply_retrieval_fallback()`, so it is evaluated before the function decides
    whether it needs it — and six parallel agents can each trigger the first, expensive build.

### Fixed while adding the API

- **Human review crashed on resume.** After an interrupt, LangGraph reloads state from the
  checkpoint with plain-string dict keys, and `human_review_node` / `save_run()` call `agent.value`
  on them → `AttributeError`. Any run scoring below 0.80 could not finish, from the CLI or anywhere
  else. Fixed by typing `GraphState`'s dicts as `dict[AgentName, ...]` so Pydantic restores the enum
  keys ([graph.py:89-120](../../pipeline/graph.py#L89-L120)); verified by running the real graph with
  stubbed models through interrupt, resume and `save_run`'s key handling.
- **Docling reloaded its models for every document.** `_build_converter()` is now cached, which
  matters for a long-running API process.

### Heads-up

- LangGraph logs *"Deserializing unregistered type … will be blocked in a future version"* for the
  Pydantic models in checkpoints. A future LangGraph upgrade will need those modules allow-listed
  in the checkpointer's serializer, or human-review resume will break again.
