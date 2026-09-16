# -*- coding: utf-8 -*-
import re
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
base = "https://www.chinacdc.cn"
url = base + "/jkkp/crb/"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
txt = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore")
print("page bytes:", len(txt))
# 所有 .html 链接
allh = re.findall(r'href=["\']([^"\']+\.html)["\']', txt)
uniq = list(dict.fromkeys(allh))
print("total .html links:", len(uniq))
for a in uniq[:40]:
    print("  ", a)
