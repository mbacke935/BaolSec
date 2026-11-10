# Règles de détection

Une règle par fichier, nommé d'après son code (`AUTH-001.yml`). Format : contrat
`shared/contracts/rule/v1/schema.json`. Les règles sont chargées dans PostgreSQL par `make rules-load`
(une nouvelle version est créée si le fichier a changé) ; `detection-worker` les relit toutes les 30 s,
sans redémarrage.

```yaml
id: AUTH-001                         # code stable : rule.id des alertes
name: Force brute sur un compte
severity: elevee                     # faible, moyenne, elevee, critique
type: window                         # simple : un événement suffit ; window : seuil sur une fenêtre
category: [authentication]           # event.category de l'alerte ; sert à la corrélation (C16)
match:                               # toutes les conditions doivent être vraies
  event.category: authentication     # valeur exacte, sans tenir compte de la casse
  event.outcome: [failure]           # liste : l'une des valeurs
  process.command_line: {regex: '…'} # opérateurs : equals, in, not, exists, contains, regex, gte, lte
group_by: [user.name, source.ip]     # un compteur par combinaison
window: 10m                          # s, m ou h ; 24 h au plus
threshold: 5
distinct: destination.port           # facultatif : compter des valeurs distinctes
followed_by:                         # facultatif : alerte quand cet événement suit le seuil atteint
  match: {event.outcome: success}
message: "{count} échecs en {window} pour {user.name} depuis {source.ip}"
requires:                            # données nécessaires, utilisées par la couverture (C17)
  - source_type: linux
    fields: [user.name, source.ip]
```

Aucune expression n'est exécutée comme du code : seuls les opérateurs ci-dessus existent.

| Code | Règle | Type |
|---|---|---|
| AUTH-001 | Force brute sur un compte : 5 échecs en 10 min, même utilisateur et même IP | window |
| SYS-001 | PowerShell lancé avec une commande encodée | simple |

Le jeu complet (authentification, pare-feu, web et API, système) est l'objet de la carte C13.
