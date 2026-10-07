#!/usr/bin/env python3
"""
Bridge QLab (OSC/UDP) -> grandMA2 onPC (Telnet/TCP).

QLab manda triggers abstractos (/lx/go/8) y el bridge los traduce al comando
de grandMA2 definido en config.json (p. ej. "Go Executor 1.108").

Solo usa la librería estándar de Python: no hay que instalar nada con pip.
"""

import argparse
import json
import logging
import logging.handlers
import os
import re
import socket
import struct
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
log = logging.getLogger("ma2_bridge")


# --------------------------------------------------------------------------
# OSC (parser mínimo: mensajes y bundles, tipos i f s h d T F N)
# --------------------------------------------------------------------------

def _read_osc_string(data, i):
    end = data.index(b"\0", i)
    return data[i:end].decode("utf-8", "replace"), (end + 4) & ~3


def parse_osc(data):
    """Devuelve una lista de (address, [args]). Los bundles se aplanan."""
    if data.startswith(b"#bundle\0"):
        messages = []
        i = 16  # "#bundle\0" + timetag de 8 bytes
        while i + 4 <= len(data):
            (size,) = struct.unpack(">i", data[i:i + 4])
            i += 4
            messages.extend(parse_osc(data[i:i + size]))
            i += size
        return messages

    address, i = _read_osc_string(data, 0)
    if not address.startswith("/"):
        raise ValueError("no es un mensaje OSC")
    args = []
    if i < len(data) and data[i:i + 1] == b",":
        tags, i = _read_osc_string(data, i)
        for tag in tags[1:]:
            if tag == "i":
                args.append(struct.unpack(">i", data[i:i + 4])[0]); i += 4
            elif tag == "f":
                args.append(struct.unpack(">f", data[i:i + 4])[0]); i += 4
            elif tag == "h":
                args.append(struct.unpack(">q", data[i:i + 8])[0]); i += 8
            elif tag == "d":
                args.append(struct.unpack(">d", data[i:i + 8])[0]); i += 8
            elif tag == "s":
                s, i = _read_osc_string(data, i); args.append(s)
            elif tag == "T":
                args.append(True)
            elif tag == "F":
                args.append(False)
            elif tag == "N":
                args.append(None)
            else:
                raise ValueError("tipo OSC no soportado: %r" % tag)
    return [(address, args)]


def _osc_string(s):
    b = s.encode("utf-8") + b"\0"
    return b + b"\0" * (-len(b) % 4)


def build_osc(address, *args):
    """Construye un mensaje OSC con argumentos int, float o str."""
    tags, payload = ",", b""
    for a in args:
        if isinstance(a, bool) or a is None:
            raise TypeError("tipo no soportado")
        if isinstance(a, int):
            tags += "i"; payload += struct.pack(">i", a)
        elif isinstance(a, float):
            tags += "f"; payload += struct.pack(">f", a)
        else:
            tags += "s"; payload += _osc_string(str(a))
    return _osc_string(address) + _osc_string(tags) + payload


# --------------------------------------------------------------------------
# Cliente Telnet de grandMA2 (conexión persistente con reconexión automática)
# --------------------------------------------------------------------------

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_IAC = re.compile(rb"\xff[\xfb-\xfe].|\xff[\xf0-\xfa]", re.S)


class MA2Telnet:
    def __init__(self, host, port, user="", password="", retry_seconds=2.0):
        self.host, self.port = host, port
        self.user, self.password = user, password
        self.retry_seconds = retry_seconds
        self._sock = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="ma2-telnet", daemon=True)

    @property
    def connected(self):
        return self._sock is not None

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        with self._lock:
            self._close()

    def _connect(self):
        """Debe llamarse con self._lock tomado."""
        if self._sock is not None:
            return
        sock = socket.create_connection((self.host, self.port), timeout=3)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        for opt, val in (("TCP_KEEPIDLE", 5), ("TCP_KEEPINTVL", 2), ("TCP_KEEPCNT", 3)):
            if hasattr(socket, opt):
                sock.setsockopt(socket.IPPROTO_TCP, getattr(socket, opt), val)
        if hasattr(socket, "SIO_KEEPALIVE_VALS"):  # Windows
            sock.ioctl(socket.SIO_KEEPALIVE_VALS, (1, 5000, 2000))
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.settimeout(1.0)
        self._sock = sock
        if self.user:
            self._send_raw('Login "%s" "%s"' % (self.user, self.password))
        log.info("Conectado a grandMA2 en %s:%s", self.host, self.port)

    def _close(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
            log.warning("Desconectado de grandMA2")

    def _send_raw(self, cmd):
        self._sock.sendall((cmd + "\r\n").encode("utf-8"))

    def send(self, cmd):
        """Envía un comando a la línea de comandos de MA. Devuelve True si salió."""
        with self._lock:
            for attempt in (1, 2):
                try:
                    self._connect()
                    self._send_raw(cmd)
                    return True
                except OSError as e:
                    log.error("Fallo al enviar a grandMA2 (intento %d): %s", attempt, e)
                    self._close()
        return False

    def _run(self):
        """Mantiene la conexión viva y registra lo que responde MA."""
        buf = b""
        while not self._stop.is_set():
            with self._lock:
                if self._sock is None:
                    try:
                        self._connect()
                    except OSError as e:
                        log.debug("grandMA2 no disponible: %s", e)
                sock = self._sock
            if sock is None:
                self._stop.wait(self.retry_seconds)
                continue
            try:
                chunk = sock.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                chunk = b""
            if not chunk:
                with self._lock:
                    if self._sock is sock:
                        self._close()
                continue
            buf += _IAC.sub(b"", chunk)
            *lines, buf = buf.split(b"\n")
            for line in lines:
                text = _ANSI.sub("", line.decode("latin-1")).strip()
                if text:
                    log.debug("MA2 > %s", text)


class DryRun:
    """Sustituto de MA2Telnet para probar sin consola: solo registra."""
    connected = True

    def start(self):
        pass

    def stop(self):
        pass

    def send(self, cmd):
        log.info("[dry-run] %s", cmd)
        return True


# --------------------------------------------------------------------------
# Bridge
# --------------------------------------------------------------------------

def _trigger_key(value):
    """Normaliza 8, 8.0, "08" y "8" a "8"; conserva decimales como "8.5"."""
    s = str(value).strip()
    try:
        f = float(s)
    except ValueError:
        return s
    return str(int(f)) if f.is_integer() else repr(f)


class Bridge:
    def __init__(self, config, ma):
        self.ma = ma
        self.prefix = config.get("osc_prefix", "/lx").rstrip("/")
        self.default_command = config.get("default_command")
        self.allow_raw = bool(config.get("allow_raw_commands", False))
        self.triggers = {}
        for key, entry in config.get("triggers", {}).items():
            if isinstance(entry, str):
                entry = {"command": entry}
            self.triggers[_trigger_key(key)] = entry

    def command_for(self, trigger):
        entry = self.triggers.get(trigger)
        if entry is not None:
            return entry["command"]
        if self.default_command:
            return self.default_command.format(n=trigger)
        return None

    def fire(self, trigger):
        trigger = _trigger_key(trigger)
        cmd = self.command_for(trigger)
        if cmd is None:
            log.warning("LX %s no está en config.json; ignorado", trigger)
            return False
        name = self.triggers.get(trigger, {}).get("name", "")
        log.info("LX %s %s-> %s", trigger, "(%s) " % name if name else "", cmd)
        return self.ma.send(cmd)

    def handle(self, address, args, reply):
        """Procesa un mensaje OSC. `reply(address, *args)` responde al remitente."""
        p = self.prefix
        if address == p + "/go" and args:
            return self.fire(args[0])
        if address.startswith(p + "/go/"):
            return self.fire(address[len(p) + 4:])
        if address == p + "/ping":
            reply(p + "/pong", "ma2:connected" if self.ma.connected else "ma2:disconnected")
            return True
        if address == p + "/cmd":
            if not self.allow_raw:
                log.warning("Comando directo rechazado (allow_raw_commands=false): %s", args)
                return False
            if args and isinstance(args[0], str):
                log.info("Comando directo -> %s", args[0])
                return self.ma.send(args[0])
        log.warning("Mensaje OSC no reconocido: %s %s", address, args)
        return False


def serve(bridge, host, port, stop_event=None, ready=None):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # Sin SO_REUSEADDR: un segundo bridge en el mismo puerto debe fallar, no
    # repartirse los paquetes en silencio con el primero.
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):  # Windows
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    sock.bind((host, port))
    sock.settimeout(0.5)
    log.info("Escuchando OSC en %s:%d (prefijo %s)", host, sock.getsockname()[1], bridge.prefix)
    if ready is not None:
        ready(sock.getsockname())
    try:
        while stop_event is None or not stop_event.is_set():
            try:
                data, sender = sock.recvfrom(65535)
            except socket.timeout:
                continue
            except ConnectionResetError:  # Windows tras ICMP "port unreachable"
                continue

            def reply(address, *args, _to=sender):
                sock.sendto(build_osc(address, *args), _to)

            try:
                messages = parse_osc(data)
            except (ValueError, struct.error, IndexError) as e:
                log.warning("Paquete inválido de %s: %s", sender[0], e)
                continue
            for address, args in messages:
                log.debug("OSC < %s %s %s", sender[0], address, args)
                try:
                    bridge.handle(address, args, reply)
                except Exception:
                    log.exception("Error procesando %s", address)
    finally:
        sock.close()


def load_config(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def setup_logging(verbose, log_file):
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s")
    log.setLevel(logging.DEBUG)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    console.setFormatter(fmt)
    log.addHandler(console)
    if log_file:
        fh = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        log.addHandler(fh)


EXIT_CONFIG = 2
EXIT_PORT_IN_USE = 3


def check(config, bridge):
    """Valida la configuración y comprueba si grandMA2 responde. No dispara nada."""
    osc, mc = config.get("osc", {}), config["ma2"]
    print("Python %s" % sys.version.split()[0])
    print("OSC:      escuchando en UDP %s:%s, prefijo %s"
          % (osc.get("host", "0.0.0.0"), osc.get("port", 8000), bridge.prefix))
    print("grandMA2: telnet %s:%s" % (mc["host"], mc.get("port", 30000)))
    print("Triggers:")
    for key in sorted(bridge.triggers, key=lambda k: (float(k) if k.replace(".", "", 1).isdigit() else 1e9, k)):
        entry = bridge.triggers[key]
        print("  LX %-5s %-24s -> %s" % (key, entry.get("name", ""), entry["command"]))
    if bridge.default_command:
        print("  (resto)  -> %s" % bridge.default_command)
    try:
        socket.create_connection((mc["host"], int(mc.get("port", 30000))), timeout=2).close()
        print("grandMA2 responde en el puerto Telnet: OK")
    except OSError as e:
        print("grandMA2 NO responde (%s). ¿Está abierta grandMA2 onPC con Telnet = Login Enabled?" % e)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Bridge OSC (QLab) -> Telnet (grandMA2 onPC)")
    ap.add_argument("--config", default=os.path.join(HERE, "config.json"))
    ap.add_argument("--dry-run", action="store_true", help="no conecta a MA; solo muestra los comandos")
    ap.add_argument("--fire", metavar="LX", help="dispara un trigger una vez y sale (prueba)")
    ap.add_argument("--check", action="store_true", help="valida config.json y la conexión a MA, y sale")
    ap.add_argument("-v", "--verbose", action="store_true", help="muestra también lo que responde MA")
    args = ap.parse_args(argv)

    try:
        config = load_config(args.config)
        config["ma2"]["host"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        print("Error en %s: %s" % (args.config, e), file=sys.stderr)
        return EXIT_CONFIG

    if args.check:
        return check(config, Bridge(config, DryRun()))

    setup_logging(args.verbose, os.path.join(HERE, config.get("log_file", "ma2_bridge.log")))

    if args.dry_run:
        ma = DryRun()
    else:
        mc = config["ma2"]
        ma = MA2Telnet(mc["host"], int(mc.get("port", 30000)),
                       mc.get("user", ""), mc.get("password", ""))
    bridge = Bridge(config, ma)

    if args.fire:
        ok = bridge.fire(args.fire)
        time.sleep(0.5)  # deja que MA responda antes de cerrar
        return 0 if ok else 1

    ma.start()
    osc = config.get("osc", {})
    port = int(osc.get("port", 8000))
    try:
        serve(bridge, osc.get("host", "0.0.0.0"), port)
    except KeyboardInterrupt:
        log.info("Detenido")
    except OSError as e:
        if e.errno in (98, 10048) or getattr(e, "winerror", None) in (10013, 10048):
            log.error("El puerto UDP %d ya está en uso: probablemente el bridge ya está "
                      "corriendo en otra ventana.", port)
            return EXIT_PORT_IN_USE
        raise
    finally:
        ma.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
