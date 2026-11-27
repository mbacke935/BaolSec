"""Protection de l'API (ES-05, C3 4.6) : en-têtes de sécurité, taille maximale, limitation de débit.

Middleware ASGI pur (pas de BaseHTTPMiddleware) : il s'applique avant tout traitement de route.

- En-têtes : nosniff, refus d'intégration en cadre, pas de référent, CSP minimale (l'API ne
  sert que du JSON), HSTS (ignoré par les navigateurs sur HTTP, actif derrière TLS).
- Taille : Content-Length déclaré au-delà de la limite → 413 ; corps transmis par morceaux
  au-delà de la limite → 413 également.
- Débit : seau à jetons par adresse cliente ; plus strict sur POST /auth/login (attaque par
  essais successifs). Dépassement → 429 avec Retry-After. L'état est en mémoire : avec
  plusieurs instances de l'API, la limite s'applique par instance (limite documentée).
"""
from __future__ import annotations

import json
import math
import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
    (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
    (b"cross-origin-resource-policy", b"same-site"),
    (b"permissions-policy", b"geolocation=(), camera=(), microphone=()"),
    (b"cache-control", b"no-store"),
]
# Pages de documentation (mode debug) : elles chargent leurs propres scripts.
_DOCS = ("/docs", "/redoc", "/openapi.json")
_EXEMPT = ("/health", "/metrics")


class TokenBucket:
    def __init__(self, per_minute: int, burst: int | None = None):
        self.rate = per_minute / 60.0
        self.capacity = float(burst or per_minute)
        self._state: dict[str, tuple[float, float]] = {}

    def take(self, key: str, now: float | None = None) -> float:
        """0 si la requête passe ; sinon le délai d'attente en secondes."""
        now = time.monotonic() if now is None else now
        tokens, last = self._state.get(key, (self.capacity, now))
        tokens = min(self.capacity, tokens + (now - last) * self.rate)
        if tokens >= 1.0:
            self._state[key] = (tokens - 1.0, now)
            if len(self._state) > 50_000:          # borne mémoire : on oublie les plus anciens
                for k in list(self._state)[:10_000]:
                    self._state.pop(k, None)
            return 0.0
        self._state[key] = (tokens, now)
        return (1.0 - tokens) / self.rate


class _TooLarge(Exception):
    pass


async def _json(send: Send, status: int, detail: str, headers: list[tuple[bytes, bytes]] | None = None) -> None:
    body = json.dumps({"detail": detail}, ensure_ascii=False).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
                + SECURITY_HEADERS + (headers or [])})
    await send({"type": "http.response.body", "body": body})


class SecurityMiddleware:
    def __init__(self, app: ASGIApp, *, max_body_bytes: int = 1_048_576,
                 rate_per_minute: int = 600, login_per_minute: int = 10) -> None:
        self.app = app
        self.max_body = max_body_bytes
        self.general = TokenBucket(rate_per_minute)
        self.login = TokenBucket(login_per_minute, burst=login_per_minute)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope.get("path", "")
        method: str = scope.get("method", "GET")
        client = scope.get("client")
        ip = client[0] if client else "inconnu"

        if not path.startswith(_EXEMPT):
            bucket = self.login if (method == "POST" and path.endswith("/auth/login")) else self.general
            wait = bucket.take(f"{ip}|{'login' if bucket is self.login else 'api'}")
            if wait > 0:
                await _json(send, 429, "Trop de requêtes : réessayez plus tard.",
                            [(b"retry-after", str(max(1, math.ceil(wait))).encode())])
                return

        headers = dict(scope.get("headers") or [])
        declared = headers.get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_body:
            await _json(send, 413, f"Requête trop volumineuse (maximum {self.max_body} octets).")
            return

        received = 0
        started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body:
                    raise _TooLarge()
            return message

        add_headers = not path.startswith(_DOCS)

        async def send_with_headers(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                if add_headers:
                    existing = {k.lower() for k, _ in message.get("headers", [])}
                    message["headers"] = list(message.get("headers", [])) + [
                        (k, v) for k, v in SECURITY_HEADERS if k not in existing
                    ]
            await send(message)

        try:
            await self.app(scope, limited_receive, send_with_headers)
        except _TooLarge:
            if not started:
                await _json(send, 413, f"Requête trop volumineuse (maximum {self.max_body} octets).")
