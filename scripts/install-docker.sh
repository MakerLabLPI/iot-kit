#!/usr/bin/env bash
# Docker engine, used by the broker (phase 4), the UniFi controller (phase 6)
# and the web UIs (phase 7). Needs internet the first time.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
need_root
log "Docker engine"

export DEBIAN_FRONTEND=noninteractive

# Before the package, so that the very first dockerd start already uses it.
# ip-forward-no-drop: Docker must not set the FORWARD policy to drop, the Pi
# is a router.
CHANGED=0
install_file "$KIT_DIR/configs/docker/daemon.json" /etc/docker/daemon.json

if ! command -v docker >/dev/null; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  # shellcheck disable=SC1091
  codename=$(. /etc/os-release && echo "$VERSION_CODENAME")
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $codename stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
elif (( CHANGED )) && systemctl is-active -q docker; then
  systemctl restart docker
  log "docker restarted"
fi

systemctl enable -q docker.service containerd.service
systemctl start docker

# docker without sudo for the user who runs the kit. Membership of the docker
# group is equivalent to root on the Pi; it takes effect at the next login.
KIT_USER=${SUDO_USER:-}
if [[ -z $KIT_USER || $KIT_USER == root ]]; then
  warn "no login user to add to the docker group (run with sudo as that user)"
elif ! id -nG "$KIT_USER" | tr ' ' '\n' | grep -qx docker; then
  usermod -aG docker "$KIT_USER"
  log "$KIT_USER added to the docker group: log out and back in to use docker without sudo"
fi

log "Docker engine done"
