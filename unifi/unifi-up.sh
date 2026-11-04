#!/usr/bin/env bash
# Start the UniFi controller. Only needed to (re)configure the AP.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE=/etc/iot-kit/unifi.env

sudo test -f "$ENV_FILE" || { echo "missing $ENV_FILE: run scripts/phase6-unifi.sh first" >&2; exit 1; }

sudo systemctl start docker
sudo docker compose --env-file "$ENV_FILE" -f "$DIR/docker-compose.yml" up -d

echo "Waiting for the controller (the first start takes a few minutes)..."
for _ in $(seq 1 90); do
  if curl -ksf -m 3 -o /dev/null https://127.0.0.1:8443/; then
    echo "UniFi controller is up: https://192.168.50.1:8443"
    echo "Stop it with: $DIR/unifi-down.sh"
    exit 0
  fi
  sleep 5
done

echo "Controller did not answer on :8443 after 7.5 min. Check: docker logs unifi" >&2
exit 1
