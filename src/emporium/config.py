from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://emporium:emporium@db:5432/emporium"
    # Optional dedicated read-only URL for the MCP operational-data tools.
    mcp_database_url: str = ""

    # Ollama (generation gateway via LiteLLM and embeddings)
    ollama_base_url: str = "http://ollama:11434"
    embedding_model: str = "bge-m3"
    embedding_dim: int = 1024

    # Model allowlist exposed to the frontend. Comma-separated LiteLLM model ids.
    default_model: str = "ollama/qwen3.5:9b"
    model_allowlist: str = "ollama/qwen3.5:9b,ollama/llama3.2"

    # MCP server (operational-data tool boundary)
    mcp_url: str = "http://mcp:8000/mcp"
    mcp_shared_secret: str = "change-me-in-production"
    mcp_context_ttl_seconds: int = 300

    # Policy retrieval
    policy_similarity_threshold: float = 0.5
    policy_top_k: int = 4

    # Agent
    agent_max_iterations: int = 8
    prompt_version: str = "v1"

    # Local paths
    raw_data_dir: Path = PROJECT_ROOT / "data" / "raw"
    prompts_dir: Path = PROJECT_ROOT / "prompts"

    @property
    def allowed_models(self) -> list[str]:
        return [m.strip() for m in self.model_allowlist.split(",") if m.strip()]

    @property
    def mcp_db_url(self) -> str:
        return self.mcp_database_url or self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
