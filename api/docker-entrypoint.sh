#!/bin/sh
set -eu

if [ "$(id -u)" = "0" ]; then
  mkdir -p /app/data/uploads
  chown -R appuser:appuser /app/data
  exec su appuser -s /bin/sh -c "exec $*"
fi

exec "$@"
