"""Read world metadata from a 1.4.5.8 Terraria fixture on loopback."""
import socket
import struct
import sys

def check_world(port):
    # Desktop release 326 is the curRelease constant in the pinned 1.4.5.8 server.
    def packet(kind, data=b""):
        return struct.pack("<HB", len(data) + 3, kind) + data

    with socket.create_connection(("127.0.0.1", port), 5) as sock, sock.makefile("rb") as wire:
        def receive():
            size, kind = struct.unpack("<HB", wire.read(3))
            if not 3 <= size <= 65535:
                raise ValueError("Invalid packet size")
            return kind, wire.read(size - 3)
        version = b"Terraria326"
        sock.sendall(packet(1, bytes([len(version)]) + version))
        kind, data = receive()
        assert kind == 3, f"Terraria did not accept release 326 (packet {kind})."
        sock.sendall(packet(6))
        for _ in range(16):
            kind, data = receive()
            if kind == 7:
                assert b"SDK fixture" in data, "Wrong world in the server response"
                return
        raise AssertionError("World information was not delivered")


if __name__ == "__main__":
    check_world(int(sys.argv[1]))
