# C26 — A-04 : limite du mécanisme d'identifiant d'événement (décision du 24/11/2026)

## Décision

**Option A retenue** : le mécanisme actuel de génération de `event_id` est conservé tel
quel. Le contrat `raw_event/v1` et la logique de `gateway/event_id/__init__.py` ne sont
**pas modifiés**. Aucun horodatage artificiel n'est introduit dans le hash de contenu.

Raison : introduire un élément temporel (même une fenêtre arrondie) dans
`content_hash()` romprait l'idempotence recherchée pour une vraie retransmission (un
agent qui renvoie un événement après un redémarrage doit obtenir le même `event_id`,
pas un nouveau).

## Mécanisme actuel (rappel)

1. Identifiant natif quand la source en fournit un — aujourd'hui, uniquement Windows
   (`win:<Computer>:<Channel>:<EventRecordID>`), qui ne passe jamais par `content_hash`.
2. Sinon, empreinte SHA-256 de `(source_id, payload_format, payload)`. Le champ `date`
   de l'agent (heure de lecture) est retiré du corps avant le calcul : seul un
   horodatage **porté par le contenu lui-même** distingue alors deux événements
   survenus à des instants différents.

## Vérification par source C7 (24/11/2026)

Vérification faite à partir des configurations Fluent Bit réelles
(`agents/fluent-bit/*/fluent-bit*.yaml`), des parseurs et du code de normalisation
— pas d'hypothèse non vérifiée.

| Source | Mécanisme d'identifiant | Horodatage propre dans le payload | Statut |
|---|---|---|---|
| Linux `auth.log` (tail, rsyslog) | `content_hash` | Oui — ligne rsyslog classique, horodatage en tête de ligne | Sûr |
| Linux journald (`systemd` input) | `content_hash` | **Non vérifié** — dépend des champs que Fluent Bit 5.1.5 restitue réellement (`__REALTIME_TIMESTAMP` ou non) ; non démontrable sans exécution réelle de l'agent (cf. A-09) | À vérifier lors de la validation Fluent Bit |
| Windows (`winevtlog`) | **`native_id`**, ne passe pas par `content_hash` | `TimeCreated` présent par ailleurs | Sûr, et hors sujet pour A-04 |
| Webapp — `web.access` | `content_hash` | Oui — format d'accès (combined/common), horodatage entre crochets imposé par le parseur (`parse_access`, regex) | Sûr |
| Webapp — **`web.app`** (journal applicatif) | `content_hash` | **Non garanti** — `normalizer/parsers/web.py::parse_app()` reconnaît un champ `ts`/`timestamp`/`@timestamp`/`time` mais tolère explicitement son absence (`timestamp = None`) | **Exposition réelle, déjà intégrée** |
| pfSense / équipements Syslog (collecteur) | `content_hash` | Oui — ligne Syslog brute conservée avec son en-tête (`raw_message_key: log`), qui porte un horodatage RFC 3164/5424 | Sûr |

## Conclusion

A-04 n'est **pas** un défaut avéré sur l'ensemble des sources C7 actuelles : quatre des
cinq familles connectées embarquent structurellement leur propre horodatage dans le
payload, et Windows n'est de toute façon pas concerné (identifiant natif). En revanche,
l'affirmation « toutes les sources C7 actuelles embarquent un timestamp » n'est pas
exacte sans nuance :

- **`web.app` (journal applicatif)** est une source déjà intégrée et déjà exposée : si
  l'application surveillée écrit une ligne JSON sans aucun des champs temporels
  reconnus, deux occurrences de contenu identique à des instants différents obtiennent
  le même `event_id`. Ce n'est pas hypothétique, c'est permis par le code actuel
  (`parse_app`) et dépend uniquement du format choisi par l'application cliente, hors
  du contrôle de BaolSec.
- **Linux journald** n'a pas pu être vérifié avec certitude dans cet environnement
  (pas d'exécution réelle de Fluent Bit disponible, cf. A-09/A-10) ; son statut reste
  à confirmer lors de la prochaine validation réelle des agents.

## Limite connue et condition de réévaluation

Cette limite est acceptée en l'état pour les sources C7 actuelles. Elle doit être
réévaluée, avant intégration, pour :

- tout futur connecteur applicatif JSON qui ne garantirait pas un champ temporel
  (recommandation : exiger `ts`/`timestamp` dans le format attendu dès la spécification
  de la source, plutôt que de le rendre optionnel comme `parse_app` le fait aujourd'hui) ;
- la confirmation du comportement réel de la collecte journald sur Fluent Bit 5.1.5.

## Tests démontrant le comportement actuel

Ajoutés le 24/11/2026 dans `services/ingestion-gateway/tests/test_units.py` :

- `test_json_sans_timestamp_propre_collision_connue` — démontre la collision acceptée
  pour un enregistrement JSON sans champ temporel (ex. `web.app` dégradé).
- `test_json_avec_timestamp_propre_diverge` — contre-exemple : dès qu'un champ temporel
  propre est présent dans le payload, deux occurrences distinctes divergent.

Ces tests s'ajoutent à `test_meme_evenement_meme_identifiant` (déjà existant), qui
couvrait déjà le cas texte (`log`).

## Re-vérification (tour de validation conditionnelle du 24/11/2026)

Les deux tests ci-dessus ont été ré-exécutés dans le cadre de la re-vérification
demandée avant clôture de la Phase 1, avec l'ensemble de la suite
`services/ingestion-gateway` : **46/46 PASSED**, aucune régression. Aucun contenu de ce
document n'a été modifié par ce tour — la décision (Option A), le tableau de
vérification par source et ses deux limites connues (web.app, journald) restent
inchangés et sont repris tels quels dans `C26_audit_C6C7_phase1_corrections.md`.
