# C26 — A-06 : cohérence du cache de sources et délai de révocation

Date : 24 novembre 2026. Aucune ligne de production n'a été modifiée pour A-06 : le
mécanisme existant (`SourcesCache`, `services/ingestion-gateway/src/gateway/sources_cache/__init__.py`)
était déjà correct. Ce document consigne la vérification effectuée et complète la
couverture de tests, conformément à la correction demandée par l'audit (« conserver un
délai de révocation explicite... test de cache périmé, test de source révoquée sur
connexion Syslog existante et HTTP »).

## Mécanisme réel (vérifié dans le code, pas supposé)

`SourcesCache` est un index en mémoire rafraîchi périodiquement
(`sources_refresh_s`, 30 s par défaut en Compose) depuis le référentiel de sources
(PostgreSQL en production, fichier JSON en test/développement). Deux garanties
découlent directement du code :

1. **Révocation prise en compte au prochain rafraîchissement.** `refresh()`
   reconstruit entièrement les index `_by_token_hash` et `_by_fingerprint` à partir des
   seuls identifiants valides retournés par le référentiel (`FileSourceRegistry._valid()`
   exclut tout credential dont `revoked_at` est renseigné). Un identifiant révoqué
   disparaît donc de l'index dès le rafraîchissement suivant — **délai explicite : au
   plus `sources_refresh_s` (30 s par défaut)**, pas immédiat.
2. **Cache périmé → aucune source acceptée.** La propriété `usable` compare
   `age_s` à `sources_max_stale_s` (300 s par défaut) ; `by_token_hash()` et
   `by_fingerprint()` retournent systématiquement `None` quand `usable` est faux, quel
   que soit leur contenu. Si le référentiel devient injoignable, l'index précédent reste
   utilisé pendant au plus `sources_max_stale_s`, puis **toute source est refusée** —
   une révocation ne peut donc jamais rester ignorée indéfiniment, y compris en cas de
   panne du référentiel.

Ce « délai de révocation explicite » demandé par l'audit est donc : **entre 0 et
`sources_refresh_s` en fonctionnement normal, et au plus `sources_max_stale_s` en cas de
panne du référentiel** — deux bornes déjà présentes dans `config.py` et déjà
commentées en ligne (`sources_max_stale_s: float = 300.0   # au-delà, refus (503)`).

## Ce qui manquait : la couverture de test de bout en bout

Le cache lui-même avait déjà un test de péremption
(`test_cache_perime_refuse_tout`), repris côté HTTP par
`test_referentiel_indisponible_503`. Ce qui manquait, et qu'aucun test n'exerçait
jusqu'ici :

- **Syslog** : une révocation décidée *pendant* qu'une connexion TCP/TLS est déjà
  ouverte. Contrairement à HTTP, Syslog est une connexion persistante : le certificat
  client n'est vérifié qu'à l'établissement de la connexion (TLS), pas à chaque trame.
  `SyslogServer.handle()` revérifie pourtant explicitement la validité de la source à
  chaque itération de sa boucle de lecture (`if self._cache.by_fingerprint(fingerprint)
  is None: ... break`), donc une révocation prend effet sans attendre la fermeture de la
  connexion — mais ce comportement n'était pas démontré par un test.
- **HTTP** : une révocation prise en compte sans redémarrage de la Gateway (HTTP
  étant sans état, chaque requête relit le cache — différent du cas Syslog, mais non
  démontré non plus).

## Tests ajoutés

- `services/ingestion-gateway/tests/test_syslog.py::test_source_revoquee_en_cours_de_connexion_ferme_sans_publier_la_suite` —
  une connexion Syslog TLS est établie avec un certificat valide ; après publication de la
  1re trame, le credential correspondant est révoqué dans le référentiel et le cache est
  rafraîchi (simulant une révocation décidée en cours de connexion, sans aucune nouvelle
  négociation TLS) ; la 2e trame, déjà présente dans le flux, n'est jamais publiée et la
  connexion est fermée. Confirme le comportement déjà implémenté par le `while True` de
  `handle()`.
- `services/ingestion-gateway/tests/test_http.py::test_source_revoquee_rejetee_sans_redemarrage_de_la_gateway` —
  une 1re requête HTTP avec un jeton valide est acceptée (202) ; le cache est ensuite
  mis dans l'état qu'aurait produit un `refresh()` réel après révocation (le jeton
  retiré de `_by_token_hash`) ; une 2e requête avec le même jeton est refusée (401),
  sans qu'aucun nouvel événement ne soit publié.

## Résultat

Suite complète `services/ingestion-gateway` : **48/48 PASSED** (46 précédents + 2
nouveaux pour A-06), aucune régression.

## Non modifié

Aucun fichier de production n'a été touché pour A-06 : le mécanisme de révocation et
de péremption du cache était déjà conforme à ce que demandait l'audit. Seule la
couverture de test était incomplète ; elle est maintenant comblée, et ce document tient
lieu de consignation du délai de révocation explicite demandé par l'audit (pas de
document de modèle de menace dédié trouvé dans le dépôt ; ce point peut être intégré à
un tel document s'il est créé ultérieurement, hors périmètre de cette phase).
