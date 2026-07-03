# Legal AI — End-to-End Data Flow

> Recreation/improvement of a Flowise multi-agent workflow as a production Python system.
> Priority: **accuracy > speed**, minimize hallucination, `None` over guessing.

## Design invariants (enforced across the whole pipeline)

1. **Agents are isolated.** Each extraction agent receives only its routed chunks + its prompt (+ retriever for the Statute Agent). No agent reads another agent's output.
2. **RAG is verification-only.** The Qdrant KB (IPC + Constitution) is used *only* by the Statute Agent to verify citations — never to generate extractions.
3. **Every field carries provenance.** `SourceRef` (page + char offsets + verbatim quote). No quote ⇒ cannot be validated ⇒ treated as unsupported.
4. **Validation is a second LLM, span-grounded.** Validator must cite a verbatim source span or the field FAILS. No RAG in validation.
5. **Retries are blind (strict isolation).** No validator feedback reaches the agent; only the sampling temperature varies across attempts (temp 0 → 0.4 → 0.7) so retries can actually recover. Max 3, then `None`.
6. **Confidence is deterministic.** Computed from measurable signals, never produced by an LLM.

## Pipeline

```mermaid
flowchart TD
    A[PDF upload] --> B[Docling parse]
    B --> B1{Text-layer density<br/>per page OK?}
    B1 -- low density --> B2[OCR fallback]
    B1 -- ok --> C
    B2 --> C[Hierarchical document model<br/>headings / sections / tables]

    C --> D[Hierarchical semantic chunking<br/>+ recursive split<br/>chunks keep section-path metadata]
    D --> E[Embed chunks: BAAI/bge-m3<br/>index for per-agent retrieval]

    E --> R[Structure-first router<br/>maps Docling sections to agents]

    subgraph EXTRACT[Parallel extraction — isolated agents]
        R --> M[Metadata Agent]
        R --> F[Facts Agent]
        R --> S[Statute Agent]
        R --> P[Petitioner Agent]
        R --> RESP[Respondent Agent]
        R --> EV[Evidence Agent]
    end

    R -. retrieval fallback<br/>bge-m3 recall → bge-reranker-v2-m3 .-> EXTRACT

    S --> SR[Statute retriever]
    SR --> Q[(Qdrant KB<br/>IPC + Constitution<br/>keyed by act+section+version)]
    Q --> SV[Statute verification<br/>VERIFIED / NOT_FOUND / MISMATCH]
    SV --> S

    M --> V[Validator LLM<br/>span-grounded, per-field]
    F --> V
    S --> V
    P --> V
    RESP --> V
    EV --> V

    V --> RT{Field PASS?}
    RT -- fail & retries<3 --> RETRY[Re-run agent<br/>temp 0 → 0.4 → 0.7]
    RETRY --> V
    RT -- fail & retries=3 --> NONE[Field = None]
    RT -- pass --> OK[Validated field]

    NONE --> RA[Response Agent<br/>assemble unified JSON<br/>NO extraction]
    OK --> RA

    RA --> CONF[Deterministic confidence<br/>validation rate · statute rate ·<br/>provenance coverage · completeness ·<br/>cross-agent consistency]

    CONF --> DEC{Score}
    DEC -- ">= 0.90" --> SAVE[Auto-save]
    DEC -- "0.80 - 0.90" --> REVIEW[Needs review]
    DEC -- "< 0.80" --> HUMAN[Mandatory human review<br/>LangGraph interrupt node]

    SAVE --> DB[(PostgreSQL<br/>doc · JSON · confidence ·<br/>validation/retry logs · metadata)]
    REVIEW --> DB
    HUMAN --> DB
```

## Orchestration (LangGraph supervisor)

- Fan-out: launch the 6 extraction agents in parallel over their routed inputs.
- Barrier: wait for all agents → trigger validation → drive retries.
- Assembly: hand validated fields to the Response Agent (assembly only).
- Scoring + routing: deterministic confidence → save / review / human interrupt.
- **Checkpointing:** graph state is persisted so a crash mid-run resumes instead of reprocessing a 200-page document.
- **Reproducibility:** temperature 0 baseline, versioned prompts (prompt hash stored per output), tracing via Langfuse.
  - One Langfuse **session per document run** (`traced_run_config` in [observability/langfuse_client.py](../../observability/langfuse_client.py)) so all 6 agents + validator + retries land under a single trace.
  - LangGraph nodes are traced via `langfuse.langchain.CallbackHandler`; any agent that calls OpenRouter directly (outside a LangChain node) uses the traced `get_openrouter_client()` wrapper instead — both paths report to the same trace via the shared session id.

## Known, accepted limitation

KB is **IPC + Constitution only**. Post-2024 judgments citing **BNS/BNSS/BSA** will not verify. The KB schema stores `act` + `act_version` + `effective_dates` so BNS can be added later as configuration, not a rewrite, and so a section number is always matched against the *correct* act rather than blindly.
