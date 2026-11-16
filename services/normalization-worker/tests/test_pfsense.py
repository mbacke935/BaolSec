"""Pare-feu pfSense : messages filterlog (formats d'en-tête BSD et RFC 5424, IPv4 et IPv6)."""
from __future__ import annotations

import json

import pytest

from baolsec_common.messaging import ProcessingError

from .conftest import raw


def test_udp_autorise_sans_nom_d_hote(norm):
    # En-tête BSD de pfSense : pas de nom d'hôte. L'équipement est nommé par le référentiel (C10).
    d = norm("firewall", "<134>Jul  3 19:10:30 filterlog[72237]: 176,,,1520797901,igb1.27,match,pass,in,4,0xb8,,64,58355,0,none,17,udp,76,10.170.27.27,175.16.199.1,123,123,56",
             received_at="2026-07-03T19:10:31Z")
    assert d["event"]["type"] == ["connection", "allowed"] and d["event"]["action"] == "connection_allowed"
    assert d["observer"]["name"] == "fw-edge-01"            # config.sources.host
    assert d["source"] == {"ip": "10.170.27.27", "port": 123} and d["destination"]["port"] == 123
    assert d["network"] == {"transport": "udp", "direction": "ingress"}
    assert d["baolsec"]["severity"]["label"] == "info"


def test_rfc5424_avec_fuseau(norm):
    d = norm("firewall", "<134>1 2021-07-03T19:10:14.578288-05:00 pfSense.example.com filterlog 72237 - - 146,,,1535324496,igb1.12,match,block,in,4,0x0,,63,32989,0,DF,6,tcp,60,10.170.12.50,175.16.199.1,49652,853,0,S,1818117648,,64240,,mss;sackOK;TS;nop;wscale")
    assert d["@timestamp"] == "2021-07-04T00:10:14.578Z"
    assert d["observer"]["name"] == "pfSense.example.com"
    assert d["rule"]["id"] == "146" and d["destination"] == {"ip": "175.16.199.1", "port": 853}


def test_ipv6(norm):
    d = norm("firewall", "<134>Jul  3 19:10:31 filterlog[72237]: 6,,,1000000105,igb1.27,match,block,in,6,0x00,0xf6279,1,UDP,17,32,fe80::208:9bff:fef3:652b,ff02::1:2,546,547,32",
             received_at="2026-07-03T19:10:31Z")
    assert d["source"] == {"ip": "fe80::208:9bff:fef3:652b", "port": 546}
    assert d["baolsec"]["ip_scope"] == {"source": "private", "destination": "private"}


def test_icmp_sans_ports(norm):
    d = norm("firewall", "<134>1 2023-06-13T20:19:42.319750+03:00 pfSense.example.com filterlog 30459 - - 4,,,1000000103,em0,match,block,in,4,0x28,,53,28808,0,none,1,icmp,56,10.100.10.23,224.0.0.1,unreachport,10.100.10.23,UDP,5336")
    assert d["source"] == {"ip": "10.100.10.23"} and d["destination"] == {"ip": "224.0.0.1"}
    assert d["network"]["transport"] == "icmp"
    assert d["message"].startswith("Connexion ICMP bloquée de 10.100.10.23 vers 224.0.0.1")


def test_reject_tcp(norm):
    d = norm("firewall", "<134>Jul  3 19:10:30 filterlog[1]: 7,,,1,em0,match,reject,out,4,0x0,,64,1,0,none,6,tcp,60,10.0.0.2,8.8.8.8,1000,443")
    assert d["event"]["action"] == "connection_denied" and d["network"] == {"transport": "tcp", "direction": "egress"}


@pytest.mark.parametrize("payload", [
    "<30>Jul  3 19:10:30 dhcpd[1234]: DHCPACK on 10.0.0.5 to aa:bb:cc:dd:ee:ff",   # autre programme pfSense
    "<134>Jul  3 19:10:30 filterlog[1]: 5,,,1,em0,match",                          # trop court
    "<134>Jul  3 19:10:30 filterlog[1]: 5,,,1,em0,match,drop,in,4,0x0,,64,0,0,DF,6,tcp,60,a,b,1,2",
    "texte quelconque",
])
def test_messages_refuses(normalizer, payload):
    with pytest.raises(ProcessingError) as err:
        normalizer.run(json.dumps(raw("firewall", payload, received_at="2026-07-03T19:10:31Z")).encode())
    assert err.value.reason_code == "parse_error" and err.value.permanent
