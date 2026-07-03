"""Structure-first router — maps Docling sections to the 6 extraction agents.

Primary routing is by heading keyword match against each section's `section_path`
(cheap, deterministic, no embeddings). When an agent's structure-routed chunk set
is too thin, `apply_retrieval_fallback` pulls additional chunks via the ephemeral
per-document embedding index (bge-m3 recall -> bge-reranker-v2-m3 rerank).
"""

from __future__ import annotations

from schemas import AgentName, RoutedInput

from .chunking import Chunk
from .docling_parse import ParsedDocument
from .embeddings import JudgmentChunkIndex

MIN_STRUCTURE_CHUNKS = 3

# Heading keywords that identify each agent's section(s) in a typical Indian
# court judgment. Matched case-insensitively against a section's heading path.
AGENT_HEADING_KEYWORDS: dict[AgentName, list[str]] = {
    AgentName.METADATA: ["IN THE", "CORAM", "BENCH", "JUDGMENT", "ORDER", "CASE NO"],
    AgentName.FACTS: ["FACTS", "BACKGROUND", "BRIEF FACTS", "CASE OF THE PROSECUTION"],
    AgentName.STATUTE: ["STATUTE", "PROVISION", "SECTION", "CHARGE"],
    AgentName.PETITIONER: ["PETITIONER", "APPELLANT", "PLAINTIFF", "SUBMISSION OF THE APPELLANT"],
    AgentName.RESPONDENT: ["RESPONDENT", "STATE", "DEFENDANT", "SUBMISSION OF THE RESPONDENT"],
    AgentName.EVIDENCE: ["EVIDENCE", "WITNESS", "EXHIBIT", "TESTIMONY"],
}

# Fallback semantic query per agent, used only when structure routing is thin.
AGENT_FALLBACK_QUERY: dict[AgentName, str] = {
    AgentName.METADATA: "court, bench, judges, case number, parties, decision date",
    AgentName.FACTS: "background facts and chronology of the case",
    AgentName.STATUTE: "sections and statutes cited, legal provisions invoked",
    AgentName.PETITIONER: "arguments and submissions made by the petitioner or appellant",
    AgentName.RESPONDENT: "arguments and submissions made by the respondent or state",
    AgentName.EVIDENCE: "witnesses, exhibits, and evidence produced",
}


def _matches(section_path: str, keywords: list[str]) -> bool:
    upper = section_path.upper()
    return any(kw in upper for kw in keywords)


def route_document(parsed: ParsedDocument, chunks: list[Chunk]) -> dict[AgentName, RoutedInput]:
    routed: dict[AgentName, RoutedInput] = {}

    for agent, keywords in AGENT_HEADING_KEYWORDS.items():
        matched_section_indices = {
            idx for idx, section in enumerate(parsed.sections) if _matches(section.section_path, keywords)
        }
        matched_chunks = [c for c in chunks if c.section_index in matched_section_indices]

        routed[agent] = RoutedInput(
            agent=agent,
            chunk_ids=[c.chunk_id for c in matched_chunks],
            routed_by="structure",
        )

    return routed


def apply_retrieval_fallback(
    agent: AgentName,
    routed_input: RoutedInput,
    chunk_index: JudgmentChunkIndex,
    *,
    top_k: int = 8,
    rerank_k: int = 5,
) -> RoutedInput:
    """If structure routing found too few chunks, pull more via semantic recall
    + rerank and merge them in. Never removes structure-routed chunks."""
    if len(routed_input.chunk_ids) >= MIN_STRUCTURE_CHUNKS:
        return routed_input

    query = AGENT_FALLBACK_QUERY[agent]
    candidates = [c for c, _ in chunk_index.search(query, top_k=top_k)]
    reranked = chunk_index.rerank(query, candidates, top_k=rerank_k)

    merged_ids = list(routed_input.chunk_ids)
    for chunk, _score in reranked:
        if chunk.chunk_id not in merged_ids:
            merged_ids.append(chunk.chunk_id)

    routed_by = "hybrid" if routed_input.chunk_ids else "retrieval"
    return routed_input.model_copy(update={"chunk_ids": merged_ids, "routed_by": routed_by})
