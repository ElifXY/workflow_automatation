#!/bin/sh
set -e
export DOMAIN="${DOMAIN:-kanzlei-automation.com}"
NGINX_ENV="${NGINX_ENV:-production}"

rm -f /etc/nginx/conf.d/default.conf
rm -f /etc/nginx/http-globals.conf

if [ "$NGINX_ENV" = "development" ]; then
  echo "[nginx] http-globals (dev + upstream frontend) → /etc/nginx/http-globals.conf"
  cp /etc/nginx/build-conf.d/00-http-globals.dev.conf /etc/nginx/http-globals.conf
  echo "[nginx] development → conf.d/default.conf (aus build-conf.d/default.conf)"
  cp /etc/nginx/build-conf.d/default.conf /etc/nginx/conf.d/default.conf
else
  echo "[nginx] http-globals (production) → /etc/nginx/http-globals.conf"
  cp /etc/nginx/build-conf.d/00-http-globals.prod.conf /etc/nginx/http-globals.conf
  if ! command -v envsubst >/dev/null 2>&1; then
    echo "envsubst fehlt" >&2
    exit 1
  fi
  CERT="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
  if [ -f "$CERT" ]; then
    echo "[nginx] production + TLS (DOMAIN=$DOMAIN)"
    envsubst '${DOMAIN}' < /etc/nginx/build-conf.d/default.prod.conf.template > /etc/nginx/conf.d/default.conf
  else
    echo "[nginx] bootstrap HTTP-only (kein Zertifikat unter $CERT)."
    envsubst '${DOMAIN}' < /etc/nginx/build-conf.d/default.bootstrap.conf.template > /etc/nginx/conf.d/default.conf
  fi
fi

# Cloudflare: echte Client-IP + korrektes Scheme (521-/Proxy-Diagnose)
if [ "${CLOUDFLARE_PROXY:-0}" = "1" ] || [ "${CLOUDFLARE_PROXY:-}" = "true" ]; then
  echo "[nginx] CLOUDFLARE_PROXY aktiv → real_ip an http-globals anhängen"
  cat /etc/nginx/build-conf.d/cloudflare-realip.snippet >> /etc/nginx/http-globals.conf
fi

# Immer: https://localhost mit selbstsigniertem Zertifikat (curl -k https://localhost)
if [ -f /etc/nginx/certs/localhost.crt ] && [ -f /etc/nginx/certs/localhost.key ]; then
  cp /etc/nginx/build-conf.d/10-localhost-https.conf /etc/nginx/conf.d/10-localhost-https.conf
  echo "[nginx] https://localhost (self-signed) aktiv"
fi

if [ "$NGINX_ENV" != "development" ] && [ -x /etc/nginx/nginx-cert-watcher.sh ]; then
  nohup /etc/nginx/nginx-cert-watcher.sh >>/var/log/nginx/cert-watcher.log 2>&1 &
fi

exec nginx -g 'daemon off;'
