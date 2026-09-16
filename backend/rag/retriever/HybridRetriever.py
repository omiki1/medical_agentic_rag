import json
import threading
import time

from ai.EmbeddingService import EmbeddingService

from rag.BM25Retriever import BM25Retriever
from rag.CorpusBM25Retriever import CorpusBM25Retriever
from rag.fusion.EvidenceFusion import fuse
from rag.retriever.QARetriever import QARetriever
from rag.VectorRetriever import VectorRetriever


class HybridRetriever:
    # 低于这个规模，探索模式按需构建全量向量索引仍然很快（实测约 24 篇/秒），
    # 不值得强制走离线预构建流程；超过就必须预构建，否则会撞满请求超时。
    EXPLORATION_PREBUILD_THRESHOLD = 3000

    def __init__(self, corpus, settings):
        self.corpus, self.settings = corpus, settings
        with corpus.connect() as conn:
            disk_index = conn.execute("SELECT 1 FROM sqlite_master WHERE name='document_search'").fetchone()
        self.bm25 = CorpusBM25Retriever(corpus) if disk_index else BM25Retriever(corpus.reviewed)
        self.exploration_bm25 = (
            CorpusBM25Retriever(corpus, reviewed_only=False)
            if disk_index
            else BM25Retriever(list(corpus.documents.values()))
        )
        self.dense = None
        self.exploration_dense = None  # lazy: full corpus (incl. legacy) vectors
        self.reranker = None
        self.model_lock = threading.Lock()
        self._embedding = None
        self.warnings = []
        if settings.embedding_model:
            try:
                self._embedding = EmbeddingService(settings.embedding_model, settings.model_device)
                self.dense = VectorRetriever(
                    corpus.reviewed,
                    settings.embedding_model,
                    settings.data_dir / "indexes",
                    settings.model_device,
                    embedding=self._embedding,
                )
            except Exception as exc:
                self.warnings.append("Dense unavailable: " + type(exc).__name__)
        self.qa = QARetriever(settings, self.dense.embedding if self.dense else None)
        self.warnings.extend(self.qa.warnings)
        self._exploration_ready = self._read_exploration_sentinel()

    @property
    def exploration_sentinel(self):
        return self.settings.data_dir / "indexes" / "exploration-index.json"

    def exploration_ready(self):
        """探索模式的全量向量索引是否已构建。

        为什么要单独记一个哨兵文件：真正的缓存键要对 11 万篇文档做 JSON 序列化才能算出来，
        代价太高，不能在每次请求里现算。哨兵只记录"文档数 + 嵌入模型"，够用且极便宜。
        """
        return self._exploration_ready

    def exploration_blocked_reason(self):
        """探索模式此刻无法安全处理请求时返回原因字符串，否则 None。

        为什么必须挡在请求之前：全量语料（111,385 篇）的向量索引是惰性构建的，
        2 vCPU 上要 60-90 分钟。若在请求内触发，会撞满请求超时（240 秒），
        而且 `asyncio.to_thread` 起的编码线程**无法取消** —— 请求早已超时返回给用户，
        线程却继续占满一个 CPU 核跑一个多小时，把所有请求都拖慢。
        线上真实发生过：一次探索模式提问烧掉 396 秒 CPU 且仍在继续，只能靠重启容器终止。
        """
        if self._exploration_ready:
            return None
        # 没有 dense 通道（未配置嵌入模型）时根本不会触发编码，交给既有的降级逻辑。
        if self.dense is None or self._embedding is None:
            return None
        # 小语料按需构建很快，不强制预构建（测试与轻量部署走这条路）。
        if len(self.corpus.documents) <= self.EXPLORATION_PREBUILD_THRESHOLD:
            return None
        return (
            f"探索模式需要全量语料（{len(self.corpus.documents):,} 篇）的向量索引，"
            "该索引尚未构建（一次性构建约 60-90 分钟）。请先使用权威模式。"
            "构建命令：app 容器执行 deploy/warmup_index.py --with-exploratory。"
        )

    def _read_exploration_sentinel(self):
        try:
            data = json.loads(self.exploration_sentinel.read_text(encoding="utf-8"))
        except Exception:
            return False
        return (
            data.get("documents") == len(self.corpus.documents)
            and data.get("embedding_model") == self.settings.embedding_model
        )

    def _mark_exploration_ready(self):
        try:
            self.exploration_sentinel.parent.mkdir(parents=True, exist_ok=True)
            self.exploration_sentinel.write_text(
                json.dumps(
                    {
                        "documents": len(self.corpus.documents),
                        "embedding_model": self.settings.embedding_model,
                        "built_at": time.time(),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except Exception as exc:  # 哨兵写失败不应影响索引本身可用
            self.warnings.append("Exploration sentinel unwritable: " + type(exc).__name__)
        self._exploration_ready = True

    def _full_dense(self):
        """Lazy full-corpus dense index (reviewed + legacy), shared embedding model.

        Failed builds are remembered with a cooldown so one transient failure does not
        make every subsequent request attempt a full 100k-document re-encode.
        """
        if self.dense is None or self._embedding is None:
            return None
        if self.exploration_dense is None:
            if getattr(self, "_full_dense_blocked_until", 0) > 0:
                return None  # cooldown: do not retry every request
            with self.model_lock:
                if self.exploration_dense is None:
                    try:
                        self.exploration_dense = VectorRetriever(
                            list(self.corpus.documents.values()),
                            self.settings.embedding_model,
                            self.settings.data_dir / "indexes",
                            self.settings.model_device,
                            embedding=self._embedding,
                        )
                        self._mark_exploration_ready()
                    except Exception as exc:
                        import time as _time

                        self.warnings.append("Full-corpus dense unavailable: " + type(exc).__name__)
                        self._full_dense_blocked_until = _time.time() + 60
        return self.exploration_dense

    def hybrid(self, query, k=None, mode="authoritative"):
        k = k or self.settings.retrieval_k
        lexical = (self.exploration_bm25 if mode == "exploratory" else self.bm25).search(query, k)
        dense = []
        dense_degraded = False
        try:
            if mode == "exploratory":
                # Exploration searches the full corpus: let the dense route see legacy
                # documents too, instead of only the reviewed subset, so semantic recall
                # and lexical recall operate on the same document space.
                full = self._full_dense()
                dense = full.search(query, k) if full else []
            else:
                dense = self.dense.search(query, k) if self.dense else []
        except Exception as error:
            # A dense runtime failure must never take down the request: keep the BM25
            # route, mark the degradation visibly (warning + flag) for observability.
            dense = []
            dense_degraded = True
            message = "Dense search degraded: " + type(error).__name__
            if message not in self.warnings:
                self.warnings.append(message)
        try:
            qa = self.qa.search(query, min(k, 12)) if mode == "exploratory" else []
        except Exception as error:
            qa = []
            message = "QA search degraded: " + type(error).__name__
            if message not in self.warnings:
                self.warnings.append(message)
        # Preserve source-checked candidates. Unreviewed QA cannot crowd them out.
        verified = fuse(dense, lexical, k=k)
        if dense_degraded:
            # Tag the returned candidates so callers can surface the degradation.
            for ev in verified:
                ev.raw_scores["dense_degraded"] = 1
        return verified + qa
