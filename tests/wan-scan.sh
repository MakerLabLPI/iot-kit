#!/usr/bin/env bash
# Run from a computer on the HOST network (WAN side of the kit), not on the Pi
# and not from the kit WiFi (from there every port is open, as it should be):
#   tests/wan-scan.sh <WAN IP of the Pi>
# Only SSH may answer. For a full scan including UDP:
#   sudo nmap -sS -sU -p T:1-10000,U:53,67,123,3478,5353,10001 <WAN IP>
set -uo pipefail

TARGET=${1:?usage: wan-scan.sh <WAN IP of the Pi>}

if [[ "$(uname)" == Darwin ]]; then
  probe() { nc -z -G 2 "$TARGET" "$1" >/dev/null 2>&1; }
else
  probe() { nc -z -w 2 "$TARGET" "$1" >/dev/null 2>&1; }
fi

fail=0
case $TARGET in
  192.168.50.*) echo "this is the LAN address: use the Pi's address on the host network" >&2; exit 1 ;;
esac

for port in 22 53 1883 9001 8080 8443 1880 8090 9090 8001 8002 8003; do
  if probe "$port"; then state=open; else state=closed; fi
  if [[ $port == 22 ]]; then expected=open; else expected=closed; fi
  if [[ $state == "$expected" ]]; then
    printf '  ok    tcp/%-5s %s\n' "$port" "$state"
  else
    printf '  FAIL  tcp/%-5s %s (expected %s)\n' "$port" "$state" "$expected"
    fail=1
  fi
done
exit "$fail"
