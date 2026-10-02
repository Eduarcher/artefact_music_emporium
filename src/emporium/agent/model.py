from langchain_core.language_models.chat_models import BaseChatModel
from langchain_litellm import ChatLiteLLM
from langchain_ollama import ChatOllama

from emporium.config import get_settings

_OLLAMA_PREFIX = "ollama/"


def build_model(model_id: str | None = None) -> BaseChatModel:
    settings = get_settings()
    model = model_id or settings.default_model
    if model not in settings.allowed_models:
        raise ValueError(f"Model '{model}' is not in the configured allowlist")

    if model.startswith(_OLLAMA_PREFIX):
        return ChatOllama(
            model=model.removeprefix(_OLLAMA_PREFIX),
            base_url=settings.ollama_base_url,
            temperature=0,
            num_ctx=8192,
        )

    return ChatLiteLLM(model=model, temperature=0, max_retries=2)
