"""
network.py — LAN multiplayer plumbing for do-o-english.

Two players (or more) on the same WiFi can find each other and play together.
This is pure stdlib so no extra deps beyond pygame.

HOW IT WORKS
============

1. HOST: starts a TCP server on a random free port and a UDP "beacon"
   that announces "I'm here, name=Alice, port=12345" every second on the
   broadcast address. Anyone on the same WiFi who's listening will see it.

2. CLIENT: opens a UDP socket on the discovery port and listens for those
   beacons. Anything it hears (and that's still alive within ~5 s) shows
   up as a joinable host in the lobby.

3. JOIN: the client opens a TCP connection to the host, says
   {"type": "hello", "name": "..."} and from then on host and client
   exchange small JSON messages over that socket.

Threading model
---------------
All network I/O lives on background threads. They never touch pygame
state directly. Instead, they push events into a `queue.Queue` that the
main pygame thread drains once per frame inside `App.update()`.

Wire format
-----------
Each TCP message is a 4-byte big-endian length followed by a JSON body.
This keeps a clean message boundary even if TCP fragments / merges.
"""
from __future__ import annotations

import json
import queue
import socket
import struct
import threading
import time
import uuid

# ---- Constants --------------------------------------------------------------

DISCOVERY_PORT     = 54545
BROADCAST_ADDR     = "255.255.255.255"
APP_TAG            = "do-o-english"
PROTOCOL_VERSION   = 1
BEACON_INTERVAL_S  = 1.0
HOST_TIMEOUT_S     = 5.0
MAX_MSG_BYTES      = 1_000_000


# ---- Low-level helpers ------------------------------------------------------

def _recv_exact(sock, n):
    """Read exactly n bytes from a TCP socket, or None on close/error."""
    buf = b""
    while len(buf) < n:
        try:
            chunk = sock.recv(n - len(buf))
        except OSError:
            return None
        if not chunk:
            return None
        buf += chunk
    return buf


def send_msg(sock, msg):
    """Send a single length-prefixed JSON message over a TCP socket."""
    try:
        data = json.dumps(msg, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError):
        return False
    try:
        sock.sendall(struct.pack("!I", len(data)) + data)
        return True
    except OSError:
        return False


def recv_msg(sock):
    """Read the next message from a TCP socket, or None on close/error."""
    hdr = _recv_exact(sock, 4)
    if hdr is None:
        return None
    (n,) = struct.unpack("!I", hdr)
    if n <= 0 or n > MAX_MSG_BYTES:
        return None
    body = _recv_exact(sock, n)
    if body is None:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except Exception:
        return None


def local_ips():
    """Return non-loopback IPv4 addresses for this machine (best effort)."""
    ips = []
    # Trick: open a UDP socket to a public IP (no packet is sent for AF_INET
    # SOCK_DGRAM with no actual send) and read its local endpoint.
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for entry in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = entry[4][0]
            if ip != "127.0.0.1" and ip not in ips:
                ips.append(ip)
    except OSError:
        pass
    return ips


# ---- HOST: beacon broadcaster ----------------------------------------------

class LobbyBeacon:
    """
    Runs on a HOST. Broadcasts a small UDP packet every second so any
    other machine on the same WiFi can find this game.
    """

    def __init__(self, host_name: str, tcp_port: int, host_id: str | None = None):
        self.host_name = host_name
        self.tcp_port = tcp_port
        self.host_id = host_id or uuid.uuid4().hex[:8]
        self._sock = None
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass

    def _run(self):
        payload = {
            "app":      APP_TAG,
            "type":     "host",
            "name":     self.host_name,
            "host_id":  self.host_id,
            "tcp_port": self.tcp_port,
            "version":  PROTOCOL_VERSION,
        }
        data = json.dumps(payload).encode("utf-8")
        while not self._stop.is_set():
            try:
                self._sock.sendto(data, (BROADCAST_ADDR, DISCOVERY_PORT))
            except OSError:
                pass
            self._stop.wait(BEACON_INTERVAL_S)


# ---- CLIENT: beacon listener ------------------------------------------------

class LobbyListener:
    """
    Runs on a CLIENT (and also locally on the host so they can see
    themselves in the list, harmless). Listens for HOST beacons on the
    discovery UDP port and keeps a fresh list of live hosts.
    """

    def __init__(self):
        self._sock = None
        self._stop = threading.Event()
        self._thread = None
        self._hosts: dict[str, dict] = {}
        self._lock = threading.Lock()

    def start(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # SO_REUSEPORT lets multiple processes on the same machine all bind
        # to the discovery port — handy if you run two instances on one PC
        # while testing. Not available on Windows; ignore failures.
        try:
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except (AttributeError, OSError):
            pass
        try:
            self._sock.bind(("0.0.0.0", DISCOVERY_PORT))
        except OSError:
            # Someone else owns the port without SO_REUSEPORT — fall back to
            # an ephemeral port (we'll only see our own machine's broadcasts).
            self._sock.bind(("0.0.0.0", 0))
        self._sock.settimeout(0.5)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass

    def hosts(self):
        """Return the list of currently-alive hosts (last_seen < 5 s ago)."""
        now = time.time()
        with self._lock:
            return sorted(
                [h for h in self._hosts.values()
                 if now - h["last_seen"] < HOST_TIMEOUT_S],
                key=lambda h: h["name"].lower(),
            )

    def _run(self):
        while not self._stop.is_set():
            try:
                data, addr = self._sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                msg = json.loads(data.decode("utf-8"))
            except Exception:
                continue
            if msg.get("app") != APP_TAG or msg.get("type") != "host":
                continue
            host_id = msg.get("host_id")
            if not host_id:
                continue
            with self._lock:
                self._hosts[host_id] = {
                    "host_id":  host_id,
                    "name":     msg.get("name", "?"),
                    "addr":     addr[0],
                    "tcp_port": int(msg.get("tcp_port", 0)),
                    "last_seen": time.time(),
                }


# ---- HOST: TCP server -------------------------------------------------------

class HostServer:
    """
    TCP server that accepts peer connections. Per peer we spawn a small
    reader thread that pushes any incoming message into `self.events`
    as {"kind": "msg", "peer_id": int, "msg": dict}. We also push
    {"kind": "join"} and {"kind": "leave"} so the main thread can react
    to lobby changes.

    The host's own player is NOT a peer — it lives in the App directly
    and is referred to as peer_id 0.
    """

    def __init__(self):
        self.sock = None
        self.tcp_port = 0
        self.events: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._peers: dict[int, dict] = {}
        self._next_peer_id = 1
        self._lock = threading.Lock()

    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("0.0.0.0", 0))   # any free port
        self.tcp_port = self.sock.getsockname()[1]
        self.sock.listen(8)
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def stop(self):
        self._stop.set()
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
        with self._lock:
            for p in list(self._peers.values()):
                try:
                    p["sock"].close()
                except OSError:
                    pass
            self._peers.clear()

    # -- peer bookkeeping -------------------------------------------------
    def peer_ids(self):
        with self._lock:
            return list(self._peers.keys())

    def peer_name(self, pid):
        with self._lock:
            p = self._peers.get(pid)
            return p["name"] if p else None

    def set_peer_name(self, pid, name):
        with self._lock:
            p = self._peers.get(pid)
            if p:
                p["name"] = name

    def peer_count(self):
        with self._lock:
            return len(self._peers)

    # -- I/O --------------------------------------------------------------
    def send_to(self, peer_id, msg):
        with self._lock:
            p = self._peers.get(peer_id)
        if p:
            send_msg(p["sock"], msg)

    def broadcast(self, msg, exclude=None):
        with self._lock:
            items = [(pid, p["sock"]) for pid, p in self._peers.items()
                     if exclude is None or pid != exclude]
        for pid, sock in items:
            send_msg(sock, msg)

    # -- internals --------------------------------------------------------
    def _accept_loop(self):
        while not self._stop.is_set():
            try:
                sock, addr = self.sock.accept()
            except OSError:
                break
            with self._lock:
                pid = self._next_peer_id
                self._next_peer_id += 1
                self._peers[pid] = {"sock": sock, "addr": addr, "name": "?"}
            threading.Thread(
                target=self._peer_loop, args=(pid,), daemon=True
            ).start()

    def _peer_loop(self, pid):
        sock = self._peers[pid]["sock"]
        self.events.put({"kind": "join", "peer_id": pid})
        while not self._stop.is_set():
            msg = recv_msg(sock)
            if msg is None:
                break
            self.events.put({"kind": "msg", "peer_id": pid, "msg": msg})
        with self._lock:
            try:
                sock.close()
            except OSError:
                pass
            self._peers.pop(pid, None)
        self.events.put({"kind": "leave", "peer_id": pid})


# ---- CLIENT: TCP peer -------------------------------------------------------

class ClientPeer:
    """TCP client connected to a host. Pushes events into `self.events`."""

    def __init__(self, host_addr, host_port, name):
        self.host_addr = host_addr
        self.host_port = int(host_port)
        self.name = name
        self.sock = None
        self.events: queue.Queue = queue.Queue()
        self._stop = threading.Event()

    def start(self):
        """Synchronously connect + send hello. Returns True on success."""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(5.0)
        try:
            self.sock.connect((self.host_addr, self.host_port))
        except OSError as e:
            self.events.put({"kind": "error", "error": str(e)})
            return False
        self.sock.settimeout(None)
        if not send_msg(self.sock, {"type": "hello", "name": self.name}):
            self.events.put({"kind": "error", "error": "could not send hello"})
            return False
        threading.Thread(target=self._read_loop, daemon=True).start()
        return True

    def stop(self):
        self._stop.set()
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass

    def send(self, msg):
        if self.sock:
            send_msg(self.sock, msg)

    def _read_loop(self):
        while not self._stop.is_set():
            msg = recv_msg(self.sock)
            if msg is None:
                break
            self.events.put({"kind": "msg", "msg": msg})
        self.events.put({"kind": "disconnected"})
