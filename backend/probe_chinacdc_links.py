# -*- coding: utf-8 -*-
import re
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
url = "https://www.chinacdc.cn/"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
txt = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore")
links = re.findall(r'href="([^"]+)"', txt)
keys = ["jkzt", "crb", "yf", "jbzt", "health", "jk", "jbyf", "zy", "xz"]
out = []
for h in links:
    low = h.lower()
    if any(k in low for k in keys):
        out.append(h)
unique = list(dict.fromkeys(out))
print("candidate links:", len(unique))
for h in unique[:80]:
    print(" ", h)
