"""Journal Sécurité Windows tel que l'envoie l'entrée winevtlog de Fluent Bit (event_data_as_map)."""
from __future__ import annotations

import json

import pytest

from baolsec_common.messaging import ProcessingError

from .conftest import raw

BASE = {"ProviderName": "Microsoft-Windows-Security-Auditing", "Channel": "Security", "Computer": "PC-WIN-COMPTA",
        "TimeCreated": "2026-11-02 10:40:52 +0000", "EventRecordID": 1}


def test_ouverture_de_session(norm):
    d = norm("windows", {**BASE, "EventID": 4624, "EventData": {
        "TargetUserName": "admin", "LogonType": "10", "IpAddress": "10.0.4.23", "IpPort": "50000"}})
    assert d["event"]["action"] == "logon" and d["event"]["outcome"] == "success" and d["event"]["code"] == "4624"
    assert d["baolsec"]["windows"] == {"logon_type": "10"}
    assert d["@timestamp"] == "2026-11-02T10:40:52Z"
    assert d["message"] == "Ouverture de session réussie pour admin depuis 10.0.4.23"
    assert d["baolsec"]["severity"]["label"] == "info"


def test_echec_local_sans_adresse(norm):
    d = norm("windows", {**BASE, "EventID": 4625, "EventData": {
        "TargetUserName": "IEUser", "LogonType": "2", "IpAddress": "-", "IpPort": "-"}})
    assert "source" not in d and d["user"]["name"] == "IEUser"
    assert d["baolsec"]["severity"] == {"label": "faible", "score": 1}


def test_liste_string_inserts(norm):
    inserts = ["S-1-0-0", "-", "-", "0x0", "S-1-0-0", "admin", "PC", "0xc000006d", "%%2313", "0xc000006a",
               "3", "NtLmSsp", "NTLM", "KALI", "-", "-", "0", "0x0", "-", "10.0.4.23", "51240"]
    d = norm("windows", {**BASE, "EventID": 4625, "StringInserts": inserts})
    assert d["user"]["name"] == "admin" and d["source"] == {"ip": "10.0.4.23", "port": 51240}
    assert d["baolsec"]["windows"]["logon_type"] == "3"


def test_creation_de_processus(norm):
    d = norm("windows", {**BASE, "EventID": 4688, "EventData": {
        "SubjectUserName": "WIN-77LTAPHIQ1R$", "NewProcessId": "0x0000000000000ae8",
        "NewProcessName": "C:\\Windows\\System32\\wbem\\WmiPrvSE.exe", "CommandLine": ""}})
    assert d["process"] == {"pid": 2792, "executable": "C:\\Windows\\System32\\wbem\\WmiPrvSE.exe",
                            "name": "WmiPrvSE.exe"}
    assert d["event"]["category"] == ["process"] and d["event"]["action"] == "process_start"


def test_fermeture_de_session(norm):
    d = norm("windows", {**BASE, "EventID": 4634, "EventData": {"TargetUserName": "admin", "LogonType": "3"}})
    assert d["event"]["type"] == ["end"] and d["event"]["action"] == "logoff"


def test_evenement_hors_table(norm):
    d = norm("windows", {**BASE, "EventID": 4672, "Message": "Privilèges spéciaux attribués à la nouvelle ouverture de session.\r\n\r\nSujet :"})
    assert d["event"]["action"] == "windows_4672" and d["event"]["type"] == ["info"]
    assert d["message"] == "Privilèges spéciaux attribués à la nouvelle ouverture de session."


def test_heure_absente_heure_de_reception(norm):
    record = {k: v for k, v in BASE.items() if k != "TimeCreated"}
    d = norm("windows", {**record, "EventID": 4634, "EventData": {"TargetUserName": "admin"}})
    assert d["baolsec"]["timestamp_source"] == "received" and d["@timestamp"] == "2026-11-02T10:40:53.120Z"


def test_heure_invalide_heure_de_reception(norm):
    d = norm("windows", {**BASE, "TimeCreated": "invalide", "EventID": 4624, "EventData": {"TargetUserName": "admin"}})
    assert d["baolsec"]["timestamp_source"] == "received"


@pytest.mark.parametrize("payload", [json.dumps({"Computer": "PC"}), "pas du JSON", json.dumps([1, 2])])
def test_enregistrements_refuses(normalizer, payload):
    with pytest.raises(ProcessingError) as err:
        normalizer.run(json.dumps(raw("windows", payload, fmt="json")).encode())
    assert err.value.reason_code == "parse_error"
