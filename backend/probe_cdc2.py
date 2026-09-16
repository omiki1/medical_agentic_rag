# -*- coding: utf-8 -*-
import re
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
base = "https://www.chinacdc.cn"
for name, path in [("crb(传染病目录)", "/jkkp/crb/"), ("mxfcrb(慢病目录)", "/jkkp/mxfcrb/")]:
    try:
        url = base + path
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        txt = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore")
        # 目录页通常 t2026..html 文章链接
        art = re.findall(r'href="([^"]*?/jkkp/[^"]*?t20\d+[^"]*\.html)"', txt)
        uniq = list(dict.fromkeys((a if a.startswith("http") else base + a) for a in art))
        print(f"[{name}] {url} -> {len(uniq)} articles")
        for a in uniq[:15]:
            print("   ", a)
        # 分类子目录
        subs = list(dict.fromkeys(base + a for a in re.findall(r'href="(/jkkp/[a-z0-9_]+/)"', txt)))
        print("   subdirs:", subs[:15])
    except Exception as e:
        print(f"[{name}] ERR {type(e).__name__}: {str(e)[:80]}")
