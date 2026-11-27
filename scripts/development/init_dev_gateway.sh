#!/usr/bin/env bash
# Prépare l'environnement de développement de la passerelle d'ingestion :
#   - AC des sources, certificat serveur de la passerelle, certificat client pour l'entrée Syslog TLS directe ;
#   - un certificat signé par une autre AC (tests : il doit être refusé) ;
#   - le référentiel des sources de développement (sources.json) et leurs jetons (tokens.env).
# Tout est écrit dans infrastructure/tls/dev/ (ignoré par Git). Usage, depuis la racine du dépôt :
#   bash scripts/development/init_dev_gateway.sh
set -euo pipefail

DIR=infrastructure/tls/dev
DAYS=825
# Clés et jetons de développement : jamais versionnés (ES-08)
grep -qxF "$DIR/" .gitignore 2>/dev/null || echo "$DIR/" >> .gitignore
grep -qxF "test-data/runtime/" .gitignore 2>/dev/null || echo "test-data/runtime/" >> .gitignore
mkdir -p test-data/runtime/agent
mkdir -p "$DIR"
cd "$DIR"

# Variables des agents de test (C7) : jeton de la source dev-linux (agent) et dev-pfsense (collecteur Syslog)
write_agent_env() {
  grep '^DEV_TOKEN_LINUX=' tokens.env | sed 's/^DEV_TOKEN_LINUX=/BAOLSEC_SOURCE_TOKEN=/' > agent-test.env
  grep '^DEV_TOKEN_PFSENSE=' tokens.env | sed 's/^DEV_TOKEN_PFSENSE=/BAOLSEC_SOURCE_TOKEN=/' > collector.env
  chmod 644 agent-test.env collector.env   # lus par les conteneurs de test ; jetons de développement uniquement
}

# Certificat HTTPS de l'interface (ES-04 : navigateur → API chiffré), signé par l'AC de développement.
# Généré aussi sur un environnement déjà initialisé (ajout C26), sans toucher au reste.
frontend_cert() {
  openssl req -newkey rsa:2048 -nodes -subj "/O=BaolSec dev/CN=localhost" -keyout frontend.key -out frontend.csr 2>/dev/null
  openssl x509 -req -in frontend.csr -CA sources-ca.crt -CAkey sources-ca.key -CAcreateserial -days "$DAYS" \
    -out frontend.crt -extfile <(printf '%s\n' "subjectAltName=DNS:localhost,DNS:frontend,IP:127.0.0.1" \
      "extendedKeyUsage=serverAuth" "basicConstraints=critical,CA:FALSE" \
      "keyUsage=critical,digitalSignature,keyEncipherment") 2>/dev/null
  rm -f frontend.csr
  chmod 644 frontend.crt frontend.key   # lus par le conteneur nginx ; certificat de développement uniquement
  echo "certificat HTTPS de l'interface écrit (frontend.crt)"
}

if [[ -f sources-ca.crt && "${1:-}" != "--force" ]]; then
  [[ -f frontend.crt ]] || frontend_cert
  if ! grep -q '^DEV_TOKEN_PFSENSE=' tokens.env 2>/dev/null; then
    echo "Fichier tokens.env incomplet (DEV_TOKEN_PFSENSE absent) : relancer avec --force pour le régénérer."
    exit 1
  fi
  [[ -f agent-test.env && -f collector.env ]] || { write_agent_env; echo "agent-test.env et collector.env écrits"; }
  echo "Déjà initialisé ($DIR). Relancer avec --force pour tout régénérer."
  exit 0
fi

subj() { echo "/O=BaolSec dev/CN=$1"; }

# AC des sources et de la passerelle (développement uniquement)
# Extensions exigées par les vérifications strictes (Python 3.13+, OpenSSL 3) : AC marquée critique.
CA_EXT=(-addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,keyCertSign,cRLSign"
        -addext "subjectKeyIdentifier=hash")
openssl req -x509 -newkey rsa:3072 -nodes -days "$DAYS" -subj "$(subj 'BaolSec dev CA')" "${CA_EXT[@]}" \
  -keyout sources-ca.key -out sources-ca.crt 2>/dev/null

sign() {  # $1 = nom du fichier, $2 = CN, $3 = extensions
  openssl req -newkey rsa:2048 -nodes -subj "$(subj "$2")" -keyout "$1.key" -out "$1.csr" 2>/dev/null
  openssl x509 -req -in "$1.csr" -CA sources-ca.crt -CAkey sources-ca.key -CAcreateserial \
    -days "$DAYS" -out "$1.crt" -extfile <(printf '%s\n' "$3" "basicConstraints=critical,CA:FALSE" \
      "keyUsage=critical,digitalSignature,keyEncipherment" "subjectKeyIdentifier=hash" \
      "authorityKeyIdentifier=keyid") 2>/dev/null
  rm -f "$1.csr"
}

sign gateway "ingestion-gateway" \
  "subjectAltName=DNS:localhost,DNS:ingestion-gateway,IP:127.0.0.1
extendedKeyUsage=serverAuth"
sign syslog-client "syslog-client" "extendedKeyUsage=clientAuth"

# Certificat client signé par une AC étrangère : doit être refusé par la passerelle
openssl req -x509 -newkey rsa:2048 -nodes -days "$DAYS" -subj "$(subj 'rogue')" "${CA_EXT[@]}" \
  -keyout rogue.key -out rogue.crt 2>/dev/null

# Le conteneur (utilisateur 10001) doit pouvoir lire les clés : acceptable en développement seulement.
chmod 644 ./*.key ./*.crt

python3 - <<'EOF'
import hashlib, json, secrets, subprocess, uuid

def fingerprint(path):
    der = subprocess.run(["openssl", "x509", "-in", path, "-outform", "DER"], capture_output=True, check=True).stdout
    return hashlib.sha256(der).hexdigest()

tokens, sources = {}, []
# host et criticality : colonnes de config.sources lues par l'enrichissement (C10)
for name, stype, var, host, crit in [("dev-linux", "linux", "DEV_TOKEN_LINUX", "srv-test", "moyenne"),
                                     ("dev-windows", "windows", "DEV_TOKEN_WINDOWS", "pc-dev-windows", "faible"),
                                     ("dev-webapp", "http", "DEV_TOKEN_WEBAPP", "web-dev", "elevee"),
                                     ("dev-pfsense", "firewall", "DEV_TOKEN_PFSENSE", "fw-edge-01", "critique")]:
    token = "bsk_" + secrets.token_urlsafe(32)
    tokens[var] = token
    sources.append({"id": str(uuid.uuid4()), "name": name, "source_type": stype, "transport": "https",
                    "ingestion_mode": "direct", "host": host, "criticality": crit, "is_enabled": True,
                    "credentials": [{"credential_type": "token",
                                     "secret_hash": hashlib.sha256(token.encode()).hexdigest()}]})
sources.append({"id": str(uuid.uuid4()), "name": "dev-syslog-direct", "source_type": "firewall", "transport": "syslog",
                "ingestion_mode": "direct", "is_enabled": True,
                "credentials": [{"credential_type": "client_cert",
                                 "cert_fingerprint": fingerprint("syslog-client.crt")}]})
with open("sources.json", "w", encoding="utf-8") as f:
    json.dump({"sources": sources}, f, indent=2)
with open("tokens.env", "w", encoding="utf-8") as f:
    f.writelines(f"{k}={v}\n" for k, v in tokens.items())
print("sources.json et tokens.env écrits")
EOF
chmod 666 sources.json   # les tests de révocation le modifient
chmod 600 tokens.env
write_agent_env
echo "Environnement de développement prêt dans $DIR"

frontend_cert
