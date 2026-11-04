# Access point and UniFi controller

The controller is only needed to configure the AP. The AP keeps its
configuration and keeps broadcasting without it.

```sh
~/iot-kit/unifi/unifi-up.sh      # then open https://192.168.50.1:8443
~/iot-kit/unifi/unifi-down.sh
```

The first start takes a few minutes. The browser warns about a self-signed
certificate, that is expected.

`https://192.168.50.1:8443` only loads from a computer **on the kit LAN**
(kit WiFi, or a cable on `eth0`). From the host network the firewall only
lets SSH through, so use a tunnel and open `https://localhost:8443` instead:

```sh
ssh -N -L 8443:127.0.0.1:8443 pi@<WAN IP>
```

This is the way in before the first adoption, when there is no kit WiFi yet.

## Adopting the AP

1. AP on the PoE+ injector, injector on the Pi's `eth0`. Start the controller.
2. First run of the controller: create a local account (the setup wizard
   has an option to skip the cloud login, the kit must work offline).
3. **In the settings, find "Inform Host" (under System → Advanced), enable
   the override and set it to `192.168.50.1`.** The controller sees several
   addresses of the Pi and can announce the wrong one, the AP then stays in
   "Adopting".
4. The AP shows up under UniFi Devices: click **Adopt**.
5. While adopted: update the AP firmware (needs the WAN uplink).
6. Copy the AP's MAC address into `AP_MAC` in `kit.local.env`, deploy, run
   `sudo ~/iot-kit/scripts/phase2-dnsmasq.sh`, power-cycle the AP. It gets
   `192.168.50.2` from then on.

If the AP does not show up:

- It may still belong to an old controller. Factory reset: hold the reset
  button about 10 s while powered.
- The kit's DNS already answers `unifi` with `192.168.50.1`, which is where a
  factory-default AP looks for a controller. If that is not enough, find the
  AP's address in `/var/lib/misc/dnsmasq.leases`, then:

  ```sh
  ssh ubnt@192.168.50.xxx          # password: ubnt
  set-inform http://192.168.50.1:8080/inform
  ```

## WLAN checklist (ESP32-friendly)

Set in the controller under Settings → WiFi:

- [ ] Dedicated SSID, **2.4 GHz only**, band steering off
- [ ] **WPA2-PSK** only (no WPA3, no mixed mode)
- [ ] 802.11r fast roaming **off**, BSS transition **off**
- [ ] Client device isolation **off**
- [ ] Fixed channel 1, 6 or 11; TX power medium or low
- [ ] Minimum RSSI off
- [ ] AP firmware updated
- [ ] `192.168.50.2` reserved for the AP (`AP_MAC` in `kit.local.env`)
