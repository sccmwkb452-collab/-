#!/usr/bin/env bash
# Obtains a Let's Encrypt certificate and switches nginx to HTTPS.
# Requirements: DNS A record of DOMAIN points to this server, ports 80/443 open.
# LETSENCRYPT_STAGING=1 uses the staging CA (for test runs, avoids rate limits).
source "$(dirname "$0")/lib.sh"
load_env
[ -n "${LETSENCRYPT_EMAIL:-}" ] || die "set LETSENCRYPT_EMAIL in .env"
STAGING_ARG=""
[ "${LETSENCRYPT_STAGING:-0}" = "1" ] && STAGING_ARG="--staging"

if [ -f "$ROOT/deploy/certbot/conf/live/$DOMAIN/fullchain.pem" ]; then
  log "certificate for $DOMAIN already exists; renewal runs automatically in the certbot container"
  exit 0
fi

"${COMPOSE[@]}" up -d web   # serves HTTP only while there is no certificate
sleep 3
log "requesting certificate for $DOMAIN"
"${COMPOSE[@]}" run --rm --entrypoint certbot certbot certonly --webroot -w /var/www/certbot \
  -d "$DOMAIN" --email "$LETSENCRYPT_EMAIL" --agree-tos --no-eff-email --non-interactive $STAGING_ARG \
  || die "certificate request failed: check DNS for $DOMAIN and that port 80 is reachable, then re-run"
log "switching nginx to HTTPS"
"${COMPOSE[@]}" restart web
log "HTTPS is active: https://$DOMAIN"
