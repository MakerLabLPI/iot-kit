#!/usr/bin/env bash
# Phase 5: NTP server for the LAN (chrony). DHCP option 42 is set in dnsmasq.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
need_root
log "Phase 5: chrony"

grep -Eq '^\s*confdir\s+/etc/chrony/conf.d' /etc/chrony/chrony.conf \
  || die "/etc/chrony/chrony.conf does not include /etc/chrony/conf.d"

CHANGED=0
install_file "$KIT_DIR/configs/chrony/iot-kit.conf" /etc/chrony/conf.d/iot-kit.conf

systemctl enable chrony
if (( CHANGED )) || ! systemctl is-active -q chrony; then
  systemctl restart chrony
  log "chrony restarted"
fi

log "Phase 5 done"
