"""PDF structural safety scan — runs before Docling ever touches the file.

Checks structure only (size, page count, auto-actions, embedded JavaScript/
files) via pikepdf — no antivirus/byte-signature scanning. Rejects a PDF
outright rather than trying to sanitize it; this pipeline's job is extraction,
not disarming malicious documents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pikepdf

from .config import get_settings


class PdfSafetyError(Exception):
    """Raised when a PDF fails the structural safety scan. `reasons` lists
    every check that failed, not just the first one."""

    def __init__(self, reasons: list[str]):
        self.reasons = reasons
        super().__init__(f"PDF failed safety scan: {'; '.join(reasons)}")


@dataclass
class PdfSafetyResult:
    safe: bool
    reasons: list[str] = field(default_factory=list)


def scan_pdf_safety(path: str | Path) -> PdfSafetyResult:
    settings = get_settings()
    path = Path(path)
    reasons: list[str] = []

    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb > settings.pdf_max_size_mb:
        reasons.append(f"file_too_large: {size_mb:.1f}MB > {settings.pdf_max_size_mb}MB limit")

    try:
        with pikepdf.open(str(path)) as pdf:
            if len(pdf.pages) > settings.pdf_max_pages:
                reasons.append(f"too_many_pages: {len(pdf.pages)} > {settings.pdf_max_pages} limit")

            root = pdf.Root
            if "/OpenAction" in root:
                reasons.append("has_open_action")
            if "/AA" in root:
                reasons.append("has_document_level_auto_action")

            names = root.get("/Names")
            if names is not None and "/JavaScript" in names:
                reasons.append("has_embedded_javascript")
            if names is not None and "/EmbeddedFiles" in names:
                reasons.append("has_embedded_files")

            for i, page in enumerate(pdf.pages):
                if "/AA" in page:
                    reasons.append(f"page_{i}_has_auto_action")
                annots = page.get("/Annots")
                if annots is not None:
                    for annot in annots:
                        if annot.get("/Subtype") == "/FileAttachment":
                            reasons.append(f"page_{i}_has_file_attachment_annotation")
    except pikepdf.PasswordError:
        reasons.append("password_protected")
    except pikepdf.PdfError as exc:
        reasons.append(f"malformed_pdf: {exc}")

    return PdfSafetyResult(safe=not reasons, reasons=reasons)
