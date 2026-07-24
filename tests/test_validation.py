"""Phase 1 — validator integrity.

Covers the two bugs fixed in pipeline/validation.py:
  1. The entailment gate must run on `settings.validator_llm_model` (previously it
     silently used the extractor's model — the setting was dead config).
  2. Verdicts are reconciled to candidates *by index*; a missing/duplicate/non-PASS
     verdict FAILS the field instead of letting it vanish from the pass-rate
     denominator (which would inflate confidence for exactly the fields the
     validator skipped).

These import only pydantic + schemas — no langchain/docling needed — so they run
on the bare local interpreter, not just inside the Docker image.
"""

from __future__ import annotations

import sys
import types

from pydantic import BaseModel

from pipeline.validation import (
    SourcedField,
    _FieldVerdict,
    _ValidationBatch,
    _entailment_check,
    _reconcile,
    validate_agent_output,
    walk_sourced_fields,
)
from schemas import AgentName, FieldValidation, Sourced, SourceRef, ValidationStatus


def _cand(path: str, quote: str, value: str = "v") -> tuple[SourcedField, str]:
    return SourcedField(field_path=path, value=value, sources=[]), quote


# --------------------------------------------------------------------------- #
# _reconcile — the core anti-regression for the "unaligned batch" bug
# --------------------------------------------------------------------------- #


def test_reconcile_matches_verdicts_by_index_not_order():
    candidates = [_cand("a", "qa"), _cand("b", "qb")]
    batch = _ValidationBatch(
        verdicts=[
            _FieldVerdict(index=1, status=ValidationStatus.FAIL, reason="nope"),
            _FieldVerdict(index=0, status=ValidationStatus.PASS),
        ]
    )
    res = _reconcile(candidates, batch)
    assert [r.field_path for r in res] == ["a", "b"]
    assert res[0].status == ValidationStatus.PASS
    assert res[0].supporting_quote == "qa"  # our verified quote, not the LLM's echo
    assert res[1].status == ValidationStatus.FAIL
    assert res[1].supporting_quote is None
    assert res[1].reason == "nope"


def test_reconcile_missing_verdict_fails_and_field_does_not_vanish():
    candidates = [_cand("a", "qa"), _cand("b", "qb")]
    batch = _ValidationBatch(verdicts=[_FieldVerdict(index=0, status=ValidationStatus.PASS)])
    res = _reconcile(candidates, batch)
    assert len(res) == 2, "b must not silently drop out"
    assert res[1].field_path == "b"
    assert res[1].status == ValidationStatus.FAIL
    assert "no verdict" in res[1].reason.lower()


def test_reconcile_duplicate_verdict_fails():
    candidates = [_cand("a", "qa")]
    batch = _ValidationBatch(
        verdicts=[
            _FieldVerdict(index=0, status=ValidationStatus.PASS),
            _FieldVerdict(index=0, status=ValidationStatus.PASS),
        ]
    )
    res = _reconcile(candidates, batch)
    assert res[0].status == ValidationStatus.FAIL
    assert "ambiguous" in res[0].reason.lower()


def test_reconcile_ignores_unknown_extra_indices():
    candidates = [_cand("a", "qa")]
    batch = _ValidationBatch(
        verdicts=[
            _FieldVerdict(index=0, status=ValidationStatus.PASS),
            _FieldVerdict(index=99, status=ValidationStatus.PASS),
        ]
    )
    res = _reconcile(candidates, batch)
    assert len(res) == 1
    assert res[0].status == ValidationStatus.PASS


def test_reconcile_non_pass_status_fails():
    candidates = [_cand("a", "qa")]
    batch = _ValidationBatch(verdicts=[_FieldVerdict(index=0, status=ValidationStatus.NOT_APPLICABLE)])
    res = _reconcile(candidates, batch)
    assert res[0].status == ValidationStatus.FAIL


def test_reconcile_empty_batch_fails_everything():
    candidates = [_cand("a", "qa"), _cand("b", "qb")]
    res = _reconcile(candidates, _ValidationBatch())
    assert len(res) == 2
    assert all(r.status == ValidationStatus.FAIL for r in res)


# --------------------------------------------------------------------------- #
# validate_agent_output — gate 1 (deterministic quote-existence)
# --------------------------------------------------------------------------- #


class _Tiny(BaseModel):
    field_a: Sourced[str]


def test_gate1_missing_quote_fails_without_calling_llm(monkeypatch):
    def _boom(_candidates):
        raise AssertionError("entailment must not run when gate 1 already failed")

    monkeypatch.setattr("pipeline.validation._entailment_check", _boom)

    out = _Tiny(field_a=Sourced(value="x", sources=[SourceRef(page=1, quote="needle", chunk_id="c1")]))
    chunks = {"c1": types.SimpleNamespace(text="a haystack without the word")}

    res = validate_agent_output(AgentName.METADATA, out, chunks, attempt=2)
    assert res.attempt == 2
    assert len(res.fields) == 1
    assert res.fields[0].status == ValidationStatus.FAIL
    assert "not found verbatim" in res.fields[0].reason


def test_gate1_pass_forwards_verified_quote_to_entailment(monkeypatch):
    captured: dict = {}

    def _fake_entail(candidates):
        captured["candidates"] = candidates
        sf, quote = candidates[0]
        return [FieldValidation(field_path=sf.field_path, status=ValidationStatus.PASS, supporting_quote=quote)]

    monkeypatch.setattr("pipeline.validation._entailment_check", _fake_entail)

    out = _Tiny(field_a=Sourced(value="x", sources=[SourceRef(page=1, quote="needle", chunk_id="c1")]))
    chunks = {"c1": types.SimpleNamespace(text="a needle in the text")}

    res = validate_agent_output(AgentName.METADATA, out, chunks, attempt=0)
    assert captured["candidates"][0][1] == "needle"  # the verified span, forwarded
    assert res.fields[0].status == ValidationStatus.PASS
    assert res.fields[0].supporting_quote == "needle"


# --------------------------------------------------------------------------- #
# _entailment_check — bug #1: must use the validator model, end-to-end reconcile
# --------------------------------------------------------------------------- #


def test_entailment_uses_validator_model(monkeypatch):
    calls: dict = {}

    class _FakeStructured:
        def invoke(self, messages):
            calls["messages"] = messages
            return _ValidationBatch(verdicts=[_FieldVerdict(index=0, status=ValidationStatus.PASS)])

    class _FakeChat:
        def with_structured_output(self, schema, **kwargs):
            calls["schema"] = schema
            calls["method"] = kwargs.get("method")
            return _FakeStructured()

    def _fake_get_chat_model(*, model=None, temperature=0.0, **_kw):
        calls["model"] = model
        calls["temperature"] = temperature
        return _FakeChat()

    fake_llm = types.ModuleType("pipeline.llm")
    fake_llm.get_chat_model = _fake_get_chat_model
    monkeypatch.setitem(sys.modules, "pipeline.llm", fake_llm)

    import pipeline.config as cfg

    monkeypatch.setattr(cfg, "get_settings", lambda: types.SimpleNamespace(validator_llm_model="validator-xyz"))

    res = _entailment_check([_cand("field_a", "needle")])

    assert calls["model"] == "validator-xyz"
    assert calls["temperature"] == 0.0
    assert calls["schema"] is _ValidationBatch
    assert res[0].status == ValidationStatus.PASS
    assert res[0].supporting_quote == "needle"


def test_entailment_check_never_crashes_on_bad_validator_output(monkeypatch):
    """Regression: _entailment_check used to bare-assert on the validator's own
    structured output. Since this runs in the confidence node (outside
    per-agent error isolation), a validator failure must FAIL every candidate
    rather than raise and crash the whole document run."""
    from pipeline.validation import _entailment_check

    class _FakeStructured:
        def invoke(self, messages):
            return None  # model returned no valid structured output

    class _FakeChat:
        def with_structured_output(self, schema, **kwargs):
            return _FakeStructured()

    fake_llm = types.ModuleType("pipeline.llm")
    fake_llm.get_chat_model = lambda **kw: _FakeChat()
    monkeypatch.setitem(sys.modules, "pipeline.llm", fake_llm)
    import pipeline.config as cfg

    monkeypatch.setattr(cfg, "get_settings", lambda: types.SimpleNamespace(validator_llm_model="v"))

    res = _entailment_check([_cand("a", "qa"), _cand("b", "qb")])
    assert len(res) == 2
    assert all(r.status == ValidationStatus.FAIL for r in res)


def test_entailment_check_never_crashes_on_llm_exception(monkeypatch):
    from pipeline.validation import _entailment_check

    class _FakeChat:
        def with_structured_output(self, schema, **kwargs):
            raise ConnectionError("model unreachable")

    fake_llm = types.ModuleType("pipeline.llm")
    fake_llm.get_chat_model = lambda **kw: _FakeChat()
    monkeypatch.setitem(sys.modules, "pipeline.llm", fake_llm)
    import pipeline.config as cfg

    monkeypatch.setattr(cfg, "get_settings", lambda: types.SimpleNamespace(validator_llm_model="v"))

    res = _entailment_check([_cand("a", "qa")])
    assert len(res) == 1
    assert res[0].status == ValidationStatus.FAIL
    assert "ConnectionError" in res[0].reason


def test_gate1_accepts_whitespace_and_glyph_variants():
    from pipeline.validation import quote_in_chunk

    chunk = "The court held that “the accused\n   shall be   released” — forthwith."
    assert quote_in_chunk('the accused shall be released', chunk)  # ws + curly quotes flattened
    assert quote_in_chunk("“the accused shall be released”", chunk)
    assert not quote_in_chunk("the accused shall be detained", chunk)  # paraphrase still fails


def test_walk_sourced_fields_finds_nested_sourced_value():
    out = _Tiny(field_a=Sourced(value="x", sources=[SourceRef(page=1, quote="q", chunk_id="c1")]))
    found = walk_sourced_fields(out)
    assert [sf.field_path for sf in found] == ["field_a"]
    assert found[0].value == "x"
