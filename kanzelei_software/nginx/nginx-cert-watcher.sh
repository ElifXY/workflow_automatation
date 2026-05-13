#!/bin/sh
# Hintergrund: (1) Bootstrap → TLS sobald Zertifikat da ist
#               (2) nginx -s reload wenn fullchain.pem sich ändert (Renew)
set -eu
DOMAIN="${DOMAIN:-kanzlei-automation.com}"
NGINX_ENV="${NGINX_ENV:-production}"
CERT="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
CONF="/etc/nginx/conf.d/default.conf"
TEMPLATE="/etc/nginx/build-conf.d/default.prod.conf.template"

last_ck=""
sleep 120
while sleep 300; do
  [ "$NGINX_ENV" = "development" ] && continue
  [ -f "$CERT" ] || continue
  if ! command -v envsubst >/dev/null 2>&1; then
    continue
  fi

  new_ck=$(cksum "$CERT" 2>/dev/null | awk '{print $1"-"$2}' || echo "")

  if ! grep -q 'listen 443' "$CONF" 2>/dev/null; then
    echo "[nginx-cert-watcher] Zertifikat vorhanden, wechsle auf TLS (DOMAIN=$DOMAIN)"
    envsubst '${DOMAIN}' < "$TEMPLATE" > "$CONF.tmp" && mv "$CONF.tmp" "$CONF"
    nginx -s reload 2>/dev/null || true
    last_ck="$new_ck"
    continue
  fi

  if [ -n "$new_ck" ] && [ "$new_ck" != "$last_ck" ]; then
    if [ -n "$last_ck" ]; then
      echo "[nginx-cert-watcher] Zertifikat geändert (Renew) — reload"
      nginx -s reload 2>/dev/null || true
    fi
    last_ck="$new_ck"
  fi
done
