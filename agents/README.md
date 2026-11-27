# Collecte — agents et collecteur Syslog (C7)

Uniquement des configurations : aucun agent n'est développé par l'équipe (C3 W1, C1 section 4).
Tous les chemins de collecte suivent le même principe : **conserver sur disque, puis transmettre, et ne retirer qu'après l'accusé 202 de la passerelle** (C6).

| Dossier | Source | Transport | Ce qui est collecté |
|---|---|---|---|
| `fluent-bit/linux/fluent-bit.yaml` | serveur Linux avec rsyslog | HTTPS | `/var/log/auth.log` ; pare-feu iptables/nftables (journal du noyau) |
| `fluent-bit/linux/fluent-bit-journald.yaml` | serveur Linux sans `auth.log` | HTTPS | journald : facilités auth et authpriv ; pare-feu (noyau) |
| `fluent-bit/windows/fluent-bit.yaml` | poste ou serveur Windows | HTTPS | journal Sécurité |
| `fluent-bit/webapp/fluent-bit.yaml` | serveur de l'application web et du backend mobile | HTTPS | journal d'accès HTTP et journal applicatif |
| `fluent-bit/syslog-collector/fluent-bit.yaml` | pfSense (et tout équipement qui n'émet qu'en Syslog) | Syslog vers le collecteur, puis HTTPS | tout ce que pfSense envoie, transmis inchangé |
| `fluent-bit/test/` | — | HTTPS | agent des tests d'intégration (fichier de test) |

Version de référence : Fluent Bit 5.1.5.

## Principe commun des agents Fluent Bit

- **Tampon disque** (`storage.type: filesystem`) : les événements lus sont écrits sur disque avant
  l'envoi et n'en sont retirés qu'après la réponse 202 de la passerelle.
- **Réessais sans limite** (`retry_limit: no_limits`), délai croissant de 2 s à 30 s.
- **Limite de capacité** : `storage.total_limit_size` (`BAOLSEC_BUFFER_LIMIT`, 1 Gio par défaut).
  Au-delà, Fluent Bit supprime les morceaux les plus anciens : c'est la limite du critère de C7.
- **Positions de lecture** (`db`) : après un redémarrage de l'agent, la lecture reprend où elle s'était arrêtée.
- **Pas de parsing côté agent** : le contenu brut est transmis, la normalisation le parse.
- **Codes de la passerelle** : 2xx retire le lot ; 408, 429, 5xx et les erreurs réseau le gardent
  pour un nouvel essai ; 400, 401 et 413 l'abandonnent (comportement de `out_http`, vérifié dans son code).
  Un jeton révoqué fait donc perdre les lots envoyés : la rotation crée le nouveau jeton avant de
  révoquer l'ancien (C4, RG-04).

## Installer un agent Linux

```bash
# 1. Fluent Bit 5.1.5 depuis le dépôt officiel (https://docs.fluentbit.io, rubrique Installation)
# 2. Fichiers BaolSec
sudo mkdir -p /etc/baolsec-agent /var/lib/baolsec-agent
sudo cp -r agents/fluent-bit/{common,linux} /etc/baolsec-agent/
sudo cp sources-ca.crt /etc/baolsec-agent/                        # AC qui a signé le certificat de la passerelle
sudo cp agents/fluent-bit/agent.env.example /etc/baolsec-agent/agent.env
sudo chmod 600 /etc/baolsec-agent/agent.env                       # contient le jeton de la source
sudoedit /etc/baolsec-agent/agent.env                             # passerelle, jeton
# 3. Service systemd : remplacer la commande et charger les variables
sudo systemctl edit fluent-bit
#   [Service]
#   EnvironmentFile=/etc/baolsec-agent/agent.env
#   ExecStart=
#   ExecStart=/opt/fluent-bit/bin/fluent-bit -c /etc/baolsec-agent/linux/fluent-bit.yaml
sudo systemctl restart fluent-bit
```

Fluent Bit doit pouvoir lire `/var/log/auth.log` et le journal (groupes `adm` et `systemd-journal`,
ou exécution en root comme le service fourni par le paquet).

**Pare-feu iptables** : seules les lignes produites par la cible `LOG` sont collectées (format
`SRC=… DST=…`). Exemple : `iptables -A INPUT -j LOG --log-prefix "BAOLSEC-DROP " --log-level 4`
avant la règle `DROP`. Le préfixe indique la décision à la normalisation (C9) : un préfixe contenant
DROP, REJECT, BLOCK ou DENY donne un refus, ACCEPT, ALLOW ou PASS une autorisation.

## Installer un agent Windows

1. Installer Fluent Bit 5.1.5 pour Windows (paquet officiel) et l'enregistrer comme service.
2. Copier `common\` et `windows\` dans `C:\ProgramData\BaolSec\agent\`, avec `sources-ca.crt`.
3. Définir les variables `BAOLSEC_*` pour le service (variables système), avec des chemins Windows.
4. Commande du service : `fluent-bit.exe -c C:\ProgramData\BaolSec\agent\windows\fluent-bit.yaml`.
5. Activer l'audit des connexions (stratégie « Auditer les événements de connexion », succès et
   échecs) pour que les événements 4624 et 4625 soient produits, et l'audit de la création de
   processus (4688), avec la ligne de commande si possible.

La configuration envoie les données de chaque événement nommées dans `EventData`
(`event_data_as_map`) : c'est la forme que lit la normalisation (C9). Le fichier
`scripts/testing/evtx_to_fluentbit.py` reproduit cette forme à partir de fichiers EVTX pour les tests.

## Collecteur Syslog pour pfSense

pfSense n'accueille pas d'agent, et son service de journalisation n'émet **qu'en UDP**
(documentation Netgate ; TCP et TLS demandent le paquet syslog-ng). Un collecteur Fluent Bit est
donc placé sur le même réseau local que pfSense :

1. il reçoit les messages (UDP, ou TCP pour un équipement qui sait le faire) sur le port 514 ;
2. il les écrit dans son tampon disque, **sans les modifier** (ligne reçue dans la clé `log`) ;
3. il les envoie à la passerelle en HTTPS, avec le jeton de la source pare-feu ;
4. il ne les retire du tampon qu'après la réponse 202.

Le collecteur utilise donc exactement le même mécanisme que les agents. Dans pfSense : Statut >
Journaux système > Paramètres > Journalisation à distance, adresse du collecteur, port 514.
Dans « Contenu de la journalisation à distance », ne cocher que **les événements du pare-feu** :
la normalisation (C9) ne traite que les messages `filterlog` d'une source pare-feu, et tout autre
message (DHCP, résolveur…) partirait en file de rejet.

```bash
docker run -d --name baolsec-syslog-collector -p 514:514/udp -p 514:514/tcp \
  --env-file /etc/baolsec-agent/agent.env -e BAOLSEC_LISTEN_PORT=514 \
  -v $PWD/agents/fluent-bit:/agents:ro -v /etc/baolsec-agent:/etc/baolsec-agent:ro \
  -v baolsec-collector-state:/var/lib/baolsec-agent \
  fluent/fluent-bit:5.1.5 /fluent-bit/bin/fluent-bit -c /agents/syslog-collector/fluent-bit.yaml
```

La passerelle garde son entrée Syslog TLS (port 6514) pour les équipements qui savent émettre en
TLS avec un certificat client ; ce n'est pas le chemin de pfSense.

## Chaîne de conservation et résultats mesurés

| Étape | Qui garde la donnée en attendant | Confirmation |
|---|---|---|
| Source → agent | Journal local (fichier, journald, journal Windows) | Position de lecture enregistrée sur disque |
| pfSense → collecteur | Aucun (UDP sur le réseau local) | Aucune : seule limite restante |
| Agent ou collecteur → passerelle | Tampon disque Fluent Bit | Réponse 202 ; sinon nouvel essai |
| Passerelle → broker | La passerelle ne répond qu'après le PubAck de chaque événement | 503 si le broker ne confirme pas |

| Test (make test-agents) | Résultat |
|---|---|
| Agent : 50 événements, coupure réseau, 200 pendant la coupure, reconnexion | 250 / 250, sans doublon |
| Agent arrêté brutalement pendant la coupure | 150 / 150 |
| Collecteur : même scénario de coupure réseau | 250 / 250 |
| Collecteur arrêté brutalement pendant la coupure | 100 / 100 |
| Passerelle arrêtée pendant l'envoi Syslog | 50 / 50 |

## Objectif de conservation : 72 heures

Objectif de conception : supporter une indisponibilité de la passerelle de **72 heures** (une
coupure d'un week-end, du vendredi soir au lundi matin) sans perte. C'est une exigence à
dimensionner et à vérifier, pas une garantie : au-delà de `BAOLSEC_BUFFER_LIMIT`, Fluent Bit
supprime les morceaux les plus anciens.

- **Dimensionnement**, par source : `BAOLSEC_BUFFER_LIMIT` ≥ débit de pointe (événements/s)
  × 259 200 s × taille moyenne mesurée (octets) × 1,5 (réserve pour le format de stockage).
  Exemples : serveur Linux à 2 évt/s de 400 octets ≈ 0,3 Go ; serveur web à 50 évt/s de 500
  octets ≈ 10 Go. Les débits et tailles réels sont mesurés en C27.
- **Rattrapage** : pour vider en H heures le retard de 72 heures, le débit d'envoi doit atteindre
  débit de collecte × (1 + 72/H). La passerelle limite le débit par source
  (`GATEWAY_RATE_LIMIT_EVENTS_PER_S`) : à régler en conséquence.
- **Côté broker** : `raw-events` refuse les nouveaux messages quand il est plein au lieu de
  supprimer ceux qui ne sont pas encore traités ; la passerelle répond alors 503 et les agents
  gardent leurs événements. Un rattrapage ne peut donc pas provoquer de perte dans le broker.
- **Prérequis sur les sources** : journald en stockage persistant (`Storage=persistent` dans
  `/etc/systemd/journald.conf`) ; journal Sécurité de Windows assez grand pour ne pas être écrasé
  pendant la coupure ; rotation des journaux plus longue que la coupure.
- **Vérification** : test accéléré (le volume de 72 heures injecté à débit élevé pendant une
  coupure) avec comptage avant/après, prévu avec les mesures de C27.

## TLS

Tous les agents chiffrent leur envoi vers la passerelle (`tls: on`, `tls.verify: on`,
`tls.ca_file: ${BAOLSEC_CA_FILE}` dans `common/gateway-output.yaml`) : l'agent vérifie le
certificat serveur de la passerelle contre l'AC indiquée par `BAOLSEC_CA_FILE`
(`sources-ca.crt`, à copier sur chaque machine qui héberge un agent ou le collecteur).
L'authentification de la source se fait par le jeton (`Authorization: Bearer
${BAOLSEC_SOURCE_TOKEN}`), pas par un certificat client HTTPS.

Le chemin Syslog TLS (port 6514, pour les équipements qui savent faire du Syslog TLS
avec certificat client — différent du collecteur pfSense ci-dessus qui reçoit en clair
sur le réseau local) utilise lui une authentification par **certificat client**, dont
l'empreinte SHA-256 identifie la source côté passerelle (`cert_fingerprint`) : ce chemin
ne concerne pas pfSense (UDP de base, voir plus haut) et demande un certificat et une clé
par équipement, délivrés par l'AC des sources.

## Rotation des identifiants (voir aussi C26, A-03)

Le token d'une source se renouvelle en deux temps, pour ne jamais perdre les lots
envoyés entre le changement côté passerelle et la reconfiguration de l'agent :

1. `POST /sources/{id}/credentials/rotate` (API BaolSec) crée un **nouveau** jeton
   `bsk_...` sans révoquer l'ancien — les deux sont valides en parallèle.
2. Mettre à jour `BAOLSEC_SOURCE_TOKEN` dans `agent.env` sur la machine de la source,
   puis recharger le service (`systemctl restart fluent-bit`, ou relancer le conteneur
   du collecteur pfSense).
3. Vérifier que l'agent envoie bien avec le nouveau jeton (voir Dépannage ci-dessous :
   un code 401 persistant signale un jeton non reconfiguré ou déjà révoqué).
4. Une fois la transition confirmée, révoquer explicitement l'ancien jeton :
   `DELETE /sources/{id}/credentials/{credential_id}`.

Un jeton révoqué fait abandonner le lot en cours par l'agent (401, sans réessai) : ne
jamais révoquer l'ancien jeton avant d'avoir confirmé que l'agent utilise le nouveau.

## Désinstallation

**Agent Linux/Windows (service système) :**

```bash
sudo systemctl stop fluent-bit
sudo systemctl disable fluent-bit
sudo rm -rf /etc/baolsec-agent /var/lib/baolsec-agent      # Linux
# Windows : équivalent avec le service Fluent Bit et C:\ProgramData\BaolSec\agent\
```

**Collecteur Syslog (conteneur) :**

```bash
docker rm -f baolsec-syslog-collector
docker volume rm baolsec-collector-state     # supprime aussi les positions de lecture et le tampon
```

Avant de désinstaller, s'assurer que le tampon disque est vide (aucun lot en attente
d'envoi) pour ne pas perdre d'événements non encore transmis — sinon, laisser le
service tourner jusqu'à ce que son tampon se vide, ou le copier ailleurs avant
suppression si les événements en attente doivent être conservés manuellement.

Côté API, révoquer le ou les credentials de la source (`DELETE
/sources/{id}/credentials/{credential_id}`) une fois l'agent arrêté, pour qu'un jeton
qui traînerait sur la machine désinstallée ne reste pas valide.

## Dépannage

| Symptôme | Causes probables | Vérifications |
|---|---|---|
| 401 persistant | Jeton non configuré, mal copié, ou révoqué côté API | `echo $BAOLSEC_SOURCE_TOKEN` (ne pas le journaliser ailleurs) ; vérifier côté API que le credential n'est pas `revoked_at` |
| Connexion TLS refusée | AC incorrecte (`BAOLSEC_CA_FILE`), horloge de la machine désynchronisée, certificat de la passerelle expiré | `openssl s_client -connect $BAOLSEC_GATEWAY_HOST:$BAOLSEC_GATEWAY_PORT -CAfile $BAOLSEC_CA_FILE` |
| Événements non reçus côté BaolSec alors que l'agent tourne | Chemin de log incorrect, droits insuffisants sur le fichier/journal, filtre pfSense mal configuré (événements non-pare-feu) | Logs de l'agent (`log_level: debug` temporairement) ; sous Linux, groupes `adm`/`systemd-journal` ; pfSense : ne cocher que les événements du pare-feu |
| Tampon qui grossit sans se vider | Passerelle ou broker indisponible, jeton révoqué (401 → abandon silencieux du lot, pas une accumulation), réseau coupé | Logs agent (codes HTTP reçus) ; `du -sh $BAOLSEC_STATE_DIR` ; métriques de la passerelle |
| Doublons visibles côté recherche/alertes | Comportement normal et attendu en cas de renvoi après coupure — l'identifiant d'événement (event_id) assure la déduplication en aval, ce n'est pas un défaut agent | Vérifier que l'event_id est bien identique entre les deux occurrences (C26, A-04) |
| `make agents-check` indisponible | Pas de démon Docker actif dans l'environnement courant (cf. C26, A-09) | Exécuter sur une machine avec Docker, ou valider manuellement la syntaxe YAML des configs |

## Tests

```bash
make agents-up       # broker, passerelle, agent de test et collecteur Syslog (profil agents-test)
make test-agents     # coupure réseau puis reconnexion, comptage avant/après
make agents-check    # vérifie la syntaxe de toutes les configurations Fluent Bit (nécessite Docker, voir C26 A-09)
```
