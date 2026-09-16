# -*- coding: utf-8 -*-
import json
import pathlib
import sys

sys.stdout.reconfigure(encoding="utf-8")
root = pathlib.Path(r"C:\workspace\medical_disease_db\medical_agentic_rag")
p = root / "data" / "curated_ext_en.jsonl"
raw = p.read_text(encoding="utf-8")
lines = [line for line in raw.splitlines() if line.strip()]
change = 0
out = []
for line in lines:
    d = json.loads(line)
    if d["id"].startswith("who-"):
        out.append(line)
        continue
    d["id"] = "who-en" + d["id"][3:]
    d["source_id"] = "who-en" + d["source_id"][3:]
    change += 1
    out.append(json.dumps(d, ensure_ascii=False))
p.write_text("\n".join(out) + "\n", encoding="utf-8")
print("changed ids:", change)
