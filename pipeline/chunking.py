"""Hierarchical semantic chunking + recursive split.

Section boundaries from Docling (see docling_parse.py) are the primary chunk
boundary — this keeps a chunk's `section_path` meaningful for structure-first
routing. Sections longer than `chunk_size` are recursively split, and each
resulting chunk still carries its parent section's path + page for provenance.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

from .docling_parse import ParsedDocument, ParsedSection


@dataclass
class Chunk:
    chunk_id: str
    text: str
    section_path: str
    page: int
    section_index: int  # index of the parent ParsedSection, for stitching context


def chunk_document(
    parsed: ParsedDocument,
    *,
    chunk_size: int = 1200,
    chunk_overlap: int = 150,
) -> list[Chunk]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    chunks: list[Chunk] = []
    for idx, section in enumerate(parsed.sections):
        pieces = splitter.split_text(section.text) if len(section.text) > chunk_size else [section.text]
        for piece in pieces:
            if not piece.strip():
                continue
            chunks.append(
                Chunk(
                    chunk_id=str(uuid.uuid4()),
                    text=piece,
                    section_path=section.section_path,
                    page=section.page,
                    section_index=idx,
                )
            )
    return chunks


def section_by_path_prefix(parsed: ParsedDocument, prefix: str) -> list[ParsedSection]:
    """Sections whose path starts with `prefix` — the structure-first router's
    primary lookup (e.g. prefix='FACTS' or 'ARGUMENTS > Petitioner')."""
    return [s for s in parsed.sections if s.section_path.upper().startswith(prefix.upper())]
