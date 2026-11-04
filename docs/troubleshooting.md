# Troubleshooting

**No DHCP lease**

- `systemctl status dnsmasq` and `journalctl -u dnsmasq -n 50`
- `ip -br addr show eth0` must show `192.168.50.1/24`. If not:
  `sudo nmcli connection up iot-kit-lan`
- Leases given so far: `cat /var/lib/misc/dnsmasq.leases`
- More than 101 clients in 12 h exhaust the pool: stop dnsmasq, delete the
  leases file, start dnsmasq.
- Cable check: Pi `eth0` → injector port "LAN", injector port "PoE" → AP.

**WiFi works but no internet, although the USB-Ethernet adapter is plugged in**

- `ip -br addr show eth1` on the Pi: no `eth1` at all means the adapter is
  not seen as a network card.
- `lsusb` showing `0bda:8151` means it is stuck as a virtual CD-ROM (its
  built-in Windows driver disc). This happens after a cold boot, and only a
  power cycle gets it out of there (ejecting the disc does nothing, we
  tried). A udev rule of the kit power-cycles the USB ports once when it
  sees that (`configs/usb-ethernet/`); `systemctl status
  iot-kit-usb-ethernet` tells whether it ran. To do it by hand:
  `sudo iot-kit-usb-ethernet`, or unplug the adapter and plug it back in.
- `eth1` there but without address: the host network gave no DHCP lease,
  check the cable and the wall socket.
- `eth1` has an address but `ping 1.1.1.1` says "Destination Net
  Unreachable": the address may come from a second DHCP server on the host
  network that leads nowhere. `nmcli -f DHCP4 device show eth1` shows which
  server answered (`dhcp_server_identifier`), and
  `sudo ~/iot-kit/tests/dhcp-servers.py` lists every server that answers.
  Add the wrong one to `WAN_DHCP_REJECT_SERVERS` in `kit.local.env`, run
  `sudo ~/iot-kit/scripts/phase1-lan.sh`, then forget the lease the Pi
  already has, otherwise it keeps asking for it:

  ```sh
  sudo nmcli connection down iot-kit-wan-eth1
  sudo rm -f /var/lib/NetworkManager/*eth1.lease
  sudo nmcli connection up iot-kit-wan-eth1
  ```

**AP not adopting**

- See [Adopting the AP](access-point.md#adopting-the-ap): Inform Host override, factory
  reset, `set-inform`.
- Is the controller up? `docker ps`, `docker logs unifi`
- Does the AP have a lease? Look for it in `/var/lib/misc/dnsmasq.leases`.

**ESP32 won't join the WiFi**

- Go through the WLAN checklist again: WPA3 or mixed mode, 5 GHz only and
  802.11r are the usual causes.
- ESP32 only does 2.4 GHz; SSID and password are case sensitive.
- 20 boards joining at once right next to the AP: lower the TX power.

**ESP32 joins but MQTT fails**

- `docker logs -f mosquitto` shows every connection attempt (also kept
  in `/var/log/iot-kit/mosquitto/mosquitto.log`).
- Is the broker up? `docker ps` must list `mosquitto` as healthy. If
  not: `sudo ~/iot-kit/scripts/phase4-mosquitto.sh`
- Two boards with the same client id kick each other out in a loop. The
  example sketch derives the id from the MAC address.
- PubSubClient `state=-2`: network problem, check the broker address.

**Wrong time after a power cut**

- The Pi 5 clock needs the optional RTC battery to keep time while
  unplugged. Without it and without uplink, the Pi boots with an old time
  and serves that to the clients.

**A web UI does not load**

- From the host network this is expected: kit LAN or SSH tunnel only.
- `docker ps` must list `nodered` and `mqttx-web`. If not:
  `sudo ~/iot-kit/scripts/phase7-webui.sh`, then `docker logs nodered`
- Cockpit: `systemctl status cockpit.socket`
