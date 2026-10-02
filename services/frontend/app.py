import json
import os

import chainlit as cl
import httpx
from chainlit.input_widget import Select

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")

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


async def _fetch_models() -> tuple[list[str], str]:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{BACKEND_URL}/api/config")
        resp.raise_for_status()
        data = resp.json()
    return [m["id"] for m in data["models"]], data["default_model"]


async def _create_session(customer_id: int, model: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{BACKEND_URL}/api/sessions", json={"customer_id": customer_id, "model": model}
        )
        resp.raise_for_status()
        return resp.json()


@cl.on_chat_start
async def on_chat_start() -> None:
    models, default_model = await _fetch_models()

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
                values=models,
                initial_index=models.index(default_model) if default_model in models else 0,
            ),
        ]
    ).send()

    await _apply_settings(settings)


@cl.on_settings_update
async def on_settings_update(settings) -> None:
    await _apply_settings(settings)


async def _apply_settings(settings) -> None:
    customer_label = settings["customer"]
    customer_id = int(customer_label.split("|")[0].strip())
    model = settings["model"]

    try:
        session = await _create_session(customer_id, model)
    except httpx.HTTPError:
        await cl.Message(content="Não foi possível conectar ao backend.").send()
        return

    cl.user_session.set("session_id", session["session_id"])
    await cl.Message(
        content=(
            f"Olá! Atendimento simulado como **{session['customer']['name']}** "
            f"(cliente #{customer_id}). Como posso ajudar?"
        )
    ).send()


@cl.on_message
async def on_message(message: cl.Message) -> None:
    session_id = cl.user_session.get("session_id")
    if not session_id:
        await cl.Message(content="Selecione um cliente nas configurações para começar.").send()
        return

    answer = cl.Message(content="")
    await answer.send()

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
                        if current_event == "status":
                            label = STATUS_LABELS.get(payload["status"], payload["status"])
                            step.name = label
                            await step.update()
                        elif current_event == "token":
                            await answer.stream_token(payload["content"])
                        elif current_event == "error":
                            await answer.stream_token("\n\nDesculpe, ocorreu um erro.")
    except httpx.HTTPError:
        await answer.stream_token("\n\nNão foi possível conectar ao backend.")

    step.name = "Concluído"
    await step.update()
    await answer.update()
