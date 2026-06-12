"""Runtime provider switching + validation (sprint §14).

Proves the productized provider workflow is SAFE and deterministic, with no live model
needed (conftest forces ABA_OFFLINE_MODE=always):

  • a switch persists, wins over the env default, and is reload/restart-safe;
  • switching re-resolves to the new provider's reference models even when the env PINS a
    model id for a different provider (no gpt-4o leaking onto Ollama);
  • clearing reverts to the server (env) default;
  • the LLM client is rebuilt to the new provider; the engine + workspace are PRESERVED;
  • validation never raises, never leaks a stack trace, and is honest offline.

Run:  .venv/bin/python -m pytest tests/test_provider_switch.py -q
"""
from __future__ import annotations

import shutil

import pytest

from app import config as C
from app.config import ROOT, get_settings
from app.llm.client import get_llm, reset_llm


@pytest.fixture()
def provider_env(tmp_path, monkeypatch):
    """Isolate the override file under a temp data dir and pin a deterministic env default
    (openai, with an explicit gpt-4o model pin) so assertions don't depend on the dev .env."""
    monkeypatch.setenv("ABA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ABA_PROVIDER", "openai")
    monkeypatch.setenv("ABA_MODEL_GENERATION", "gpt-4o")
    monkeypatch.setenv("ABA_MODEL_ROUTER", "gpt-4o-mini")
    monkeypatch.setenv("ABA_MODEL_SQL", "gpt-4o-mini")
    C.clear_runtime_provider()
    reset_llm()
    yield
    C.clear_runtime_provider()
    get_settings.cache_clear()
    reset_llm()


# -- switch mechanics --------------------------------------------------------

def test_env_default_before_any_switch(provider_env):
    s = get_settings()
    assert s.resolved_provider == "openai"
    assert s.model_generation == "gpt-4o"
    st = C.provider_override_state()
    assert st == {"applied": "openai", "default": "openai", "source": "env", "overridden": False}


def test_switch_persists_and_reresolves_models(provider_env):
    # the env PINS gpt-4o; switching to Ollama must NOT carry gpt-4o onto the local server.
    payload = C.set_runtime_provider("ollama")
    assert payload["provider"] == "ollama"
    s = get_settings()
    assert s.resolved_provider == "ollama"
    assert s.model_generation == "qwen2.5:7b-instruct"
    assert s.model_router == "qwen2.5:7b-instruct"
    assert s.model_sql == "qwen2.5:7b-instruct"
    assert s.provider_base_url == "http://localhost:11434/v1"


def test_switch_is_reload_and_restart_safe(provider_env):
    C.set_runtime_provider("ollama")
    # simulate a fresh process: drop the cached Settings and re-read the persisted override.
    get_settings.cache_clear()
    assert get_settings().resolved_provider == "ollama"
    assert C.provider_override_state()["applied"] == "ollama"


def test_switch_to_anthropic_uses_claude_models(provider_env):
    C.set_runtime_provider("anthropic")
    s = get_settings()
    assert s.resolved_provider == "anthropic"
    assert s.model_generation == "claude-opus-4-8"
    assert s.transport_family == "anthropic"


def test_clear_reverts_to_env_default(provider_env):
    C.set_runtime_provider("anthropic")
    assert get_settings().resolved_provider == "anthropic"
    C.clear_runtime_provider()
    s = get_settings()
    assert s.resolved_provider == "openai"          # back to the env default
    assert s.model_generation == "gpt-4o"           # env pin honored again
    st = C.provider_override_state()
    assert st["overridden"] is False and st["source"] == "env"


def test_override_state_reports_applied_vs_default(provider_env):
    C.set_runtime_provider("ollama")
    st = C.provider_override_state()
    assert st["applied"] == "ollama"
    assert st["default"] == "openai"
    assert st["source"] == "override"
    assert st["overridden"] is True


def test_bad_provider_rejected(provider_env):
    with pytest.raises(ValueError):
        C.set_runtime_provider("gpt-5-turbo")
    # a rejected switch must not change the applied provider
    assert get_settings().resolved_provider == "openai"


def test_reset_llm_rebuilds_to_new_provider(provider_env):
    assert get_llm().provider.name == "openai"
    C.set_runtime_provider("ollama")
    reset_llm()
    assert get_llm().provider.name == "ollama"
    C.set_runtime_provider("anthropic")
    reset_llm()
    assert get_llm().provider.name == "anthropic"


# -- workspace preservation across a switch ----------------------------------

@pytest.fixture()
def workspace_engine(tmp_path, monkeypatch):
    """A fresh engine over an isolated copy of the seed corpus (uploads + the override file
    land only under this test's data dir)."""
    data = tmp_path / "data"
    (data / "pdfs").mkdir(parents=True)
    for p in sorted((ROOT / "data" / "pdfs").glob("*.pdf")):
        shutil.copy(p, data / "pdfs" / p.name)
    shutil.copy(ROOT / "data" / "business.db", data / "business.db")

    monkeypatch.setenv("ABA_DATA_DIR", str(data))
    monkeypatch.setenv("ABA_PROVIDER", "openai")
    C.clear_runtime_provider()
    get_settings.cache_clear()
    reset_llm()
    from app.engine import Engine
    eng = Engine()
    yield eng, data
    C.clear_runtime_provider()
    get_settings.cache_clear()
    reset_llm()


def _upload_pdf(eng, data, name="Switch_Test_Brief.pdf"):
    src = sorted((ROOT / "data" / "pdfs").glob("*.pdf"))[0]
    dest = data / "uploads" / "pdfs" / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, dest)
    return eng.add_pdf(name, dest)


def _upload_db(eng, data, name="switch_test.db"):
    dest = data / "uploads" / "db" / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / "data" / "business.db", dest)
    return eng.add_database(name, dest)


def test_workspace_preserved_across_provider_switch(workspace_engine):
    eng, data = workspace_engine
    _upload_pdf(eng, data)
    _upload_db(eng, data)

    before = eng.inventory()
    assert before.total_chunks > 0
    assert any(d.origin == "uploaded" for d in before.documents)
    assert any(d.origin == "uploaded" for d in before.databases)
    statuses_before = {s.name: s.status for s in eng.sources}

    # switch the chat provider — this must NOT rebuild the engine or drop uploads.
    C.set_runtime_provider("ollama")
    reset_llm()
    assert get_settings().resolved_provider == "ollama"

    after = eng.inventory()
    assert after.total_chunks == before.total_chunks
    assert [d.name for d in after.documents] == [d.name for d in before.documents]
    assert [d.name for d in after.databases] == [d.name for d in before.databases]
    assert {s.name: s.status for s in eng.sources} == statuses_before

    # and the engine still answers (offline deterministic) without crashing.
    resp = eng.ask("How many invoices are overdue?", scope="workspace")
    assert resp.answer and isinstance(resp.answer, str)


# -- validation --------------------------------------------------------------

def test_validation_is_offline_safe_and_never_raises(provider_env):
    from app.llm.validate import validate_provider
    v = validate_provider()
    assert v.ok is True                              # offline → nothing FAILS
    by = {c.name: c for c in v.checks}
    assert set(by) == {"health", "routing", "generation", "embeddings"}
    assert by["embeddings"].status == "pass"
    assert by["routing"].status == "skipped"
    assert by["generation"].status == "skipped"
    assert by["health"].status == "skipped"


def test_validation_leaks_no_stack_trace(provider_env):
    from app.llm.validate import validate_provider
    v = validate_provider()
    for c in v.checks:
        blob = f"{c.detail} {c.fix or ''}"
        assert "Traceback" not in blob
        assert ".py" not in blob or "<internal>" in blob


def test_validation_clean_error_scrubs_paths_and_is_single_line():
    from app.llm.validate import _clean_error
    dirty = "boom at /home/user/app/llm/providers/openai_provider.py:71\nsecond line of noise"
    cleaned = _clean_error(dirty)
    assert "\n" not in cleaned                               # collapsed to one readable line
    assert "<internal>" in cleaned and "openai_provider.py" not in cleaned  # path scrubbed
    assert len(cleaned) <= 222                               # capped — never a wall of text
    assert _clean_error("") == "The provider call failed."   # empty → safe default


def test_provider_options_carry_deployment_modes():
    from app.api.routes import _provider_options
    opts = {o.name: o for o in _provider_options()}
    assert set(opts) == {"openai", "ollama", "anthropic"}
    assert opts["openai"].deployment_mode == "Production Recommended"
    assert opts["ollama"].deployment_mode == "Private / Local Deployment"
    assert opts["anthropic"].deployment_mode == "Advanced Configuration"
    assert all(o.description for o in opts.values())
