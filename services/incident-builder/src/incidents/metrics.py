"""Métriques Prometheus du service Incidents (C3, fiche 4.6 : doublons ignorés, commandes réussies et échouées)."""
from prometheus_client import Counter, Histogram

ALERTS = Counter("baolsec_incidents_alerts_received_total",
                 "Alertes enregistrées dans alert_state (première réception), par sévérité", ["severity"])
DUPLICATES = Counter("baolsec_incidents_alert_duplicates_total",
                     "Alertes déjà connues (même alert_id) ignorées")
MESSAGES = Counter("baolsec_incidents_messages_total", "Messages du flux alerts traités, par issue", ["outcome"])
SECONDS = Histogram("baolsec_incidents_alert_seconds", "Durée d'enregistrement d'une alerte",
                    buckets=(0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5))
COMMANDS = Counter("baolsec_incidents_commands_total",
                   "Commandes de l'API traitées (première application), par type et résultat",
                   ["command_type", "result"])
REPLAYS = Counter("baolsec_incidents_command_replays_total",
                  "Commandes rejouées (même command_id) : résultat enregistré renvoyé sans réapplication")

# --- C16 : corrélation et incidents ---
INCIDENTS_CREATED = Counter("baolsec_incidents_created_total",
                            "Incidents créés par le moteur de corrélation, par sévérité", ["severity"])
ALERTS_ATTACHED = Counter("baolsec_incidents_alerts_attached_total",
                          "Alertes rattachées à un incident existant, par règle de corrélation", ["rule"])
CORRELATION_CONFLICTS = Counter("baolsec_incidents_correlation_conflicts_total",
                                "Alertes déjà rattachées à un autre incident (conflit, premier rattachement conservé)")
