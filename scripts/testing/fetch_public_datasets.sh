#!/usr/bin/env bash
# Télécharge les jeux de journaux publics utilisés pour tester la normalisation (C9).
# Ils ne sont pas versionnés (licences propres à chaque projet) : test-data/public/ est ignoré par Git.
# Versions figées par commit : les résultats des tests sont reproductibles.
# Usage, depuis la racine du dépôt : bash scripts/testing/fetch_public_datasets.sh
set -euo pipefail

DIR=test-data/public
grep -qxF "$DIR/" .gitignore 2>/dev/null || echo "$DIR/" >> .gitignore
mkdir -p "$DIR/windows"

get() {   # $1 = dépôt GitHub, $2 = commit, $3 = chemin dans le dépôt, $4 = fichier local
  local url="https://raw.githubusercontent.com/$1/$2/$(python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1]))' "$3")"
  if [[ -s "$DIR/$4" ]]; then echo "déjà présent : $4"; return; fi
  curl -fsSL --retry 3 -o "$DIR/$4" "$url"
  echo "téléchargé : $4 ($1)"
}

# Linux (Loghub, LogPAI) : sshd et syslog d'un serveur Linux
LOGHUB=dd61d0952749ee7963bde24220d1be5ede023033
get logpai/loghub $LOGHUB OpenSSH/OpenSSH_2k.log linux-openssh.log
get logpai/loghub $LOGHUB Linux/Linux_2k.log linux-syslog.log

# Pare-feu Linux (Elastic Beats, module iptables : jeux de test)
BEATS=06c96caae748e1757452aa81494753eb1e8cbdba
get elastic/beats $BEATS x-pack/filebeat/module/iptables/log/test/iptables.log iptables.log
get elastic/beats $BEATS x-pack/filebeat/module/iptables/log/test/ipv6.log iptables-ipv6.log

# pfSense (Elastic Integrations, paquet pfsense : formats BSD et RFC 5424)
INTEG=52ef5eab69b6e593adfe17a42c81f35bda6a2afe
get elastic/integrations $INTEG packages/pfsense/data_stream/log/_dev/test/pipeline/test-pfsense-bsd.log pfsense-bsd.log
get elastic/integrations $INTEG packages/pfsense/data_stream/log/_dev/test/pipeline/test-pfsense-syslog.log pfsense-rfc5424.log

# Serveur web (Elastic Examples : 10 000 lignes au format combined)
EXAMPLES=6d86454ebb7a850bcd7e80abe86fe683370018a6
get elastic/examples $EXAMPLES "Common Data Formats/apache_logs/apache_logs" web-access.log

# Windows (EVTX-ATTACK-SAMPLES) : journaux Sécurité réels, convertis au format de l'agent Fluent Bit
EVTX=4ceed2f4706daf601c212a8f91c113dd85349a2c
get sbousseaden/EVTX-ATTACK-SAMPLES $EVTX "Credential Access/CA_4624_4625_LogonType2_LogonProc_chrome.evtx" windows/ca_4624_4625.evtx
get sbousseaden/EVTX-ATTACK-SAMPLES $EVTX "Lateral Movement/LM_WMI_4624_4688_TargetHost.evtx" windows/lm_wmi_4624_4688.evtx
get sbousseaden/EVTX-ATTACK-SAMPLES $EVTX "Privilege Escalation/NTLM2SelfRelay-med0x2e-security_4624_4688.evtx" windows/ntlm_relay_4624_4688.evtx
get sbousseaden/EVTX-ATTACK-SAMPLES $EVTX "Lateral Movement/LM_4624_mimikatz_sekurlsa_pth_source_machine.evtx" windows/pth_4624.evtx

uv run --quiet --with python-evtx==0.8.1 python scripts/testing/evtx_to_fluentbit.py "$DIR"/windows/*.evtx > "$DIR/windows-security.jsonl"
echo "converti : windows-security.jsonl ($(wc -l < "$DIR/windows-security.jsonl") événements)"
