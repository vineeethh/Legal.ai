"""Fallback for a retry-exhausted agent output — prunes whatever never passed
validation instead of returning a low-confidence guess as if it were fact.

Same "None over guessing" invariant the extraction prompts already enforce
(pipeline/agents/base.py's ISOLATION_REMINDER), applied to the case where an
agent's *last* attempt still has failing fields after every retry:
  - Sourced[T] (schemas/base.py) has a legitimate empty state — null it out.
  - SourcedItem[T] and StatuteReference (schemas/statutes.py) do not — a list
    item without a value/citation isn't valid, so a failing one is dropped
    from its list entirely rather than left in place unverified.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from schemas import AgentValidationResult
from schemas.base import Sourced


def apply_fallback(output: BaseModel, validation: AgentValidationResult) -> BaseModel:
    """Returns `output` with every field on `validation.failed_fields` pruned.
    A no-op (returns `output` unchanged) if nothing failed."""
    failed_paths = {f.field_path for f in validation.failed_fields}
    if not failed_paths:
        return output
    pruned, _dropped = _prune(output, failed_paths, "")
    return pruned


def _prune(obj: Any, failed_paths: set[str], path: str) -> tuple[Any, bool]:
    """Mirrors pipeline/validation.py's walk_sourced_fields traversal exactly
    (same path construction) so `path` always matches a FieldValidation's
    field_path. Returns (new_obj, drop) — `drop=True` tells a list/BaseModel
    caller to remove this element rather than keep a nulled placeholder."""

    if isinstance(obj, Sourced):
        if path not in failed_paths:
            return obj, False
        # Sourced[T] — "not present" is a first-class, legitimate state.
        return type(obj)(value=None, sources=[]), False

    if isinstance(obj, BaseModel) and hasattr(obj, "sources") and isinstance(obj.sources, list):
        if path not in failed_paths:
            return obj, False
        # SourcedItem[T] / StatuteReference — no empty state exists on this
        # type (value/raw_citation is required), so a failing one is dropped
        # from its containing list rather than nulled in place.
        return None, True

    if isinstance(obj, BaseModel):
        updates: dict[str, Any] = {}
        for name in type(obj).model_fields:
            value = getattr(obj, name)
            child_path = f"{path}.{name}" if path else name
            new_value, _drop = _prune(value, failed_paths, child_path)
            if new_value is not value:
                updates[name] = new_value
        return (obj.model_copy(update=updates) if updates else obj), False

    if isinstance(obj, list):
        new_list = []
        changed = False
        for i, item in enumerate(obj):
            new_item, drop = _prune(item, failed_paths, f"{path}[{i}]")
            if drop:
                changed = True
                continue
            if new_item is not item:
                changed = True
            new_list.append(new_item)
        return (new_list if changed else obj), False

    return obj, False
