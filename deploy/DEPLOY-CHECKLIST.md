# MediAtlas ECS 部署包清单（2 vCPU / 8 GiB / 无 GPU）

> 目标：把本地 Windows 环境的项目部署到阿里云 Ubuntu ECS。
> 上传总量约 **3.5 GB**（模型 2.6 GB + 数据 0.5 GB + 代码 0.4 GB）。

---

## 一、必须上传的内容

### 1. 代码（约 380 MB，前端含 node_modules 可排除）
```
medical_agentic_rag/
├── backend/                 # 后端源码（.env 单独处理，见下）
├── frontend/dist/           # 前端构建产物（必须，已构建）
├── deploy/                  # 本次新增的部署套件
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── deploy.sh
│   ├── .env.production.example
│   ├── nginx.conf
│   ├── prepare-models.ps1
│   └── models/              # ← 已精简的模型（2.6 GB）
├── data/
│   ├── knowledge.sqlite     # 301 MB 语料（必须）
│   ├── indexes/             # 200 MB 向量索引（必须）
│   └── curated*.jsonl       # 语料源文件（可选，便于重建）
└── requirements.txt
```

**不需要上传**：`frontend/node_modules`、`__pycache__`、`logs/`、`tmp/`、`reports/`（评测报告）、`.git/`、`.tools/`、`.ruff_cache/`

### 2. 模型（2,611 MB，已精简）
| 模型 | 大小 | 说明 |
|---|---|---|
| paraphrase-multilingual-MiniLM-L12-v2 | 454 MB | 向量检索（384 维） |
| bge-reranker-large | 2,157 MB | CrossEncoder 精排 |

> 已删除冗余：`tf_model.h5`（449MB，TF 用不到）、`pytorch_model.bin`（2,136MB，与 safetensors 重复）、`onnx/`、`openvino/`
> **注意**：`1_Pooling/config.json` 等子目录必须保留，否则加载失败（已校验）

---

## 二、ECS 上的目录布局

```
/opt/mediatlas/
├── backend/
│   ├── .env                        # 由 deploy.sh 生成（chmod 600）
│   └── .env.legacy                 # 可选：放你本地的 .env，脚本会提取模型密钥
├── frontend/dist/
├── data/
│   ├── knowledge.sqlite
│   └── indexes/
├── deploy/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── .env.production             # compose 插值用（脚本生成）
│   └── models/                     # 精简模型
└── reports/
```

---

## 三、上传方式（阿里云 OSS 中转，推荐）

### 方式 A：OSS（快且稳，适合 3.5 GB）
```powershell
# 本地：安装 ossutil 后
ossutil cp -r C:\workspace\medical_disease_db\medical_agentic_rag\deploy\models oss://你的bucket/mediatlas/models -u
ossutil cp C:\workspace\medical_disease_db\medical_agentic_rag\data\knowledge.sqlite oss://你的bucket/mediatlas/data/ -u
ossutil cp -r C:\workspace\medical_disease_db\medical_agentic_rag\data\indexes oss://你的bucket/mediatlas/data/indexes -u
ossutil cp C:\workspace\medical_disease_db\medical_agentic_rag\deploy\mediatlas-code.tar.gz oss://你的bucket/mediatlas/ -u
```
```bash
# ECS：用内网地址下载（免流量费、速度快）
ossutil cp -r oss://你的bucket/mediatlas/ /opt/mediatlas/ --endpoint oss-cn-<region>-internal.aliyuncs.com
```

### 方式 B：scp 直传（简单但慢，公网带宽 1-5 Mbps 时约 1-2 小时）
```bash
# 本地打包代码（排除大目录）
tar czf mediatlas-code.tar.gz --exclude=frontend/node_modules --exclude=__pycache__ \
    --exclude=.git --exclude=logs --exclude=tmp --exclude=reports \
    -C C:\workspace\medical_disease_db medical_agentic_rag

# 分三批传（模型最大，单独传）
scp mediatlas-code.tar.gz root@<ECS_IP>:/opt/
scp -r deploy/models root@<ECS_IP>:/opt/mediatlas/deploy/
scp data/knowledge.sqlite data/indexes/* root@<ECS_IP>:/opt/mediatlas/data/
```

---

## 四、部署步骤

```bash
# 1. 登录 ECS
ssh root@<ECS_IP>

# 2. 解包（若用 tar 方式）
mkdir -p /opt/mediatlas && tar xzf /opt/mediatlas-code.tar.gz -C /opt/mediatlas --strip-components=1

# 3. 把本地 .env 放到 backend/.env.legacy（脚本会自动提取 GLM/OpenCode 密钥）
#    这样就不用手工填 API Key
cp /opt/mediatlas/backend/.env /opt/mediatlas/backend/.env.legacy

# 4. 一键部署（自动装 Docker、配 swap、生成强口令、构建启动、健康检查）
cd /opt/mediatlas
sudo PUBLIC_HOST=<ECS_IP> bash deploy/deploy.sh
```

部署脚本会自动完成：
- 安装 Docker + Compose 插件
- 创建 4 GiB swap（防 OOM，重要）
- 生成随机强口令（PostgreSQL / Redis / Neo4j / JWT）
- **替换掉 Neo4j 默认弱口令 12345678**
- 构建镜像（CPU 版 torch，约 5-10 分钟）
- 启动 4 个容器并等待健康检查（首次加载模型 2-4 分钟）

---

## 五、关键配置说明（针对 2 核 8G 调优）

| 参数 | 值 | 原因 |
|---|---|---|
| `MED_MAX_CONCURRENT_CHATS` | 3 | 2 核 CPU 上重排耗时高，10 并发会雪崩 |
| `OMP_NUM_THREADS` | 2 | 匹配 vCPU 数，避免线程争抢 |
| PostgreSQL `shared_buffers` | 192MB | 8G 机器保守值 |
| Redis `maxmemory` | 192MB | 只做会话缓存 |
| Neo4j heap | 512m-1g | 控制 Java 内存 |
| 容器内存上限 | app 4g / pg 512m / redis 256m / neo4j 1.6g | 合计 6.4g，留系统余量 |
| swap | 4 GiB | 防止峰值 OOM 直接杀进程 |

---

## 六、上线后必做

1. **阿里云安全组**：只放行 8010（或 80/443）。**5432/6379/7687 绝不能对公网开放**（compose 里已不映射这些端口）。
2. **验证**：`curl http://<ECS_IP>:8010/api/health` 应返回 `{"status":"ok"}`
3. **观察资源**：`docker stats --no-stream` 确认内存未逼近上限
4. **测试问答**：浏览器打开 `http://<ECS_IP>:8010`，问"高血压有哪些症状"，观察首次响应时间（CPU 模式比本地 GPU 慢 3-5 倍属正常）
5. **改 PubMed 邮箱**：`.env` 里 `MED_PUBMED_EMAIL` 换成你的真实邮箱

---

## 七、已知限制（务必知悉）

> 以下性能数据为**本地 Docker 容器内实测**（镜像与 ECS 同构，限制 2 线程模拟 2 vCPU）。

| 项目 | 实测结果 | 说明 |
|---|---|---|
| **权威模式单次检索** | **20-22 秒** | 含 dense + bm25 + graph + CrossEncoder 重排。ECS 2 核 CPU 下预计相近或略慢 |
| **首次编码向量索引** | **345 秒**（8,377 篇，一次性） | 仅首次运行需要；之后命中 `data/indexes/*.npy` 缓存 |
| **探索模式全量检索** | **> 35 分钟**（11 万篇，未跑完） | ⚠️ **强烈建议生产禁用探索模式或仅开放权威模式**，否则首次请求会长时间无响应 |
| **急症分流** | **< 1 秒** | 命中危险组合直接返回急救提示，不检索（不受 CPU 慢速影响） |
| **模型加载** | reranker 1.3s / embedding 2.7s | 冷启动一次性 |
| **镜像大小** | 2.78 GB | 已使用 CPU 版 torch，无 nvidia/cuda/triton 依赖 |
| **模型加载兼容性** | 已验证 | 关键：`sentencepiece==0.2.2` 必须存在（XLM-R 分词器依赖），`transformers` 必须锁 4.x |

### 部署前必须处理

1. **禁用或限制探索模式**：CPU 环境下探索模式首次检索可能超过 35 分钟。
   - 方案 A（推荐）：前端/接口层只暴露权威模式
   - 方案 B：预先生成全量索引（需在 ECS 上跑一次约 1-2 小时的后台任务，或从本地复制 163MB 的 `dense-facf29f6eac1cde1a34b.npy`——**注意缓存 key 依赖模型文件的 mtime，跨机器复制后可能失效，需实测**）
2. **提高请求超时**：`MED_REQUEST_TIMEOUT=180` 已在模板中设置（默认 90s 对 CPU 模式偏紧）
3. **降低并发**：`MED_MAX_CONCURRENT_CHATS=3`（2 核机器上更高并发会导致排队雪崩）

### 其他限制

| 项目 | 说明 |
|---|---|
| 无 GPU 的性能 | 本地 RTX 4070 实测 10 并发 P50 13.3s；CPU 2 核慢 3-6 倍，建议控制在 1-3 并发 |
| 首次启动 | 加载语料 + 2 个模型约 30 秒（不含索引编码） |
| 必须 swap | 无 swap 时峰值内存可能触发 OOM Killer（deploy.sh 已自动配置 4 GiB） |
| HTTP + IP 访问 | Cookie 未启用 Secure；上域名后用 `deploy/nginx.conf` + certbot 配 HTTPS |
| 医学审阅未完成 | 见 `reports/releases/.../known-issues.md`，当前定位为受控演示，不可宣称面向患者的正式咨询 |
