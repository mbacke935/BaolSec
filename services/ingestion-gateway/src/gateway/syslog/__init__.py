"""Réception Syslog sur TCP/TLS (RFC 5425), port 6514.

- Authentification : certificat client obligatoire, signé par l'AC des sources ; son empreinte
  SHA-256 désigne la source (config.source_credentials.cert_fingerprint).
- Découpage : comptage d'octets (RFC 5425 / RFC 6587 « octet-counting ») ; le découpage par
  fin de ligne est aussi accepté pour les émetteurs qui ne savent pas faire autrement.
- Le contenu n'est pas interprété ici : RFC 5424 ou format BSD, c'est la normalisation qui parse.
- Syslog n'a pas d'accusé applicatif : si le broker ne répond pas, la passerelle cesse de lire la
  connexion (sans rien perdre de ce qu'elle a déjà lu) et réessaie. TCP ralentit alors l'émetteur,
  dont le relais garde les messages dans sa file persistante (C3 4.3, C7).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import ssl
from pathlib import Path

from baolsec_common.messaging import BrokerUnavailable

from .. import metrics
from ..publisher import RawEventPublisher
from ..rate_limit import RateLimiter
from ..sources_cache import Source, SourcesCache
from ..validation import build_raw_event, utc_now

log = logging.getLogger(__name__)
T = "syslog"
MAX_LENGTH_DIGITS = 10


class FrameTooLong(Exception):
    pass


async def read_frame(reader: asyncio.StreamReader, max_bytes: int) -> bytes | None:
    """Lit une trame ; None en fin de connexion. Lève FrameTooLong après avoir consommé la trame."""
    first = await reader.read(1)
    if not first:
        return None
    if first.isdigit():                                  # comptage d'octets : « LEN SP MSG »
        digits = first
        while True:
            c = await reader.readexactly(1)
            if c == b" ":
                break
            if not c.isdigit() or len(digits) >= MAX_LENGTH_DIGITS:
                raise ValueError("en-tête de longueur invalide")
            digits += c
        length = int(digits)
        if length > max_bytes:
            remaining = length
            while remaining:
                chunk = await reader.read(min(remaining, 65536))
                if not chunk:
                    raise asyncio.IncompleteReadError(b"", remaining)
                remaining -= len(chunk)
            raise FrameTooLong(length)
        return await reader.readexactly(length)
    line = first                                         # découpage par fin de ligne
    try:
        line += await reader.readuntil(b"\n")
    except asyncio.IncompleteReadError as exc:           # fin de connexion sans fin de ligne
        line += exc.partial
    except asyncio.LimitOverrunError:                    # ligne plus longue que le tampon : on la jette
        while True:
            try:
                await reader.readuntil(b"\n")
                break
            except asyncio.LimitOverrunError as exc:
                await reader.readexactly(exc.consumed)
            except asyncio.IncompleteReadError:
                break
        raise FrameTooLong("ligne")
    if len(line) > max_bytes:
        raise FrameTooLong(len(line))
    return line.rstrip(b"\r\n")


def tls_context(cert: Path, key: Path, client_ca: Path) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(cert, key)
    ctx.load_verify_locations(client_ca)
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


def peer_fingerprint(writer: asyncio.StreamWriter) -> str | None:
    ssl_obj = writer.get_extra_info("ssl_object")
    der = ssl_obj.getpeercert(binary_form=True) if ssl_obj else None
    return hashlib.sha256(der).hexdigest() if der else None


class SyslogServer:
    def __init__(self, cache: SourcesCache, limiter: RateLimiter, publisher: RawEventPublisher,
                 max_event_chars: int, idle_timeout_s: float):
        self._cache = cache
        self._limiter = limiter
        self._publisher = publisher
        self._max_bytes = max_event_chars * 4            # borne en octets (UTF-8) ; la limite en caractères est vérifiée après
        self._max_chars = max_event_chars
        self._idle = idle_timeout_s

    async def _publish_until_stored(self, event: dict, source: Source) -> None:
        delay = 0.5
        while True:
            try:
                dup = await self._publisher.publish_one(event)
                metrics.EVENTS.labels(source.id, T, "duplicate" if dup else "stored").inc()
                return
            except BrokerUnavailable as exc:
                log.warning("broker indisponible, lecture Syslog suspendue %.1fs : %s", delay, exc)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 10.0)

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        fingerprint = peer_fingerprint(writer)
        source = self._cache.by_fingerprint(fingerprint) if fingerprint else None
        if source is None:
            metrics.REJECTIONS.labels(T, "unauthenticated").inc()
            log.warning("connexion Syslog refusée de %s : certificat inconnu ou révoqué", peer)
            writer.close()
            return
        metrics.SYSLOG_CONNECTIONS.inc()
        try:
            while True:
                # Une révocation prend effet au rafraîchissement suivant du cache, y compris en cours de connexion.
                if self._cache.by_fingerprint(fingerprint) is None:
                    metrics.REJECTIONS.labels(T, "revoked").inc()
                    log.warning("source %s révoquée ou cache périmé : connexion fermée", source.name)
                    break
                try:
                    frame = await asyncio.wait_for(read_frame(reader, self._max_bytes), self._idle)
                except FrameTooLong as exc:
                    metrics.EVENTS.labels(source.id, T, "rejected").inc()
                    metrics.REJECTIONS.labels(T, "too_large").inc()
                    log.warning("message Syslog trop long (%s octets) de %s ignoré", exc, source.name)
                    continue
                if frame is None:
                    break
                text = frame.decode("utf-8", errors="replace").strip()
                if not text or len(text) > self._max_chars:
                    metrics.EVENTS.labels(source.id, T, "rejected").inc()
                    metrics.REJECTIONS.labels(T, "empty" if not text else "too_large").inc()
                    continue
                await self._limiter.acquire(source.id, 1)
                event = build_raw_event(source, T, utc_now(), "text", text)
                await self._publish_until_stored(event, source)
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, ConnectionError, ValueError, ssl.SSLError) as exc:
            log.info("connexion Syslog de %s terminée : %s", source.name, type(exc).__name__)
        finally:
            metrics.SYSLOG_CONNECTIONS.dec()
            writer.close()

    async def start(self, host: str, port: int, ctx: ssl.SSLContext) -> asyncio.Server:
        return await asyncio.start_server(self.handle, host, port, ssl=ctx, limit=self._max_bytes + 1024)
