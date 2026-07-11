"""The `PromptSpec` dataclass, split out from pipeline/prompts.py so agent
modules can import it without a cycle: agents -> prompt_spec (no
back-dependency), while pipeline/prompts.py -> prompt_spec AND agents.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptSpec:
    node: str
    system_prompt: str
    is_template: bool = False
    template_params: dict | None = None
