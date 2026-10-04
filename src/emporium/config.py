import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_project_root(start: Path) -> Path:
    """Locate the repository root by walking up to the nearest pyproject.toml.

    This works both for editable installs (source tree) and for the
    non-editable install used by the Docker image, where ``__file__`` lives
    under site-packages and is not next to the data/prompts directories.
    """
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return Path.cwd()


PROJECT_ROOT = Path(os.environ.get("EMPORIUM_ROOT", _find_project_root(Path(__file__).resolve())))


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
    ollama_num_ctx: int = 4096
    # Reasoning/thinking mode for thinking-capable local models. "false" answers
    # directly (fast); "true" enables it; "low"/"medium"/"high" set intensity;
    # "none" uses the model default.
    ollama_reasoning: str = "false"
    # Upper bound on generated tokens, to avoid runaway generation.
    ollama_num_predict: int = 512

    # Local model allowlist exposed to the frontend. Comma-separated LiteLLM model ids.
    default_model: str = "ollama/qwen3.5:4b"
    model_allowlist: str = "ollama/qwen3.5:4b"

    # Hosted providers. Anthropic models are offered in the UI only when a key is set.
    anthropic_api_key: str = ""
    anthropic_models: str = "anthropic/claude-haiku-4-5,anthropic/claude-sonnet-5-5"

    # MCP server (operational-data tool boundary)
    mcp_url: str = "http://mcp:8000/mcp"
    mcp_shared_secret: str = "change-me-in-production"
    mcp_context_ttl_seconds: int = 300
    # Host headers accepted by the MCP HTTP transport (DNS-rebinding protection).
    mcp_allowed_hosts: str = "mcp:*,localhost:*,127.0.0.1:*,[::1]:*"

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
        """Locally served models, always available without credentials."""
        return [m.strip() for m in self.model_allowlist.split(",") if m.strip()]

    @property
    def hosted_models(self) -> list[str]:
        """Hosted provider models, offered only when the provider key is configured."""
        if not self.anthropic_api_key:
            return []
        return [m.strip() for m in self.anthropic_models.split(",") if m.strip()]

    @property
    def available_models(self) -> list[str]:
        """All models selectable through the admin UI."""
        return [*self.allowed_models, *self.hosted_models]

    @property
    def reasoning_mode(self) -> bool | str | None:
        """Map the ``ollama_reasoning`` setting to ChatOllama's ``reasoning`` value."""
        value = self.ollama_reasoning.strip().lower()
        if value in {"false", "0", "no", "off", ""}:
            return False
        if value in {"true", "1", "yes", "on"}:
            return True
        if value == "none":
            return None
        return value

    @property
    def mcp_db_url(self) -> str:
        return self.mcp_database_url or self.database_url

    @property
    def allowed_mcp_hosts(self) -> list[str]:
        return [h.strip() for h in self.mcp_allowed_hosts.split(",") if h.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
