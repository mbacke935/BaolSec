"""Accès en lecture seule au broker NATS JetStream (C5 GET /dlq, EF-12).

- File de rejet (flux DLQ, contrat dlq_message/v1) : liste paginée du plus récent au plus ancien et
  consultation d'un message par séquence, par lecture directe (aucun consommateur créé, rien n'est
  acquitté ni supprimé : la reprise et la purge restent des opérations d'exploitation, dlq_admin.py).
- Supervision : état des flux (messages, octets) et retard des consommateurs.

La connexion est ouverte à la première utilisation et réutilisée ; si le broker est injoignable,
les routes répondent 503 et le reste de l'API continue de fonctionner.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

log = logging.getLogger("baolsec.broker")

_url = "nats://broker:4222"
_token: str | None = None
_stream = "DLQ"
_nc = None
_lock = asyncio.Lock()


class BrokerUnavailable(Exception):
    pass


def configure(url: str, token: str | None, dlq_stream: str = "DLQ") -> None:
    global _url, _token, _stream
    _url, _token, _stream = url, token or None, dlq_stream


async def _js():
    global _nc
    async with _lock:
        if _nc is None or not _nc.is_connected:
            try:
                import nats

                async def _quiet(_e):
                    return None
                _nc = await asyncio.wait_for(
                    nats.connect(_url, token=_token, allow_reconnect=True, max_reconnect_attempts=-1,
                                 error_cb=_quiet, name="baolsec-api"), 5)
            except Exception as exc:  # noqa: BLE001
                _nc = None
                raise BrokerUnavailable(f"broker injoignable : {type(exc).__name__}") from exc
        return _nc.jetstream()


async def close() -> None:
    global _nc
    if _nc is not None:
        try:
            await _nc.drain()
        except Exception:  # noqa: BLE001
            pass
        _nc = None


def _entry(seq: int, subject: str, data: bytes, full: bool) -> dict[str, Any]:
    text = data.decode("utf-8", "replace")
    try:
        doc = json.loads(text)
    except ValueError:
        doc = {"reason": "message de rejet illisible", "reason_code": "?"}
    item = {
        "seq": seq,
        "subject": subject,
        "service": doc.get("service") or subject.removeprefix("dlq."),
        "reason_code": doc.get("reason_code"),
        "reason": doc.get("reason"),
        "original_stream": doc.get("original_stream"),
        "source_id": doc.get("source_id"),
        "attempts": doc.get("attempts"),
        "failed_at": doc.get("failed_at"),
        "message_id": doc.get("message_id"),
    }
    payload = doc.get("payload")
    if full:
        item["payload"] = payload
        item["payload_encoding"] = doc.get("payload_encoding")
        item["document"] = doc
    else:
        item["payload_preview"] = (payload[:300] + "…") if isinstance(payload, str) and len(payload) > 300 else payload
    return item


async def dlq_summary() -> dict[str, Any]:
    js = await _js()
    try:
        info = await js.stream_info(_stream, subjects_filter="dlq.>")
    except Exception as exc:  # noqa: BLE001
        raise BrokerUnavailable(str(exc)) from exc
    st = info.state
    return {"messages": st.messages, "bytes": st.bytes, "first_seq": st.first_seq, "last_seq": st.last_seq,
            "by_subject": dict(getattr(st, "subjects", None) or {})}


async def dlq_list(limit: int = 50, offset: int = 0, service: str | None = None,
                   reason: str | None = None) -> dict[str, Any]:
    """Messages du plus récent au plus ancien, filtrés par service et motif."""
    summary = await dlq_summary()
    js = await _js()
    items: list[dict[str, Any]] = []
    skipped = 0
    seq = summary["last_seq"]
    scanned = 0
    while seq >= max(1, summary["first_seq"]) and len(items) < limit and scanned < 5000:
        scanned += 1
        try:
            msg = await js.get_msg(_stream, seq)
        except Exception:  # noqa: BLE001 — séquence supprimée (purge ou reprise)
            seq -= 1
            continue
        entry = _entry(msg.seq, msg.subject, msg.data or b"", full=False)
        seq -= 1
        if service and entry["service"] != service:
            continue
        if reason and entry["reason_code"] != reason:
            continue
        if skipped < offset:
            skipped += 1
            continue
        items.append(entry)
    return {"total": summary["messages"], "limit": limit, "offset": offset, "items": items,
            "by_subject": summary["by_subject"]}


async def dlq_get(seq: int) -> dict[str, Any] | None:
    js = await _js()
    try:
        msg = await js.get_msg(_stream, seq)
    except Exception:  # noqa: BLE001
        return None
    if not msg.subject.startswith("dlq."):
        return None
    return _entry(msg.seq, msg.subject, msg.data or b"", full=True)


async def streams_status() -> list[dict[str, Any]]:
    """Flux et retard (messages en attente) de chaque consommateur durable."""
    js = await _js()
    out = []
    for name in ("RAW_EVENTS", "NORMALIZED_EVENTS", "ALERTS", "INCIDENTS", "DLQ"):
        try:
            info = await js.stream_info(name)
        except Exception:  # noqa: BLE001
            out.append({"stream": name, "available": False})
            continue
        consumers = []
        try:
            for c in await js.consumers_info(name):
                consumers.append({"name": c.name, "pending": c.num_pending, "ack_pending": c.num_ack_pending,
                                  "redelivered": c.num_redelivered})
        except Exception:  # noqa: BLE001
            pass
        out.append({"stream": name, "available": True, "messages": info.state.messages,
                    "bytes": info.state.bytes, "consumers": consumers})
    return out
