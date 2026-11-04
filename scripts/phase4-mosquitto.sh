#!/usr/bin/env bash
# Phase 4: Mosquitto broker (1883 MQTT, 9001 WebSockets), in Docker.
#
# On a Pi that still runs the broker from the Debian package, this migrates:
# the retained messages are kept, and the package is only removed once the
# container has proven to work. If it does not, the old broker is restarted.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
need_root
log "Phase 4: mosquitto (Docker)"

command -v docker >/dev/null || die "Docker is missing: run scripts/install-docker.sh first"

export DEBIAN_FRONTEND=noninteractive
COMPOSE=(docker compose -f "$KIT_DIR/broker/docker-compose.yml")
CONF_DIR=/etc/iot-kit/mosquitto
DATA_DIR=/var/lib/iot-kit/mosquitto
LOG_DIR=/var/log/iot-kit/mosquitto
# The mosquitto user inside the container
MQ_UID=1883

# Round trip through the broker. Uses the LAN address once it exists.
roundtrip() {
  local host=127.0.0.1 topic="test/phase4/$$" out sub ok=1
  if lan_is_up; then host=$LAN_IP; fi
  out=$(mktemp)
  mosquitto_sub -h "$host" -t "$topic" -C 1 -W 5 > "$out" 2>/dev/null &
  sub=$!
  sleep 1
  mosquitto_pub -h "$host" -t "$topic" -m ping 2>/dev/null || true
  wait "$sub" || true
  if [[ "$(cat "$out")" == ping ]]; then ok=0; fi
  rm -f "$out"
  return "$ok"
}

wait_for_broker() {
  for _ in $(seq 1 10); do
    if roundtrip; then return 0; fi
    sleep 2
  done
  return 1
}

# Get the image while the old broker still runs, to keep the gap short.
"${COMPOSE[@]}" pull || warn "could not pull the image (offline?), using the local one"
docker image inspect eclipse-mosquitto:2 >/dev/null 2>&1 \
  || die "image eclipse-mosquitto:2 is not available, the broker was left untouched"

install -d -m 0750 /etc/iot-kit
install -d -m 0755 "$CONF_DIR"
install -d -m 0750 -o "$MQ_UID" -g "$MQ_UID" "$DATA_DIR" "$LOG_DIR"

CHANGED=0
install_file "$KIT_DIR/broker/mosquitto.conf" "$CONF_DIR/mosquitto.conf"
CONF_CHANGED=$CHANGED
install_file "$KIT_DIR/configs/logrotate/iot-kit-mosquitto" /etc/logrotate.d/iot-kit-mosquitto

NATIVE=0
if dpkg -s mosquitto &>/dev/null; then
  NATIVE=1
  log "migrating from the Debian package"
  # Stopping writes the retained messages to disk, so stop before copying
  systemctl disable -q --now mosquitto
  if [[ -f /var/lib/mosquitto/mosquitto.db && ! -f $DATA_DIR/mosquitto.db ]]; then
    install -m 0600 -o "$MQ_UID" -g "$MQ_UID" /var/lib/mosquitto/mosquitto.db "$DATA_DIR/mosquitto.db"
    log "retained messages copied to $DATA_DIR"
  fi
fi

ensure_kit_network
"${COMPOSE[@]}" up -d
if (( CONF_CHANGED )) && ! (( NATIVE )); then
  "${COMPOSE[@]}" restart mosquitto
  log "mosquitto restarted"
fi

if ! wait_for_broker; then
  docker logs --tail 20 mosquitto >&2 || true
  if (( NATIVE )); then
    "${COMPOSE[@]}" down
    systemctl enable -q --now mosquitto
    die "the container does not work: the old broker is running again, nothing was removed"
  fi
  die "pub/sub round trip failed (see above, or $LOG_DIR/mosquitto.log)"
fi
log "pub/sub round trip ok"

if (( NATIVE )); then
  # mosquitto-clients (mosquitto_pub / mosquitto_sub) stays installed
  apt-get purge -y mosquitto
  rm -rf /etc/mosquitto
  log "Debian package removed"
fi

log "Phase 4 done"
