"""Live test over PINE: make a function return immediately, or restore it.
  knockout.py off <addr>   save 8 bytes, write jr $ra / nop
  knockout.py on  <addr>   restore the saved bytes
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from pine import Pine
SAVE = os.path.join(os.path.expanduser("~"), "srwogg-work", "knockout.json")
saved = json.load(open(SAVE)) if os.path.exists(SAVE) else {}
p = Pine()
cmd, addr = sys.argv[1], int(sys.argv[2], 0)
if cmd == "off":
    saved.setdefault(hex(addr), p.read(addr, 8).hex())
    p.write(addr, bytes.fromhex("0800e00300000000"))
elif cmd == "on":
    p.write(addr, bytes.fromhex(saved.pop(hex(addr))))
json.dump(saved, open(SAVE, "w"))
print(cmd, hex(addr), "saved:", list(saved))
