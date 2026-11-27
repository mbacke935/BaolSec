#!/usr/bin/env bash
# Complète un .env existant avec les variables ajoutées depuis sa création (voir .env.example).
#
# - Les valeurs déjà présentes ne sont jamais modifiées.
# - Les secrets manquants sont tirés au hasard ; aucun n'est affiché.
# - POSTGRES_PASSWORD, BROKER_TOKEN et SVC_*_PASSWORD ne sont pas générés : s'ils manquent, le
#   script le signale. Une base déjà créée garde son mot de passe d'origine : en mettre un nouveau
#   empêcherait d'y accéder.
# - Copie de sauvegarde : .env.sauvegarde
#
# Usage, depuis la racine du dépôt : bash scripts/deployment/complete_env.sh
set -euo pipefail
cd "$(dirname "$0")/../.."

if [ ! -f .env ]; then
  echo ".env absent : cp .env.example .env, puis remplacer chaque <secret>." >&2
  exit 1
fi
cp .env .env.sauvegarde

gen() { openssl rand -base64 48 | tr -d '/+=\n' | cut -c1-32; }
add() {   # ajoute la variable seulement si elle est absente ou vide
  if ! grep -q "^$1=." .env; then
    sed -i "/^$1=/d" .env
    printf '%s=%s\n' "$1" "$2" >> .env
    echo "ajoutée : $1"
  fi
}

add GRAFANA_PASSWORD           "$(gen)"
add JWT_SECRET                 "$(gen)"
add INCIDENTS_COMMAND_TOKEN    "$(gen)"
add OPENSEARCH_PASSWORD        "Os$(gen)9!"     # majuscule, minuscule, chiffre et caractère spécial
add OPENSEARCH_USER            admin
add OPENSEARCH_URL             https://opensearch:9200
add OPENSEARCH_VERIFY_CERTS    false
add BROKER_URL                 nats://broker:4222
add GATEWAY_SOURCE_REGISTRY    postgres
add GATEWAY_POSTGRES_DSN       'postgresql://svc_passerelle:${SVC_PASSERELLE_PASSWORD}@postgresql:5432/baolsec'
add NORMALIZER_SOURCE_REGISTRY postgres
add NORMALIZER_POSTGRES_DSN    'postgresql://svc_normalisation:${SVC_NORMALISATION_PASSWORD}@postgresql:5432/baolsec'
add CORS_ORIGINS               https://localhost

missing=0
for v in POSTGRES_PASSWORD BROKER_TOKEN SVC_API_PASSWORD SVC_PASSERELLE_PASSWORD SVC_NORMALISATION_PASSWORD \
         SVC_DETECTION_PASSWORD SVC_INCIDENTS_PASSWORD SVC_COUVERTURE_PASSWORD; do
  if ! grep -q "^$v=." .env; then echo "À RENSEIGNER vous-même : $v"; missing=1; fi
done

chmod 600 .env
if [ "$missing" -eq 0 ] && docker compose --env-file .env -f compose.yaml config -q; then
  echo "configuration valide"
fi
