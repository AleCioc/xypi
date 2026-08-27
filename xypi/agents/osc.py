"""Raw UDP OSC sender for SuperCollider corner events."""

from __future__ import annotations

import socket
import struct


class CornerOscSender:
    def __init__(self, host: str, port: int, path: str):
        self.addr = (host, int(port))
        self.path = path
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    @staticmethod
    def _osc_string(value: str) -> bytes:
        raw = value.encode("utf-8") + b"\0"
        return raw + b"\0" * ((4 - len(raw) % 4) % 4)

    def send_corner(self, layer: str, sound: str, y_pitch: float, x_timbre: float, duration: float) -> None:
        packet = self._osc_string(self.path)
        packet += self._osc_string(",ssfff")
        packet += self._osc_string(layer)
        packet += self._osc_string(sound)
        packet += struct.pack(">fff", float(y_pitch), float(x_timbre), float(duration))
        self.sock.sendto(packet, self.addr)
