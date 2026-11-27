# C26 — Audit complet, corrections et compléments (27/11/2026)

Audit de l'ensemble du dépôt (sept services, interface, infrastructure, documentation) confronté
au cadrage (C1, C2) et à la conception (C3 à C25). Ce document recense les anomalies trouvées, leur
correction et les fonctions annoncées qui manquaient. Il complète `C26_cloture_audit_C6C7.md`.

**Réserve maintenue : F-2 (modèle de confiance mTLS des sources Syslog, A-13) reste EN ATTENTE.**
Rien n'a été implémenté ni choisi à ce sujet. L'interface se limite à l'enregistrement de
l'empreinte du certificat client, fonction qui existait déjà, sans présenter de modèle comme retenu.

## 1. Anomalies corrigées

| N° | Constat | Effet | Correction |
|---|---|---|---|
| B01 | Connexion : seul l'e-mail était accepté alors que l'écran demandait un identifiant | 401 pour un nom d'utilisateur valide | Connexion par e-mail ou nom d'utilisateur |
| B02 | Verrouillage après échecs (ES-01) non appliqué | Force brute possible sur les comptes | Compteur d'échecs, verrouillage temporaire (423), réinitialisation à la réactivation |
| B03 | `GET /sources` en erreur 500 : colonnes de C26 (hôte, IP, environnement, étiquettes, responsable) absentes du schéma | Écran Sources inutilisable | Migration `0008_sources_extend` |
| B04 | Adresse IP invalide → 500 ; 3ᵉ identifiant actif → 500 | Erreurs serveur au lieu de messages | Validation (422) ; conflits du déclencheur et de l'unicité en 409 |
| B05 | Commandes d'incident refusées (500/400) : fonctions de dépôt manquantes, charges utiles hors contrat `incident_command/v1` | Aucune action d'analyste possible | Fonctions ajoutées (commande, commentaire, nom d'utilisateur) ; charges utiles exactes du contrat |
| B06 | Réouverture d'incident : `closed_at` jamais remis à vide | Incident rouvert affiché comme clos | Sentinelle distinguant « ne pas modifier » et « vider » |
| B07 | Middleware d'audit décrit mais jamais monté | Journal d'audit (ES-07) vide | Audit des mutations et des connexions (succès et refus) |
| B08 | Aucune protection de l'API (ES-05) | Pas de limite de débit ni de taille, pas d'en-têtes de sécurité | Seau à jetons (429), corps limité (413), en-têtes de sécurité ; CORS restreint |
| B09 | Formateur de journaux JSON perdant les traces d'exception | Erreurs impossibles à diagnostiquer | Trace incluse dans le champ `error` |
| B10 | Métriques Prometheus étiquetées par URL réelle | Explosion du nombre de séries | Étiquette = modèle de route |
| B11 | Indexation : message acquitté avant l'écriture dans OpenSearch | Perte d'événements si OpenSearch échoue | Acquittement après indexation réussie, sinon nouvelle livraison différée |
| B12 | Identifiant des alertes indexées aléatoire ; modèles d'index stricts incompatibles avec les documents | Doublons, rejets d'indexation | `_id` = identifiant de l'alerte ; modèles alignés sur ECS |
| B13 | Couverture : `executemany` appelé sur la connexion ; heure de traitement mal lue | Service en erreur ; état « flux incomplet » jamais détecté | Curseur ; `baolsec.received_at` ; état FLUX_INCOMPLET quand le traitement s'arrête |
| B14 | Règles privées de données (EF-09) jamais calculées | Couverture sans conséquence visible | `sync_affected_rules` : ouverture et fermeture selon la cause |
| B15 | Cibles Prometheus fausses (ports et noms) | Supervision vide | Cibles corrigées, règles d'alerte `docker/prometheus/alerts.yml`, tableau Grafana |
| B16 | Deux chaînes de migrations divergentes (`migrations/` à la racine et `infrastructure/database`) | Schéma différent selon la commande lancée | Chaîne officielle unique `infrastructure/database` ; la migration F-3 y devient `0009_credentials_unicite` ; chaîne racine supprimée |
| B17 | Fichiers de correctifs non appliqués (`main_patch.py`, `compose_frontend_patch.txt`, `PATCH_INSTRUCTIONS.txt`), copies `.bak` et `.before-*` | Confusion sur le code réellement exécuté | Supprimés après report des corrections utiles |
| B18 | Interface : pages important des modules supprimés, vocabulaire ancien (« ELEVE », « RESOLU »), valeurs brutes à l'écran | Écrans en erreur ou incohérents avec le schéma C4 | Interface réécrite (section 3) |
| B19 | Service Incidents : le second gestionnaire de signal remplaçait le premier | Arrêt bloqué jusqu'au SIGKILL | Un seul gestionnaire qui arrête consommateur et publication |
| B20 | Paramètres de corrélation (C3 3.8) modifiables dans l'API mais jamais lus par le service Incidents | Réglages sans effet | Lecture de `config.settings` au plus une fois par minute ; migration `0010` alignant les enchaînements sur C3 |
| B21 | État global de supervision « indisponible » dès qu'OpenSearch ne répond pas | Fausse alarme : la chaîne continue sans recherche | « Dégradé » ; « indisponible » réservé à PostgreSQL et au broker |
| B22 | Adresse IP des sources renvoyée avec le masque (`10.0.0.5/32`) | Affichage trompeur | `host(ip_address)` |
| B23 | Recherche Lucene en 404 quand un index n'existe pas encore ; résultats non triés | Erreur au premier démarrage | `ignore_unavailable`, tri par date décroissante |
| B24 | Compte administrateur initial créé avec un mot de passe fixe connu | Compte par défaut devinable | `make admin-create` : mot de passe fourni ou tiré au hasard, affiché une fois |

## 2. Fonctions annoncées et ajoutées

| Référence | Fonction | Réalisation |
|---|---|---|
| EF-05 | Règles en YAML versionnées | Création et modification par définition YAML validée (`rule/v1`), version créée à chaque changement, historique consultable, code définitif |
| EF-06, EF-08 | Traitement des alertes et des incidents | Prise en charge, attribution, remise en attente, commentaires, clôture motivée, réouverture ; chronologie avec auteurs et textes |
| EF-09 | Couverture et règles affectées | États, historique, règles privées de données avec leur cause |
| EF-11 | Recherche d'événements | `GET /events` (période, source, utilisateur, IP, hôte, catégorie, résultat, texte) et détail d'un événement avec le message d'origine |
| EF-12 | Supervision | `GET /system/health` : services, PostgreSQL, OpenSearch, broker, retard des consommateurs |
| C5 | File de rejet consultable | `GET /dlq`, `GET /dlq/{seq}` (lecture seule) |
| C5 | Paramètres, rôles | `PATCH /settings/{clé}` borné ; `GET /roles` avec permissions |
| EF-01, EF-02, C7 | Ajout d'une source guidé | Assistant en quatre étapes : identité, raccordement, identifiant (jeton affiché une fois ou empreinte de certificat), configuration de l'agent et vérification de la réception du premier événement |
| ES-09 | Sauvegardes et rétention | Sauvegarde PostgreSQL quotidienne avec rotation ; instantané et purge des index OpenSearch ; `docs/deployment/sauvegarde_restauration.md` |
| C18 | Déploiement complet | `compose.yaml` racine : plateforme, interface HTTPS (nginx), Prometheus, Grafana ; ports d'exploitation liés à 127.0.0.1 |

## 3. Interface

Interface entièrement reprise : système de conception unique (`frontend/src/styles/app.css`),
polices auto-hébergées (aucun appel externe), libellés français issus des énumérations de C4,
navigation par rôle, états de chargement, d'erreur et de liste vide sur chaque écran, actions
confirmées par le serveur (le résultat réel de chaque commande est affiché), affichage adapté au
téléphone. Page d'accueil réécrite avec un contenu tiré du cadrage, sans chiffre ni client inventé.

Écrans : accueil, connexion ; analyste : tableau de bord, alertes, incidents et détail, événements,
recherche avancée, couverture, supervision, sources et règles en lecture ; administrateur : vue
d'ensemble, sources (assistant d'ajout, identifiants, raccordement), règles (éditeur, versions),
utilisateurs, paramètres, journal d'audit, file de rejet.

## 4. Vérifications effectuées

- Tests unitaires : API 78, passerelle 51, normalisation 97, détection 60, Incidents 96,
  couverture 30, indexation 15 ; interface 14 (Vitest) ; compilation TypeScript sans erreur.
- Tests d'intégration PostgreSQL (schéma, droits, règles, commandes d'incident) : 54 réussis,
  5 ignorés (ils demandent un broker de test).
- Chaîne réelle exécutée localement (PostgreSQL 16, NATS 2.15, tous les services) : journaux SSH
  envoyés à la passerelle → alertes AUTH-001 → incident « Force brute sur un compte — bob ·
  198.51.100.23 · srv-web-02 » ; prise en charge, commentaire, clôture motivée et réouverture
  depuis l'interface ; source ajoutée par l'assistant puis premier événement reçu et normalisé.
- Chaque écran contrôlé par capture (analyste et administrateur, 1440 px et 390 px).

## 5. Compléments après le premier déploiement (27/11/2026)

| Constat | Correction |
|---|---|
| Archive extraite par-dessus l'ancienne version : les fichiers retirés restaient sur le disque et faisaient échouer `tsc` dans l'image `frontend` | `scripts/deployment/nettoyer_fichiers_obsoletes.sh` (liste explicite, aperçu sans `--oui`) |
| `.env` antérieur sans les nouvelles variables | `scripts/deployment/complete_env.sh` (n'écrase aucune valeur, n'affiche aucun secret) |
| Contexte de construction de plus de 100 Mo par service (`.venv`, `.git`, `.env` envoyés au moteur Docker) | `.dockerignore` à la racine : seuls `services/`, `shared/` et `rules/` sont transmis |
| Certificat de l'interface absent : Docker crée un dossier vide à sa place et nginx redémarre en boucle | `make up` s'arrête avec la marche à suivre |
| Redirection HTTP → HTTPS toujours vers le port 443, même avec un port HTTPS personnalisé | modèle nginx complété au démarrage avec `FRONTEND_HTTPS_PORT` |
| `make admin-create` en erreur quand l'e-mail appartient déjà à un compte d'un autre identifiant | le compte est retrouvé par e-mail puis par identifiant ; conflit explicite seulement si les deux désignent des comptes différents |

**Mouvement et fluidité de l'interface** (sans bibliothèque ; tout est neutralisé par le réglage
système « réduire les animations », et aucun contenu n'attend une animation pour s'afficher) :
transition entre les pages, apparition en cascade des blocs et des lignes, indicateurs chiffrés qui
comptent jusqu'à leur valeur, ligne mise en évidence quand une alerte ou un incident arrive pendant
l'actualisation, point pulsant des éléments critiques, indicateur glissant des filtres et des
onglets, ouverture animée des fenêtres, panneaux et notifications, chronologie et barres qui se
tracent, secousse en cas d'erreur de connexion, assistant d'ajout de source animé (radar pendant
l'attente, coche à la réception), page d'accueil animée (révélation du titre, fond qui dérive,
sections qui apparaissent au défilement). Fluidité : barre d'activité discrète pendant les
chargements, liste précédente conservée (atténuée) pendant le changement de filtre, saisie des
filtres sans ralentissement, détail d'un incident préchargé au survol de sa ligne, retour immédiat
sur le bouton actionné.

**Lisibilité pour un non-développeur** (journaux, alertes et écrans techniques) :

| Écran ou outil | Avant | Après |
|---|---|---|
| Journal d'audit | requête HTTP brute (`PATCH /api/v1/sources/…`), identifiant technique | une phrase : « admin a désactivé la source « web-01 » », regroupée par jour, filtres par domaine (connexions, comptes, sources, règles, incidents et alertes, paramètres) et par personne ; motif du refus ou de l'échec en clair ; détail « ce qui a été demandé » sans aucun secret ; détails techniques repliés |
| Enregistrement de l'audit (API) | statut et durée seulement | nom de l'élément concerné, résumé des changements (jamais de mot de passe ni de jeton), motif d'un refus (403, 422, commande d'incident refusée par le service Incidents) |
| Alertes | règle et champs ECS | « Pourquoi cette alerte ? » (la règle racontée en clair : seuil, fenêtre, événements pris en compte), sens de la gravité, événements déclencheurs résumés en une phrase |
| Incident | critères R1–R4 et entrées de chronologie techniques | « Pourquoi dans cet incident » pour chaque alerte, chronologie en phrases, encadré « Ce que les alertes ont en commun » |
| Événements | catégorie et action ECS | « Ce qui s'est passé » en une phrase, champs nommés en français, ligne reçue telle quelle, document ECS replié |
| File de rejet | code de motif | explication et encadré « Que faire ? » par motif, source nommée |
| Couverture | motifs du service (`602s`) | motifs en clair (« aucun événement depuis 10 min, seuil de silence : 10 min ») |
| Supervision | noms de flux et de consommateurs NATS | files et étapes nommées en français (nom technique en second), colonnes expliquées, messages d'erreur traduits |
| Règles | YAML seul | encadré « En clair » ; catégories en français |
| Paramètres | couples `authentication > process` | relecture en clair des enchaînements, familles reconnues, saisie d'une famille inconnue refusée |
| Journaux des services | JSON brut de `docker compose logs` | `make journaux` : heure, service et niveau en français, contrôles de santé et lectures masqués (`--tout` pour tout voir), filtres `--service`, `--niveau`, `--depuis`, `--suivre` |

Correction associée : les panneaux latéraux et les fenêtres sont rendus hors de la page animée ; sur
une page courte, l'animation d'entrée les limitait à la hauteur du contenu.

Les entrées d'audit enregistrées avant cette version n'ont ni nom d'élément ni résumé : l'écran
retrouve le nom à partir des listes de comptes, de sources et de règles.

## 6. Limites connues

- OpenSearch n'a pas pu être exécuté dans l'environnement de vérification : recherche,
  indexation et maintenance des index sont vérifiées par leurs tests et par le comportement en
  absence d'OpenSearch (messages conservés dans le broker, écrans affichant l'indisponibilité).
- Les douze images ont été construites et la pile complète démarrée sur la machine de
  développement le 27/11/2026 (tous les services « healthy », OpenSearch compris) ; les
  corrections de la section 5, les animations et la lisibilité n'y ont pas encore été reconstruites.
- Les compteurs des filtres des listes d'alertes et d'incidents portent sur les 200 éléments les
  plus récents.
- **F-2 reste en attente de décision.**
