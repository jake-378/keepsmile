import re
import sys

BIN = sys.argv[1]
pattern = re.compile(sys.argv[2], re.I) if len(sys.argv) > 2 else None

data = open(BIN, "rb").read()
seen = set()
for m in re.finditer(rb"[\x20-\x7e]{4,}", data):
    s = m.group().decode("ascii")
    if pattern and not pattern.search(s):
        continue
    if s in seen:
        continue
    seen.add(s)
    print(f"{m.start():#010x} {s}")
