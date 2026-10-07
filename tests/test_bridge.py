import os
import socket
import struct
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ma2_bridge as mb  # noqa: E402


class FakeMA2:
    """Servidor TCP que imita el telnet de grandMA2 y guarda las líneas recibidas."""

    def __init__(self, port=0):
        self.lines = []
        self.srv = socket.socket()
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", port))
        self.srv.listen()
        self.port = self.srv.getsockname()[1]
        self.clients = []
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while True:
            try:
                c, _ = self.srv.accept()
            except OSError:
                return
            self.clients.append(c)
            c.sendall(b"\xff\xfb\x01\x1b[32mWelcome to grandMA2 telnet\x1b[0m\r\n")
            threading.Thread(target=self._read, args=(c,), daemon=True).start()

    def _read(self, c):
        buf = b""
        while True:
            try:
                chunk = c.recv(4096)
            except OSError:
                return
            if not chunk:
                return
            buf += chunk
            *lines, buf = buf.split(b"\r\n")
            self.lines.extend(l.decode() for l in lines)

    def close(self):
        for s in self.clients + [self.srv]:
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            s.close()

    def wait_for(self, line, timeout=3):
        end = time.time() + timeout
        while time.time() < end:
            if line in self.lines:
                return True
            time.sleep(0.02)
        return False


CONFIG = {
    "triggers": {
        "1": {"name": "Inicio", "command": "Go Executor 1.101"},
        "8": "Go Executor 1.108",
        "8.5": "Goto Executor 1.1 Cue 32",
    },
}


@pytest.fixture
def rig():
    ma = FakeMA2()
    client = mb.MA2Telnet("127.0.0.1", ma.port, "administrator", "admin", retry_seconds=0.1)
    client.start()
    bridge = mb.Bridge(CONFIG, client)
    stop = threading.Event()
    addr = {}
    ready = threading.Event()
    t = threading.Thread(target=mb.serve, args=(bridge, "127.0.0.1", 0, stop,
                                                lambda a: (addr.update(a=a), ready.set())), daemon=True)
    t.start()
    ready.wait(2)
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.settimeout(2)

    def send(address, *args):
        udp.sendto(mb.build_osc(address, *args), addr["a"])

    yield ma, client, send, udp
    stop.set()
    client.stop()
    ma.close()
    t.join(2)


def test_osc_roundtrip():
    msg = mb.build_osc("/lx/go", 8, 1.5, "hola")
    assert mb.parse_osc(msg) == [("/lx/go", [8, 1.5, "hola"])]


def test_osc_bundle():
    m1, m2 = mb.build_osc("/lx/go/1"), mb.build_osc("/lx/go/2")
    bundle = b"#bundle\0" + b"\0" * 8 + struct.pack(">i", len(m1)) + m1 + struct.pack(">i", len(m2)) + m2
    assert [a for a, _ in mb.parse_osc(bundle)] == ["/lx/go/1", "/lx/go/2"]


@pytest.mark.parametrize("value,key", [(8, "8"), (8.0, "8"), ("08", "8"), (" 8 ", "8"), ("8.5", "8.5")])
def test_trigger_key(value, key):
    assert mb._trigger_key(value) == key


def test_login_then_go_by_path(rig):
    ma, _, send, _ = rig
    assert ma.wait_for('Login "administrator" "admin"')
    send("/lx/go/1")
    assert ma.wait_for("Go Executor 1.101")


def test_go_by_argument_int_float_and_decimal(rig):
    ma, _, send, _ = rig
    send("/lx/go", 8)
    assert ma.wait_for("Go Executor 1.108")
    ma.lines.clear()
    send("/lx/go", 8.5)
    assert ma.wait_for("Goto Executor 1.1 Cue 32")


def test_unknown_trigger_and_raw_command_are_ignored(rig):
    ma, _, send, _ = rig
    send("/lx/go/99")
    send("/lx/cmd", "Off Executor Thru")
    send("/lx/go/1")
    assert ma.wait_for("Go Executor 1.101")
    assert not any("Off" in l or "99" in l for l in ma.lines)


def test_ping_reports_connection(rig):
    ma, client, send, udp = rig
    assert ma.wait_for('Login "administrator" "admin"')
    send("/lx/ping")
    data, _ = udp.recvfrom(1024)
    assert mb.parse_osc(data) == [("/lx/pong", ["ma2:connected"])]


def test_reconnects_after_ma_restart(rig):
    ma, client, send, _ = rig
    assert ma.wait_for('Login "administrator" "admin"')
    port = ma.port
    ma.close()
    time.sleep(0.3)
    ma2 = FakeMA2(port)
    try:
        assert ma2.wait_for('Login "administrator" "admin"')
        send("/lx/go/8")
        assert ma2.wait_for("Go Executor 1.108")
    finally:
        ma2.close()


def test_default_command_template():
    sent = []

    class Sink:
        connected = True

        def send(self, cmd):
            sent.append(cmd)
            return True

    b = mb.Bridge({"default_command": "Macro {n}"}, Sink())
    assert b.fire("12")
    assert sent == ["Macro 12"]
