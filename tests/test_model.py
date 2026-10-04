from emporium.agent.model import build_model


def test_build_model_applies_reasoning_override() -> None:
    """The per-request reasoning override wins over the configured default."""
    model = build_model("ollama/qwen3.5:4b", reasoning=True)

    assert model.reasoning is True


def test_build_model_reasoning_defaults_to_settings() -> None:
    model = build_model("ollama/qwen3.5:4b", reasoning=False)

    assert model.reasoning is False
