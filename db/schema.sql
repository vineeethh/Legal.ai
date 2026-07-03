-- Legal AI — Postgres schema (Supabase).
--
-- Two concerns live here:
--   1. Statute knowledge base (source of truth for citation verification —
--      Qdrant only supplies semantic recall/rerank, never the final verdict).
--   2. Pipeline run persistence (structured judgments, confidence, validation
--      and retry logs) per docs/architecture/data_flow.md.

-- =====================================================================
-- Statute knowledge base
-- =====================================================================

-- One row per (act, section, version) — amendments insert a new row and
-- close the previous one's effective_to. Never overwritten or deleted.
CREATE TABLE IF NOT EXISTS statute_sections (
    id              BIGSERIAL PRIMARY KEY,
    act             TEXT NOT NULL,              -- StatuteAct enum value, e.g. 'indian_penal_code'
    act_family      TEXT NOT NULL,               -- ActFamily enum value, e.g. 'criminal_substantive'
    act_version     TEXT NOT NULL,               -- e.g. 'IPC-1860', 'BNS-2023'
    section_number  TEXT NOT NULL,               -- as cited, e.g. '302', '304-B'
    section_title   TEXT,
    chapter_path    TEXT,                        -- e.g. 'Chapter XVI > Offences Affecting the Human Body'
    content         TEXT NOT NULL,               -- canonical section text
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'repealed', 'superseded')),
    effective_from  DATE NOT NULL,
    effective_to    DATE,                        -- NULL = still in force
    source_citation TEXT,                        -- Gazette / India Code reference
    qdrant_point_id UUID,                        -- link to the embedded point for this version
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (act, act_version, section_number)
);

CREATE INDEX IF NOT EXISTS idx_statute_sections_lookup
    ON statute_sections (act, section_number, effective_from, effective_to);

CREATE INDEX IF NOT EXISTS idx_statute_sections_family
    ON statute_sections (act_family);

-- Alternate spellings/formats a citation might appear in, e.g. "S.302 IPC",
-- "Section 302 of the Indian Penal Code, 1860". Used to normalize a raw
-- citation before the exact lookup against statute_sections.
CREATE TABLE IF NOT EXISTS statute_aliases (
    id                  BIGSERIAL PRIMARY KEY,
    statute_section_id  BIGINT NOT NULL REFERENCES statute_sections(id) ON DELETE CASCADE,
    alias               TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_statute_aliases_alias ON statute_aliases (alias);

-- Old-act -> new-act crosswalk (e.g. IPC 302 -> BNS 103). Not 1:1: sections
-- split, merge, get renumbered, or have no equivalent. Sourced from the
-- official MHA concordance tables, never inferred from embeddings.
CREATE TABLE IF NOT EXISTS statute_mappings (
    id              BIGSERIAL PRIMARY KEY,
    old_act         TEXT NOT NULL,
    old_section     TEXT NOT NULL,
    new_act         TEXT NOT NULL,
    new_section     TEXT,                        -- NULL when mapping_type = 'no_equivalent'
    mapping_type    TEXT NOT NULL CHECK (
        mapping_type IN ('exact', 'split', 'merged', 'renumbered', 'new_provision', 'no_equivalent')
    ),
    notes           TEXT
);

CREATE INDEX IF NOT EXISTS idx_statute_mappings_old ON statute_mappings (old_act, old_section);
CREATE INDEX IF NOT EXISTS idx_statute_mappings_new ON statute_mappings (new_act, new_section);

-- =====================================================================
-- Pipeline run persistence
-- =====================================================================

CREATE TABLE IF NOT EXISTS documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_filename TEXT NOT NULL,
    uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    page_count      INT,
    ocr_used        BOOLEAN NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS processing_runs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id         UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    structured_json     JSONB NOT NULL,          -- StructuredJudgment.model_dump()
    confidence_score    DOUBLE PRECISION NOT NULL,
    review_decision     TEXT NOT NULL CHECK (review_decision IN ('auto_save', 'needs_review', 'human_required')),
    llm_model           TEXT NOT NULL,
    prompt_versions     JSONB NOT NULL DEFAULT '{}',
    retry_counts        JSONB NOT NULL DEFAULT '{}',
    langfuse_session_id TEXT,
    started_at          TIMESTAMPTZ NOT NULL,
    completed_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_processing_runs_document ON processing_runs (document_id);
CREATE INDEX IF NOT EXISTS idx_processing_runs_decision ON processing_runs (review_decision);

CREATE TABLE IF NOT EXISTS validation_logs (
    id              BIGSERIAL PRIMARY KEY,
    processing_run_id UUID NOT NULL REFERENCES processing_runs(id) ON DELETE CASCADE,
    agent           TEXT NOT NULL,               -- AgentName enum value
    attempt         INT NOT NULL,
    field_path      TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('pass', 'fail', 'not_applicable')),
    supporting_quote TEXT,
    reason          TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_validation_logs_run ON validation_logs (processing_run_id);
