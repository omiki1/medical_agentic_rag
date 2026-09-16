# MediAtlas ECS 部署报告

**日期**：2026-09-11
**目标机**：阿里云 ECS `i-j6c9sclnnalqxg3e17kt`，`ecs.u1-c1m4.large`，2 vCPU / 8 GiB / Ubuntu 22.04 / 40 GB ESSD，公网 `47.83.165.114`
**部署方式**：Docker Compose（应用 + PostgreSQL 16 + Redis 7 + Neo4j 5.26），CPU 推理，无 GPU
**应用目录**：`/opt/mediatlas`
**语料指纹**：`eda2932e616a01ab`（与本地已验证基线一致）

---

## 1. 部署结果

| 项目 | 状态 |
|---|---|
| 镜像 `mediatlas-app:1.0.0` | 构建成功，CPU 版 torch 2.6.0+cpu，2.78 GB |
| 四个容器 | 全部 `healthy`，`restart: unless-stopped` |
| 端口 | 仅 8010 对外发布；PG/Redis/Neo4j 只在 compose 网络内可达 |
| 应用启动 | 模型加载成功（MiniLM 384 维 + bge-reranker-large） |
| 向量索引 | 已预热，`data/indexes/dense-d7077935a055ec091c0b.npy` 12.8 MB（= 8,377 篇 × 384 维 × 4 B） |
| 知识图谱 | **已从本地导入**：27,511 节点 / 383,229 关系，逐类型零丢边（见 §4） |
| 后端测试 | 76 项全部通过（含本次新增 5 项离题过滤测试） |
| 公网可达 | **待你在安全组放行 8010**（你已选择公开演示），见 §7.1 |

### 端到端验证（真实提问）

| 场景 | 结果 | 耗时 | 说明 |
|---|---|---|---|
| 高血压患者日常注意事项 | `answered` | 31.3 s | dense+bm25 融合 21 → 锚点 7 → 合格证据 8，覆盖度 1.0，CrossEncoder 精排生效，3/3 断言有引用支撑，引用 E1–E8 全为 `source_checked` |
| 高血压需要做哪些检查 | `answered` | 20.9 s | 走 `[dense, bm25, graph]`，`graph_status=neo4j_connected`、`graph_rows=10`；证据 `who:hypertension:test` 的 `methods` 含 `graph`、`graph_paths=[[高血压, DISEASE_CHECK, 血压测量]]`；4/4 断言有支撑 |
| 突然胸痛并放射至左臂、出冷汗 | `emergency` 短路 | 0.26 s | `risk_code=heart_attack_like`，0 次模型调用，直接给出 120/119 指引 |
| 小孩发烧 38.5 度怎么处理 | `answered` | 76.0 s | 修复离题后引用降为 1 条通用资料，`*:symptom` 病种专属文档命中 0（见 §5） |
| 拉肚子怎么办 | `abstained` | 28.7 s | 检索侧已完美（8 条 `who:diarrhoeal-disease:*`、`sufficient=true`、覆盖度 1.0），但生成引用复核未通过，见 §6.1 |
| 2 型糖尿病诊断标准 | `abstained` | 90.8 s | 同一模式：证据在库（8 条 WHO 糖尿病资料）但生成结论未通过复核，见 §6.1 |
| 糖尿病有哪些并发症 | `abstained` | 65.5 s | 图谱取到 6 行但未产出候选，覆盖度 0，空转 3 轮反思，见 §6.2 |
| 慢性胃炎需要做胃镜吗 | `abstained` | 3.0 s | 语料无胃镜相关资料，正确弃答 |
| 痛风发作时应该怎么办 | `abstained` | 9.4 s | 语料无痛风资料，正确弃答 |

### 并发实测（5 个独立账户同时提问）

| 指标 | 值 |
|---|---|
| HTTP 结果 | 5/5 = 200，**零拒绝、零错误** |
| 单请求耗时 | 32 s / 101 s / 37 s / 5 s / 10 s |
| 墙钟总时长 | 101 s |
| 应用内存峰值 | 1.97 GiB / 4 GiB 上限 |
| 整机内存 | 2.7 GiB / 7.6 GiB 占用 |
| 负载均值 | 0.42 |
| 数据库 | 8 条 run 全部 `completed` |

**结论**：2 vCPU / 8 GiB 可稳定承载 **约 5 路并发**；单请求 30–100 s。超过 `MED_MAX_CONCURRENT_CHATS=3` 的请求是**排队**而非拒绝（`Semaphore.locked()` 检查与获取之间存在竞态，实际表现为排队），这对用户体验更友好。**不适合 10 路以上同时提问**（每路都会显著变慢，且可能触发 240 s 请求超时）。

> 注意：同一账户同时只能有 **1 个在途请求** —— `ChatDao.start_run` 的守卫是
> `WHERE session_id=? AND status='running'`，按**账户**而非按会话加锁。
> 用同一账户并发会得到 `409 当前会话已有正在处理的请求`。因此上面的并发测试用了 5 个独立账户。

---

## 2. 部署过程中发现并修复的 7 个坑

这些是本项目"从开发机搬到服务器"必然踩到的问题，已全部修复，并把修复沉淀进了
`deploy/deploy.sh` 与 `deploy/ops/`，避免下次重蹈：

1. **打包带入了开发 `.env`** —— 代码包里含 `backend/.env`（CUDA 设备、`C:/model/...` Windows 路径、`localhost` 主机名、弱口令）。原部署脚本因文件已存在而**跳过生成**，容器会直接崩。修复：`deploy.sh` 现在会识别开发 `.env` 特征（`MED_MODEL_DEVICE=cuda` / Windows 盘符路径 / `CHROMA_PATH`）并备份重建。

2. **`Settings.request_timeout` 上限 180** —— 按 CPU 机器需要设为 300 会触发 pydantic 校验失败、**应用 import 期崩溃重启循环**。该 180 是按带 GPU 的开发机（P95 25 s）标定的。修复：把上限放宽到 600（`backend/common/Settings.py`），默认值仍为 75。

3. **两份 `.env` 的口令各自为政** —— `backend/.env` 供应用读取，`deploy/.env.production` 供 compose 插值。只改了前者会导致 PG/Neo4j 用**旧口令 initdb**、应用用**新口令连接** → `password authentication failed for user "mediatlas"`。修复：`deploy/ops/sync-env.sh` 以 `backend/.env` 为**唯一事实来源**派生 `.env.production` 并做三组交叉校验；`deploy.sh` 也改为无条件重新派生 + 校验。

4. **模型下载未剔除冗余权重** —— `snapshot_download` 的 `ignore_patterns` 没有排除重复格式，落地 5.1 GB（`.bin` 与 `.safetensors` 各一份）。实际只需 2.6 GB。修复：部署时删除 `.bin`/`onnx`/`openvino`。

5. **首次检索才惰性建索引** —— 审核语料 8,377 篇在 2 vCPU 上首次编码约 345 s，**超过单请求超时**，表现为"第一个真实用户必然失败"。修复：新增 `deploy/warmup_index.py`，用**独立容器**（先停 app）预热，避免两个进程同时驻留 ~2.7 GB 权重撞上 4 GiB 上限。已并入 `deploy.sh` 第 8 步。

6. **`python user/CreateAdmin.py` 报 `No module named 'common'`** —— 直接跑脚本时 `sys.path[0]` 是脚本所在目录而非 WORKDIR。修复：必须用 `python -m user.CreateAdmin`。已并入 `deploy.sh` 第 9 步。

7. **`TrustedHostMiddleware` 校验 Host** —— 用内网 IP 或未登记的域名访问会返回 400。修复：`MED_ALLOWED_ORIGINS` 必须包含实际访问地址。

---

## 3. 架构层面的重要发现：对话强制 BYOK

`ChatController.chat` 对所有账户无条件调用：

```python
agent = request.app.state.context.user_model_service.bind(user["account_id"], self.service.agent)
```

而 `UserModelService.bind()` 在没有该账户的 `user_model_settings` 记录时直接抛 `HTTPException(428, "请先在模型设置中填写自己的 API Key 和模型")`。

**这意味着**：

- `backend/.env` 里的 `GLM_API_KEY` / `OPENCODE_API_KEY` **不参与任何对话**，它们只被非对话路径使用。
- 平台不承担推理成本，**每个用户（含管理员）都必须自带 API Key**。
- `bind()` 还会把 `bound.translator = None`，即**英文原始资料不做即时翻译**（仅使用建库时的缓存翻译）。实测中英文文献的**标题**已译为中文，但**正文仍是英文**。
- 访客会话（`/auth/guestLogin`）**完全不能对话**：`/api/chat` 走 `get_current_user`，访客只拿到 `private_device_session`。

对"让朋友试试"的影响很大：朋友注册后不填自己的 Key 就一步都走不动。**你已决定保持现状**。

---

## 4. 图谱恢复（已修复的重大缺口）

**问题**：ECS 上是全新的 `neo4j:5.26-community` 容器，图谱为空。而 README 与验收清单都把
**Neo4j 的 383,229 条关系**当作"继承自原系统、只读、不清空不重建"的既有资产，
仓库里却**没有它的装载脚本**（`MergeWHO` 明确 `neo4j_writes: 0`）。
后果：图谱校验层恒返回 0 行，`graph_paths` 永远不会被标记 `neo4j_verified`，
日志持续刷 `label 'Disease' does not exist` 告警。

**恢复方式**（本地产 Neo4j 仍在，数据完好）：

1. `deploy/export_graph.py` —— 从本地 Neo4j 导出为与版本无关的 CSV
   （`nodes.csv` 0.7 MB、`disease.csv` 27.7 MB、`rels.csv` 23.4 MB）。
2. `deploy/prepare_graph_import.py` —— 生成导入包。**关键点**：图谱里有 **482 组跨标签同名节点**
   （其中 421 组涉及 Disease），所以端点必须按 `(标签, 名称)` 匹配而非仅按名称，
   否则会连到错误节点。因此关系按 `(alabel, rtype, blabel)` 三元组切成 101 个小文件，
   每行只被 `LOAD CSV` 读一次，避免 24 MB 文件被反复扫 100 多遍。
3. 导入 ECS 容器（`cypher-shell -f import.cypher`），用时 **32 秒**。

**核对结果 —— 与本地基线逐类型完全一致，零丢边**：

| 关系类型 | 数量 | | 标签 | 节点数 |
|---|---:|---|---|---:|
| DISEASE_SYMPTOM | 69,642 | | Disease | 8,807 |
| DISEASE_DRUG | 62,881 | | Symptom | 5,998 |
| DISEASE_CATEGORY | 44,472 | | Dishes | 4,506 |
| DISEASE_DISHES | 42,825 | | Drug | 3,828 |
| DISEASE_CHECK | 41,547 | | Check | 3,353 |
| DISEASE_DEPARTMENT | 35,242 | | Cureway | 544 |
| DISEASE_NOT_EAT | 23,603 | | Food | 366 |
| DISEASE_DO_EAT | 23,621 | | Category | 55 |
| DISEASE_CUREWAY | 22,021 | | Department | 54 |
| DISEASE_ACOMPANY | 17,375 | | **合计** | **27,511** |
| **合计** | **383,229** | | | |

疾病属性也一并恢复（8,806/8,807 有 `desc`，8,790/8,807 有 `cause`）。

**生效验证**：`高血压需要做哪些检查` 现在走 `[dense, bm25, graph]`，
`graph_status: neo4j_connected`、`graph_rows: 10`，
证据 `who:hypertension:test` 的 `methods` 含 `graph`，`graph_paths: [[高血压, DISEASE_CHECK, 血压测量]]`，
20.9 秒完成、覆盖度 1.0、4/4 断言有引用支撑。

---

## 5. 两处已修复的缺陷

### 5.1 检索离题：单病种症状页不再污染泛化症状问题

**原缺陷（线上实测复现）**：`小孩发烧38.5度怎么处理` 检索到并引用了
B 组链球菌 / 日本脑炎 / 呼吸道合胞病毒的 **symptom 章节** ——
只因这些页面的症状列表里出现"发热"。这是"飘逸"问题的一个残留形态。

**根因**：问题不含疾病实体（`entities=[]`），`EvidencePolicy.entity_matches` 无从约束；
`who:*:symptom:*` 这类"单病种症状页"可以满足一个泛化的症状问题。

**修复**：`EvidencePolicy.disease_specific_symptom_mismatch()` ——
authoritative 模式下，凡 `facet == "symptom"` 且文档自身实体**既不是**问题提到的疾病、
**也不是**问题所问的症状本身者，一律排除（新增排除原因 `disease_specific_symptom`）。
保留两种必要情形：

- 问题本身提到该疾病（实体/别名/字面出现）→ 保留，如"登革热有哪些症状"；
- 文档实体就是被问的症状 → 保留，如"拉肚子怎么办"必须留住 `who:diarrhoeal-disease` 的症状页
  （这是此前已修好的弃答案例，本次专门加了回归测试保护）。

**效果**：`小孩发烧38.5度怎么处理` 的引用从 3 条无关病种症状页降为
**1 条通用资料**（`who:influenza-(seasonal):treatment`），`*:symptom` 疾病专属文档命中 **0**，
回答通过全部校验（`grounded/relevant/complete`，3/3 断言有支撑）。

新增 5 项测试（无关病种症状页被排除、点到疾病时保留、症状即实体时保留、exploratory 不过滤、
非 symptom facet 不受影响），后端测试 **76 项全部通过**。

### 5.2 前端在纯 HTTP 下完全无法提问（最严重的一处，已修复）

**症状（用户报告）**：网页上输入问题点发送（或按回车）**毫无反应**；
发送按钮变成一个点了也没用的「停止」按钮；点侧边栏任何入口都没反应；只有刷新页面才恢复。

**根因**：浏览器只在**安全上下文**（HTTPS 或 localhost）暴露 `crypto.randomUUID()`。
站点跑在 `http://47.83.165.114:8010`（纯 HTTP + 公网 IP）→ 该 API 为 `undefined` →
`Chat.vue` 里构造 `item.id` 时抛 `TypeError: crypto.randomUUID is not a function`。

**为什么会卡死**：该行位于 `busy.value = true` 之后、`try {` **之前**，
异常一抛 `finally` 就不执行 → `busy` 永久为 true → 界面只剩一个无效的「停止」按钮。

**为什么一直没发现**：
1. 本地开发用 `http://127.0.0.1:8010`，**localhost 属于安全上下文**，问题完全隐身；
2. 此前的"公网验证"全部用 `curl` 直连 API，**绕过了浏览器**——接口全 200，但用户在浏览器里一步都走不动。

**修复**：

1. 新增 `frontend/src/api/Ids.js` 的 `uuid()`，三级回退：
   `crypto.randomUUID` → `crypto.getRandomValues`（**不受**安全上下文限制）→ `Math.random`（兜底）。
2. 把易抛异常的 `item` 构造移入 `try` 内部，保证 `finally` 一定复位 `busy`。
3. 新增 5 项前端单测锁定回归（含"只有 getRandomValues 的 crypto"与"完全没有 crypto"两种情形），
   前端测试由 4 项增至 **9 项，全部通过**。

**验证方式（这次补上了）**：用 `puppeteer-core` + 本机 Chrome 对**线上地址**跑真实浏览器交互测试：

| 测试 | 结果 |
|---|---|
| 登录 → 提问 → 进入生成态 → 回答产出 | PASS（20.1–38.5 秒，345–355 字，状态"有来源支持"） |
| busy 期间点品牌 logo / 「开启新对话」：停留对话页 + 明确提示 + 不清空问答 | PASS |
| 回答完成后「开启新对话」真正生效（回到欢迎页） | PASS |
| 逐个打开 知识与来源/四层记忆/评测与质量/系统设置/模型设置/知识问答 | PASS（10/10） |
| 推荐问题卡片填入、探索模式切换 | PASS |
| 全程无 JS 运行时错误 | PASS |

**并发的第二个修复**：所有"正在生成时点击入口静默无反应"的路径都改成
**先落到对话页并给出明确提示**（品牌 logo、开启新对话、历史对话项、忙时再次发送），
不再有静默 `return`。

**教训（已写入手册 `04-故障排查手册` 问题 11）**：
- 只在 localhost 验证过的前端功能，上线到 HTTP+IP 前**必须用真实浏览器复测**；
- **curl 验证接口通过 ≠ 浏览器可用**；
- `busy`/`loading` 这类状态标志的赋值必须放在 `try` **内部**。

---

## 6. 其余已知问题（未修，按优先级）

### 6.1 生成复核过严 —— 证据充分却弃答

**查询**：`拉肚子怎么办`（检索侧已完美：8 条证据全为 `who:diarrhoeal-disease:*`，
`evidence_grade.sufficient=true`、`coverage=1.0`）

**现象**：仍弃答，`generation_unavailable`。trace 显示两次尝试都在 **`citations` 阶段**失败：

```
grade_answer blocked {"verification":"failed",
  "attempts":[{"attempt":1,"stage":"citations","feedback":["可能遗漏了重要的证据维度"]},
              {"attempt":2,"stage":"citations","feedback":["可能遗漏了重要的证据维度"]}]}
warnings: ["生成检查失败，未自动转为原文摘录"]
```

**根因**：引用覆盖度检查要求回答覆盖全部"重要证据维度"。当 8 条证据横跨
overview / treatment / prevention / cause 多个 facet 时，模型只引用最相关的若干条即被判不合格；
而证据只有 1 条时反而轻松通过。`2型糖尿病诊断标准` 是同一模式（90 秒后弃答）。

**权衡**：这条检查正是本项目的可信度来源，**不应轻易放宽**。可行方向是按"证据维度覆盖率"
分级放行（例如覆盖主要 facet 即通过），或退化为"带原始资料面板的受限回答"而不是完全弃答。
需要确认后再改。

### 6.2 并发症类问题的图谱候选为空 + 反思空转

**查询**：`糖尿病有哪些并发症`

**现象**：`graph_rows: 6`（Neo4j 取到了数据）、`use_graph: true`，
但 `graph_candidates: 0`，本地图谱未产出任何候选文档，`coverage` 始终 0。
于是连做 3 轮反思迭代（16.8 s → 37.9 s → 65.5 s），最终 `stop: no_progress` 弃答，**空耗 65 秒 CPU**。

**两个子问题**：

1. `DISEASE_ACOMPANY` 边没有映射到证据文档（WHO 糖尿病资料里没有 `complication` facet 文档）；
2. 反思迭代在覆盖度为 0 时仍重试 3 次、每次耗时翻倍，缺少"无进展即早停"的成本护栏。

### 6.3 英文资料正文未翻译

`UserModelService.bind()` 会把 `bound.translator = None`（"不产生平台出资的翻译调用"）。
实测英文 WHO 文献的**标题**已是中文（建库时缓存），但**正文仍为英文原文**。
这与最初"翻译英文来源"的诉求仍有差距，且 BYOK 策略下无法在请求内即时翻译。

---

## 7. 待决事项

### 7.1 公网访问（唯一阻塞项，需你操作）

联通性已排查清楚：

- 阿里云**安全组未放行 8010**（22 端口通，链路正常）
- 主机侧 ufw 未启用、iptables INPUT 策略 ACCEPT、Docker 已把 8010 发布到 `0.0.0.0`

**你已选择公开演示。需要你在控制台操作**：ECS → 安全组 → 配置规则 → 入方向 → 添加
`TCP 8010`，授权对象 `0.0.0.0/0`。

⚠️ 当前是 **纯 HTTP**（`MED_SECURE_COOKIE=false`）。公网放行后登录口令与全部问诊内容**明文过网**。
建议尽早配域名 + HTTPS（`deploy/nginx.conf` 已备好：SSE 免缓冲、300 s 超时）。

### 7.2 已确认的决策

- **BYOK 保持现状**（你选择）：平台不承担推理成本，用户自带 Key。
  代价是朋友注册后不填自己的 Key 就无法试用；访客会话完全不能对话。
- **开放注册**：`POST /users/register` 无邀请码、无审核。公开演示期间建议关闭或加邀请码。
- **探索模式索引：已构建完成（2026-09-11 17:03）**。详见 §7.2.1。

### 7.2.1 探索模式索引构建（已完成）

**构建结果**：

| 项目 | 值 |
|---|---|
| 语料规模 | 111,385 篇（8,377 已核验 + 103,008 历史） |
| 耗时 | **62 分钟**（16:01 → 17:03） |
| 索引文件 | `data/indexes/dense-688c00000ad777bd367c.npy` **171,087,488 字节** |
| 校验 | 171,087,488 ÷ (384 × 4) = **111,385** ✓ 与文档数完全吻合 |
| 哨兵文件 | `data/indexes/exploration-index.json` → `{"documents": 111385, ...}` |
| 索引目录总大小 | 176 MB |
| `/api/status` | `exploration_index_ready: True` |

**效果验证 —— 探索模式确实带来新增价值**：

| 问题 | 权威模式 | 探索模式 |
|---|---|---|
| 慢性胃炎需要做胃镜吗 | `abstained`，**0 条证据**，1.8 秒 | **`answered`**，8 条证据（全为 legacy 历史文档），coverage 1.0，28.8 秒 |
| 3岁小孩发高烧是什么原因 | `abstained`，4.4 秒 | `abstained`，4.5 秒（该主题语料确实没有覆盖） |

**为什么之前会挂死（已修复的缺陷，保留记录）**：

索引缺失时探索模式请求会挂满 240 秒超时，且 `asyncio.to_thread` 起的编码线程**无法取消** ——
请求返回后仍继续占满一个 CPU 核，实测已烧 **396 秒 CPU** 且仍在继续，把所有人的请求一起拖慢，
只能靠重启容器终止。线上真实发生过一次。

**三层修复（已上线并验证）**：

1. `HybridRetriever.exploration_blocked_reason()` —— 用哨兵文件 + 小语料（≤3000 篇）/无 dense 通道豁免，
   缺索引时**立即（0.0 秒）**返回明确原因（HTTP 503），不再触发长编码；
2. `ChatService.chat` 前置拦截，把判定放在进入请求处理之前；
3. 前端把真实失败原因显示在那条问答上，不再只有「这次回答未完成」。

后端测试由 76 项增至 **78 项**，前端 **9 项**，全部通过。
查询后 CPU 实测 **0 jiffies**，确认无跑飞线程。

**重建命令**（换语料或换模型路径时才需要）：

```bash
cd /opt/mediatlas
COMPOSE="docker compose --env-file deploy/.env.production -f deploy/docker-compose.yml"
$COMPOSE stop app
$COMPOSE run --rm -T -v /opt/mediatlas/deploy:/warmup:ro app \
    python /warmup/warmup_index.py --with-exploratory
$COMPOSE start app
```

⚠️ 构建期间服务不可用，且**中途不能中断**（不会保留部分成果）。

### 7.3 其它

- **释放旧实例** `i-j6cfz6s1er13qbvv8jq4`（47.86.25.137，经济型 e 突发性能实例）—— 仍在计费，请到控制台释放。
- 外审医学风险模板、六维人工评分、备份恢复演练、隐私合规声明 —— 仍为未完成项
  （见 `deploy/DEPLOY-CHECKLIST.md`）。

---

## 8. 运维手册

```bash
cd /opt/mediatlas
COMPOSE="docker compose --env-file deploy/.env.production -f deploy/docker-compose.yml"

$COMPOSE ps                       # 状态
$COMPOSE logs -f --tail=100 app   # 应用日志
$COMPOSE restart app              # 重启应用（模型重载约 60 s）
$COMPOSE down && $COMPOSE up -d   # 整体重启（数据在命名卷中，保留）
bash deploy/ops/status.sh         # 一键状态速查（容器/索引/资源/健康/错误）
```

**管理员凭据**：`/opt/mediatlas/.tools/admin-credentials.txt`（`admin@mediatlas.local`，600 权限）。
查看：`cat /opt/mediatlas/.tools/admin-credentials.txt`

**使用前必须先配模型**：登录后在"模型设置"里填自己的 API Key（可选服务商：OpenCode Go /
DeepSeek 官方 / 智谱 BigModel / OpenAI），否则 `/api/chat` 直接返回 428。

**数据库口令**：`backend/.env` 为唯一事实来源，随机 48 位十六进制；`deploy/.env.production` 由它派生。

**修改配置后必须同步两份文件**：

```bash
vim /opt/mediatlas/backend/.env              # 改配置
bash /opt/mediatlas/deploy/ops/sync-env.sh   # 重新派生 .env.production 并三组交叉校验
```

⚠️ 若改的是数据库口令，已存在的数据卷仍固化旧口令，需要 `$COMPOSE down -v` 后重建（会清空业务数据）。

**防火墙策略**：容器端口**不受 ufw 管控**（Docker 自行改写 iptables），因此统一以**阿里云安全组**作为边界控制，主机 ufw 保持关闭以避免虚假安全感。

---

## 9. 成本与容量

- 实例 `ecs.u1-c1m4.large`：约 ¥0.702/小时（按量），预算 ¥300 ≈ 427 小时 ≈ 17.8 天
- 选型理由：通用算力型 u1 是**独享 vCPU**，不会像经济型 e 那样因 CPU 积分耗尽被限流
- 8 GiB 是硬性下限：应用 2.0 GiB + Neo4j 0.8 GiB + PG/Redis 0.2 GiB + 页缓存，6.5 GiB 以下会 OOM
- 磁盘：模型 2.6 GB + 语料 0.3 GB + 镜像 2.8 GB + 图谱约 0.2 GB ≈ 占用 19 GB / 40 GB
