"""Section-splitter for bare-act PDFs.

Heuristic, not perfect: matches the "<number>. <Title>.—<body>" pattern common
to IPC/CrPC/Evidence Act/BNS/BNSS/BSA/Constitution as published. Every run
writes a coverage report (data/processed/<version>.report.json) listing gaps
in the section-number sequence so a human can spot-check before this data is
trusted for citation verification — do not skip that review step.

India Code bare-act PDFs commonly print a section's marginal title on its own
line, then repeat it verbatim right before the operative text opens (e.g.
"91.\nExclusion of ... harm cause.\nExclusion of ... harm cause.--The
exceptions..."). Sometimes the section number repeats too (e.g. "46.\nArrest
how made.\n46.  Arrest how made.  (1) In making an arrest..."). The title
group allows one optional line break, an optional repeat of the number
(backreference \1), then either an exact repeat of the title (backreference
\2) or a dash — whichever is present.

Critically, an act may use *neither* convention consistently: CrPC frequently
has no dash at all between title and body (e.g. "248.Acquittal or
conviction. (1) If, in any case..."), while IPC almost always does. A dash
is required only when the title does NOT repeat; when it does repeat, the
repeat itself is treated as strong enough evidence of a real section
boundary. This still can't be relaxed to "the title may just span multiple
lines with no repeat check" — an earlier version of this pattern did that
and, hunting for the next ".--" on a title that never has one, swallowed
everything up to the next section that did, silently merging ~170 CrPC
sections into one on a real ingestion run. Requiring an *exact* repeat (not
just "some later dash") is what keeps that failure mode closed.

Text is whitespace-normalized (runs of spaces/tabs collapsed to one) before
matching, since Docling's extraction is inconsistent about this between a
title's marginal-note occurrence and its body occurrence (observed: "Pursuit
of offenders" vs "Pursuit  of offenders") — without normalizing, the
backreference match would silently fail on that whitespace difference alone.
A residual few sections still won't match (e.g. a rare word-glue OCR
artifact — "of police station" on one line vs "ofpolice station" on the
other) and will show up as coverage-report gaps for human review, same as
any other section this heuristic can't confidently claim.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pipeline.docling_parse import ParsedDocument

SECTION_HEADER_RE = re.compile(
    r"(?m)^(\d{1,3}[A-Z]{0,3})\.[ \t]*\n?[ \t]*([A-Z][^.\n]{2,180}?)\.[ \t]*\n?"
    r"(?:[ \t]*\1\.)?(?:[ \t]*\2\.[ \t]*[-—–]?|[ \t]*[-—–])\s?"
)


@dataclass
class RawSection:
    section_number: str
    section_title: str
    content: str
    chapter_path: str


def split_into_sections(parsed: ParsedDocument) -> tuple[list[RawSection], list[str]]:
    """Returns the parsed sections plus a list of section_paths for
    ParsedSection blocks that had text but yielded zero header matches — a
    signal that content was silently dropped by this function (as opposed to
    upstream in Docling), so a human can go look at that specific block."""
    sections: list[RawSection] = []
    unmatched_paths: list[str] = []

    for parsed_section in parsed.sections:
        text = re.sub(r"[ \t]+", " ", parsed_section.text)
        matches = list(SECTION_HEADER_RE.finditer(text))
        if not matches:
            if text.strip():
                unmatched_paths.append(parsed_section.section_path)
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

    return sections, unmatched_paths


def coverage_report(sections: list[RawSection], unmatched_paths: list[str] | None = None) -> dict:
    """Flags likely-missed sections by looking for gaps in the numeric sequence.
    Only checks the purely-numeric part of section_number (ignores 'A'/'B' suffixed
    inserted sections, which legitimately break strict sequence).

    `unmatched_paths` (from split_into_sections) lists heading-groups that had
    text but produced zero header matches — i.e. content this module saw and
    dropped, as distinct from content Docling itself never surfaced upstream.
    A gap number with no corresponding unmatched_path entry likely means the
    loss happened before split_into_sections ever ran (Docling's layout/OCR),
    not in this file's regex."""
    numbers = sorted({int(m.group()) for s in sections if (m := re.match(r"\d+", s.section_number))})
    gaps = [n for n in range(numbers[0], numbers[-1] + 1) if n not in numbers] if numbers else []
    duplicates = [s.section_number for s in sections if sections.count(s) > 1]
    return {
        "total_sections_found": len(sections),
        "numeric_range": [numbers[0], numbers[-1]] if numbers else None,
        "missing_numbers_in_range": gaps,
        "unmatched_heading_groups": unmatched_paths or [],
        "note": (
            "Missing numbers may be legitimately repealed sections, or parser misses — "
            "verify against the source PDF before trusting this KB for verification. "
            "If unmatched_heading_groups is empty, gaps were most likely dropped by "
            "Docling's parse/OCR before this file's regex ever ran, not by the regex."
        ),
    }
