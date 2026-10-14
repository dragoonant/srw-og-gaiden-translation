"""PCSX2 PINE client: read/write EE memory and save/load states while the game runs.

Needs EnablePINE = true in PCSX2.ini (slot 28011, TCP on localhost on Windows).

  pine.py info                          game id, title, status
  pine.py dump  <addr> <len> <out.bin>  read EE memory
  pine.py write <addr> <in.bin>         write EE memory
  pine.py find  <hex|text> [start] [end]   search EE RAM (text is encoded Shift-JIS)
  pine.py save  <slot> / load <slot>    save state to / load state from a slot
"""
import socket
import struct
import sys

R8, R16, R32, R64, W8, W16, W32, W64 = range(8)
VERSION, SAVESTATE, LOADSTATE, TITLE, ID, UUID, GAMEVER, STATUS = range(8, 16)
MAX_BATCH = 60000  # stay under PINE's 650,000-byte reply buffer


class Pine:
    def __init__(self, port=28011):
        self.s = socket.create_connection(("127.0.0.1", port), timeout=10)

    def _call(self, body):
        self.s.sendall(struct.pack("<I", len(body) + 4) + body)
        hdr = self._recv(4)
        n = struct.unpack("<I", hdr)[0]
        reply = self._recv(n - 4)
        if reply[0] != 0:
            raise IOError("PINE command failed")
        return reply[1:]

    def _recv(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.s.recv(n - len(buf))
            if not chunk:
                raise IOError("PINE connection closed")
            buf += chunk
        return buf

    def read(self, addr, length):
        out = bytearray()
        addr0, end = addr, addr + length
        a = addr0 & ~7
        while a < end:
            cnt = min(MAX_BATCH // 9, (end - a + 7) // 8)
            body = b"".join(struct.pack("<BI", R64, a + 8 * i) for i in range(cnt))
            out += self._call(body)
            a += 8 * cnt
        skip = addr0 & 7
        return bytes(out[skip:skip + length])

    def write(self, addr, data):
        body = b""
        for i, b in enumerate(data):
            body += struct.pack("<BIB", W8, addr + i, b)
            if len(body) > MAX_BATCH:
                self._call(body)
                body = b""
        if body:
            self._call(body)

    def string(self, op):
        r = self._call(bytes([op]))
        n = struct.unpack_from("<I", r)[0]
        return r[4:4 + n].rstrip(b"\0").decode("utf-8", "replace")

    def status(self):
        return {0: "running", 1: "paused", 2: "shutdown"}.get(struct.unpack("<I", self._call(bytes([STATUS])))[0])

    def save(self, slot):
        self._call(bytes([SAVESTATE, slot]))

    def load(self, slot):
        self._call(bytes([LOADSTATE, slot]))


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    p = Pine()
    if a[0] == "info":
        print(p.string(ID), "|", p.string(TITLE), "|", p.status())
    elif a[0] == "dump":
        data = p.read(int(a[1], 0), int(a[2], 0))
        open(a[3], "wb").write(data)
        print(f"{len(data)} bytes")
    elif a[0] == "write":
        p.write(int(a[1], 0), open(a[2], "rb").read())
    elif a[0] == "find":
        try:
            pat = bytes.fromhex(a[1])
        except ValueError:
            pat = a[1].encode("cp932")
        start = int(a[2], 0) if len(a) > 2 else 0
        end = int(a[3], 0) if len(a) > 3 else 0x2000000
        data = p.read(start, end - start)
        i = data.find(pat)
        while i >= 0:
            print(hex(start + i))
            i = data.find(pat, i + 1)
    elif a[0] == "save":
        p.save(int(a[1]))
    elif a[0] == "load":
        p.load(int(a[1]))


if __name__ == "__main__":
    main()
