#!/usr/bin/env python3
"""List the DHCP servers that answer on an interface.

    sudo ~/iot-kit/tests/dhcp-servers.py [interface]     (default: eth1)

Sends DHCPDISCOVER and prints every offer received. It takes no lease and
changes nothing. More than one server on a network means a client gets its
address from whichever offer it accepts first.
"""
import random
import select
import socket
import struct
import sys
import time

MAGIC = b"\x63\x82\x53\x63"
WAIT = 8
ETH_P_IP = 0x0800


def mac_of(iface):
    with open(f"/sys/class/net/{iface}/address") as f:
        return bytes.fromhex(f.read().strip().replace(":", ""))


def build_discover(mac, xid):
    # Broadcast flag set: the answers must not depend on us having an address
    bootp = struct.pack(
        "!BBBBIHH4s4s4s4s16s64s128s",
        1, 1, 6, 0, xid, 0, 0x8000,
        bytes(4), bytes(4), bytes(4), bytes(4),
        mac, b"", b"",
    )
    options = (
        bytes([53, 1, 1])                 # DHCPDISCOVER
        + bytes([61, 7, 1]) + mac         # same client id as NetworkManager
        + bytes([55, 4, 1, 3, 6, 51])     # ask for mask, router, DNS, lease time
        + bytes([255])
    )
    return bootp + MAGIC + options


def parse_dhcp(payload):
    """Return (xid, offered address, options) or None if this is not DHCP."""
    if len(payload) < 240 or payload[236:240] != MAGIC:
        return None
    xid = struct.unpack("!I", payload[4:8])[0]
    offered = socket.inet_ntoa(payload[16:20])
    options = {}
    i = 240
    while i < len(payload):
        code = payload[i]
        if code == 255:
            break
        if code == 0:
            i += 1
            continue
        if i + 1 >= len(payload):
            break
        length = payload[i + 1]
        options[code] = payload[i + 2:i + 2 + length]
        i += 2 + length
    return xid, offered, options


def parse_ip_udp(packet):
    """Return (source address, destination port, UDP payload) or None."""
    if len(packet) < 28 or packet[0] >> 4 != 4 or packet[9] != 17:
        return None
    header = (packet[0] & 0x0F) * 4
    if len(packet) < header + 8:
        return None
    dport = struct.unpack("!H", packet[header + 2:header + 4])[0]
    return socket.inet_ntoa(packet[12:16]), dport, packet[header + 8:]


def addresses(raw):
    return ", ".join(socket.inet_ntoa(raw[i:i + 4]) for i in range(0, len(raw) - 3, 4))


def main():
    iface = sys.argv[1] if len(sys.argv) > 1 else "eth1"
    mac = mac_of(iface)
    xid = random.getrandbits(32)

    # Listening below the firewall and next to NetworkManager's own client
    listener = socket.socket(socket.AF_PACKET, socket.SOCK_DGRAM, socket.htons(ETH_P_IP))
    listener.bind((iface, ETH_P_IP))

    sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sender.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sender.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sender.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, iface.encode())
    try:
        sender.bind(("", 68))
    except OSError:
        sender.bind(("", 0))

    print(f"DHCPDISCOVER on {iface} ({mac.hex(':')}), listening {WAIT} s")
    seen = {}
    deadline = time.monotonic() + WAIT
    next_send = 0.0
    while time.monotonic() < deadline:
        if time.monotonic() >= next_send:
            sender.sendto(build_discover(mac, xid), ("255.255.255.255", 67))
            next_send = time.monotonic() + 3
        ready, _, _ = select.select([listener], [], [], 0.5)
        if not ready:
            continue
        packet, sockaddr = listener.recvfrom(4096)
        udp = parse_ip_udp(packet)
        if udp is None or udp[1] != 68:
            continue
        dhcp = parse_dhcp(udp[2])
        if dhcp is None or dhcp[0] != xid:
            continue
        _, offered, options = dhcp
        if options.get(53) != bytes([2]):
            continue
        server = addresses(options.get(54, b"")) or udp[0]
        if server in seen:
            continue
        seen[server] = True
        lease = struct.unpack("!I", options[51])[0] if len(options.get(51, b"")) == 4 else None
        print()
        print(f"  server     {server}   (hardware address {sockaddr[4].hex(':')})")
        print(f"  offers     {offered}")
        print(f"  router     {addresses(options.get(3, b'')) or '-'}")
        print(f"  dns        {addresses(options.get(6, b'')) or '-'}")
        print(f"  lease      {lease} s" if lease is not None else "  lease      -")

    print()
    print(f"{len(seen)} DHCP server(s) answered")
    return 0 if seen else 1


if __name__ == "__main__":
    sys.exit(main())
