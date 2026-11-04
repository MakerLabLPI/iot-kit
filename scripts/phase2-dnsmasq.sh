#!/usr/bin/env bash
# Phase 2: DHCP + DNS on the LAN (dnsmasq).
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
need_root
log "Phase 2: dnsmasq"

CHANGED=0
install_file "$KIT_DIR/configs/dnsmasq/dhcp-event" /usr/local/sbin/iot-kit-dhcp-event 0755
install_file "$KIT_DIR/configs/dnsmasq/iot-kit.conf" /etc/dnsmasq.d/iot-kit.conf

AP_CONF=/etc/dnsmasq.d/iot-kit-ap.conf
if [[ -n $AP_MAC ]]; then
  tmp=$(mktemp)
  printf '# Generated from kit.env (AP_MAC). Do not edit.\ndhcp-host=%s,unifi-ap,%s\n' \
    "$AP_MAC" "$AP_IP" > "$tmp"
  install_file "$tmp" "$AP_CONF"
  rm -f "$tmp"
elif [[ -f $AP_CONF ]]; then
  rm -f "$AP_CONF"
  CHANGED=1
else
  warn "AP_MAC is empty in kit.env: no $AP_IP reservation for the AP yet"
fi

dnsmasq --test --conf-dir=/etc/dnsmasq.d,.dpkg-dist,.dpkg-old,.dpkg-new

if lan_is_up; then
  systemctl enable dnsmasq
  if (( CHANGED )) || ! systemctl is-active -q dnsmasq; then
    systemctl restart dnsmasq
    log "dnsmasq restarted"
  fi
else
  # eth0 is still on somebody else's network: serve nothing there.
  systemctl disable --now dnsmasq 2>/dev/null || true
  warn "$LAN_IF is not the LAN yet: dnsmasq left stopped, phase 1 starts it"
fi

log "Phase 2 done"
