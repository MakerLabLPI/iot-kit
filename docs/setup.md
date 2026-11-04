# Setup and maintenance

How to build the kit from a blank SD card, change its configuration, add an internet uplink and check that everything works.

# Rebuild from a fresh SD card

State on the Pi that is not in this repository. Back it up to keep it across
a rebuild:

| Path | Content |
|---|---|
| `/var/lib/iot-kit/mosquitto/` | retained MQTT messages |
| `/var/lib/iot-kit/unifi/` | controller data: the adopted AP, the WLAN settings |
| `/var/lib/iot-kit/nodered/` | Node-RED flows and dashboards |
| `/etc/iot-kit/` | generated passwords and secrets |
| `~/iot-kit/kit.local.env` | your site-specific settings (also on your computer) |


1. Flash **Raspberry Pi OS Lite 64-bit**; in Raspberry Pi Imager set hostname
   `iot-kit`, user `pi`, your SSH public key, timezone Europe/Paris.
2. Plug the **USB-Ethernet adapter** (`eth1`) into a network with internet.
   Leave `eth0` for the AP. Then no step below can cut your SSH session.
3. From your computer: `./deploy.sh pi@<IP>`
4. On the Pi: `sudo ~/iot-kit/setup.sh --cutover`
5. `sudo reboot`, then `~/iot-kit/tests/check.sh`
6. Adopt the AP again ([access-point.md](access-point.md)), unless you restored
   `/var/lib/iot-kit/unifi/` and `/etc/iot-kit/unifi.env` from a backup.

If the only uplink you have is `eth0` itself: run `sudo ~/iot-kit/setup.sh`
(without `--cutover`), then follow the header of `scripts/phase1-lan.sh`. It
runs the cutover detached with an automatic rollback, and
`scripts/lan-rollback.sh` undoes it from keyboard + screen.

`setup.sh` runs the firewall first and the `eth0` cutover last, which is not
the phase order: no service is ever reachable from the WAN side, and SSH is
cut as late as possible.

# Change something

Edit the file in `configs/` or `kit.env` on your computer, then:

```sh
./deploy.sh pi@192.168.50.1            # or pi@<WAN IP>
ssh pi@192.168.50.1
sudo ~/iot-kit/scripts/phase2-dnsmasq.sh   # the phase you changed,
                                           # phase4 for broker/mosquitto.conf
~/iot-kit/tests/check.sh
```

Every script only restarts its service when the config really changed.

# Internet uplink (optional)

- **USB-Ethernet** (`eth1`): plug it in, it is a DHCP client.
- **WiFi** (`wlan0`): `sudo nmcli device wifi connect "<ssid>" --ask`
  (on a new image, set the WiFi country first: `sudo raspi-config`).
  Do not join eduroam or a university network with personal credentials.

No uplink is a normal state: DHCP, `broker.lan`, MQTT and NTP keep working.
Laptops and phones will say "no internet", some phones then leave the WiFi
unless told to stay.

# Acceptance tests

`tests/check.sh` covers what the Pi can verify alone. By hand:

- [ ] Reboot with WAN unplugged: a laptop on the kit WiFi gets `192.168.50.x`,
      resolves `broker.lan`, pub/sub works on 1883 and 9001
- [ ] Reboot with WAN plugged: LAN clients reach the internet
- [ ] From the host network (not from the kit WiFi): `tests/wan-scan.sh
      <WAN IP>` shows only SSH open
- [ ] An ESP32 with `examples/esp32-mqtt-minimal` connects and publishes
- [ ] Controller started, AP adopted, controller stopped: the AP still
      broadcasts after a power cycle
- [ ] Offline, a client gets the time: `sntp 192.168.50.1` (macOS) or
      `chronyc -h 192.168.50.1 tracking`

Quick pub/sub test from a laptop on the kit WiFi:

```sh
mosquitto_sub -h broker.lan -t 'test/#' -v
mosquitto_pub -h broker.lan -t test/hello -m world
```
