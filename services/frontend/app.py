import json
import os

import chainlit as cl
import httpx
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from chainlit.input_widget import Select
from starlette.datastructures import Headers

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
CHAINLIT_DB_URL = os.environ.get("CHAINLIT_DB_URL", "")
SHOW_AGENT_STEPS = os.environ.get("SHOW_AGENT_STEPS", "false").lower() in {"1", "true", "yes"}

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
]

STATUS_LABELS = {
    "thinking": "Pensando...",
    "consulting_data": "Consultando os dados do atendimento...",
    "consulting_policies": "Consultando as políticas da loja...",
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


async def _fetch_models() -> tuple[list[tuple[str, str]], str]:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{BACKEND_URL}/api/config")
        resp.raise_for_status()
        data = resp.json()
    return [(m["id"], m["label"]) for m in data["models"]], data["default_model"]


def _model_choice(model_id: str, label: str) -> str:
    return f"{label} | {model_id}"


def _parse_model_choice(value: str) -> str:
    return value.rsplit(" | ", 1)[-1].strip()


async def _create_session(customer_id: int, model: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{BACKEND_URL}/api/sessions", json={"customer_id": customer_id, "model": model}
        )
        resp.raise_for_status()
        return resp.json()


def _first_name(full_name: str) -> str:
    return full_name.split()[0] if full_name else "cliente"


async def _greet(customer_name: str) -> None:
    await cl.Message(
        content=(
            f"Olá, {_first_name(customer_name)}! Sou o assistente virtual da "
            "Empório da Música. Como posso ajudar?"
        )
    ).send()


async def _create_and_greet(customer_id: int, model: str) -> None:
    try:
        session = await _create_session(customer_id, model)
    except httpx.HTTPError:
        await cl.Message(content="Não foi possível conectar ao backend.").send()
        return

    cl.user_session.set("session_id", session["session_id"])
    cl.user_session.set("customer_name", session["customer"]["name"])
    await _greet(session["customer"]["name"])


@cl.on_chat_start
async def on_chat_start() -> None:
    models, default_model = await _fetch_models()
    model_values = [_model_choice(model_id, label) for model_id, label in models]
    default_index = next(
        (i for i, (model_id, _) in enumerate(models) if model_id == default_model), 0
    )

    settings = await cl.ChatSettings(
        [
            Select(
                id="customer",
                label="Cliente (simulação)",
                values=[f"{c['id']} | {c['name']}" for c in FIXTURE_CUSTOMERS],
                initial_index=0,
            ),
            Select(
                id="model",
                label="Modelo",
                values=model_values,
                initial_index=default_index,
            ),
        ]
    ).send()

    await _apply_settings(settings)


@cl.on_chat_resume
async def on_chat_resume(thread) -> None:
    """Restore a previously persisted conversation.

    The bound backend session and customer name are read back from the persisted
    Chainlit user session, so no new session is created on reload.
    """
    session_id = cl.user_session.get("session_id")
    customer_name = cl.user_session.get("customer_name")
    if session_id and customer_name:
        await _greet(customer_name)
        return

    settings = cl.user_session.get("chat_settings")
    if settings:
        await _apply_settings(settings)


@cl.on_settings_update
async def on_settings_update(settings) -> None:
    await _apply_settings(settings)


async def _apply_settings(settings) -> None:
    customer_label = settings["customer"]
    customer_id = int(customer_label.split("|")[0].strip())
    model = _parse_model_choice(settings["model"])
    await _create_and_greet(customer_id, model)


@cl.on_message
async def on_message(message: cl.Message) -> None:
    session_id = cl.user_session.get("session_id")
    if not session_id:
        await cl.Message(content="Selecione um cliente nas configurações para começar.").send()
        return

    answer = cl.Message(content="")
    await answer.send()

    step = None
    if SHOW_AGENT_STEPS:
        step = cl.Step(name=STATUS_LABELS["thinking"], type="run")
        await step.send()

    current_event = None
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{BACKEND_URL}/api/sessions/{session_id}/messages",
                json={"content": message.content},
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("event:"):
                        current_event = line[len("event:"):].strip()
                    elif line.startswith("data:"):
                        payload = json.loads(line[len("data:"):].strip())
                        if current_event == "status" and step is not None:
                            step.name = STATUS_LABELS.get(payload["status"], payload["status"])
                            await step.update()
                        elif current_event == "token":
                            await answer.stream_token(payload["content"])
                        elif current_event == "error":
                            await answer.stream_token("\n\nDesculpe, ocorreu um erro.")
    except httpx.HTTPError:
        await answer.stream_token("\n\nNão foi possível conectar ao backend.")

    if step is not None:
        step.name = "Concluído"
        await step.update()
    await answer.update()
