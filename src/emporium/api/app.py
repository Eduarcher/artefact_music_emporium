import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from langchain_mcp_adapters.client import MultiServerMCPClient
from sse_starlette.sse import EventSourceResponse

from emporium.agent.model import build_model
from emporium.agent.prompts import load_system_prompt
from emporium.agent.runner import stream_turn
from emporium.api.schemas import (
    ConfigResponse,
    CreateSessionRequest,
    CreateSessionResponse,
    CustomerInfo,
    MessageRequest,
    ModelInfo,
)
from emporium.config import get_settings
from emporium.db.engine import create_engine, create_session_factory
from emporium.db.init_db import init_db
from emporium.rag.embedder import build_embedder
from emporium.rag.retriever import PolicyRetriever
from emporium.security import sign_customer_token
from emporium.sessions import service as session_service
from emporium.tools.policy_tool import build_policy_tool

logger = logging.getLogger("emporium.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = create_engine()
    await init_db(engine)
    session_factory = create_session_factory(engine)

    embedder = build_embedder()
    retriever = PolicyRetriever(session_factory, embedder)

    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.policy_tool = build_policy_tool(retriever)
    app.state.system_prompt = load_system_prompt()

    yield

    await engine.dispose()


app = FastAPI(title="Empório da Música Agent", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config", response_model=ConfigResponse)
async def config() -> ConfigResponse:
    settings = get_settings()
    models = [ModelInfo(id=m, label=m) for m in settings.allowed_models]
    return ConfigResponse(models=models, default_model=settings.default_model)


@app.post("/api/sessions", response_model=CreateSessionResponse, status_code=201)
async def create_session(body: CreateSessionRequest) -> CreateSessionResponse:
    settings = get_settings()
    session_factory = app.state.session_factory

    if not await session_service.customer_exists(session_factory, body.customer_id):
        raise HTTPException(status_code=404, detail="customer not found")

    model = body.model or settings.default_model
    if model not in settings.allowed_models:
        raise HTTPException(status_code=400, detail="model not allowed")

    session_row = await session_service.create_session(
        session_factory,
        customer_id=body.customer_id,
        model=model,
        prompt_version=settings.prompt_version,
    )
    customer_name = await session_service.get_customer_name(
        session_factory, body.customer_id
    )

    return CreateSessionResponse(
        session_id=session_row.session_id,
        customer=CustomerInfo(id=body.customer_id, name=customer_name or ""),
    )


@app.post("/api/sessions/{session_id}/messages")
async def send_message(session_id: str, body: MessageRequest) -> EventSourceResponse:
    session_factory = app.state.session_factory

    session_row = await session_service.get_session(session_factory, session_id)
    if session_row is None:
        raise HTTPException(status_code=404, detail="session not found")

    await session_service.add_message(
        session_factory, session_id=session_id, role="user", content=body.content
    )

    async def event_stream() -> AsyncIterator[dict]:
        try:
            async for event in _run_turn(session_row, body.content):
                yield event
        except Exception:  # noqa: BLE001
            logger.exception("turn failed for session %s", session_id)
            yield {
                "event": "error",
                "data": json.dumps({"detail": "Não consegui processar sua mensagem."}),
            }

    return EventSourceResponse(event_stream())


async def _run_turn(session_row, user_content: str) -> AsyncIterator[dict]:
    settings = get_settings()
    session_factory = app.state.session_factory

    token = sign_customer_token(
        settings.mcp_shared_secret,
        customer_id=session_row.customer_id,
        session_id=session_row.session_id,
        ttl_seconds=settings.mcp_context_ttl_seconds,
    )

    mcp_client = MultiServerMCPClient(
        {
            "operational": {
                "transport": "streamable_http",
                "url": settings.mcp_url,
                "headers": {"Authorization": f"Bearer {token}"},
            }
        }
    )
    mcp_tools = await mcp_client.get_tools()

    tools = [*mcp_tools, app.state.policy_tool]
    model = build_model(session_row.model)
    history = await session_service.get_transcript(session_factory, session_row.session_id)
    recursion_limit = settings.agent_max_iterations * 2 + 2

    async for event in stream_turn(
        model=model,
        tools=tools,
        system_prompt=app.state.system_prompt,
        history=history,
        user_message=user_content,
        recursion_limit=recursion_limit,
    ):
        if event["type"] == "done":
            await session_service.add_message(
                session_factory,
                session_id=session_row.session_id,
                role="assistant",
                content=event["content"],
            )
            yield {"event": "done", "data": json.dumps({"session_id": session_row.session_id})}
        elif event["type"] == "status":
            yield {"event": "status", "data": json.dumps({"status": event["status"]})}
        elif event["type"] == "token":
            yield {"event": "token", "data": json.dumps({"content": event["content"]})}
