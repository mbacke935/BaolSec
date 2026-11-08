"""Enrichissement des événements normalisés (C10).

Ajoute le contexte utile à l'analyse, sans rien inventer :
- nom de la source et criticité de l'actif, déclarés par l'Administrateur (config.sources) ;
- hôte ou équipement d'origine (config.sources.host) quand le journal ne le nomme pas
  (journal d'accès web, pfSense sans nom d'hôte dans l'en-tête Syslog) ;
- classement des adresses IP : « private » (réseau interne ou adresse non routable sur Internet)
  ou « public ».
"""
from __future__ import annotations

import ipaddress
import logging

from .sources import SourcesCache

log = logging.getLogger(__name__)

# Adresses internes ou non routables sur Internet (RFC 1918, 6598, 3927, 5735, 4193, 4291)
DEFAULT_INTERNAL = (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",   # réseaux privés
    "100.64.0.0/10",                                     # partage d'adresses (CGNAT)
    "127.0.0.0/8", "169.254.0.0/16", "0.0.0.0/8",       # boucle locale, lien local, « cette machine »
    "224.0.0.0/4", "255.255.255.255/32",                 # multidiffusion, diffusion
    "::1/128", "::/128", "fc00::/7", "fe80::/10", "ff00::/8",
)


class Enricher:
    def __init__(self, sources: SourcesCache, extra_internal: list[str] | tuple[str, ...] = ()):
        self._sources = sources
        self._networks = [ipaddress.ip_network(n, strict=False) for n in (*DEFAULT_INTERNAL, *extra_internal)]
        self.unknown_sources = 0

    def scope(self, ip: str) -> str:
        addr = ipaddress.ip_address(ip)
        if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
            addr = addr.ipv4_mapped
        return "private" if any(addr in net for net in self._networks if net.version == addr.version) else "public"

    def apply(self, doc: dict) -> None:
        bl = doc["baolsec"]
        info = self._sources.get(bl["source"]["id"])
        if info is None:
            # Source supprimée du référentiel depuis la réception : l'événement reste publié, sans nom.
            self.unknown_sources += 1
            log.warning("source %s absente du référentiel : événement non enrichi", bl["source"]["id"])
        else:
            bl["source"]["name"] = info.name
            if info.criticality:
                bl["source"]["criticality"] = info.criticality
            if info.host:
                if "observer" in doc:
                    doc["observer"].setdefault("name", info.host)
                elif "host" not in doc or "name" not in doc["host"]:
                    doc.setdefault("host", {})["name"] = info.host
        if "observer" in doc and "name" not in doc["observer"] and info is not None:
            doc["observer"]["name"] = info.name     # pare-feu sans nom d'hôte ni hôte déclaré

        scopes = {}
        for side in ("source", "destination"):
            ip = doc.get(side, {}).get("ip")
            if ip:
                scopes[side] = self.scope(ip)
        if scopes:
            bl["ip_scope"] = scopes
