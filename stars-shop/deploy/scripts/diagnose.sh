#!/usr/bin/env bash
# Health overview. --short prints only the summary.
source "$(dirname "$0")/lib.sh"
load_env
log "containers"
"${COMPOSE[@]}" ps
log "API health"
"${COMPOSE[@]}" exec -T api python -c "import urllib.request,json;print(urllib.request.urlopen('http://127.0.0.1:8000/api/health/ready',timeout=5).read().decode())" || warn "API is not healthy"
log "public endpoint"
curl -fsS -o /dev/null -w "https://$DOMAIN/api/health -> %{http_code} in %{time_total}s\n" "https://$DOMAIN/api/health" || warn "public HTTPS check failed"
log "configuration (no secrets)"
"${COMPOSE[@]}" exec -T api python -m starshop.cli check || true
if [ "${1:-}" = "--short" ]; then exit 0; fi
log "certificate expiry"
echo | openssl s_client -servername "$DOMAIN" -connect "$DOMAIN:443" 2>/dev/null | openssl x509 -noout -enddate || warn "could not read certificate"
log "Telegram webhook info (token hidden)"
"${COMPOSE[@]}" exec -T api python -c "
import json, os, urllib.request
t = os.environ.get('BOT_TOKEN', '')
info = json.load(urllib.request.urlopen(f'https://api.telegram.org/bot{t}/getWebhookInfo', timeout=10))['result']
print({k: info.get(k) for k in ('url', 'pending_update_count', 'last_error_date', 'last_error_message')})
" || warn "Telegram API unreachable"
log "disk"
df -h "$ROOT" | tail -1
log "recent errors (last 200 lines per service)"
for s in api worker bot web; do
  echo "--- $s"
  "${COMPOSE[@]}" logs --tail 200 "$s" 2>/dev/null | grep -iE '"level": "(ERROR|CRITICAL)"|error|traceback' | tail -5 || true
done
