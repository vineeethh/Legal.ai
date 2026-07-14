"""Registry of acts to ingest — one entry per (act, version).

Effective dates and act metadata here are the load-bearing legal facts for
verification; keep them accurate and update this table (never the PDF text)
if an amendment changes an effective date.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from schemas.enums import ActFamily, StatuteAct


@dataclass(frozen=True)
class ActEntry:
    act: StatuteAct
    act_family: ActFamily
    act_version: str
    pdf_path: str
    effective_from: date
    effective_to: date | None
    status: str  # 'active' | 'repealed' | 'superseded'
    source_citation: str


ACT_REGISTRY: list[ActEntry] = [
    ActEntry(
        act=StatuteAct.IPC,
        act_family=ActFamily.CRIMINAL_SUBSTANTIVE,
        act_version="IPC-1860",
        pdf_path="data/raw/ipc/IPC.pdf",
        effective_from=date(1862, 1, 1),
        effective_to=date(2024, 7, 1),
        status="superseded",
        source_citation="Act No. 45 of 1860; superseded by BNS effective 2024-07-01 for new offenses.",
    ),
    ActEntry(
        act=StatuteAct.CRPC,
        act_family=ActFamily.CRIMINAL_PROCEDURAL,
        act_version="CrPC-1973",
        pdf_path="data/raw/crpc/Code of Criminal Procedure.pdf",
        effective_from=date(1974, 4, 1),
        effective_to=date(2024, 7, 1),
        status="superseded",
        source_citation="Act No. 2 of 1974; superseded by BNSS effective 2024-07-01.",
    ),
    ActEntry(
        act=StatuteAct.EVIDENCE_ACT,
        act_family=ActFamily.EVIDENCE,
        act_version="EVIDENCE_ACT-1872",
        pdf_path="data/raw/evidence_act/Indian Evidence Act.pdf",
        effective_from=date(1872, 9, 1),
        effective_to=date(2024, 7, 1),
        status="superseded",
        source_citation="Act No. 1 of 1872; superseded by BSA effective 2024-07-01.",
    ),
    ActEntry(
        act=StatuteAct.CONSTITUTION,
        act_family=ActFamily.CONSTITUTIONAL,
        act_version="CONSTITUTION-1950",
        pdf_path="data/raw/constitution/constitution_of_india.pdf",
        effective_from=date(1950, 1, 26),
        effective_to=None,
        status="active",
        source_citation="Constitution of India, adopted 1949-11-26, in force 1950-01-26.",
    ),
    ActEntry(
        act=StatuteAct.BNS,
        act_family=ActFamily.CRIMINAL_SUBSTANTIVE,
        act_version="BNS-2023",
        pdf_path="data/raw/bns/Bharatiya Nyaya Sanhita.pdf",
        effective_from=date(2024, 7, 1),
        effective_to=None,
        status="active",
        source_citation="Act No. 45 of 2023, in force 2024-07-01.",
    ),
    ActEntry(
        act=StatuteAct.BNSS,
        act_family=ActFamily.CRIMINAL_PROCEDURAL,
        act_version="BNSS-2023",
        pdf_path="data/raw/bnss/Bharatiya Nagarik Suraksha Sanhita.pdf",
        effective_from=date(2024, 7, 1),
        effective_to=None,
        status="active",
        source_citation="Act No. 46 of 2023, in force 2024-07-01.",
    ),
    ActEntry(
        act=StatuteAct.BSA,
        act_family=ActFamily.EVIDENCE,
        act_version="BSA-2023",
        pdf_path="data/raw/bsa/Bharatiya Sakshya Adhiniyam.pdf",
        effective_from=date(2024, 7, 1),
        effective_to=None,
        status="active",
        source_citation="Act No. 47 of 2023, in force 2024-07-01.",
    ),
]
