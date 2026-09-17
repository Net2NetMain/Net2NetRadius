#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -eq 0 ]]; then
  SUDO=""
else
  SUDO="sudo"
fi

echo "Installing PostgreSQL, FreeRADIUS, Redis and development dependencies..."
$SUDO apt-get update
$SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y \
  postgresql postgresql-contrib freeradius freeradius-postgresql freeradius-utils \
  redis-server python3 python3-venv python3-pip build-essential libpq-dev jq curl

$SUDO systemctl enable postgresql freeradius redis-server
$SUDO systemctl start postgresql freeradius redis-server

echo "Verifying installed services..."
$SUDO systemctl is-active --quiet postgresql
$SUDO systemctl is-active --quiet freeradius
$SUDO systemctl is-active --quiet redis-server
$SUDO freeradius -XC >/dev/null
test "$($SUDO redis-cli ping)" = "PONG"

echo "Base services are installed and healthy. No live router configuration was changed."
