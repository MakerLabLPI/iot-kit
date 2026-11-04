#!/usr/bin/env bash
# Shared helpers for the iot-kit setup scripts. Source it, don't execute it.
set -euo pipefail

KIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../kit.env
source "$KIT_DIR/kit.env"
# shellcheck disable=SC1091
[[ -f $KIT_DIR/kit.local.env ]] && source "$KIT_DIR/kit.local.env"

STATE_DIR=/var/lib/iot-kit
LAN_CON=iot-kit-lan
WAN_CON=iot-kit-wan-$WAN_ETH_IF

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m !!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m xx\033[0m %s\n' "$*" >&2; exit 1; }

need_root() {
  [[ $EUID -eq 0 ]] || die "must run as root: sudo $0"
}

# install_file SRC DST [MODE]
# Copies only when the content differs and sets CHANGED=1 if it did, so
# callers can restart a service only when its config really changed.
CHANGED=0
install_file() {
  local src=$1 dst=$2 mode=${3:-0644}
  if [[ -f $dst ]] && cmp -s "$src" "$dst"; then
    return 0
  fi
  install -D -m "$mode" "$src" "$dst"
  CHANGED=1
  log "installed $dst"
}

# The one Docker network of the kit. Every stack joins it, so containers
# reach each other by name (the broker is "mosquitto", alias "broker.lan")
# and /etc/nftables.conf has a single bridge to deal with (br-kit).
KIT_NET=iot-kit
KIT_BRIDGE=br-kit
ensure_kit_network() {
  if docker network inspect "$KIT_NET" >/dev/null 2>&1; then return 0; fi
  docker network create --driver bridge \
    -o com.docker.network.bridge.name="$KIT_BRIDGE" "$KIT_NET" >/dev/null
  log "created the docker network $KIT_NET ($KIT_BRIDGE)"
}

# True once eth0 carries the kit's static LAN address.
lan_is_up() {
  ip -4 -o addr show dev "$LAN_IF" 2>/dev/null | grep -qF " $LAN_IP/$LAN_PREFIX "
}
