#!/usr/bin/env bash
# Supprime les fichiers et dossiers retirés du dépôt lors de l'audit du 27/11/2026
# (docs/conception/C26_audit_complet_corrections.md).
#
# À lancer une fois si la nouvelle version a été extraite PAR-DESSUS l'ancienne : l'extraction
# ajoute et remplace des fichiers mais ne supprime rien. Les anciens fichiers de l'interface
# (src/api/resources.ts, src/hooks/useAuth.ts, …) font alors échouer « tsc » pendant la
# construction de l'image frontend.
#
# Seuls les chemins listés ci-dessous sont supprimés ; .env et vos données ne sont pas touchés.
# Usage, depuis la racine du dépôt :
#   bash scripts/deployment/nettoyer_fichiers_obsoletes.sh          # affiche ce qui serait supprimé
#   bash scripts/deployment/nettoyer_fichiers_obsoletes.sh --oui    # supprime
set -euo pipefail
cd "$(dirname "$0")/../.."

OBSOLETES=(
  "migrations"
  "services/api"
  "frontend/src/features"
  "frontend/src/app"
  "frontend/src/services"
  "frontend/src/stores"
  "frontend/src/utils"
  "frontend/src/components/__tests__"
  "frontend/src/pages/__tests__"
  "frontend/nginx.conf"
  "CHANGEMENTS.txt"
  "compose_frontend_patch.txt"
  "frontend/PATCH_INSTRUCTIONS.txt"
  "frontend/public/.gitkeep"
  "frontend/public/assets/Futuristic_global_threat_map_visualization__dark_background_.png"
  "frontend/public/assets/Gemini_Generated_Image_yfy78kyfy78kyfy7(1).jpeg"
  "frontend/public/assets/Gemini_Generated_Image_yfy78kyfy78kyfy7(2).jpeg"
  "frontend/public/assets/Gemini_Generated_Image_yfy78kyfy78kyfy7(3).jpeg"
  "frontend/public/assets/Gemini_Generated_Image_yfy78kyfy78kyfy7(4).jpeg"
  "frontend/public/assets/Gemini_Generated_Image_yfy78kyfy78kyfy7.jpeg"
  "frontend/public/assets/Logo.jpeg"
  "frontend/public/assets/Luxury_dark_cybersecurity_SIEM_hero_background__deep_navy_bl.png"
  "frontend/public/assets/logo.jpg"
  "frontend/src/api/analyst.ts"
  "frontend/src/api/resources.ts"
  "frontend/src/assets/.gitkeep"
  "frontend/src/assets/logo.jpg"
  "frontend/src/components/.gitkeep"
  "frontend/src/components/AdminLayout.tsx"
  "frontend/src/components/AnalystLayout.tsx"
  "frontend/src/components/Modal.tsx"
  "frontend/src/hooks/.gitkeep"
  "frontend/src/hooks/useAuth.ts"
  "frontend/src/lib/.gitkeep"
  "frontend/src/lib/ui.ts"
  "frontend/src/pages/IncidentsPage.tsx"
  "frontend/src/pages/OverviewPage.tsx"
  "frontend/src/styles/design-system.css"
  "frontend/src/styles/maquette.css"
  "frontend/src/types/.gitkeep"
  "infrastructure/prometheus/prometheus.yml"
  "main_patch.py"
  "services/coverage-worker/Dockerfile.Dockerfile.bak"
  "services/coverage-worker/src/coverage/repositories.py.bak"
  "services/coverage-worker/src/coverage/repositories.py.before-schema-fix"
  "services/coverage-worker/tests/test_tracker.py.bak"
  "shared/python-common/src/baolsec_common/messaging/nats_adapter.py.before-fetch-timeout-fix"
)

present=()
for p in "${OBSOLETES[@]}"; do [ -e "$p" ] && present+=("$p"); done
if [ "${#present[@]}" -eq 0 ]; then echo "Aucun fichier obsolète : rien à faire."; exit 0; fi

printf '%s\n' "${present[@]}"
if [ "${1:-}" != "--oui" ]; then
  echo
  echo "${#present[@]} élément(s) obsolète(s). Relancer avec --oui pour les supprimer."
  exit 0
fi
rm -rf -- "${present[@]}"
# Dossiers de l'ancienne interface restés vides
find frontend/src frontend/public -type d -empty -delete 2>/dev/null || true
echo "${#present[@]} élément(s) supprimé(s)."
