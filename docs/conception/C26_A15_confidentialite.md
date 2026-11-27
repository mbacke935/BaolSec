# C26 — A-15 : fichier `.env` dans l'archive (confidentialité)

Date : 24 novembre 2026.

## Vérification effectuée

Recherche exhaustive d'un fichier `.env` dans l'archive de travail courante
(`baolsec_tar_5.xz`, extraite dans `work_v5/`) : **aucun fichier `.env` trouvé**, à la
racine ni ailleurs dans le dépôt. Seul `.env.example` est présent (un gabarit sans
secret, avec des champs vides ou des placeholders — vérifié, pas de valeur réelle).

`.gitignore` exclut déjà correctement `.env` et `.env.*`.

## Conclusion (initiale)

Le constat A-15 de l'audit (fichier `.env` non versionné présent dans l'archive
transmise à l'auditeur) ne s'applique pas à l'archive `baolsec_tar_5.xz` traitée dans
cette phase : elle ne contient aucun `.env`. Rien à purger ni à faire roter ici.

**Rappel permanent (règle de session, déjà en vigueur, reconfirmée)** : aucun fichier
`.env` ni `.gitignore` ne sera inclus dans l'archive finale livrée à l'utilisateur à la
clôture de cette phase, par précaution, même si aucun des deux n'a été trouvé contenant
de secret dans cette itération.

## Correction (24/11/2026, F-1/F-5) : la conclusion « rien à purger » était erronée

L'audit de clôture mené après cette conclusion a montré qu'elle ne portait que sur le
nom de fichier littéral `.env`, et que la commande `tar --exclude` alors utilisée pour
construire l'archive livrée (`baolsec_corrige_A13_complet.tar.xz`) n'excluait ni les
fichiers `*.env`-suffixés, ni `*.key`/`*.pem`, ni le répertoire
`infrastructure/tls/dev/` — pourtant explicitement exclu par le `.gitignore` du dépôt.
**Cette archive contenait réellement** des clés privées (`gateway.key`, `rogue.key`,
`sources-ca.key`, `syslog-client.key`, `syslog-relay.key`) et des fichiers de secrets de
développement (`tokens.env`, `collector.env`, `agent-test.env`) — confirmé par
extraction et recherche exhaustive, pas par supposition. C'est le constat **F-1**
(bloquant) du rapport d'audit.

**Correction appliquée** : la méthode de construction de l'archive a été remplacée par
un mécanisme qui interprète réellement le `.gitignore` du dépôt (bibliothèque
`pathspec`, y compris la négation `!.env.example`), au lieu d'une liste d'exclusions
maintenue à la main. La nouvelle archive (`baolsec_corrige_A13_v2_sans_secrets.tar.xz`)
a été vérifiée deux fois (construction puis ré-extraction indépendante) : recherche
exhaustive de motifs de noms de fichiers (`*.key`, `*.pem`, `.env*`), recherche de
contenu (`BEGIN...PRIVATE KEY`, `_TOKEN=`, `_SECRET=`, `_PASSWORD=`, `API_KEY=`), et
comparaison programmatique complète (670 fichiers, 0 différence) entre l'archive extraite
et le dépôt filtré par la même logique de `.gitignore`. Livraison autorisée par
l'utilisateur après ce contrôle.

**Point non tranché, signalé et non résolu** : la nouvelle méthode exclut aussi
`infrastructure/compose/c26-pre/.env.c26.example` et `.env.prepared.example`, qui ne
correspondent pas à la seule négation `!.env.example` du `.gitignore`. Un document de
conception antérieur (`C26_PRE_preparation_environnement.md`) affirme que ces fichiers
contiennent « des variables et placeholders sans secret » — affirmation **non confirmée**
par cette vérification : une analyse non-disclosive (longueur des valeurs, homogénéité
des caractères, recherche de mots-clés de type placeholder) montre que leurs valeurs ne
ressemblent pas à de simples placeholders vides, bien qu'une comparaison par hachage
SHA-256 confirme qu'elles sont différentes des valeurs réelles actuelles du `.env.c26`
correspondant (donc pas une copie fuitée de secrets actuellement valides). **Il reste
donc un doute non résolu sur l'origine exacte de ces deux fichiers** — leur exclusion de
l'archive v2 est une précaution justifiée dans tous les cas, mais ne doit pas être lue
comme une confirmation qu'ils contenaient effectivement un secret, ni comme une
infirmation de l'affirmation de `C26_PRE_preparation_environnement.md`. Ce document
(`C26_PRE_preparation_environnement.md`) n'a pas été corrigé dans cette phase : sa
vérification/correction, si elle s'avère nécessaire, n'était pas demandée pour F-5 et
reste ouverte pour une session ultérieure.

**Conclusion révisée** : la conclusion initiale « rien à purger » (ci-dessus) est
**annulée** pour l'archive alors en circulation. L'archive corrigée et vérifiée
(v2) est la seule à livrer désormais ; l'ancienne archive
(`baolsec_corrige_A13_complet.tar.xz`) contenait des secrets réels et ne doit plus être
distribuée.
