from langchain_ollama import OllamaEmbeddings

from emporium.config import get_settings


def build_embedder() -> OllamaEmbeddings:
    settings = get_settings()
    return OllamaEmbeddings(model=settings.embedding_model, base_url=settings.ollama_base_url)
