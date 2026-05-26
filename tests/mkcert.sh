#!/usr/bin/env bash
set -e

command -v mkcert &>/dev/null || { echo "mkcert requis : sudo apt install mkcert"; exit 1; }

# CA système
mkcert -install

# Cert wildcard — seulement si absent
CERT="_wildcard.127.0.0.1.nip.io.pem"
if [[ ! -f "$CERT" ]]; then
  mkcert "*.127.0.0.1.nip.io"
  echo "Cert wildcard généré"
else
  echo "Cert wildcard déjà présent, skipping"
fi

# Copy mkcert CA for Keycloak trust store
cp "$(mkcert -CAROOT)/rootCA.pem" ./rootCA.pem
echo "CA mkcert copiée pour Keycloak (rootCA.pem)"

# Firefox Snap
FIREFOX_PROFILE=$(find ~/snap/firefox/common/.mozilla/firefox -name "*.default*" -type d 2>/dev/null | head -1)
if [[ -n "$FIREFOX_PROFILE" ]]; then
  command -v certutil &>/dev/null || { echo "certutil requis : sudo apt install libnss3-tools"; exit 1; }
  CA_NICK="mkcert $(hostname)"
  ALREADY=$(certutil -L -d "sql:$FIREFOX_PROFILE" 2>/dev/null | grep -F "$CA_NICK" || true)
  if [[ -z "$ALREADY" ]]; then
    certutil -A \
      -n "$CA_NICK" \
      -t "CT,," \
      -i "$(mkcert -CAROOT)/rootCA.pem" \
      -d "sql:$FIREFOX_PROFILE"
    echo "CA mkcert installée dans Firefox Snap"
  else
    echo "CA mkcert déjà présente dans Firefox Snap, skipping"
  fi
else
  echo "Firefox Snap non détecté, skipping"
fi