#!/bin/sh
# Picks the nginx site before the image renders templates (20-envsubst-on-templates.sh):
# HTTPS once a certificate exists for $DOMAIN, otherwise plain HTTP so that
# Let's Encrypt can complete the HTTP-01 challenge (deploy/scripts/init-letsencrypt.sh).
set -eu
mkdir -p /etc/nginx/templates
if [ -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]; then
  echo "select-site: certificate found for ${DOMAIN}, enabling HTTPS"
  cp /etc/nginx/sites/https.conf.template /etc/nginx/templates/default.conf.template
else
  echo "select-site: no certificate for ${DOMAIN} yet, serving HTTP only"
  cp /etc/nginx/sites/http.conf.template /etc/nginx/templates/default.conf.template
fi
