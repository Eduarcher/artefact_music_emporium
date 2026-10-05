import json
import os
from typing import Any

import chainlit as cl
import httpx
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from chainlit.input_widget import Select, Switch
from starlette.datastructures import Headers

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
CHAINLIT_DB_URL = os.environ.get("CHAINLIT_DB_URL", "")

DEBUG_DEFAULT = os.environ.get("SHOW_AGENT_STEPS", "true").lower() in {"1", "true", "yes"}

ADMIN_USER = os.environ.get("CHAINLIT_ADMIN_USER", "admin")

FIXTURE_CUSTOMERS = [
    {"id": 1, "name": "Lucas Mendes da Silva"},
    {"id": 2, "name": "Ana Carolina Ferreira"},
    {"id": 3, "name": "Pedro Henrique Oliveira"},
    {"id": 4, "name": "Mariana Costa Santos"},
    {"id": 5, "name": "Rafael Augusto Pereira"},
    {"id": 6, "name": "Juliana Almeida Rodrigues"},
    {"id": 7, "name": "Thiago Barbosa Lima"},
    {"id": 8, "name": "Fernanda Ribeiro Souza"},
    {"id": 9, "name": "Gabriel Santos Araújo"},
    {"id": 10, "name": "Camila Duarte Nascimento"},
    {"id": 11, "name": "Bruno Carvalho Martins"},
    {"id": 12, "name": "Isabela Moreira Cunha"},
    {"id": 13, "name": "Diego Fernandes Castro"},
    {"id": 14, "name": "Letícia Gonçalves Rocha"},
    {"id": 15, "name": "Matheus Ramos Correia"},
    {"id": 16, "name": "Patrícia Vieira Cardoso"},
    {"id": 17, "name": "Gustavo Teixeira Nunes"},
    {"id": 18, "name": "Aline Borges Monteiro"},
    {"id": 19, "name": "Rodrigo Silva"},
    {"id": 20, "name": "Amanda Lima"},
    {"id": 21, "name": "Felipe Gomes"},
    {"id": 22, "name": "Beatriz Rocha"},
    {"id": 23, "name": "Marcelo Dias"},
    {"id": 24, "name": "Camila Alves"},
    {"id": 25, "name": "Thiago Costa"},
    {"id": 26, "name": "Larissa Mendes"},
    {"id": 27, "name": "Bruno Carvalho"},
    {"id": 28, "name": "Juliana Castro"},
    {"id": 29, "name": "Leonardo Santos"},
    {"id": 30, "name": "Natália Martins"},
    {"id": 31, "name": "Joao Silva"},
    {"id": 32, "name": "Maria Oliveira"},
    {"id": 33, "name": "Carlos Souza"},
    {"id": 34, "name": "Ana Costa"},
    {"id": 35, "name": "Pedro Santos"},
    {"id": 36, "name": "Paula Lima"},
    {"id": 37, "name": "Lucas Pereira"},
    {"id": 38, "name": "Julia Carvalho"},
    {"id": 39, "name": "Marcos Rodrigues"},
    {"id": 40, "name": "Fernanda Almeida"},
    {"id": 41, "name": "Rafael Alves"},
    {"id": 42, "name": "Camila Ribeiro"},
    {"id": 43, "name": "Bruno Martins"},
    {"id": 44, "name": "Leticia Gomes"},
    {"id": 45, "name": "Thiago Dias"},
    {"id": 46, "name": "Amanda Rocha"},
    {"id": 47, "name": "Diego Castro"},
    {"id": 48, "name": "Beatriz Mendes"},
    {"id": 49, "name": "Felipe Nunes"},
    {"id": 50, "name": "Mariana Cardoso"},
]

REASONING_VALUES = {
    "off": "Desligado (rápido)",
    "on": "Ligado (reflexivo)",
}

STATUS_LABELS = {
    "thinking": "Pensando...",
    "consulting_data": "Consultando os dados do atendimento...",
    "consulting_knowledge": "Consultando a base de conhecimento...",
    "preparing_response": "Preparando a resposta...",
    "validating_response": "Conferindo a resposta...",
}

if CHAINLIT_DB_URL:

    @cl.data_layer
    def get_data_layer() -> SQLAlchemyDataLayer:
        return SQLAlchemyDataLayer(conninfo=CHAINLIT_DB_URL)

    @cl.header_auth_callback
    async def auto_login(_headers: Headers) -> cl.User | None:
        # Local prototype: sign in automatically as the admin user so the UI can
        # persist and resume conversations without showing a login form.
        return cl.User(identifier=ADMIN_USER, metadata={"role": "admin"})


async def _fetch_models() -> tuple[list[dict], str]:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{BACKEND_URL}/api/config")
        resp.raise_for_status()
        data = resp.json()
    models = [
        {
            "id": m["id"],
            "label": m["label"],
            "supports_reasoning": m.get("supports_reasoning", False),
        }
        for m in data["models"]
    ]
    return models, data["default_model"]


def _model_choice(model: dict) -> str:
    return f"{model['label']} | {model['id']}"


def _model_supports_reasoning(models: list[dict], model_id: str) -> bool:
    for model in models:
        if model["id"] == model_id:
            return bool(model.get("supports_reasoning", False))
    return False


def _parse_model_choice(value: str) -> str:
    return value.rsplit(" | ", 1)[-1].strip()


def _customer_choice(customer: dict) -> str:
    return f"{customer['id']} | {customer['name']}"


def _parse_customer_id(value: str) -> int:
    return int(value.split("|")[0].strip())


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if value is None:
        return default
    return bool(value)


_reasoning_label = {label: key for key, label in REASONING_VALUES.items()}


async def _create_session(customer_id: int, model: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{BACKEND_URL}/api/sessions", json={"customer_id": customer_id, "model": model}
        )
        resp.raise_for_status()
        return resp.json()


def _first_name(full_name: str) -> str:
    return full_name.split()[0] if full_name else "cliente"


async def _send_message(content: str) -> cl.Message:
    """Send a top-level message.

    ``parent_id`` is forced to ``None`` because Chainlit otherwise inherits the
    id of the ephemeral ``on_message``/``on_chat_start`` run step, which is not
    persisted and would orphan the message on resume.
    """
    message = cl.Message(content=content)
    message.parent_id = None
    await message.send()
    return message


async def _greet(customer_name: str) -> None:
    await _send_message(
        f"Olá, {_first_name(customer_name)}! Sou o assistente virtual da "
        "Empório da Música. Como posso ajudar?"
    )


async def _clear_conversation() -> None:
    """Remove every message of the current thread so a new session starts clean."""
    for message in cl.chat_context.get():
        await message.remove()


async def _begin_session(
    *, customer_id: int, model: str, clear: bool, greet: bool
) -> bool:
    """Create a backend session and bind it to this conversation."""
    try:
        session = await _create_session(customer_id, model)
    except httpx.HTTPError:
        await _send_message("Não foi possível conectar ao backend.")
        return False

    if clear:
        await _clear_conversation()

    cl.user_session.set("session_id", session["session_id"])
    cl.user_session.set("customer_id", customer_id)
    cl.user_session.set("customer_name", session["customer"]["name"])
    cl.user_session.set("model", model)

    if greet:
        await _greet(session["customer"]["name"])
    return True


def _settings_payload(settings: dict) -> tuple[int, str, bool, bool]:
    reasoning_label = settings.get("reasoning", REASONING_VALUES["off"])
    reasoning = _reasoning_label.get(reasoning_label, "off") == "on"
    return (
        _parse_customer_id(settings["customer"]),
        _parse_model_choice(settings["model"]),
        _as_bool(settings.get("debug"), DEBUG_DEFAULT),
        reasoning,
    )


def _build_settings(models: list[dict], restored: dict | None = None) -> cl.ChatSettings:
    restored = restored or {}
    model_values = [_model_choice(m) for m in models]
    customer_values = [_customer_choice(c) for c in FIXTURE_CUSTOMERS]
    reasoning_values = list(REASONING_VALUES.values())

    model_value = _first_match(restored.get("model"), model_values, 0)
    model_id = _parse_model_choice(model_value)
    reasoning_enabled = _model_supports_reasoning(models, model_id)

    return cl.ChatSettings(
        [
            Select(
                id="customer",
                label="Cliente (simulação)",
                values=customer_values,
                initial_value=_first_match(restored.get("customer"), customer_values, 0),
            ),
            Select(
                id="model",
                label="Modelo",
                values=model_values,
                initial_value=model_value,
            ),
            Select(
                id="reasoning",
                label="Raciocínio",
                values=reasoning_values,
                initial_value=_first_match(
                    restored.get("reasoning"), reasoning_values, 0
                ),
                disabled=not reasoning_enabled,
            ),
            Switch(
                id="debug",
                label="Modo debug",
                initial=_as_bool(restored.get("debug"), DEBUG_DEFAULT),
            ),
        ]
    )


def _first_match(value: Any, values: list[str], default_index: int) -> str:
    if isinstance(value, str) and value in values:
        return value
    return values[default_index]


@cl.on_chat_start
async def on_chat_start() -> None:
    models, _default_model = await _fetch_models()
    default_index = next(
        (i for i, model in enumerate(models) if model["id"] == _default_model), 0
    )
    restored = {"model": _model_choice(models[default_index])}

    cl.user_session.set("models", models)
    settings = await _build_settings(models, restored).send()

    customer_id, model, debug, reasoning = _settings_payload(settings)
    cl.user_session.set("debug", debug)
    cl.user_session.set("reasoning", reasoning)
    await _begin_session(customer_id=customer_id, model=model, clear=False, greet=True)


@cl.on_chat_resume
async def on_chat_resume(thread) -> None:
    """Restore a previously persisted conversation.

    Chainlit restores ``cl.user_session`` (including the backend session binding)
    from the thread metadata, and re-renders the stored messages. The settings
    widgets are re-sent so the admin sidebar (cogwheel) is available again, and
    no greeting is sent. A session is only created when an older thread lacks a
    binding.
    """
    restored = cl.user_session.get("chat_settings") or {}
    models, _default_model = await _fetch_models()
    cl.user_session.set("models", models)
    await _build_settings(models, restored).send()

    if cl.user_session.get("session_id"):
        cl.user_session.set("debug", _as_bool(restored.get("debug"), DEBUG_DEFAULT))
        cl.user_session.set("reasoning", restored.get("reasoning") == REASONING_VALUES["on"])
        return

    customer_id, model, _debug, _reasoning = _settings_payload({**restored})
    await _begin_session(customer_id=customer_id, model=model, clear=False, greet=False)


@cl.on_settings_edit
async def on_settings_edit(settings: dict) -> None:
    """Re-render the widgets on every live settings change.

    Chainlit has no cross-field reactive settings, so the Raciocínio control's
    disabled state is only recomputed when the widgets are re-emitted. Live
    edits (before Confirm) arrive here, which keeps Raciocínio in sync with the
    selected model without touching the user's current form values.
    """
    models = cl.user_session.get("models") or []
    if models:
        await _build_settings(models, settings).refresh()


@cl.on_settings_update
async def on_settings_update(settings: dict) -> None:
    customer_id, model, debug, reasoning = _settings_payload(settings)
    cl.user_session.set("debug", debug)
    cl.user_session.set("reasoning", reasoning)

    if (
        customer_id == cl.user_session.get("customer_id")
        and model == cl.user_session.get("model")
    ):
        return

    # A new customer or model starts a fresh conversation bound to a new session.
    await _begin_session(customer_id=customer_id, model=model, clear=True, greet=True)


def _debug_value(value: Any) -> tuple[str, str]:
    """Return ``(language, text)`` for a debug value, JSON when it parses."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return "text", value
    if isinstance(value, (dict, list)):
        return "json", json.dumps(value, ensure_ascii=False, indent=2)
    return "text", str(value)


def _render_tool_debug(args: Any, result: Any) -> str:
    """Format a tool call as clearly labeled Entrada/Resultado markdown blocks."""
    args_lang, args_text = _debug_value(args)
    result_lang, result_text = _debug_value(result)
    return (
        f"**Entrada:**\n\n```{args_lang}\n{args_text}\n```\n\n"
        f"**Resultado:**\n\n```{result_lang}\n{result_text}\n```"
    )


async def _render_debug_event(
    payload: dict,
    tool_steps: dict[str, cl.Step],
    tool_args: dict[str, Any],
    parent_id: str | None,
) -> None:
    event = payload.get("event")
    key = payload.get("id") or payload.get("tool") or "tool"

    if event == "tool_call":
        tool_args[key] = payload.get("args") or {}
        step = cl.Step(
            name=payload.get("tool", "tool"),
            type="tool",
            show_input=False,
            parent_id=parent_id,
        )
        await step.send()
        tool_steps[key] = step
    elif event == "tool_result":
        step = tool_steps.get(key)
        if step is None:
            step = cl.Step(
                name=payload.get("tool", "tool"),
                type="tool",
                show_input=False,
                parent_id=parent_id,
            )
            await step.send()
            tool_steps[key] = step
        step.output = _render_tool_debug(tool_args.get(key, {}), payload.get("content", ""))
        await step.update()


@cl.on_message
async def on_message(message: cl.Message) -> None:
    session_id = cl.user_session.get("session_id")
    if not session_id:
        await _send_message("Selecione um cliente nas configurações para começar.")
        return

    debug = _as_bool(cl.user_session.get("debug"), False)
    reasoning = _as_bool(cl.user_session.get("reasoning"), False)

    answer = cl.Message(content="")
    answer.parent_id = None
    await answer.send()

    status_step: cl.Step | None = None
    if debug:
        status_step = cl.Step(
            name=STATUS_LABELS["thinking"], type="run", parent_id=answer.id
        )
        await status_step.send()

    async def _hide_status() -> None:
        nonlocal status_step
        if status_step is not None:
            await status_step.remove()
            status_step = None

    tool_steps: dict[str, cl.Step] = {}
    tool_args: dict[str, Any] = {}
    current_event: str | None = None
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{BACKEND_URL}/api/sessions/{session_id}/messages",
                json={
                    "content": message.content,
                    "debug": debug,
                    "reasoning": reasoning,
                },
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("event:"):
                        current_event = line[len("event:") :].strip()
                    elif line.startswith("data:"):
                        payload: dict[str, Any] = json.loads(line[len("data:") :].strip())
                        if current_event == "status" and status_step is not None:
                            status_step.name = STATUS_LABELS.get(
                                payload["status"], payload["status"]
                            )
                            await status_step.update()
                        elif current_event == "debug":
                            await _render_debug_event(payload, tool_steps, tool_args, answer.id)
                        elif current_event == "token":
                            await _hide_status()
                            await answer.stream_token(payload["content"])
                        elif current_event == "error":
                            await _hide_status()
                            await answer.stream_token("\n\nDesculpe, ocorreu um erro.")
    except httpx.HTTPError:
        await _hide_status()
        await answer.stream_token("\n\nNão foi possível conectar ao backend.")

    await _hide_status()
    await answer.update()
