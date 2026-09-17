#!/bin/sh
set -eu

: "${APP_SECRET:?APP_SECRET must be set}"
: "${BOOTSTRAP_SUPERADMIN_PASSWORD:?BOOTSTRAP_SUPERADMIN_PASSWORD must be set}"
: "${RADIUS_SHARED_SECRET:?RADIUS_SHARED_SECRET must be set}"

uvicorn app.main:app --host 0.0.0.0 --port 8080 &
api_pid=$!

attempt=0
until python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=2)" >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 30 ]; then
    echo "Net2Net API did not become ready" >&2
    kill -TERM "$api_pid" 2>/dev/null || true
    exit 1
  fi
  sleep 1
done

python -m app.freeradius_sync
freeradius -f &
radius_pid=$!

stop() {
  kill -TERM "$radius_pid" "$api_pid" 2>/dev/null || true
  wait "$radius_pid" "$api_pid" 2>/dev/null || true
}
trap stop INT TERM
wait "$api_pid"
stop
