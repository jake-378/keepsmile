import re
import sys

BIN, start, end = sys.argv[1], int(sys.argv[2], 16), int(sys.argv[3], 16)
data = open(BIN, "rb").read()[start:end]
for m in re.finditer(rb"[\x20-\x7e]{2,}", data):
    print(f"{start + m.start():#010x} {m.group().decode('ascii')}")
