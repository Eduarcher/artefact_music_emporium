import time
from dataclasses import dataclass

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from emporium.config import Settings
from emporium.security import sign_customer_token

# Refresh the token/cached tools slightly before it expires so an in-flight
# tool call is never rejected by the MCP server.
_REFRESH_MARGIN_SECONDS = 30


@dataclass
class _CachedTools:
    tools: list[BaseTool]
    expires_at: float


class MCPToolProvider:
    """Loads and caches the MCP operational-data tools per session.

    The tool schemas are static but the MCP client carries the signed
    customer-context token, so the cache is keyed by ``session_id`` and the
    tools are rebuilt when the token nears expiry. This avoids a full MCP
    handshake on every chat message.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cache: dict[str, _CachedTools] = {}

    async def get_tools(self, *, customer_id: int, session_id: str) -> list[BaseTool]:
        now = time.time()
        self._prune(now)

        cached = self._cache.get(session_id)
        if cached is not None and cached.expires_at - now > _REFRESH_MARGIN_SECONDS:
            return cached.tools

        ttl = self._settings.mcp_context_ttl_seconds
        token = sign_customer_token(
            self._settings.mcp_shared_secret,
            customer_id=customer_id,
            session_id=session_id,
            ttl_seconds=ttl,
        )
        client = MultiServerMCPClient(
            {
                "operational": {
                    "transport": "streamable_http",
                    "url": self._settings.mcp_url,
                    "headers": {"Authorization": f"Bearer {token}"},
                }
            }
        )
        tools = await client.get_tools()
        self._cache[session_id] = _CachedTools(tools=tools, expires_at=now + ttl)
        return tools

    def _prune(self, now: float) -> None:
        expired = [key for key, item in self._cache.items() if item.expires_at <= now]
        for key in expired:
            del self._cache[key]
