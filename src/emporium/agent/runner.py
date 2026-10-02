from collections.abc import AsyncIterator
from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessageChunk, BaseMessage, HumanMessage
from langchain_core.tools import BaseTool

STATUS_THINKING = "thinking"
STATUS_CONSULTING_DATA = "consulting_data"
STATUS_CONSULTING_POLICIES = "consulting_policies"
STATUS_PREPARING_RESPONSE = "preparing_response"

_POLICY_TOOL = "search_policies"


def _status_for_tool(tool_name: str) -> str:
    return STATUS_CONSULTING_POLICIES if tool_name == _POLICY_TOOL else STATUS_CONSULTING_DATA


async def stream_turn(
    *,
    model: BaseChatModel,
    tools: list[BaseTool],
    system_prompt: str,
    history: list[BaseMessage],
    user_message: str,
    recursion_limit: int,
) -> AsyncIterator[dict[str, Any]]:
    graph = create_agent(model=model, tools=tools, system_prompt=system_prompt)
    messages = [*history, HumanMessage(content=user_message)]
    config = {"recursion_limit": recursion_limit}

    yield {"type": "status", "status": STATUS_THINKING}

    emitted_statuses: set[str] = set()
    answer_started = False
    answer_parts: list[str] = []

    async for chunk, _metadata in graph.astream(
        {"messages": messages}, stream_mode="messages", config=config
    ):
        if isinstance(chunk, AIMessageChunk):
            if chunk.tool_calls:
                for tool_call in chunk.tool_calls:
                    name = tool_call.get("name")
                    if name:
                        status = _status_for_tool(name)
                        if status not in emitted_statuses:
                            emitted_statuses.add(status)
                            yield {"type": "status", "status": status}
                continue

            content = chunk.content
            if isinstance(content, str) and content:
                if not answer_started:
                    answer_started = True
                    yield {"type": "status", "status": STATUS_PREPARING_RESPONSE}
                yield {"type": "token", "content": content}
                answer_parts.append(content)

    yield {"type": "done", "content": "".join(answer_parts)}
