"""预热检索索引。

为什么需要它：向量索引是惰性构建的，第一次检索时才编码语料并写缓存。
在 2 vCPU 的云主机上，审核语料（8,377 篇）首次编码约 5~6 分钟，
会超过单请求超时（MED_REQUEST_TIMEOUT），表现为"第一个用户必然失败"。
因此在容器启动后、对外开放前单独跑一次，把缓存写进 data/indexes。

用法（在宿主机）：
    docker compose -f deploy/docker-compose.yml exec -T app python deploy/warmup_index.py
    docker compose -f deploy/docker-compose.yml exec -T app python deploy/warmup_index.py --with-exploratory

--with-exploratory 会构建全量语料（含 103,008 篇历史文献）的向量索引，
CPU 上约 60~90 分钟，属一次性成本；完成后探索模式才可用。
"""

import os
import sys
import time

# 以 `python /warmup/warmup_index.py` 方式运行时，sys.path[0] 是脚本所在目录，
# 不含应用代码目录；应用代码在容器 WORKDIR（/app/backend）下，需显式加入。
_BACKEND = os.environ.get("MED_BACKEND_DIR") or os.getcwd()
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


def main() -> int:
    from common.ApplicationContext import ApplicationContext
    from common.Settings import Settings

    settings = Settings()
    print(f"device={settings.model_device}", flush=True)
    print(f"data_dir={settings.data_dir}", flush=True)
    print(f"embedding={settings.embedding_model}", flush=True)
    print(f"reranker={settings.reranker_model}", flush=True)
    print(f"timeout={settings.request_timeout}s  max_concurrent={settings.max_concurrent_chats}", flush=True)

    started = time.time()
    context = ApplicationContext(settings)
    print(f"[1/3] ApplicationContext 就绪 {time.time() - started:.1f}s", flush=True)
    if context.retriever.warnings:
        print(f"      检索告警: {context.retriever.warnings}", flush=True)

    started = time.time()
    docs = context.retriever.hybrid("高血压 治疗", k=8, mode="authoritative")
    print(f"[2/3] authoritative 索引预热完成 {time.time() - started:.1f}s，命中 {len(docs)} 条", flush=True)

    if "--with-exploratory" in sys.argv:
        started = time.time()
        docs = context.retriever.hybrid("高血压 治疗", k=8, mode="exploratory")
        print(
            f"[3/3] exploratory 全量索引预热完成 {time.time() - started:.1f}s，命中 {len(docs)} 条",
            flush=True,
        )
    else:
        print("[3/3] 跳过 exploratory 全量索引（加 --with-exploratory 启用）", flush=True)

    context.close()
    print("预热结束", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
