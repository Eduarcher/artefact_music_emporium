from collections.abc import AsyncIterator
from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessageChunk, BaseMessage, ToolMessage
from langchain_core.tools import BaseTool

STATUS_THINKING = "thinking"
STATUS_CONSULTING_DATA = "consulting_data"
STATUS_CONSULTING_POLICIES = "consulting_policies"
STATUS_PREPARING_RESPONSE = "preparing_response"

_POLICY_TOOL = "search_policies"
_DEBUG_RESULT_MAX_CHARS = 2000


def _status_for_tool(tool_name: str) -> str:
    return STATUS_CONSULTING_POLICIES if tool_name == _POLICY_TOOL else STATUS_CONSULTING_DATA


def _as_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    return str(content)


async def stream_turn(
    *,
    model: BaseChatModel,
    tools: list[BaseTool],
    system_prompt: str,
    history: list[BaseMessage],
    recursion_limit: int,
    debug: bool = False,
) -> AsyncIterator[dict[str, Any]]:
    """Run one agent turn over the conversation ``history``.

    ``history`` is the persisted transcript and already ends with the current
    user message, so no message is appended here.
    """
    graph = create_agent(model=model, tools=tools, system_prompt=system_prompt)
    config = {"recursion_limit": recursion_limit}

    yield {"type": "status", "status": STATUS_THINKING}

    emitted_statuses: set[str] = set()
    emitted_tool_calls: set[str] = set()
    answer_started = False
    answer_parts: list[str] = []

    async for chunk, _metadata in graph.astream(
        {"messages": history}, stream_mode="messages", config=config
    ):
        if isinstance(chunk, ToolMessage):
            if debug:
                yield {
                    "type": "debug",
                    "event": "tool_result",
                    "id": chunk.tool_call_id or "",
                    "tool": chunk.name or "",
                    "content": _as_text(chunk.content)[:_DEBUG_RESULT_MAX_CHARS],
                }
            continue

        if isinstance(chunk, AIMessageChunk):
            if chunk.tool_calls:
                for tool_call in chunk.tool_calls:
                    name = tool_call.get("name")
                    if not name:
                        continue
                    status = _status_for_tool(name)
                    if status not in emitted_statuses:
                        emitted_statuses.add(status)
                        yield {"type": "status", "status": status}
                    call_id = tool_call.get("id") or name
                    if debug and call_id not in emitted_tool_calls:
                        emitted_tool_calls.add(call_id)
                        yield {
                            "type": "debug",
                            "event": "tool_call",
                            "id": call_id,
                            "tool": name,
                            "args": tool_call.get("args"),
                        }
                continue

            content = chunk.content
            if isinstance(content, str) and content:
                if not answer_started:
                    answer_started = True
                    yield {"type": "status", "status": STATUS_PREPARING_RESPONSE}
                yield {"type": "token", "content": content}
                answer_parts.append(content)

    yield {"type": "done", "content": "".join(answer_parts)}
