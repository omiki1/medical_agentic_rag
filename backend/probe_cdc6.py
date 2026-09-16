# -*- coding: utf-8 -*-
import re
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
base = "https://www.chinacdc.cn"


def fetch(url, depth=0):
    if depth > 4:
        return None
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    txt = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore")
    m = re.search(r'location\.replace\("([^"]+)"\)', txt)
    if m:
        nxt = m.group(1)
        nxt = (
            nxt
            if nxt.startswith("http")
            else base + nxt
            if nxt.startswith("/")
            else url.rstrip("/") + "/" + nxt.lstrip("./")
        )
        return fetch(nxt, depth + 1)
    return txt, url


for start in ["/jkkp/crb/", "/jkkp/mxfcrb/"]:
    r = fetch(base + start)
    if r is None:
        print(f"[{start}] failed")
        continue
    txt, final_url = r
    print(f"[{start}] final={final_url} bytes={len(txt)}")
    art = list(
        dict.fromkeys(
            (a if a.startswith("http") else base + a)
            for a in re.findall(r'href="([^"]*?t20\d+[^"]*\.html)"', txt)
        )
    )
    print("   articles:", len(art))
    for a in art[:10]:
        print("     ", a)
