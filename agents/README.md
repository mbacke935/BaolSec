# Collecte — agents et relais (C7)

Uniquement des configurations : aucun agent n'est développé par l'équipe (C3 W1, C1 section 4).
Les agents envoient en HTTPS à la passerelle (C6), le relais en Syslog TLS.

| Dossier | Source | Transport | Ce qui est collecté |
|---|---|---|---|
| `fluent-bit/linux/fluent-bit.yaml` | serveur Linux avec rsyslog | HTTPS | `/var/log/auth.log` ; pare-feu iptables/nftables (journal du noyau) |
| `fluent-bit/linux/fluent-bit-journald.yaml` | serveur Linux sans `auth.log` | HTTPS | journald : facilités auth et authpriv ; pare-feu (noyau) |
| `fluent-bit/windows/fluent-bit.yaml` | poste ou serveur Windows | HTTPS | journal Sécurité |
| `fluent-bit/webapp/fluent-bit.yaml` | serveur de l'application web et du backend mobile | HTTPS | journal d'accès HTTP et journal applicatif |
| `syslog-relay/` | pfSense | Syslog TLS | tout ce que pfSense envoie au relais |
| `fluent-bit/test/` | — | HTTPS | agent des tests d'intégration (fichier de test) |

Versions de référence : Fluent Bit 5.1.5, rsyslog 8.2312 (Ubuntu 24.04).

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

## Relais Syslog pour pfSense

pfSense n'accueille pas d'agent. Il envoie ses journaux au relais (Statut > Journaux système >
Paramètres > Journalisation à distance : adresse du relais, port 514). Le relais :
- garde chaque message dans une **file persistante sur disque** (`queue.type LinkedList`,
  `queue.saveOnShutdown`, 1 Gio) tant que la passerelle n'a pas reçu le message ;
- transmet le message **inchangé** (`%rawmsg%`) en **Syslog TLS** (RFC 5425, comptage d'octets),
  avec son certificat client, et vérifie le nom de la passerelle dans son certificat.

```bash
docker build -t baolsec-syslog-relay agents/syslog-relay
docker run -d --name baolsec-syslog-relay -p 514:514/udp -p 514:514/tcp \
  -e BAOLSEC_GATEWAY_HOST=baolsec.example.local \
  -v /etc/baolsec-relay:/etc/baolsec-relay:ro -v baolsec-relay-spool:/var/spool/baolsec-relay \
  baolsec-syslog-relay
```

### Limites mesurées du chemin Syslog

| Situation | Résultat mesuré |
|---|---|
| Coupure réseau entre relais et passerelle (paquets perdus), puis rétablissement | aucun message perdu (50 + 200) |
| Passerelle arrêtée pendant l'envoi | 2 messages perdus sur 20 : les premiers envoyés après l'arrêt |
| Relais redémarré pendant que la passerelle est arrêtée | file conservée sur disque, rejouée à la reprise |

La perte à l'arrêt de la passerelle est propre au Syslog sur TCP simple : le protocole n'a pas
d'accusé applicatif, et un message écrit dans une connexion déjà fermée par l'autre côté est
perdu avant que l'émetteur ne détecte l'erreur. RELP corrigerait ce point ; il n'est pas pris en
charge par la passerelle dans cette version (C3 4.3 : « sinon la limite est documentée »).
Entre pfSense et le relais, le transport est UDP sur le réseau local : le relais doit être placé
au plus près de pfSense.

## Tests

```bash
make agents-up       # broker, passerelle, agent de test et relais (profil agents-test)
make test-agents     # coupure réseau puis reconnexion, comptage avant/après
make agents-check    # vérifie la syntaxe de toutes les configurations (Fluent Bit et rsyslog)
```
