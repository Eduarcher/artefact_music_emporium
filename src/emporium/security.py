import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

_PURPOSE = "mcp-customer-context"


class SecurityError(Exception):
    """Raised when an inbound signed context cannot be trusted."""


@dataclass(frozen=True)
class CustomerContext:
    customer_id: int
    session_id: str
    expires_at: int


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _sign(secret: str, payload_b64: str) -> str:
    digest = hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).digest()
    return _b64url_encode(digest)


def sign_customer_token(
    secret: str, *, customer_id: int, session_id: str, ttl_seconds: int
) -> str:
    expires_at = int(time.time()) + ttl_seconds
    payload = {
        "purpose": _PURPOSE,
        "customer_id": customer_id,
        "session_id": session_id,
        "exp": expires_at,
    }
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signature = _sign(secret, payload_b64)
    return f"{payload_b64}.{signature}"


def verify_customer_token(secret: str, token: str) -> CustomerContext:
    try:
        payload_b64, signature = token.split(".", 1)
    except ValueError as exc:
        raise SecurityError("malformed token") from exc

    expected = _sign(secret, payload_b64)
    if not hmac.compare_digest(expected, signature):
        raise SecurityError("invalid signature")

    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except (ValueError, json.JSONDecodeError) as exc:
        raise SecurityError("invalid payload") from exc

    if payload.get("purpose") != _PURPOSE:
        raise SecurityError("unexpected token purpose")

    expires_at = int(payload.get("exp", 0))
    if expires_at < int(time.time()):
        raise SecurityError("token expired")

    try:
        customer_id = int(payload["customer_id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SecurityError("missing customer_id") from exc

    return CustomerContext(
        customer_id=customer_id,
        session_id=str(payload.get("session_id", "")),
        expires_at=expires_at,
    )
