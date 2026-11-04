#!/usr/bin/env bash
# Build the whole kit on a fresh Raspberry Pi OS Lite. Idempotent: re-run it
# after any change in configs/ or kit.env.
#
#   sudo ./setup.sh             everything except the eth0 cutover
#   sudo ./setup.sh --cutover   everything, eth0 cutover included
#
# The order is not the phase order, on purpose:
#   - firewall first, so no service is ever reachable from the WAN side
#   - eth0 cutover (phase 1) last, because it cuts an SSH session over eth0
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
[[ $EUID -eq 0 ]] || exec sudo "$0" "$@"

CUTOVER=0
for arg in "$@"; do
  case $arg in
    --cutover) CUTOVER=1 ;;
    *) sed -n '2,11p' "$0"; exit 1 ;;
  esac
done

scripts/phase0-base.sh
scripts/phase3-firewall.sh
scripts/install-docker.sh
scripts/phase4-mosquitto.sh
scripts/phase5-chrony.sh
scripts/phase2-dnsmasq.sh
scripts/phase6-unifi.sh
scripts/phase7-webui.sh

if (( CUTOVER )); then
  scripts/phase1-lan.sh
  echo
  echo "All phases done. Reboot, then run tests/check.sh"
else
  echo
  echo "Done, except phase 1 (eth0 cutover). Read the header of"
  echo "scripts/phase1-lan.sh before running it over SSH."
fi
