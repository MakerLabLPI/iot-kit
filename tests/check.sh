#!/usr/bin/env bash
# Self-check, run ON the Pi:  ~/iot-kit/tests/check.sh
# Covers what can be verified locally. The acceptance tests that need a
# client (WiFi laptop, ESP32, WAN port scan) are listed in the README.
set -uo pipefail

KIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../kit.env
source "$KIT_DIR/kit.env"
# shellcheck disable=SC1091
[[ -f $KIT_DIR/kit.local.env ]] && source "$KIT_DIR/kit.local.env"

pass=0
fail=0
skipped=0

# Some checks need root. Ask for the password once if someone is there to
# type it; otherwise those checks are skipped rather than reported as failed.
have_sudo=1
if ! sudo -n true 2>/dev/null; then
  if [[ -t 0 ]]; then
    sudo -v || have_sudo=0
  else
    have_sudo=0
  fi
fi

check_root() {
  if (( have_sudo )); then
    check "$@"
  else
    printf '  \033[33mskip\033[0m  %s (needs sudo)\n' "$1"
    skipped=$((skipped + 1))
  fi
}

# docker works without sudo for a member of the docker group
# (install-docker.sh); otherwise it needs root like the checks above.
DOCKER=(docker)
have_docker=1
if ! docker info >/dev/null 2>&1; then
  DOCKER=(sudo docker)
  have_docker=$have_sudo
fi

check_docker() {
  if (( have_docker )); then
    check "$@"
  else
    printf '  \033[33mskip\033[0m  %s (needs docker group or sudo)\n' "$1"
    skipped=$((skipped + 1))
  fi
}

check() {
  local desc=$1
  shift
  if "$@" >/dev/null 2>&1; then
    printf '  \033[32mok\033[0m    %s\n' "$desc"
    pass=$((pass + 1))
  else
    printf '  \033[31mFAIL\033[0m  %s\n' "$desc"
    fail=$((fail + 1))
  fi
}

lan_address()  { ip -4 -o addr show dev "$LAN_IF" | grep -qF " $LAN_IP/$LAN_PREFIX "; }
not_cdrom_mode() { ! lsusb -d 0bda:8151; }
cdrom_fix_installed() {
  [[ -f /etc/udev/rules.d/41-iot-kit-usb-ethernet.rules ]] \
    && systemctl cat -q iot-kit-usb-ethernet.service > /dev/null 2>&1 \
    && [[ -x /usr/sbin/uhubctl ]]   # sbin is not in the PATH of a normal user
}
no_lan_gw()    { ! ip -4 route show default dev "$LAN_IF" | grep -q .; }
# /proc rather than sysctl, which is not in the PATH of a normal user
forwarding()   { [[ "$(cat /proc/sys/net/ipv4/ip_forward)" == 1 ]]; }
resolves()     { [[ "$(dig +short +time=2 +tries=1 @"$LAN_IP" "$1")" == "$LAN_IP" ]]; }
udp_listens()  { ss -uln | grep -q ":$1 "; }
timezone_ok()  { [[ "$(timedatectl show -p Timezone --value)" == "$TIMEZONE" ]]; }
hostname_ok()  { [[ "$(hostname)" == "$KIT_HOSTNAME" ]]; }
container_up() { [[ "$("${DOCKER[@]}" inspect -f '{{.State.Running}}' "$1")" == true ]]; }
restarts_always() { [[ "$("${DOCKER[@]}" inspect -f '{{.HostConfig.RestartPolicy.Name}}' "$1")" == always ]]; }
no_native_broker() { ! dpkg -s mosquitto; }
http_ok()      { curl -ksf -m 5 -o /dev/null "$1"; }

mqtt_roundtrip() {
  local topic="test/selfcheck/$$" out sub
  out=$(mktemp)
  mosquitto_sub -h "$LAN_IP" -p 1883 -t "$topic" -C 1 -W 5 > "$out" &
  sub=$!
  sleep 1
  mosquitto_pub -h "$LAN_IP" -p 1883 -t "$topic" -m ping
  wait "$sub"
  [[ "$(cat "$out")" == ping ]]
}

websocket_handshake() {
  local reply
  # curl always ends in a timeout here: after the upgrade the socket stays open
  reply=$(curl -s -i -m 3 --http1.1 \
    -H 'Connection: Upgrade' -H 'Upgrade: websocket' \
    -H 'Sec-WebSocket-Version: 13' -H 'Sec-WebSocket-Key: SGVsbG8sIHdvcmxkIQ==' \
    -H 'Sec-WebSocket-Protocol: mqtt' \
    "http://$LAN_IP:9001/" || true)
  [[ $reply == "HTTP/1.1 101 "* ]]
}

echo "System"
check "hostname is $KIT_HOSTNAME" hostname_ok
check "timezone is $TIMEZONE" timezone_ok

echo "Network"
check "$LAN_IF has $LAN_IP/$LAN_PREFIX" lan_address
check "no default route via $LAN_IF" no_lan_gw
check "IPv4 forwarding enabled" forwarding
check "USB-Ethernet adapter not stuck in CD-ROM mode" not_cdrom_mode
check "CD-ROM mode fix installed (udev rule + service + uhubctl)" cdrom_fix_installed
check "nftables enabled at boot" systemctl is-enabled -q nftables
check_root "firewall table inet iot_kit loaded" sudo nft list table inet iot_kit

echo "DHCP + DNS"
check "dnsmasq running" systemctl is-active -q dnsmasq
check "dnsmasq enabled at boot" systemctl is-enabled -q dnsmasq
check "DHCP server listening (udp 67)" udp_listens 67
check "broker.lan resolves to $LAN_IP" resolves broker.lan
check "iot-kit.lan resolves to $LAN_IP" resolves iot-kit.lan
check "the Pi itself resolves broker.lan" getent hosts broker.lan

echo "MQTT"
check_docker "docker network iot-kit (br-kit) exists" "${DOCKER[@]}" network inspect iot-kit
check_docker "mosquitto container running" container_up mosquitto
check_docker "mosquitto container restarts at boot" restarts_always mosquitto
check "broker of the Debian package removed" no_native_broker
check "pub/sub round trip on $LAN_IP:1883" mqtt_roundtrip
check "WebSocket handshake on $LAN_IP:9001" websocket_handshake

echo "Time"
check "chrony running" systemctl is-active -q chrony
check "NTP server listening (udp 123)" udp_listens 123

echo "Docker + web UIs"
check "docker enabled at boot" systemctl is-enabled -q docker.service
check_docker "Node-RED container running" container_up nodered
check "Node-RED editor on $LAN_IP:1880" http_ok "http://$LAN_IP:1880/"
check "Node-RED dashboard on $LAN_IP:1880/dashboard" http_ok "http://$LAN_IP:1880/dashboard/"
check_docker "MQTTX Web container running" container_up mqttx-web
check_docker "presence container running" container_up presence
check_docker "leds container running" container_up leds
check "PIO device for the LED strip (/dev/pio0)" test -e /dev/pio0
check "MQTTX Web on $LAN_IP:8090" http_ok "http://$LAN_IP:8090/"
check "Cockpit enabled at boot" systemctl is-enabled -q cockpit.socket
check "Cockpit on $LAN_IP:9090" http_ok "https://$LAN_IP:9090/"

echo
echo "$pass passed, $fail failed, $skipped skipped"
(( fail == 0 ))
