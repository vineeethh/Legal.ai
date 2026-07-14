"""Section-splitter for bare-act PDFs.

Heuristic, not perfect: matches the "<number>. <Title>.—<body>" pattern common
to IPC/CrPC/Evidence Act/BNS/BNSS/BSA/Constitution as published. Every run
writes a coverage report (data/processed/<version>.report.json) listing gaps
in the section-number sequence so a human can spot-check before this data is
trusted for citation verification — do not skip that review step.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pipeline.docling_parse import ParsedDocument

SECTION_HEADER_RE = re.compile(
    r"(?m)^(\d{1,3}[A-Z]{0,3})\.\s+([A-Z][^.\n]{2,180}?)\.\s?[-—–]\s?"
)


@dataclass
class RawSection:
    section_number: str
    section_title: str
    content: str
    chapter_path: str


def split_into_sections(parsed: ParsedDocument) -> list[RawSection]:
    sections: list[RawSection] = []

    for parsed_section in parsed.sections:
        text = parsed_section.text
        matches = list(SECTION_HEADER_RE.finditer(text))
        if not matches:
            continue

        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            sections.append(
                RawSection(
                    section_number=match.group(1),
                    section_title=match.group(2).strip(),
                    content=body,
                    chapter_path=parsed_section.section_path,
                )
            )

    return sections


def coverage_report(sections: list[RawSection]) -> dict:
    """Flags likely-missed sections by looking for gaps in the numeric sequence.
    Only checks the purely-numeric part of section_number (ignores 'A'/'B' suffixed
    inserted sections, which legitimately break strict sequence)."""
    numbers = sorted({int(m.group()) for s in sections if (m := re.match(r"\d+", s.section_number))})
    gaps = [n for n in range(numbers[0], numbers[-1] + 1) if n not in numbers] if numbers else []
    duplicates = [s.section_number for s in sections if sections.count(s) > 1]
    return {
        "total_sections_found": len(sections),
        "numeric_range": [numbers[0], numbers[-1]] if numbers else None,
        "missing_numbers_in_range": gaps,
        "note": "Missing numbers may be legitimately repealed sections, or parser misses — verify against the source PDF before trusting this KB for verification.",
    }
