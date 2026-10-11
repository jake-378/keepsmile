import re
import sys

stubs = {}
for line in open(sys.argv[1], encoding="utf-8"):
    name, _, sel = line.rstrip("\n").partition("\t")
    if sel and sel != "?":
        stubs[name] = sel

src = open(sys.argv[2], encoding="utf-8").read()
out = re.sub(r"objc_stub::(FUN_[0-9a-f]+)", lambda m: "objc_stub::" + stubs.get(m.group(1), m.group(1)), src)
open(sys.argv[3], "w", encoding="utf-8").write(out)
print(f"{len(stubs)} stubs resolved")
