#!/usr/bin/env bash
# Phase 3: routing, NAT and firewall (nftables).
#
#   --guard SECONDS   remove the new rules again after SECONDS unless you
#                     confirm with: sudo systemctl stop iot-kit-fw-guard.timer
#                     (use it when applying over SSH for the first time)
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
need_root

GUARD=0
while (( $# )); do
  case $1 in
    --guard) GUARD=${2:?seconds}; shift 2 ;;
    *) die "unknown option: $1" ;;
  esac
done

log "Phase 3: routing, NAT, firewall"

CHANGED=0
install_file "$KIT_DIR/configs/sysctl/90-iot-kit.conf" /etc/sysctl.d/90-iot-kit.conf
sysctl -q -p /etc/sysctl.d/90-iot-kit.conf

SRC="$KIT_DIR/configs/nftables/nftables.conf"
nft -c -f "$SRC"

if [[ -f /etc/nftables.conf && ! -f /etc/nftables.conf.orig ]] && ! cmp -s "$SRC" /etc/nftables.conf; then
  cp -p /etc/nftables.conf /etc/nftables.conf.orig
fi
install_file "$SRC" /etc/nftables.conf 0755

if (( GUARD > 0 )); then
  systemctl reset-failed iot-kit-fw-guard.service 2>/dev/null || true
  systemd-run --unit=iot-kit-fw-guard --on-active="$GUARD" \
    /usr/sbin/nft delete table inet iot_kit
  warn "guard armed: rules are removed in ${GUARD}s"
  warn "to keep them: sudo systemctl stop iot-kit-fw-guard.timer"
fi

systemctl enable nftables
nft -f /etc/nftables.conf
log "ruleset loaded"

log "Phase 3 done"
