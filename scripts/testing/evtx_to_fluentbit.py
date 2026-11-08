"""Convertit des fichiers EVTX (journal Sécurité Windows) en enregistrements JSON, une ligne par événement,
dans la forme que produit l'entrée winevtlog de Fluent Bit 5.1.5 avec event_data_as_map :
champs système à la racine (EventID, Computer, Channel, EventRecordID, TimeCreated…) et données
de l'événement nommées dans EventData.

Sert aux tests de normalisation (C9) sans machine Windows : le contenu des événements est réel,
seule la mise en forme de l'agent est reproduite. Usage :
    python evtx_to_fluentbit.py fichier1.evtx [fichier2.evtx …] > windows-security.jsonl
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from datetime import datetime

import Evtx.Evtx as evtx

NS = {"e": "http://schemas.microsoft.com/win/2004/08/events/event"}


def convert(xml: str) -> dict:
    root = ET.fromstring(xml)
    system = root.find("e:System", NS)

    def text(tag):
        node = system.find(f"e:{tag}", NS)
        return node.text if node is not None else None

    created = system.find("e:TimeCreated", NS).get("SystemTime")
    dt = datetime.fromisoformat(created.replace(" ", "T"))
    record = {
        "ProviderName": system.find("e:Provider", NS).get("Name"),
        "EventID": int(text("EventID")),
        "Version": int(text("Version") or 0),
        "Level": int(text("Level") or 0),
        "Task": int(text("Task") or 0),
        "Keywords": text("Keywords"),
        "TimeCreated": dt.strftime("%Y-%m-%d %H:%M:%S %z"),     # format de Fluent Bit
        "EventRecordID": int(text("EventRecordID")),
        "Channel": text("Channel"),
        "Computer": text("Computer"),
    }
    data = root.find("e:EventData", NS)
    if data is not None:
        record["EventData"] = {d.get("Name"): (d.text or "") for d in data.findall("e:Data", NS) if d.get("Name")}
    return record


def main(paths: list[str]) -> None:
    for path in paths:
        with evtx.Evtx(path) as log:
            for rec in log.records():
                print(json.dumps(convert(rec.xml()), ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
