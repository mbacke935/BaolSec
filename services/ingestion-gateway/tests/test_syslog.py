"""Découpage des trames Syslog (RFC 5425 / RFC 6587)."""
from __future__ import annotations

import asyncio

import pytest

from gateway.syslog import FrameTooLong, read_frame


def reader(data: bytes, limit: int = 2048) -> asyncio.StreamReader:
    r = asyncio.StreamReader(limit=limit)
    r.feed_data(data)
    r.feed_eof()
    return r


async def frames(data: bytes, max_bytes: int = 1000, limit: int = 2048) -> list:
    r, out = reader(data, limit), []
    while True:
        try:
            f = await read_frame(r, max_bytes)
        except FrameTooLong:
            out.append("TROP_LONG")
            continue
        if f is None:
            return out
        out.append(f)


async def test_comptage_octets():
    m1, m2 = b"<134>1 2026-11-05T10:00:00Z fw filterlog - - - a", "<134>1 é".encode()
    data = f"{len(m1)} ".encode() + m1 + f"{len(m2)} ".encode() + m2
    assert await frames(data) == [m1, m2]


async def test_fin_de_ligne_et_derniere_ligne_sans_retour():
    assert await frames(b"<13>ligne un\r\n<13>ligne deux\n<13>fin") == [b"<13>ligne un", b"<13>ligne deux", b"<13>fin"]


async def test_trame_trop_longue_ignoree_puis_suite_lue():
    long = b"<13>" + b"x" * 1500
    data = f"{len(long)} ".encode() + long + b"5 <13>a"
    assert await frames(data) == ["TROP_LONG", b"<13>a"]


async def test_ligne_trop_longue_ignoree():
    assert await frames(b"<13>" + b"y" * 5000 + b"\n<13>ok\n", max_bytes=1000, limit=1024) == ["TROP_LONG", b"<13>ok"]


async def test_entete_de_longueur_invalide():
    with pytest.raises(ValueError):
        await read_frame(reader(b"12x <13>a"), 1000)
