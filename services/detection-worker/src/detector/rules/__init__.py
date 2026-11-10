"""Chargement des règles actives et cache rafraîchi périodiquement.

Sources : PostgreSQL (config.rules et version courante dans config.rule_versions, compte svc_detection)
ou dossier de fichiers YAML (tests et développement). Une règle refusée par le contrat est écartée
et signalée ; les autres continuent d'être appliquées.
"""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Protocol

from .. import metrics
from .model import Rule, RuleError, RuleValidator, checksum, rule_uuid

log = logging.getLogger(__name__)

__all__ = ["Rule", "RuleError", "RuleValidator", "RulesCache", "FileRules", "PostgresRules", "checksum", "rule_uuid"]


class RuleSource(Protocol):
    async def load(self) -> list[tuple[str, int, str]]:
        """Liste de (origine, version, YAML) des règles actives."""


class FileRules:
    def __init__(self, directory: Path):
        self._dir = Path(directory)

    async def load(self) -> list[tuple[str, int, str]]:
        files = sorted(self._dir.rglob("*.yml")) + sorted(self._dir.rglob("*.yaml"))
        return [(str(f.relative_to(self._dir)), 1, f.read_text(encoding="utf-8")) for f in files]


class PostgresRules:
    QUERY = """
SELECT r.name, v.version, v.definition_yaml
FROM config.rules AS r
JOIN config.rule_versions AS v ON v.rule_id = r.id AND v.version = r.current_version
WHERE r.is_enabled
"""

    def __init__(self, dsn: str):
        self._dsn = dsn

    async def load(self) -> list[tuple[str, int, str]]:
        import psycopg
        async with await psycopg.AsyncConnection.connect(self._dsn, connect_timeout=5) as conn:
            await conn.set_read_only(True)
            async with conn.cursor() as cur:
                await cur.execute(self.QUERY)
                return [(r[0], r[1], r[2]) for r in await cur.fetchall()]


class RulesCache:
    """Règles valides et actives. Tant qu'aucun chargement n'a réussi, le service ne lit pas les événements."""

    def __init__(self, source: RuleSource, validator: RuleValidator, refresh_s: float = 30.0):
        self._source, self._validator, self._refresh = source, validator, refresh_s
        self._rules: tuple[Rule, ...] = ()
        self._by_category: dict[str, tuple[Rule, ...]] = {}
        self._any: tuple[Rule, ...] = ()
        self.loaded_at: float | None = None
        self.last_error: str | None = None
        self.rejected: dict[str, str] = {}

    @property
    def usable(self) -> bool:
        return self.loaded_at is not None

    @property
    def rules(self) -> tuple[Rule, ...]:
        return self._rules

    def __len__(self) -> int:
        return len(self._rules)

    def candidates(self, categories: list) -> tuple[Rule, ...]:
        """Règles à évaluer pour un événement, d'après son event.category (index)."""
        found = list(self._any)
        for c in categories:
            found.extend(self._by_category.get(c, ()))
        return tuple({r.code: r for r in found}.values())

    def set_rules(self, rules: list[Rule]) -> None:
        active = tuple(r for r in rules if r.enabled)
        index: dict[str, list[Rule]] = {}
        anyc: list[Rule] = []
        for r in active:
            if r.needs_category is None:
                anyc.append(r)
            else:
                for c in r.needs_category:
                    index.setdefault(c, []).append(r)
        self._rules, self._any = active, tuple(anyc)
        self._by_category = {k: tuple(v) for k, v in index.items()}
        metrics.RULES_LOADED.set(len(active))

    async def refresh(self) -> None:
        rows = await self._source.load()
        rules, rejected, seen = [], {}, set()
        for origin, version, text in rows:
            try:
                rule = self._validator.parse(text, version)
            except RuleError as exc:
                rejected[origin] = str(exc)
                continue
            if rule.code in seen:
                rejected[origin] = f"code {rule.code} déjà utilisé"
                continue
            seen.add(rule.code)
            rules.append(rule)
        for origin, why in rejected.items():
            if self.rejected.get(origin) != why:
                log.error("règle %s refusée : %s", origin, why)
        self.rejected = rejected
        metrics.RULES_REJECTED.set(len(rejected))
        self.set_rules(rules)
        self.loaded_at = time.monotonic()
        self.last_error = None

    async def run(self) -> None:
        while True:
            try:
                await self.refresh()
            except Exception as exc:     # base injoignable : on garde les règles déjà chargées
                self.last_error = f"{type(exc).__name__}: {exc}"
                log.warning("lecture des règles impossible : %s", self.last_error)
            await asyncio.sleep(self._refresh)
