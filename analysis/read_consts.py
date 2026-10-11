"""Print bytes at virtual addresses in the app's arm64 Mach-O.

Usage: read_consts.py <ipa> <length> <hex address>...
"""

import struct
import sys
import zipfile

LC_SEGMENT_64 = 0x19


def load_binary(ipa: str) -> bytes:
    with zipfile.ZipFile(ipa) as z:
        name = next(n for n in z.namelist() if n.count("/") == 2 and n.startswith("Payload/")
                    and n.split("/")[2] == n.split("/")[1].removesuffix(".app"))
        return z.read(name)


def segments(data: bytes):
    magic, _cpu, _sub, _ftype, ncmds, _size, _flags, _res = struct.unpack_from("<8I", data, 0)
    assert magic == 0xFEEDFACF, "expected a thin 64-bit Mach-O"
    off = 32
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from("<2I", data, off)
        if cmd == LC_SEGMENT_64:
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<4Q", data, off + 24)
            yield vmaddr, vmsize, fileoff, filesize
        off += cmdsize


def read(data: bytes, addr: int, length: int) -> bytes:
    for vmaddr, _vmsize, fileoff, filesize in segments(data):
        if vmaddr <= addr < vmaddr + filesize:
            start = fileoff + addr - vmaddr
            return data[start:start + length]
    raise ValueError(f"{addr:#x} is not file-backed")


data = load_binary(sys.argv[1])
length = int(sys.argv[2])
for a in sys.argv[3:]:
    print(a, read(data, int(a, 16), length).hex(" "))
