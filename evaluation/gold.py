"""Gold-label format — what a person writes down after reading a judgment.

Only objective, checkable fields are labelled. Free-text fields (background,
arguments, incident summary) are not scored here: matching them needs a human
or an LLM judge, and an LLM judge would reintroduce the thing being measured.

Leaving a key OUT means "not labelled, skip it". Writing `null` (or `[]` for a
list) means "this judgment does not contain it" — and the pipeline should then
return None/empty rather than invent a value. The difference matters: it is
how the scorer tells a correct abstention from a hallucination.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from schemas import StatuteAct

SCALAR_FIELDS = ["court", "bench", "decision_date", "case_number", "jurisdiction"]
LIST_FIELDS = ["judges", "petitioners", "respondents", "statutes", "evidence_labels", "timeline_dates"]


class GoldStatute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    act: StatuteAct
    section: str


class GoldMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    court: str | None = None
    bench: str | None = None
    decision_date: date | None = None
    case_number: str | None = None
    jurisdiction: str | None = None
    judges: list[str] = Field(default_factory=list)
    petitioners: list[str] = Field(default_factory=list)  # party names
    respondents: list[str] = Field(default_factory=list)


class GoldJudgment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(..., description="Matches the prediction file name: predictions/<case_id>.json")
    pdf: str = Field(..., description="Path to the judgment PDF, relative to the repo root.")
    synthetic: bool = Field(default=False, description="True for made-up examples; reports are flagged.")
    notes: str | None = None

    metadata: GoldMetadata = Field(default_factory=GoldMetadata)
    statutes: list[GoldStatute] = Field(default_factory=list)
    evidence_labels: list[str] = Field(default_factory=list)  # e.g. "PW-1", "Ext. P-5", "MO-1"
    timeline_dates: list[date] = Field(default_factory=list)  # dates of events in the chronology

    def labelled(self) -> set[str]:
        """Names of the fields this file actually labels (see module docstring)."""
        names = {f for f in self.metadata.model_fields_set if f in SCALAR_FIELDS + LIST_FIELDS}
        names |= {f for f in self.model_fields_set if f in LIST_FIELDS}
        return names


def load_gold_dir(gold_dir: Path) -> list[GoldJudgment]:
    """Every *.json in `gold_dir` except files starting with '_' (templates)."""
    golds = []
    for path in sorted(gold_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        golds.append(GoldJudgment.model_validate_json(path.read_text()))
    return golds
