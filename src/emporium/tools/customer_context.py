from contextvars import ContextVar

from emporium.security import CustomerContext

_customer_context: ContextVar[CustomerContext | None] = ContextVar(
    "mcp_customer_context", default=None
)


def set_customer_context(context: CustomerContext) -> object:
    return _customer_context.set(context)


def get_customer_context() -> CustomerContext:
    context = _customer_context.get()
    if context is None:
        raise PermissionError("No valid backend customer context bound to this call")
    return context
