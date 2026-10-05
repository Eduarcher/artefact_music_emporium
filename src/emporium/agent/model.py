import litellm
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_litellm import ChatLiteLLM
from langchain_ollama import ChatOllama

from emporium.config import get_settings

_OLLAMA_PREFIX = "ollama/"

# Reasoning models such as claude-sonnet-5-5 only accept temperature=1. Dropping
# unsupported params lets LiteLLM use the model's defaults instead of raising.
litellm.drop_params = True


def build_model(
    model_id: str | None = None, reasoning: bool | str | None = None
) -> BaseChatModel:
    settings = get_settings()
    model = model_id or settings.default_model
    if model not in settings.available_models:
        raise ValueError(f"Model '{model}' is not in the configured allowlist")

    if model.startswith(_OLLAMA_PREFIX):
        return ChatOllama(
            model=model.removeprefix(_OLLAMA_PREFIX),
            base_url=settings.ollama_base_url,
            temperature=0,
            num_ctx=settings.ollama_num_ctx,
            num_predict=settings.ollama_num_predict,
            reasoning=settings.reasoning_mode if reasoning is None else reasoning,
        )

    if model.startswith("anthropic/") and settings.anthropic_api_key:
        return ChatLiteLLM(
            model=model, temperature=0, max_retries=2, api_key=settings.anthropic_api_key
        )

    if model.startswith("anthropic/"):
        raise ValueError(
            f"Model '{model}' requires ANTHROPIC_API_KEY, which is not configured"
        )

    return ChatLiteLLM(model=model, temperature=0, max_retries=2)
