"""PDF parsing via Docling — hierarchical document model with OCR fallback.

`do_ocr=True, force_full_page_ocr=False` makes Docling apply OCR only to pages/
regions where the native text layer is insufficient (the B1 density-check node
in docs/architecture/data_flow.md) rather than forcing OCR on every page.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel


@dataclass
class ParsedSection:
    """One heading-delimited section of the parsed document."""

    heading: str
    level: int
    section_path: str  # e.g. "ORDER > Held"
    text: str
    page: int


@dataclass
class ParsedDocument:
    document: DoclingDocument
    sections: list[ParsedSection] = field(default_factory=list)
    page_count: int = 0
    ocr_used: bool = False


def _build_converter() -> DocumentConverter:
    pipeline_options = PdfPipelineOptions(
        do_table_structure=True,
        do_ocr=True,
        force_full_page_ocr=False,
    )
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
    )


def parse_pdf(path: str | Path) -> ParsedDocument:
    """Parse a PDF into a hierarchical document model, grouped into sections
    by heading. Each section keeps its heading breadcrumb (`section_path`) so
    downstream chunking/routing can attach provenance back to page + section.
    """
    converter = _build_converter()
    result = converter.convert(str(path))
    doc = result.document

    sections: list[ParsedSection] = []
    heading_stack: list[str] = []
    current_heading = "root"
    current_level = 0
    current_page = 1
    buffer: list[str] = []

    def flush() -> None:
        text = "\n".join(buffer).strip()
        if text:
            sections.append(
                ParsedSection(
                    heading=current_heading,
                    level=current_level,
                    section_path=" > ".join(heading_stack) if heading_stack else current_heading,
                    text=text,
                    page=current_page,
                )
            )
        buffer.clear()

    for item, level in doc.iterate_items():
        text = getattr(item, "text", None)
        if not text:
            continue
        page_no = 1
        prov = getattr(item, "prov", None)
        if prov:
            page_no = prov[0].page_no

        if item.label in (DocItemLabel.TITLE, DocItemLabel.SECTION_HEADER):
            flush()
            heading_stack = heading_stack[: level - 1] if level > 0 else []
            heading_stack.append(text)
            current_heading = text
            current_level = level
            current_page = page_no
        else:
            current_page = page_no
            buffer.append(text)

    flush()

    ocr_used = any(
        getattr(page, "parsed_page", None) is not None
        and getattr(page.parsed_page, "predictions", None) is not None
        for page in getattr(doc, "pages", {}).values()
    )

    return ParsedDocument(
        document=doc,
        sections=sections,
        page_count=len(getattr(doc, "pages", {})) or 1,
        ocr_used=ocr_used,
    )
