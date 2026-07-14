"""Deterministic prompt-injection pattern scan over chunk text.

Flags, never blocks: court documents legitimately contain adversarial-sounding
text (quoted testimony, counsel submissions, "the court is directed to
disregard..."), so excluding matched chunks risks silently dropping real case
text. Matches are attached to PipelineState.injection_matches and factored
into the review decision in graph.py's assemble_node — a flagged document
can't auto-save, it always routes to at least needs_review.
"""

from __future__ import annotations

import re

from .chunking import Chunk

# Each pattern targets phrasing aimed at an LLM reading the chunk as an
# instruction, not phrasing that could plausibly appear in ordinary judgment
# text (e.g. "disregard" alone is too common in legal writing to flag).
_PATTERNS: dict[str, re.Pattern] = {
    "override_instructions": re.compile(
        r"\bignore (all|any|the) (previous|prior|above|preceding) instructions\b", re.IGNORECASE
    ),
    "disregard_system": re.compile(
        r"\bdisregard (the )?(system|your) (prompt|instructions)\b", re.IGNORECASE
    ),
    "role_reassignment": re.compile(
        r"\byou are now\b|\bact as (if you were|a)\b.{0,30}\b(ai|assistant|model)\b", re.IGNORECASE
    ),
    "fake_role_marker": re.compile(r"^\s*(system|assistant)\s*:\s*", re.IGNORECASE | re.MULTILINE),
    "injected_directive_block": re.compile(r"###\s*(system|instructions?)\b", re.IGNORECASE),
    "prompt_exfiltration": re.compile(
        r"\b(reveal|print|output|repeat) (your |the )?(system )?prompt\b", re.IGNORECASE
    ),
    "new_instructions": re.compile(r"\bnew instructions?\s*:", re.IGNORECASE),
    "always_mark_verified": re.compile(
        r"\balways (mark|treat|classify) this (as|document as) (verified|valid|correct)\b",
        re.IGNORECASE,
    ),
}


def scan_chunk(text: str) -> list[str]:
    """Returns the names of every pattern that matched this chunk's text."""
    return [name for name, pattern in _PATTERNS.items() if pattern.search(text)]


def scan_chunks(chunks: list[Chunk]) -> dict[str, list[str]]:
    """Scans every chunk; returns {chunk_id: [pattern names]} for chunks with
    at least one match. Clean chunks are omitted, so an empty dict means the
    whole document scanned clean."""
    matches: dict[str, list[str]] = {}
    for chunk in chunks:
        hits = scan_chunk(chunk.text)
        if hits:
            matches[chunk.chunk_id] = hits
    return matches
