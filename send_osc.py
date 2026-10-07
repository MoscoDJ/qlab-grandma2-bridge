#!/usr/bin/env python3
"""
Simula a QLab: manda un mensaje OSC al bridge y muestra la respuesta, si la hay.

    python send_osc.py 192.168.1.50 8000 /lx/go/3
    python send_osc.py 192.168.1.50 8000 /lx/go 3
    python send_osc.py 192.168.1.50 8000 /lx/ping
"""

import socket
import sys

from ma2_bridge import build_osc, parse_osc


def _arg(text):
    for conv in (int, float):
        try:
            return conv(text)
        except ValueError:
            pass
    return text


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    host, port, address, *rest = argv
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(1.0)
    sock.sendto(build_osc(address, *map(_arg, rest)), (host, int(port)))
    print("enviado:", address, *rest)
    try:
        data, _ = sock.recvfrom(65535)
        for addr, args in parse_osc(data):
            print("respuesta:", addr, *args)
    except (socket.timeout, ConnectionResetError):
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
