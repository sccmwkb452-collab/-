#!/bin/sh
# Reload nginx every 6 hours so certificates renewed by the certbot container
# are picked up without downtime.
(while :; do sleep 21600; nginx -s reload >/dev/null 2>&1; done) &
