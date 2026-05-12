"""Fake STUN server for WebRTC IP spoofing.

For each registered device (LAN IP → proxy public IP), responds to STUN
Binding Requests with the proxy server's IP as the XOR-MAPPED-ADDRESS.

Flow:
  1. Browser on proxied device resolves stun.l.google.com → 192.168.1.1 (via DNS override)
  2. STUN Binding Request arrives at 192.168.1.1:3478 (router, bypasses TPROXY)
  3. FakeStunServer looks up sender IP → proxy IP mapping
  4. Replies with XOR-MAPPED-ADDRESS = proxy_ip:random_port
  5. Browser believes its public IP is the proxy server's IP
"""

import socket
import struct
import threading
import logging
import random

logger = logging.getLogger(__name__)

STUN_BINDING_REQUEST  = 0x0001
STUN_BINDING_RESPONSE = 0x0101
STUN_MAGIC_COOKIE     = 0x2112A442
ATTR_XOR_MAPPED_ADDRESS = 0x0020


class FakeStunServer:
    """UDP STUN server that returns the proxy IP for registered devices."""

    def __init__(self, host: str = '0.0.0.0', port: int = 3478):
        self.host = host
        self.port = port
        self._device_map: dict = {}   # {device_ip: proxy_ip}
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread = None
        self._sock: socket.socket = None

    # ------------------------------------------------------------------ #
    #  Device registry                                                     #
    # ------------------------------------------------------------------ #

    def register(self, device_ip: str, proxy_ip: str) -> None:
        """Map a LAN device IP to the proxy server public IP it should claim."""
        with self._lock:
            self._device_map[device_ip] = proxy_ip
        logger.info(f"STUN: registered {device_ip} → {proxy_ip}")

    def unregister(self, device_ip: str) -> None:
        """Remove a device from the mapping."""
        with self._lock:
            self._device_map.pop(device_ip, None)
        logger.info(f"STUN: unregistered {device_ip}")

    def get_all(self) -> dict:
        """Return a snapshot of all registered device→proxy mappings."""
        with self._lock:
            return dict(self._device_map)

    # ------------------------------------------------------------------ #
    #  Lifecycle                                                           #
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._serve, daemon=True, name='fake-stun')
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    #  Internal                                                            #
    # ------------------------------------------------------------------ #

    def _serve(self) -> None:
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.bind((self.host, self.port))
            self._sock.settimeout(1.0)
            logger.info(f"Fake STUN server listening on UDP {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Fake STUN server failed to bind {self.host}:{self.port}: {e}")
            self._running = False
            return

        while self._running:
            try:
                data, addr = self._sock.recvfrom(2048)
                self._handle(data, addr)
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    logger.debug(f"STUN recv error: {e}")

        try:
            self._sock.close()
        except Exception:
            pass

    def _handle(self, data: bytes, addr) -> None:
        """Parse STUN Binding Request and reply with proxy IP as XOR-MAPPED-ADDRESS."""
        if len(data) < 20:
            return

        msg_type, _msg_len = struct.unpack_from('!HH', data, 0)
        magic              = struct.unpack_from('!I',  data, 4)[0]
        txn_id             = data[8:20]

        if msg_type != STUN_BINDING_REQUEST or magic != STUN_MAGIC_COOKIE:
            return

        sender_ip = addr[0]
        with self._lock:
            proxy_ip = self._device_map.get(sender_ip)

        if not proxy_ip:
            logger.debug(f"STUN: unregistered sender {sender_ip}, ignoring")
            return

        # Encode XOR-MAPPED-ADDRESS (IPv4)
        port   = random.randint(10000, 60000)
        xport  = port ^ (STUN_MAGIC_COOKIE >> 16)
        ip_int = struct.unpack('!I', socket.inet_aton(proxy_ip))[0]
        xaddr  = struct.pack('!I', ip_int ^ STUN_MAGIC_COOKIE)

        # Attribute TLV: type(2) + length(2) + reserved(1) + family(1) + xport(2) + xaddr(4)
        attr = struct.pack('!HHBBH', ATTR_XOR_MAPPED_ADDRESS, 8, 0, 1, xport) + xaddr

        # Response header: type(2) + attr_len(2) + magic(4) + transaction_id(12)
        resp = struct.pack('!HHI', STUN_BINDING_RESPONSE, len(attr), STUN_MAGIC_COOKIE) + txn_id + attr

        try:
            self._sock.sendto(resp, addr)
            logger.debug(f"STUN: replied to {sender_ip} → proxy {proxy_ip}:{port}")
        except Exception as e:
            logger.debug(f"STUN: send error to {addr}: {e}")


# Module-level singleton ─────────────────────────────────────────────────── #

_stun_server: FakeStunServer = None


def get_stun_server() -> FakeStunServer:
    global _stun_server
    if _stun_server is None:
        _stun_server = FakeStunServer()
    return _stun_server
