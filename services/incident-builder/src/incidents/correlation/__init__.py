"""Corrélation des alertes en incidents (C3 section 3.8, C16).

Chaque alerte reçue par le consumer est transmise au moteur de corrélation
qui décide de créer un incident ou de rattacher l'alerte à un incident ouvert.

Règles de rattachement :
- R1 : même utilisateur ET même IP source
- R2 : même utilisateur ET même hôte
- R3 : même IP source ET même hôte
- R4 : même utilisateur ET activités enchaînées (auth→auth, auth→système, auth→réseau, web→système)

Exclusions :
- E1 : IP seule → pas de rattachement
- E2 : hôte seul → pas de rattachement
- E3 : même règle seule → pas de rattachement
- E4 : fenêtre de 30 min dépassée → nouvel incident
- E5 : incident clos → pas de rattachement

Entités comparées sans casse ; valeurs vides ou génériques ignorées.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)

# --- valeurs génériques : jamais comptées comme entité commune (C3 3.8) ---
GENERIC_VALUES = frozenset({"anonymous", "—", "-", "n/a", "system", "unknown", ""})

# --- enchaînements d'activités autorisés pour R4 (C3 table 7) ---
# clé = catégorie de l'incident, valeur = catégories qui peuvent s'y enchaîner
ACTIVITY_CHAINS: dict[str, frozenset[str]] = {
    "authentication": frozenset({"authentication", "process", "network", "host", "session", "iam"}),
    "web":            frozenset({"process", "host"}),
}

# catégories ECS → famille d'activité pour le matching
CATEGORY_TO_FAMILY: dict[str, str] = {
    "authentication": "authentication",
    "session":        "authentication",
    "iam":            "authentication",
    "process":        "process",
    "host":           "host",
    "network":        "network",
    "web":            "web",
    "file":           "host",
    "configuration":  "host",
    "api":            "web",
    "intrusion_detection": "network",
}

# --- paramètres par défaut (configurables, C3 3.8) ---
DEFAULT_WINDOW_MINUTES = 30
DEFAULT_MAX_DURATION_HOURS = 24


@dataclass(frozen=True)
class Entities:
    """Entités extraites d'une alerte (normalisées en minuscules, génériques filtrées)."""
    user: str | None = None
    source_ip: str | None = None
    host: str | None = None
    categories: tuple[str, ...] = ()

    @property
    def activity_family(self) -> str | None:
        """Famille d'activité principale pour R4."""
        for cat in self.categories:
            fam = CATEGORY_TO_FAMILY.get(cat)
            if fam is not None:
                return fam
        return None


def _clean(value: str | None) -> str | None:
    """Nettoie une valeur d'entité : minuscules, None si générique."""
    if value is None:
        return None
    v = value.strip().lower()
    return None if v in GENERIC_VALUES else v


def extract_entities(doc: dict) -> Entities:
    """Extrait les entités de l'alerte (document alert/v1)."""
    user = _clean(doc.get("user", {}).get("name"))
    source_ip = _clean(doc.get("source", {}).get("ip"))
    host = _clean(doc.get("host", {}).get("name"))
    cats = tuple(doc.get("event", {}).get("category", []))
    return Entities(user=user, source_ip=source_ip, host=host, categories=cats)


@dataclass(frozen=True)
class IncidentContext:
    """Contexte de corrélation d'un incident ouvert (stocké dans correlation_context jsonb)."""
    users: frozenset[str] = frozenset()
    source_ips: frozenset[str] = frozenset()
    hosts: frozenset[str] = frozenset()
    activity_families: frozenset[str] = frozenset()

    def to_dict(self) -> dict:
        return {
            "users": sorted(self.users),
            "source_ips": sorted(self.source_ips),
            "hosts": sorted(self.hosts),
            "activity_families": sorted(self.activity_families),
        }

    @classmethod
    def from_dict(cls, d: dict) -> IncidentContext:
        return cls(
            users=frozenset(d.get("users", [])),
            source_ips=frozenset(d.get("source_ips", [])),
            hosts=frozenset(d.get("hosts", [])),
            activity_families=frozenset(d.get("activity_families", [])),
        )

    def merge(self, entities: Entities) -> IncidentContext:
        """Enrichit le contexte avec les entités d'une nouvelle alerte."""
        users = self.users | ({entities.user} if entities.user else set())
        ips = self.source_ips | ({entities.source_ip} if entities.source_ip else set())
        hosts = self.hosts | ({entities.host} if entities.host else set())
        fam = entities.activity_family
        families = self.activity_families | ({fam} if fam else set())
        return IncidentContext(users=frozenset(users), source_ips=frozenset(ips),
                               hosts=frozenset(hosts), activity_families=frozenset(families))

    @classmethod
    def from_entities(cls, entities: Entities) -> IncidentContext:
        return cls().merge(entities)


@dataclass(frozen=True)
class CandidateIncident:
    """Incident ouvert candidat à un rattachement."""
    incident_id: uuid.UUID
    context: IncidentContext
    last_activity_at: datetime
    opened_at: datetime
    status: str
    severity: str


@dataclass(frozen=True)
class MatchResult:
    """Résultat du matching d'une alerte contre un incident candidat."""
    rule: str | None               # R1, R2, R3, R4 ou None
    common_entities: dict          # {"user": "admin", "source_ip": "10.0.4.23"}
    entity_count: int              # nombre d'entités communes (pour le tri)
    exclusion: str | None = None   # E1, E2, E3, E4, E5 ou None


@dataclass(frozen=True)
class CorrelationDecision:
    """Décision prise par le moteur de corrélation."""
    action: str                    # "attach" ou "create"
    incident_id: uuid.UUID | None  # incident existant (attach) ou nouveau (create)
    rule: str | None               # règle R1-R4 (attach) ou None (create)
    justification: dict            # critères jsonb complets
    new_context: IncidentContext   # contexte mis à jour


def _check_activity_chain(incident_families: frozenset[str], alert_family: str | None) -> bool:
    """Vérifie si l'activité de l'alerte s'enchaîne avec celles de l'incident (R4)."""
    if alert_family is None:
        return False
    for inc_fam in incident_families:
        allowed = ACTIVITY_CHAINS.get(inc_fam)
        if allowed and alert_family in allowed:
            return True
    return False


def match_alert_to_incident(
    entities: Entities,
    candidate: CandidateIncident,
    alert_rule_code: str,
    *,
    window_minutes: int = DEFAULT_WINDOW_MINUTES,
    max_duration_hours: int = DEFAULT_MAX_DURATION_HOURS,
    now: datetime | None = None,
) -> MatchResult:
    """Évalue la compatibilité d'une alerte avec un incident candidat.

    Retourne un MatchResult avec la règle trouvée ou l'exclusion qui empêche le rattachement.
    """
    now = now or datetime.now(timezone.utc)
    ctx = candidate.context

    # --- E5 : incident clos ---
    if candidate.status == "clos":
        return MatchResult(rule=None, common_entities={}, entity_count=0, exclusion="E5")

    # --- E4 : fenêtre dépassée ---
    delta = now - candidate.last_activity_at
    if delta > timedelta(minutes=window_minutes):
        return MatchResult(rule=None, common_entities={}, entity_count=0, exclusion="E4")

    # --- durée totale de l'incident ---
    if now - candidate.opened_at > timedelta(hours=max_duration_hours):
        return MatchResult(rule=None, common_entities={}, entity_count=0, exclusion="E4")

    # --- entités communes ---
    common: dict[str, str] = {}
    if entities.user and entities.user in ctx.users:
        common["user"] = entities.user
    if entities.source_ip and entities.source_ip in ctx.source_ips:
        common["source_ip"] = entities.source_ip
    if entities.host and entities.host in ctx.hosts:
        common["host"] = entities.host

    count = len(common)

    # --- au moins 2 entités communes : R1, R2, R3 ---
    if count >= 2:
        if "user" in common and "source_ip" in common:
            rule = "R1"
        elif "user" in common and "host" in common:
            rule = "R2"
        else:
            rule = "R3"
        return MatchResult(rule=rule, common_entities=common, entity_count=count)

    # --- R4 : même utilisateur + activités enchaînées ---
    if "user" in common and count == 1:
        if _check_activity_chain(ctx.activity_families, entities.activity_family):
            common["activity_chain"] = f"{','.join(sorted(ctx.activity_families))}→{entities.activity_family}"
            return MatchResult(rule="R4", common_entities=common, entity_count=count + 1)

    # --- exclusions E1, E2, E3 ---
    if count == 1:
        if "source_ip" in common:
            return MatchResult(rule=None, common_entities=common, entity_count=count, exclusion="E1")
        if "host" in common:
            return MatchResult(rule=None, common_entities=common, entity_count=count, exclusion="E2")
        # user seul sans chaîne d'activité valide
        return MatchResult(rule=None, common_entities=common, entity_count=count, exclusion="E1")

    # --- aucune entité commune ---
    return MatchResult(rule=None, common_entities={}, entity_count=0, exclusion="E3")


def correlate(
    entities: Entities,
    alert_rule_code: str,
    alert_severity: str,
    alert_triggered_at: datetime,
    candidates: list[CandidateIncident],
    *,
    window_minutes: int = DEFAULT_WINDOW_MINUTES,
    max_duration_hours: int = DEFAULT_MAX_DURATION_HOURS,
) -> CorrelationDecision:
    """Décide de créer un incident ou de rattacher l'alerte à un incident existant.

    Parmi les incidents candidats, choisit celui qui partage le plus d'entités,
    puis le plus récent. Si aucun ne convient, crée un nouvel incident.
    """
    best_match: MatchResult | None = None
    best_candidate: CandidateIncident | None = None
    exclusions: list[dict] = []

    for candidate in candidates:
        result = match_alert_to_incident(
            entities, candidate, alert_rule_code,
            window_minutes=window_minutes, max_duration_hours=max_duration_hours,
            now=alert_triggered_at,
        )
        if result.rule is not None:
            if (best_match is None
                    or result.entity_count > best_match.entity_count
                    or (result.entity_count == best_match.entity_count
                        and candidate.last_activity_at > best_candidate.last_activity_at)):
                best_match = result
                best_candidate = candidate
        elif result.exclusion:
            exclusions.append({
                "incident_id": str(candidate.incident_id),
                "exclusion": result.exclusion,
                "common_entities": result.common_entities,
            })

    if best_match is not None and best_candidate is not None:
        # --- rattachement ---
        new_context = best_candidate.context.merge(entities)
        justification = {
            "rule": best_match.rule,
            "common_entities": best_match.common_entities,
            "time_delta_s": int((alert_triggered_at - best_candidate.last_activity_at).total_seconds()),
            "window_minutes": window_minutes,
        }
        return CorrelationDecision(
            action="attach",
            incident_id=best_candidate.incident_id,
            rule=best_match.rule,
            justification=justification,
            new_context=new_context,
        )

    # --- création ---
    new_id = uuid.uuid4()
    new_context = IncidentContext.from_entities(entities)
    reason = "aucun incident ouvert compatible"
    if exclusions:
        reason = f"candidats écartés : {exclusions}"
    justification = {"reason": reason, "window_minutes": window_minutes}
    return CorrelationDecision(
        action="create",
        incident_id=new_id,
        rule=None,
        justification=justification,
        new_context=new_context,
    )


# --- titre automatique de l'incident ---
SEVERITY_ORDER = {"faible": 1, "moyenne": 2, "elevee": 3, "critique": 4}


def max_severity(current: str, incoming: str) -> str:
    """Retourne la sévérité la plus élevée entre deux valeurs."""
    return incoming if SEVERITY_ORDER.get(incoming, 0) > SEVERITY_ORDER.get(current, 0) else current


def incident_title(entities: Entities, rule_name: str) -> str:
    """Génère un titre d'incident à partir de la première alerte."""
    parts = [rule_name]
    if entities.user:
        parts.append(f"({entities.user}")
        if entities.source_ip:
            parts[-1] += f", {entities.source_ip}"
        if entities.host:
            parts[-1] += f", {entities.host}"
        parts[-1] += ")"
    elif entities.source_ip:
        parts.append(f"({entities.source_ip})")
    elif entities.host:
        parts.append(f"({entities.host})")
    return " ".join(parts)


__all__ = [
    "GENERIC_VALUES", "ACTIVITY_CHAINS", "DEFAULT_WINDOW_MINUTES", "DEFAULT_MAX_DURATION_HOURS",
    "Entities", "extract_entities", "IncidentContext", "CandidateIncident", "MatchResult",
    "CorrelationDecision", "match_alert_to_incident", "correlate", "max_severity", "incident_title",
    "SEVERITY_ORDER",
]
