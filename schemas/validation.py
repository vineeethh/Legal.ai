"""Validation schemas — span-grounded, second-LLM verification.

The validator does NOT use RAG. For each extracted field it must decide whether the
value is *entailed* by the field's own source quotes, and it must echo the supporting
span. A field asserted without a quotable span cannot PASS.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .enums import AgentName, ValidationStatus


class FieldValidation(BaseModel):
    """Validation verdict for a single field (or list item) of an agent's output."""

    field_path: str = Field(..., description="Dotted path, e.g. 'metadata.judges[0]'.")
    status: ValidationStatus
    supporting_quote: str | None = Field(
        default=None, description="Verbatim span the validator relied on. Required for PASS."
    )
    reason: str | None = Field(default=None, description="Why it failed, if it failed.")


class AgentValidationResult(BaseModel):
    """Aggregated validation for one agent's output, across attempts."""

    agent: AgentName
    attempt: int = Field(..., ge=0, description="0 = first run; increments on each retry.")
    fields: list[FieldValidation] = Field(default_factory=list)

    @property
    def failed_fields(self) -> list[FieldValidation]:
        return [f for f in self.fields if f.status == ValidationStatus.FAIL]

    @property
    def overall(self) -> ValidationStatus:
        if any(f.status == ValidationStatus.FAIL for f in self.fields):
            return ValidationStatus.FAIL
        return ValidationStatus.PASS

    @property
    def pass_rate(self) -> float:
        """Fraction of applicable fields that passed. Feeds the confidence score."""
        applicable = [f for f in self.fields if f.status != ValidationStatus.NOT_APPLICABLE]
        if not applicable:
            return 1.0
        passed = sum(1 for f in applicable if f.status == ValidationStatus.PASS)
        return passed / len(applicable)
