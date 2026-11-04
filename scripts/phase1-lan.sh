#!/usr/bin/env bash
# Phase 1: eth0 becomes the static LAN interface (NetworkManager).
#
# WARNING: if your SSH session runs over eth0, this cuts it. Run it detached
# so it finishes anyway, with an automatic rollback if you cannot get back in:
#
#   sudo systemd-run --unit=iot-kit-cutover --collect \
#     /home/pi/iot-kit/scripts/phase1-lan.sh --rollback-after 600
#
# Once reconnected, keep the new config with:
#   sudo systemctl stop iot-kit-lan-rollback.timer
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
need_root

ROLLBACK_AFTER=0
while (( $# )); do
  case $1 in
    --rollback-after) ROLLBACK_AFTER=${2:?seconds}; shift 2 ;;
    *) die "unknown option: $1" ;;
  esac
done

log "Phase 1: LAN interface $LAN_IF = $LAN_IP/$LAN_PREFIX"
install -d "$STATE_DIR"

CHANGED=0
install_file "$KIT_DIR/configs/NetworkManager/10-iot-kit.conf" /etc/NetworkManager/conf.d/10-iot-kit.conf
if (( CHANGED )); then
  nmcli general reload conf
fi

# Remember what was active on eth0, for lan-rollback.sh.
prev=$(nmcli -g GENERAL.CONNECTION device show "$LAN_IF" 2>/dev/null || true)
if [[ -n $prev && $prev != "$LAN_CON" ]]; then
  echo "$prev" > "$STATE_DIR/lan-previous-profile"
  log "previous profile on $LAN_IF: '$prev' (kept for rollback)"
fi

LAN_SETTINGS=(
  connection.interface-name "$LAN_IF"
  connection.autoconnect yes
  connection.autoconnect-priority 100
  ipv4.method manual
  ipv4.addresses "$LAN_IP/$LAN_PREFIX"
  ipv4.gateway ""
  ipv4.dns ""
  ipv4.never-default yes
  ipv6.method disabled
)
if nmcli -g connection.id connection show "$LAN_CON" &>/dev/null; then
  nmcli connection modify "$LAN_CON" "${LAN_SETTINGS[@]}"
else
  nmcli connection add type ethernet con-name "$LAN_CON" "${LAN_SETTINGS[@]}"
  log "created profile $LAN_CON"
fi

# The USB-Ethernet adapter boots as a virtual CD-ROM: power-cycle the USB
# ports when it appears like that (details in the rules file).
CHANGED=0
install_file "$KIT_DIR/configs/usb-ethernet/iot-kit-usb-ethernet" /usr/local/sbin/iot-kit-usb-ethernet 0755
install_file "$KIT_DIR/configs/usb-ethernet/iot-kit-usb-ethernet.service" /etc/systemd/system/iot-kit-usb-ethernet.service
install_file "$KIT_DIR/configs/usb-ethernet/41-iot-kit-usb-ethernet.rules" /etc/udev/rules.d/41-iot-kit-usb-ethernet.rules
if (( CHANGED )); then
  systemctl daemon-reload
  udevadm control --reload
fi
# Earlier kits tried usb_modeswitch, which this adapter ignores
if [[ -e /etc/usb_modeswitch.d/0bda:8151 ]]; then
  rm -f /etc/usb_modeswitch.d/0bda:8151
  log "removed the usb_modeswitch config, the adapter ignores it"
fi

# WAN over USB-Ethernet: plain DHCP client. The adapter being absent is normal.
WAN_SETTINGS=(
  connection.interface-name "$WAN_ETH_IF"
  connection.autoconnect yes
  ipv4.method auto
  ipv4.route-metric 100
  ipv4.dhcp-reject-servers "${WAN_DHCP_REJECT_SERVERS// /,}"
  ipv6.method auto
)
if nmcli -g connection.id connection show "$WAN_CON" &>/dev/null; then
  nmcli connection modify "$WAN_CON" "${WAN_SETTINGS[@]}"
else
  nmcli connection add type ethernet con-name "$WAN_CON" "${WAN_SETTINGS[@]}"
  log "created profile $WAN_CON"
fi

# Any other ethernet profile pinned to eth0 must not come back at boot.
while IFS=: read -r uuid type; do
  [[ $type == 802-3-ethernet ]] || continue
  name=$(nmcli -g connection.id connection show "$uuid")
  [[ $name != "$LAN_CON" && $name != "$WAN_CON" ]] || continue
  if [[ "$(nmcli -g connection.interface-name connection show "$uuid")" == "$LAN_IF" \
     && "$(nmcli -g connection.autoconnect connection show "$uuid")" == yes ]]; then
    nmcli connection modify "$uuid" connection.autoconnect no
    log "autoconnect disabled on old profile '$name'"
  fi
done < <(nmcli -t -f UUID,TYPE connection show)

if (( ROLLBACK_AFTER > 0 )) && [[ -s $STATE_DIR/lan-previous-profile ]] && ! lan_is_up; then
  systemctl reset-failed iot-kit-lan-rollback.service 2>/dev/null || true
  systemd-run --unit=iot-kit-lan-rollback --on-active="$ROLLBACK_AFTER" \
    "$KIT_DIR/scripts/lan-rollback.sh"
  warn "rollback armed: in ${ROLLBACK_AFTER}s $LAN_IF goes back to '$(cat "$STATE_DIR/lan-previous-profile")'"
  warn "to keep the new config: sudo systemctl stop iot-kit-lan-rollback.timer"
fi

# This is the step that cuts an SSH session running over eth0.
active=$(nmcli -g GENERAL.CONNECTION device show "$LAN_IF" 2>/dev/null || true)
if [[ $active == "$LAN_CON" ]] && lan_is_up; then
  log "$LAN_CON already active"
elif ! nmcli connection up "$LAN_CON"; then
  warn "could not activate $LAN_CON now; it will come up at next boot"
fi

# Phase 2 leaves dnsmasq stopped until eth0 really is the LAN.
if [[ -f /etc/dnsmasq.d/iot-kit.conf ]] && lan_is_up; then
  systemctl enable -q dnsmasq
  if ! systemctl is-active -q dnsmasq; then
    systemctl start dnsmasq
    log "dnsmasq started on $LAN_IF"
  fi
fi

log "Phase 1 done"
