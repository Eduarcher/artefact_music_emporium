from pathlib import Path

from emporium.config import get_settings


def load_system_prompt(version: str | None = None) -> str:
    settings = get_settings()
    prompt_version = version or settings.prompt_version
    path: Path = settings.prompts_dir / f"system_prompt_{prompt_version}.md"
    if not path.exists():
        raise FileNotFoundError(f"System prompt not found: {path}")
    return path.read_text(encoding="utf-8")
