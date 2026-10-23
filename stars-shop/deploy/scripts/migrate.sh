#!/usr/bin/env bash
# Apply database migrations (safe to run repeatedly).
source "$(dirname "$0")/lib.sh"
load_env
"${COMPOSE[@]}" build migrate
"${COMPOSE[@]}" run --rm migrate
log "migrations applied"
