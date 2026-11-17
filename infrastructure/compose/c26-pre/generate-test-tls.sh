#!/usr/bin/env bash
# Génère exclusivement des identifiants de test C26 ; ne jamais utiliser en production.
# Usage futur autorisé : bash generate-test-tls.sh /chemin/absolu/baolsec-c26-tls
set -euo pipefail
target=${1:?chemin absolu C26 requis}
case "$target" in /*) ;; *) echo "Le chemin doit être absolu" >&2; exit 2;; esac
umask 077
mkdir -p "$target"
cd "$target"
openssl req -x509 -newkey rsa:3072 -nodes -days 30 -subj '/O=BaolSec C26 test/CN=BaolSec C26 Test CA' \
  -addext 'basicConstraints=critical,CA:TRUE' -addext 'keyUsage=critical,keyCertSign,cRLSign' \
  -keyout sources-ca.key -out sources-ca.crt 2>/dev/null
openssl req -newkey rsa:2048 -nodes -subj '/O=BaolSec C26 test/CN=ingestion-gateway' -keyout gateway.key -out gateway.csr 2>/dev/null
openssl x509 -req -in gateway.csr -CA sources-ca.crt -CAkey sources-ca.key -CAcreateserial -days 30 -out gateway.crt \
  -extfile <(printf '%s\n' 'subjectAltName=DNS:localhost,DNS:ingestion-gateway,IP:127.0.0.1' 'extendedKeyUsage=serverAuth') 2>/dev/null
rm -f gateway.csr sources-ca.srl
python3 - <<'PY'
import hashlib, json, secrets, uuid
token = "bsk_c26_" + secrets.token_urlsafe(32)
source_id = str(uuid.uuid4())
data = {"sources": [{"id": source_id, "name": "c26-linux", "source_type": "linux", "transport": "https", "ingestion_mode": "direct", "host": "c26-host", "criticality": "moyenne", "is_enabled": True, "credentials": [{"credential_type": "token", "secret_hash": hashlib.sha256(token.encode()).hexdigest()}]}]}
open("sources.json", "w", encoding="utf-8").write(json.dumps(data, indent=2) + "\n")
open("tokens.env", "w", encoding="utf-8").write("C26_HTTPS_TOKEN=" + token + "\n")
PY
chmod 600 *.key tokens.env
chmod 644 *.crt sources.json
echo "Artefacts TLS/test C26 créés dans $target (clés et token non affichés)."
