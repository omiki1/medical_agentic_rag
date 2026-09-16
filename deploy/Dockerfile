# MediAtlas 生产镜像 · CPU 推理（向量检索 + CrossEncoder 精排 + FastAPI）
# 目标机器：2 vCPU / 8 GiB Ubuntu 22.04+，无 GPU
FROM python:3.12-slim

# 单请求并发受 MED_MAX_CONCURRENT_CHATS 控制；这里限制 BLAS 线程避免 2 核过载
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    OMP_NUM_THREADS=2 \
    MKL_NUM_THREADS=2 \
    OPENBLAS_NUM_THREADS=2 \
    TOKENIZERS_PARALLELISM=false \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    SENTENCE_TRANSFORMERS_HOME=/models

# 构建期需要编译器（chromadb 等），运行期保留 libpq5 与 curl（健康检查）
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl libpq5 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend

# 1) 先装 CPU 版 torch：避免 sentence-transformers 拉取 2GB+ 的 CUDA 依赖
RUN pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cpu

# 2) 装项目依赖（此时可能带入 transformers 5.x）
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install -r requirements.txt

# 3) 最后强制锁定 transformers 栈到本地已验证可用的版本，并补齐 tokenizer 依赖。
#    必须放在 requirements 之后：sentence-transformers 5.6.1 会把 transformers
#    升级到 5.x，而 5.x 无法为本项目的 MiniLM/bge 模型构建 tokenizer。
#    sentencepiece 是 XLM-RoBERTa 分词器的运行时依赖（模型用 sentencepiece.bpe.model），
#    requirements.txt 未包含，缺失会导致容器内报
#    "Unrecognized processing class"，模型无法加载。
RUN pip install --force-reinstall --no-deps \
        "transformers==4.57.6" \
        "tokenizers==0.22.0" \
        "huggingface-hub==0.36.2" \
        "safetensors==0.8.0" \
        "numpy==1.26.4" \
    && pip install "sentencepiece==0.2.2"

# 4) 代码与前端产物
COPY backend/ /app/backend/
COPY frontend/dist/ /app/frontend/dist/

# 5) 运行期目录；以非 root 运行
RUN mkdir -p /app/data /app/reports /models \
    && useradd -m -u 10001 mediatlas \
    && chown -R mediatlas:mediatlas /app /models
USER mediatlas

EXPOSE 8010

# start-period 放宽：首次启动需加载 embedder + reranker 权重
HEALTHCHECK --interval=30s --timeout=10s --start-period=240s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8010/api/health || exit 1

# 单进程：模型常驻内存，多 worker 会成倍占用（8GiB 机器不可行）
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8010", "--workers", "1", "--no-access-log", "--timeout-keep-alive", "75"]
