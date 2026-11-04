#!/usr/bin/env bash
# Phase 7: web UIs. Needs internet (packages, images, npm).
#   Cockpit     native  https://192.168.50.1:9090   router admin, login "pi"
#   Node-RED    docker  http://192.168.50.1:1880    flows + /dashboard
#   MQTTX Web   docker  http://192.168.50.1:8090    MQTT client in the browser
# Cockpit manages the host itself (systemd, NetworkManager), so it cannot
# live in a container.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
need_root
log "Phase 7: web UIs"

command -v docker >/dev/null || die "Docker is missing: run scripts/install-docker.sh first"

export DEBIAN_FRONTEND=noninteractive
COMPOSE=(docker compose -f "$KIT_DIR/tools/docker-compose.yml")
NR_ETC=/etc/iot-kit/nodered
NR_DATA=/var/lib/iot-kit/nodered
NR_PASSWORD=/etc/iot-kit/nodered-admin-password
# The node-red user inside the container
NR_UID=1000

# --- Cockpit ---------------------------------------------------------------
if ! dpkg -s cockpit cockpit-networkmanager &>/dev/null; then
  apt-get update
  apt-get install -y --no-install-recommends cockpit cockpit-networkmanager
fi
systemctl enable -q --now cockpit.socket

# --- Node-RED --------------------------------------------------------------
install -d -m 0750 /etc/iot-kit
install -d -m 0750 -o "$NR_UID" -g "$NR_UID" "$NR_ETC"
install -d -m 0755 -o "$NR_UID" -g "$NR_UID" "$NR_DATA"

if [[ ! -f $NR_PASSWORD ]]; then
  (umask 077; openssl rand -base64 12 > "$NR_PASSWORD")
  log "generated the Node-RED admin password: sudo cat $NR_PASSWORD"
fi
if [[ ! -f $NR_ETC/credential-secret ]]; then
  (umask 077; openssl rand -hex 32 > "$NR_ETC/credential-secret")
  chown "$NR_UID:$NR_UID" "$NR_ETC/credential-secret"
fi

# Starter flow, only if there is none: never overwrite what was built since.
if [[ ! -f $NR_DATA/flows.json ]]; then
  install -m 0644 -o "$NR_UID" -g "$NR_UID" "$KIT_DIR/tools/nodered/flows.json" "$NR_DATA/flows.json"
  log "installed the starter flow"
fi

"${COMPOSE[@]}" pull --ignore-buildable
"${COMPOSE[@]}" build

# To change the password: edit $NR_PASSWORD, re-run this script.
HASH_CHANGED=0
if [[ ! -s $NR_ETC/admin.hash || $NR_PASSWORD -nt $NR_ETC/admin.hash ]]; then
  tmp=$(mktemp)
  docker run --rm -i --network none --entrypoint node iot-kit/nodered:local \
    -e 'const pw = require("fs").readFileSync(0, "utf8").trim();
        console.log(require("bcryptjs").hashSync(pw, 8));' \
    < "$NR_PASSWORD" > "$tmp"
  [[ "$(cat "$tmp")" == '$2'* ]] || die "could not hash the Node-RED admin password"
  install -m 0400 -o "$NR_UID" -g "$NR_UID" "$tmp" "$NR_ETC/admin.hash"
  rm -f "$tmp"
  HASH_CHANGED=1
  log "Node-RED admin password (re)applied"
fi

ensure_kit_network
"${COMPOSE[@]}" up -d --remove-orphans
# The bridge the tools had before they joined the kit network
docker network rm tools_tools >/dev/null 2>&1 || true
if (( HASH_CHANGED )); then
  "${COMPOSE[@]}" restart nodered
fi

log "waiting for Node-RED"
for _ in $(seq 1 30); do
  if curl -sf -m 3 -o /dev/null http://127.0.0.1:1880/; then
    log "Phase 7 done"
    exit 0
  fi
  sleep 2
done
die "Node-RED does not answer on :1880. Check: sudo docker logs nodered"
