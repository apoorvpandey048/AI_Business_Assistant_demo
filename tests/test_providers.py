"""Provider abstraction tests (sprint §13).

Covers: provider/model resolution, backward compatibility, the strategy selection, and —
critically — the Ollama failure modes (server down, model not pulled), all WITHOUT a real
Ollama running. The "Ollama not running" path is itself the thing under test.
"""
from __future__ import annotations

from app.config import Settings
from app.llm.providers import (AnthropicProvider, OllamaProvider, OpenAIProvider,
                               make_provider)
from app.llm.providers.ollama_provider import _model_present


def _s(**kw) -> Settings:
    # _env_file=None so the developer's real .env never leaks into these assertions.
    kw.setdefault("offline_mode", "auto")
    kw.setdefault("embedding_backend", "hashing")
    return Settings(_env_file=None, **kw)


# -- provider + model resolution --------------------------------------------

def test_default_is_anthropic_with_claude_models():
    s = _s()
    assert s.resolved_provider == "anthropic"
    assert s.transport_family == "anthropic"
    assert s.model_generation == "claude-opus-4-8"
    assert s.model_router == "claude-sonnet-4-6"


def test_legacy_llm_provider_still_honored():
    s = _s(llm_provider="openai", model_generation="gpt-4o", model_router="gpt-4o-mini")
    assert s.resolved_provider == "openai"
    assert s.transport_family == "openai"
    assert s.model_generation == "gpt-4o"


def test_aba_provider_wins_over_legacy():
    s = _s(provider="ollama", llm_provider="openai")
    assert s.resolved_provider == "ollama"


def test_openai_provider_derives_model_defaults():
    s = _s(provider="openai")
    assert s.model_generation == "gpt-4o"
    assert s.model_router == "gpt-4o-mini"
    assert s.model_sql == "gpt-4o-mini"


def test_ollama_provider_derives_qwen_default_and_local_url():
    s = _s(provider="ollama")
    assert s.model_generation == "qwen2.5:7b-instruct"
    assert s.model_router == "qwen2.5:7b-instruct"
    assert s.model_sql == "qwen2.5:7b-instruct"
    assert s.transport_family == "openai"
    assert s.provider_base_url == "http://localhost:11434/v1"
    assert s.is_local_endpoint is True
    assert s.has_api_key is True  # a local server needs no key


def test_explicit_model_overrides_provider_default():
    s = _s(provider="ollama", model_generation="llama3.1")
    assert s.model_generation == "llama3.1"
    assert s.model_router == "qwen2.5:7b-instruct"  # untouched ones still default


def test_custom_ollama_url_and_model():
    s = _s(provider="ollama", ollama_url="http://box:1234/", ollama_model="qwen2.5:14b")
    assert s.provider_base_url == "http://box:1234/v1"
    assert s.model_generation == "qwen2.5:14b"


# -- strategy selection ------------------------------------------------------

def test_make_provider_selects_the_right_strategy():
    assert isinstance(make_provider(_s(provider="anthropic")), AnthropicProvider)
    assert isinstance(make_provider(_s(provider="openai")), OpenAIProvider)
    assert isinstance(make_provider(_s(provider="ollama")), OllamaProvider)
    # OllamaProvider rides the OpenAI-compatible transport (subclass), by design
    assert issubclass(OllamaProvider, OpenAIProvider)


# -- Ollama failure modes (no real server needed) ---------------------------

def test_ollama_status_server_down():
    # 127.0.0.1:9 (discard) refuses connections → reachable=False
    s = _s(provider="ollama", ollama_url="http://127.0.0.1:9")
    st = make_provider(s).status()
    assert st.provider == "ollama"
    assert st.connection == "disconnected"
    assert st.health == "unavailable"
    assert "ollama serve" in (st.fix or "")
    assert st.generation_model == "qwen2.5:7b-instruct"


def test_ollama_status_model_present(monkeypatch):
    s = _s(provider="ollama")
    prov = make_provider(s)
    monkeypatch.setattr(prov, "_probe", lambda: (True, ["qwen2.5:7b-instruct", "llama3.1:8b"], ""))
    st = prov.status()
    assert st.connection == "connected"
    assert st.health == "healthy"
    assert "available" in st.detail


def test_ollama_status_model_missing(monkeypatch):
    s = _s(provider="ollama")
    prov = make_provider(s)
    monkeypatch.setattr(prov, "_probe", lambda: (True, ["llama3.1:8b"], ""))
    st = prov.status()
    assert st.connection == "connected"
    assert st.health == "degraded"
    assert st.fix == "ollama pull qwen2.5:7b-instruct"


def test_model_present_matcher_tolerates_tag_suffix():
    assert _model_present("qwen2.5:7b-instruct", ["qwen2.5:7b-instruct"])
    assert _model_present("qwen2.5:7b-instruct", ["qwen2.5:7b-instruct:latest"])
    assert not _model_present("qwen2.5:7b-instruct", ["llama3.1:8b"])
    assert not _model_present("qwen2.5:7b-instruct", [])


def test_ollama_offline_mode_does_not_probe():
    # forced offline → no network touch, deterministic status
    s = _s(provider="ollama", offline_mode="always")
    st = make_provider(s).status()
    assert st.health == "unavailable"
    assert "Offline" in st.detail


# -- hosted provider status --------------------------------------------------

def test_anthropic_status_without_key_is_unavailable():
    st = make_provider(_s(provider="anthropic")).status()
    assert st.connection == "disconnected"
    assert "ANTHROPIC_API_KEY" in (st.fix or "")


def test_openai_local_endpoint_needs_no_key():
    s = _s(provider="openai", openai_base_url="http://localhost:1234/v1")
    st = make_provider(s).status()
    assert s.has_api_key is True
    assert st.connection == "connected"
