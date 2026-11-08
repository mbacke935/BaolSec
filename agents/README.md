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
`SRC=… DST=…`). Exemple : `iptables -A INPUT -j LOG --log-prefix "BAOLSEC-FW " --log-level 4`
avant la règle `DROP`.

## Installer un agent Windows

1. Installer Fluent Bit 5.1.5 pour Windows (paquet officiel) et l'enregistrer comme service.
2. Copier `common\` et `windows\` dans `C:\ProgramData\BaolSec\agent\`, avec `sources-ca.crt`.
3. Définir les variables `BAOLSEC_*` pour le service (variables système), avec des chemins Windows.
4. Commande du service : `fluent-bit.exe -c C:\ProgramData\BaolSec\agent\windows\fluent-bit.yaml`.
5. Activer l'audit des connexions (stratégie « Auditer les événements de connexion », succès et
   échecs) pour que les événements 4624 et 4625 soient produits.

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

## Tests

```bash
make agents-up       # broker, passerelle, agent de test et collecteur Syslog (profil agents-test)
make test-agents     # coupure réseau puis reconnexion, comptage avant/après
make agents-check    # vérifie la syntaxe de toutes les configurations Fluent Bit
```
