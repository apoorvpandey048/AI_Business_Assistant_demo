"""Provider strategies for the LLM layer (sprint §13).

`make_provider(settings)` returns the right `LLMProvider` for the resolved provider:
  openai → OpenAIProvider · ollama → OllamaProvider · anthropic → AnthropicProvider
Provider differences end here; the rest of the app speaks one `generate()` contract.
"""
from __future__ import annotations

from app.config import Settings
from app.llm.providers.anthropic_provider import AnthropicProvider
from app.llm.providers.base import LLMProvider
from app.llm.providers.ollama_provider import OllamaProvider
from app.llm.providers.openai_provider import OpenAIProvider

__all__ = ["LLMProvider", "OpenAIProvider", "OllamaProvider",
           "AnthropicProvider", "make_provider", "PROVIDER_CATALOG", "DEPLOYMENT_MODE"]


# UI-facing provider metadata (sprint §14). `deployment_mode` is INFORMATIONAL — it sets
# expectations in Settings; it never gates which provider can be selected.
DEPLOYMENT_MODE: dict[str, str] = {
    "openai": "Production Recommended",
    "ollama": "Private / Local Deployment",
    "anthropic": "Advanced Configuration",
}

PROVIDER_CATALOG: dict[str, dict[str, str]] = {
    "openai": {
        "label": "OpenAI",
        "transport": "openai-compatible",
        "deployment_mode": DEPLOYMENT_MODE["openai"],
        "description": "Hosted GPT models (gpt-4o + gpt-4o-mini). Best quality with the "
                       "least setup — needs an OPENAI_API_KEY. Recommended for production.",
    },
    "ollama": {
        "label": "Ollama (local)",
        "transport": "openai-compatible",
        "deployment_mode": DEPLOYMENT_MODE["ollama"],
        "description": "Runs qwen2.5:7b-instruct entirely on your own hardware — fully "
                       "private, no API key, no data leaves the machine. Requires Ollama.",
    },
    "anthropic": {
        "label": "Anthropic",
        "transport": "anthropic",
        "deployment_mode": DEPLOYMENT_MODE["anthropic"],
        "description": "Claude via the Anthropic API. Supported for advanced / "
                       "bring-your-own-key deployments; needs an ANTHROPIC_API_KEY.",
    },
}


def make_provider(settings: Settings) -> LLMProvider:
    p = settings.resolved_provider
    if p == "anthropic":
        return AnthropicProvider(settings)
    if p == "ollama":
        return OllamaProvider(settings)
    return OpenAIProvider(settings)
