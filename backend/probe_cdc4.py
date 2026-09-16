# -*- coding: utf-8 -*-
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
url = "https://www.chinacdc.cn/jkkp/crb/"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
txt = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore")
print(txt)
