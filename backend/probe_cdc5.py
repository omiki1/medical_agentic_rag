# -*- coding: utf-8 -*-
import re
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
base = "https://www.chinacdc.cn"


def get(path):
    try:
        req = urllib.request.Request(base + path, headers={"User-Agent": "Mozilla/5.0"})
        return urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore")
    except Exception:
        return None


for path in ["/jkkp/jcr/", "/jkkp/mxfcrb/", "/jkkp/yyjk/", "/jkkp/ggws/"]:
    txt = get(path)
    if txt is None:
        print(f"[{path}] unreachable")
        continue
    # 重定向?
    redir = re.search(r'location\.replace\("([^"]+)"\)', txt)
    if redir:
        print(f"[{path}] redirect -> {redir.group(1)}")
        txt2 = get(
            redir.group(1).lstrip("./").lstrip(".") if not redir.group(1).startswith("/") else redir.group(1)
        )
        # 简单处理
        path = redir.group(1)
        continue
    art = list(
        dict.fromkeys(
            (a if a.startswith("http") else base + a)
            for a in re.findall(r'href="([^"]*?t20\d+[^"]*\.html)"', txt)
        )
    )
    print(f"[{path}] bytes={len(txt)} articles={len(art)}")
    for a in art[:12]:
        print("   ", a)
