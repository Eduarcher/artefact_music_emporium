import json
from collections.abc import AsyncIterator
from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessageChunk, BaseMessage, ToolMessage
from langchain_core.tools import BaseTool

STATUS_THINKING = "thinking"
STATUS_CONSULTING_DATA = "consulting_data"
STATUS_CONSULTING_KNOWLEDGE = "consulting_knowledge"
STATUS_PREPARING_RESPONSE = "preparing_response"

_KNOWLEDGE_TOOL = "search_knowledge"
_DEBUG_RESULT_MAX_CHARS = 2000


def _status_for_tool(tool_name: str) -> str:
    return STATUS_CONSULTING_KNOWLEDGE if tool_name == _KNOWLEDGE_TOOL else STATUS_CONSULTING_DATA


def _extract_text(content: Any) -> str:
    """Return the human-readable text carried by a tool result.

    Tool results arrive either as a plain string or as a list of content
    blocks (e.g. ``[{"type": "text", "text": "..."}]``) produced by the MCP
    adapter. Unwrap the text blocks instead of leaking the raw repr.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
            elif isinstance(item, str):
                parts.append(item)
            else:
                parts.append(str(item))
        return "\n".join(parts)
    if isinstance(content, dict):
        return json.dumps(content, ensure_ascii=False)
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
    current_ai: AIMessageChunk | None = None
    seen_tool = False
    pending_answer: list[str] = []

    async for chunk, _metadata in graph.astream(
        {"messages": history}, stream_mode="messages", config=config
    ):
        if isinstance(chunk, ToolMessage):
            # Any text emitted before the first tool call is the model narrating
            # its plan, not part of the answer. Discard it so the narration (and
            # its trailing colon, which Chainlit's markdown directive parser
            # would mangle) never reaches the customer.
            seen_tool = True
            pending_answer.clear()

            # The AI message that requested the tool is now complete: its tool
            # calls carry the full arguments (streamed chunks only had partial
            # args), so emit the debug step here rather than on the first chunk.
            if current_ai is not None and current_ai.tool_calls:
                for tool_call in current_ai.tool_calls:
                    name = tool_call.get("name")
                    if not name:
                        continue
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
            current_ai = None

            if debug:
                yield {
                    "type": "debug",
                    "event": "tool_result",
                    "id": chunk.tool_call_id or "",
                    "tool": chunk.name or "",
                    "content": _extract_text(chunk.content)[:_DEBUG_RESULT_MAX_CHARS],
                }
            continue

        if isinstance(chunk, AIMessageChunk):
            current_ai = current_ai + chunk if current_ai is not None else chunk

            if chunk.tool_calls:
                for tool_call in chunk.tool_calls:
                    name = tool_call.get("name")
                    if not name:
                        continue
                    status = _status_for_tool(name)
                    if status not in emitted_statuses:
                        emitted_statuses.add(status)
                        yield {"type": "status", "status": status}
                continue

            content = chunk.content
            if isinstance(content, str) and content:
                if seen_tool:
                    if not answer_started:
                        answer_started = True
                        yield {"type": "status", "status": STATUS_PREPARING_RESPONSE}
                    yield {"type": "token", "content": content}
                    answer_parts.append(content)
                else:
                    # No tool has run yet, so this text may still be narration
                    # followed by a tool call. Buffer it until we know.
                    pending_answer.append(content)

    # Direct answer that never called a tool: flush the buffered content as the
    # final answer.
    for content in pending_answer:
        if not answer_started:
            answer_started = True
            yield {"type": "status", "status": STATUS_PREPARING_RESPONSE}
        yield {"type": "token", "content": content}
        answer_parts.append(content)

    yield {"type": "done", "content": "".join(answer_parts)}
