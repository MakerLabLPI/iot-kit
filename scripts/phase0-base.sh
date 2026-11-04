#!/usr/bin/env bash
# Phase 0: base system (upgrade, timezone, hostname, packages). Needs internet.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
need_root
log "Phase 0: base system"

export DEBIAN_FRONTEND=noninteractive
APT_OPTS=(-y -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold)

if [[ "$(timedatectl show -p Timezone --value)" != "$TIMEZONE" ]]; then
  timedatectl set-timezone "$TIMEZONE"
  log "timezone set to $TIMEZONE"
fi

if [[ "$(hostnamectl hostname)" != "$KIT_HOSTNAME" ]]; then
  warn "hostname is '$(hostnamectl hostname)', setting it to '$KIT_HOSTNAME'"
  hostnamectl set-hostname "$KIT_HOSTNAME"
  if grep -q '^127\.0\.1\.1' /etc/hosts; then
    sed -i "s/^127\.0\.1\.1.*/127.0.1.1\t$KIT_HOSTNAME/" /etc/hosts
  else
    printf '127.0.1.1\t%s\n' "$KIT_HOSTNAME" >> /etc/hosts
  fi
fi

# The Pi itself does not use dnsmasq as resolver, so give it the local names.
# cloud-init rewrites /etc/hosts from its template at every boot, so the
# names have to be in the template as well.
for hosts in /etc/hosts /etc/cloud/templates/hosts.debian.tmpl; do
  if [[ -f $hosts ]] && ! grep -q 'broker\.lan' "$hosts"; then
    printf '%s\tbroker.lan iot-kit.lan\n' "$LAN_IP" >> "$hosts"
    log "added broker.lan / iot-kit.lan to $hosts"
  fi
done

apt-get update
apt-get "${APT_OPTS[@]}" full-upgrade

# Packages must not start with their default config (dnsmasq would listen on
# every interface). Each phase starts its own service once it is configured.
# The broker itself runs in Docker (phase 4): only its clients are installed.
POLICY=/usr/sbin/policy-rc.d
if [[ ! -e $POLICY ]]; then
  printf '#!/bin/sh\nexit 101\n' > "$POLICY"
  chmod 0755 "$POLICY"
  trap 'rm -f "$POLICY"' EXIT
fi

apt-get "${APT_OPTS[@]}" install --no-install-recommends \
  dnsmasq nftables mosquitto-clients chrony \
  curl ca-certificates rsync openssl bind9-dnsutils \
  usbutils uhubctl

log "Phase 0 done"
