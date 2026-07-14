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

## Compiled LangGraph structure (generated — do not hand-edit)

Regenerate with `python -m pipeline.architecture_doc` after any change to `pipeline/graph.py`,
an agent's prompt, or `pipeline/llm_config.py`. This is the actual compiled `StateGraph`, not
a hand-drawn approximation — the diagram above documents the wider pipeline (parse/chunk/embed/
route) that runs *before* the graph is built; this one documents only the graph itself.

Prefer an image over reading Mermaid source? Open [graph.png](./graph.png) — regenerated
alongside this file, same command.

<!-- GRAPH:START -->
```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	pdf_safety_gate(pdf_safety_gate)
	parse_and_chunk(parse_and_chunk)
	injection_screen(injection_screen)
	rejected(rejected)
	fan_in_gate(fan_in_gate)
	metadata(metadata)
	metadata_confidence(metadata_confidence)
	facts(facts)
	facts_confidence(facts_confidence)
	statute(statute)
	statute_confidence(statute_confidence)
	petitioner(petitioner)
	petitioner_confidence(petitioner_confidence)
	respondent(respondent)
	respondent_confidence(respondent_confidence)
	evidence(evidence)
	evidence_confidence(evidence_confidence)
	assemble(assemble)
	confidence(confidence)
	human_review(human_review)
	__end__([<p>__end__</p>]):::last
	__start__ --> pdf_safety_gate;
	assemble --> confidence;
	confidence -. &nbsp;save&nbsp; .-> __end__;
	confidence -. &nbsp;review&nbsp; .-> human_review;
	evidence --> evidence_confidence;
	evidence_confidence -. &nbsp;retry&nbsp; .-> evidence;
	evidence_confidence -. &nbsp;done&nbsp; .-> fan_in_gate;
	facts --> facts_confidence;
	facts_confidence -. &nbsp;retry&nbsp; .-> facts;
	facts_confidence -. &nbsp;done&nbsp; .-> fan_in_gate;
	fan_in_gate -. &nbsp;wait&nbsp; .-> __end__;
	fan_in_gate -. &nbsp;ready&nbsp; .-> assemble;
	injection_screen --> evidence;
	injection_screen --> facts;
	injection_screen --> metadata;
	injection_screen --> petitioner;
	injection_screen --> respondent;
	injection_screen --> statute;
	metadata --> metadata_confidence;
	metadata_confidence -. &nbsp;done&nbsp; .-> fan_in_gate;
	metadata_confidence -. &nbsp;retry&nbsp; .-> metadata;
	parse_and_chunk --> injection_screen;
	pdf_safety_gate -. &nbsp;safe&nbsp; .-> parse_and_chunk;
	pdf_safety_gate -. &nbsp;unsafe&nbsp; .-> rejected;
	petitioner --> petitioner_confidence;
	petitioner_confidence -. &nbsp;done&nbsp; .-> fan_in_gate;
	petitioner_confidence -. &nbsp;retry&nbsp; .-> petitioner;
	respondent --> respondent_confidence;
	respondent_confidence -. &nbsp;done&nbsp; .-> fan_in_gate;
	respondent_confidence -. &nbsp;retry&nbsp; .-> respondent;
	statute --> statute_confidence;
	statute_confidence -. &nbsp;done&nbsp; .-> fan_in_gate;
	statute_confidence -. &nbsp;retry&nbsp; .-> statute;
	human_review --> __end__;
	rejected --> __end__;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc

```
<!-- GRAPH:END -->

### Node reference

<!-- NODES:START -->
| Node | Prompt | Model | Temperature ladder | top_p | max_tokens | Confidence threshold | Writes state field |
|---|---|---|---|---|---|---|---|
| `metadata` | You are the Metadata Agent for an Indian court judgment extraction system. | settings.llm_model | [0.0, 0.4, 0.7] | None | None | — | `metadata` |
| `metadata_confidence` | _(no LLM call — scores AgentValidationResult.pass_rate; loops back to `metadata` on retry, else -> assemble)_ | — | — | — | — | 1.0 | `validations`, `retry_counts`, `retry_decision` |
| `facts` | You are the Facts Agent for an Indian court judgment extraction system. | settings.llm_model | [0.0, 0.4, 0.7] | None | None | — | `facts` |
| `facts_confidence` | _(no LLM call — scores AgentValidationResult.pass_rate; loops back to `facts` on retry, else -> assemble)_ | — | — | — | — | 1.0 | `validations`, `retry_counts`, `retry_decision` |
| `statute` | You are the Statute Agent for an Indian court judgment extraction system. | settings.llm_model | [0.0, 0.4, 0.7] | None | None | — | `statutes` |
| `statute_confidence` | _(no LLM call — scores AgentValidationResult.pass_rate; loops back to `statute` on retry, else -> assemble)_ | — | — | — | — | 1.0 | `validations`, `retry_counts`, `retry_decision` |
| `petitioner` | You are the Petitioner Agent for an Indian court judgment extraction system. _(template, params={'side': 'petitioner'})_ | settings.llm_model | [0.0, 0.4, 0.7] | None | None | — | `petitioner` |
| `petitioner_confidence` | _(no LLM call — scores AgentValidationResult.pass_rate; loops back to `petitioner` on retry, else -> assemble)_ | — | — | — | — | 1.0 | `validations`, `retry_counts`, `retry_decision` |
| `respondent` | You are the Respondent Agent for an Indian court judgment extraction system. _(template, params={'side': 'respondent'})_ | settings.llm_model | [0.0, 0.4, 0.7] | None | None | — | `respondent` |
| `respondent_confidence` | _(no LLM call — scores AgentValidationResult.pass_rate; loops back to `respondent` on retry, else -> assemble)_ | — | — | — | — | 1.0 | `validations`, `retry_counts`, `retry_decision` |
| `evidence` | You are the Evidence Agent for an Indian court judgment extraction system. | settings.llm_model | [0.0, 0.4, 0.7] | None | None | — | `evidence` |
| `evidence_confidence` | _(no LLM call — scores AgentValidationResult.pass_rate; loops back to `evidence` on retry, else -> assemble)_ | — | — | — | — | 1.0 | `validations`, `retry_counts`, `retry_decision` |
| `fan_in_gate` | _(no LLM call — manual barrier; only proceeds to assemble once agents_done covers all 6 agents)_ | — | — | — | — | — | — |
| `pdf_safety_gate` | _(no LLM call — structural PDF scan, pipeline/pdf_safety.py)_ | — | — | — | — | — | `pdf_safety_reasons` |
| `parse_and_chunk` | _(no LLM call — Docling parse + chunk, only reached if pdf_safety_gate passes)_ | — | — | — | — | — | `chunk_count`, `ocr_used`, `agent_inputs` |
| `injection_screen` | _(no LLM call — pattern scan, pipeline/injection_screen.py)_ | — | — | — | — | — | `injection_matches` |
| `rejected` | _(no LLM call — terminal node for an unsafe PDF)_ | — | — | — | — | — | — |
| `assemble` | _(no LLM call — statute verification only, pipeline.agents.response assembly happens in \`confidence\`)_ | — | — | — | — | — | `statutes` |
| `confidence` | _(no LLM call — document-level ConfidenceBreakdown + builds the final result)_ | — | — | — | — | — | `confidence`, `result` |
| `human_review` | _(no LLM call — interrupt() pauses for a human decision)_ | — | — | — | — | — | `result` |
<!-- NODES:END -->

## Known, accepted limitation

KB is **IPC + Constitution only**. Post-2024 judgments citing **BNS/BNSS/BSA** will not verify. The KB schema stores `act` + `act_version` + `effective_dates` so BNS can be added later as configuration, not a rewrite, and so a section number is always matched against the *correct* act rather than blindly.
