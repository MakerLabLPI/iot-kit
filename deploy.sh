#!/usr/bin/env bash
# Run on your computer: copy this folder to ~/iot-kit on the Pi.
#   ./deploy.sh                      # pi@iot-kit.local
#   ./deploy.sh pi@192.168.50.1
# Nothing on the Pi lives only in ~/iot-kit (state is in /etc/iot-kit and
# /var/lib/iot-kit), so --delete is safe.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

HOST=${1:-pi@iot-kit.local}

rsync -az --delete \
  --exclude .git --exclude .DS_Store --exclude .claude --exclude .env \
  ./ "$HOST:iot-kit/"
echo "Deployed to $HOST:~/iot-kit"
