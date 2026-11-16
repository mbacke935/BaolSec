"""Serveurs Linux : auth.log, journald et journal du pare-feu (C5, sections 2 à 4)."""
from __future__ import annotations

import pytest

from baolsec_common.messaging import ProcessingError


def test_echec_ssh_utilisateur_invalide(norm):
    d = norm("linux", "Nov  2 10:40:52 srv-linux-01 sshd[1842]: Failed password for invalid user oracle from 203.0.113.9 port 40022 ssh2")
    assert d["event"]["action"] == "ssh_login" and d["event"]["outcome"] == "failure"
    assert d["user"] == {"name": "oracle"}
    assert d["source"] == {"ip": "203.0.113.9", "port": 40022}
    assert d["baolsec"]["ip_scope"] == {"source": "public"}
    assert d["baolsec"]["severity"] == {"label": "info", "score": 0}     # pas de PRI : sévérité native absente
    assert "log" not in d


def test_connexion_ssh_reussie_horodatage_iso(norm):
    d = norm("linux", "2026-11-02T10:40:52.123456+00:00 srv-linux-01 sshd[2001]: Accepted publickey for deploy from 10.0.4.30 port 51000 ssh2: ED25519 SHA256:abc")
    assert d["@timestamp"] == "2026-11-02T10:40:52.123Z"
    assert d["event"]["outcome"] == "success" and d["user"]["name"] == "deploy"
    assert d["message"] == "Connexion SSH réussie pour deploy depuis 10.0.4.30"


def test_utilisateur_inconnu_vide(norm):
    d = norm("linux", "Nov  2 10:40:52 srv-linux-01 sshd[1842]: Invalid user  from 198.51.100.7 port 4242")
    assert "user" not in d and d["source"]["ip"] == "198.51.100.7"
    assert d["event"]["outcome"] == "failure"


def test_message_repete(norm):
    d = norm("linux", "Nov  2 10:40:52 srv-linux-01 sshd[1842]: message repeated 3 times: [ Failed password for root from 10.0.4.23 port 51234 ssh2]")
    assert d["event"]["action"] == "ssh_login" and d["user"]["name"] == "root"


def test_commande_sudo(norm):
    d = norm("linux", "<86>Nov  2 10:41:00 srv-linux-01 sudo:    alice : TTY=pts/0 ; PWD=/home/alice ; USER=root ; COMMAND=/usr/bin/cat /etc/shadow")
    assert d["event"]["category"] == ["process"] and d["event"]["action"] == "sudo_command"
    assert d["event"]["outcome"] == "success"
    assert d["process"]["command_line"] == "/usr/bin/cat /etc/shadow"
    assert d["related"]["user"] == ["alice", "root"]
    assert d["log"]["syslog"]["severity"]["code"] == 6


def test_commande_sudo_refusee(norm):
    d = norm("linux", "Nov  2 10:41:00 srv-linux-01 sudo:      bob : 3 incorrect password attempts ; TTY=pts/1 ; PWD=/home/bob ; USER=root ; COMMAND=/bin/bash")
    assert d["event"]["outcome"] == "failure" and d["user"]["name"] == "bob"


def test_echec_pam_sudo(norm):
    d = norm("linux", "Nov  2 10:41:00 srv-linux-01 sudo: pam_unix(sudo:auth): authentication failure; logname=alice uid=1000 euid=0 tty=/dev/pts/0 ruser=alice rhost=  user=alice")
    assert d["event"]["action"] == "sudo_auth" and d["event"]["outcome"] == "failure"
    assert d["user"]["name"] == "alice"


def test_echec_pam_ssh_ancien_format(norm):
    d = norm("linux", "Jun 14 15:16:01 combo sshd(pam_unix)[19939]: authentication failure; logname= uid=0 euid=0 tty=NODEVssh ruser= rhost=218.188.2.4")
    assert d["event"]["action"] == "pam_auth" and d["source"]["ip"] == "218.188.2.4"
    assert d["process"] == {"name": "sshd(pam_unix)", "pid": 19939}


def test_programme_hors_table(norm):
    d = norm("linux", "Nov  2 10:40:00 srv-linux-01 CRON[999]: pam_unix(cron:session): session opened for user root(uid=0) by (uid=0)")
    assert d["event"]["category"] == ["host"] and d["event"]["type"] == ["info"]
    assert d["event"]["action"] == "cron" and d["event"]["outcome"] == "unknown"
    assert d["message"].startswith("pam_unix(cron:session)")


def test_annee_precedente(norm):
    d = norm("linux", "Dec 31 23:59:58 srv-linux-01 sshd[1]: Failed password for root from 10.0.0.1 port 1 ssh2",
             received_at="2027-01-01T00:00:01.000Z")
    assert d["@timestamp"] == "2026-12-31T23:59:58Z"


def test_ligne_sans_entete_refusee(normalizer):
    import json
    from .conftest import raw
    with pytest.raises(ProcessingError) as err:
        normalizer.run(json.dumps(raw("linux", "ceci n'est pas une ligne syslog")).encode())
    assert err.value.reason_code == "parse_error" and err.value.permanent


def test_journald_authentification(norm):
    record = {"MESSAGE": "Failed password for admin from 10.0.4.23 port 51234 ssh2", "PRIORITY": "6",
              "SYSLOG_IDENTIFIER": "sshd", "_PID": "1842", "_HOSTNAME": "srv-linux-01",
              "SYSLOG_FACILITY": "4", "_SOURCE_REALTIME_TIMESTAMP": "1793616052640000", "_TRANSPORT": "syslog"}
    d = norm("linux", record, read_at="2026-11-02T10:40:52.700Z")
    assert d["@timestamp"] == "2026-11-02T10:40:52.640Z" and d["baolsec"]["timestamp_source"] == "original"
    assert d["event"]["action"] == "ssh_login" and d["host"]["name"] == "srv-linux-01"
    assert d["process"]["pid"] == 1842 and d["log"]["syslog"]["severity"]["code"] == 6


def test_journald_pare_feu_noyau(norm):
    record = {"MESSAGE": "BAOLSEC-DROP IN=eth0 OUT= MAC=00:11 SRC=203.0.113.36 DST=10.0.4.10 LEN=52 TOS=0x00 PROTO=TCP SPT=17805 DPT=22 WINDOW=8192 SYN",
              "PRIORITY": "4", "_TRANSPORT": "kernel", "_HOSTNAME": "srv-linux-01"}
    d = norm("linux", record, read_at="2026-11-02T10:40:52.700Z")
    assert d["event"]["action"] == "connection_denied" and d["event"]["dataset"] == "iptables.log"
    assert d["observer"] == {"name": "srv-linux-01", "product": "iptables", "type": "firewall"}
    assert "host" not in d
    assert d["network"] == {"transport": "tcp", "direction": "ingress"}
    assert d["rule"]["id"] == "BAOLSEC-DROP"
    assert d["baolsec"]["severity"]["label"] == "faible"
    assert d["baolsec"]["ip_scope"] == {"source": "public", "destination": "private"}


def test_iptables_ipv6_sortant_sans_decision(norm):
    d = norm("linux", "Jan 22 09:05:05 ubuntu-bionic kernel: [16571.459614] IN= OUT=lo SRC=2001:0db8:0000:0000:0000:0000:0000:0001 DST=2001:0db8:0000:0000:0000:0000:0000:0002 LEN=104 PROTO=ICMPv6 TYPE=128",
             received_at="2026-01-23T00:00:00Z")
    assert d["source"]["ip"] == "2001:db8::1" and d["network"] == {"transport": "icmp", "direction": "egress"}
    assert d["event"]["action"] == "connection_logged" and d["event"]["type"] == ["connection"]
    assert "rule" not in d


@pytest.mark.parametrize(("prefix", "action", "transport"), [
    ("REJECT", "connection_denied", "udp"),
    ("ACCEPT", "connection_allowed", "tcp"),
])
def test_iptables_decisions_et_protocoles(norm, prefix, action, transport):
    d = norm("linux", f"Nov  2 10:40:52 host kernel: {prefix} IN=eth0 OUT= SRC=10.0.0.2 DST=8.8.8.8 PROTO={transport.upper()} SPT=1 DPT=53")
    assert d["event"]["action"] == action and d["event"]["outcome"] in {"failure", "success"} and d["network"]["transport"] == transport
