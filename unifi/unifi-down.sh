#!/usr/bin/env bash
# Stop the UniFi controller. The AP keeps its config and keeps broadcasting.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE=/etc/iot-kit/unifi.env

sudo docker compose --env-file "$ENV_FILE" -f "$DIR/docker-compose.yml" down
echo "UniFi controller stopped."
