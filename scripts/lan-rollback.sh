#!/usr/bin/env bash
# Undo phase 1: give eth0 back to the profile it had before the cutover.
# Usable from keyboard + screen:  sudo ~/iot-kit/scripts/lan-rollback.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
need_root

[[ -s $STATE_DIR/lan-previous-profile ]] || die "no previous profile recorded in $STATE_DIR"
prev=$(cat "$STATE_DIR/lan-previous-profile")

# dnsmasq must never serve on eth0 while it sits on somebody else's network.
systemctl disable --now dnsmasq 2>/dev/null || true

nmcli connection modify "$LAN_CON" connection.autoconnect no
nmcli connection modify "$prev" connection.autoconnect yes
nmcli connection up "$prev" ifname "$LAN_IF"
log "$LAN_IF is back on '$prev'. Re-run scripts/phase1-lan.sh to cut over again."
