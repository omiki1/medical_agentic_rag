#!/usr/bin/env bash
# MediAtlas ECS 一键部署（Ubuntu 22.04/24.04，2 vCPU / 8 GiB，无 GPU）
# 幂等：可重复执行；已存在的 .env 与数据卷不会被覆盖。
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/mediatlas}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PUBLIC_HOST="${PUBLIC_HOST:-}"
PUBMED_EMAIL="${PUBMED_EMAIL:-mediatlas.research@example.com}"

log()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[warn] %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m[error] %s\033[0m\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "请使用 sudo 运行：sudo bash deploy/deploy.sh"

# ---------------------------------------------------------------- 1. 系统准备
log "1/9 系统准备"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq curl ca-certificates gnupg git rsync jq >/dev/null

if ! command -v docker >/dev/null 2>&1; then
  log "安装 Docker Engine + Compose 插件"
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >/dev/null
  systemctl enable --now docker
else
  echo "Docker 已安装：$(docker --version)"
fi
docker compose version >/dev/null 2>&1 || die "docker compose 插件不可用"

# ---------------------------------------------------------------- 2. Swap
# 8 GiB 机器上模型 + 图库并存，预留 swap 防止 OOM 直接杀进程
log "2/9 配置 swap（4 GiB，若已存在则跳过）"
if ! swapon --show | grep -q .; then
  fallocate -l 4G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=4096
  chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  sysctl -qw vm.swappiness=10
  echo "swap 已启用：$(free -h | awk '/Swap/{print $2}')"
else
  echo "已存在 swap：$(free -h | awk '/Swap/{print $2}')"
fi

# ---------------------------------------------------------------- 3. 目录
log "3/9 准备目录 $APP_DIR"
mkdir -p "$APP_DIR"
rsync -a --delete \
  --exclude '.git' --exclude 'frontend/node_modules' --exclude '__pycache__' \
  --exclude 'logs' --exclude 'tmp' --exclude '.ruff_cache' \
  "$REPO_DIR"/ "$APP_DIR"/
mkdir -p "$APP_DIR"/{data/indexes,reports,logs}

[[ -f "$APP_DIR/data/knowledge.sqlite" ]] || die "缺少 $APP_DIR/data/knowledge.sqlite（语料未上传）"
[[ -d "$APP_DIR/deploy/models/bge-reranker-large" ]] || die "缺少 deploy/models/bge-reranker-large（模型未上传）"
[[ -d "$APP_DIR/deploy/models/paraphrase-multilingual-MiniLM-L12-v2" ]] || die "缺少 deploy/models/paraphrase-multilingual-MiniLM-L12-v2（模型未上传）"
[[ -d "$APP_DIR/frontend/dist" ]] || die "缺少 frontend/dist（前端未构建）"

# ---------------------------------------------------------------- 4. 生成 .env
log "4/9 生成 backend/.env"
ENV_FILE="$APP_DIR/backend/.env"
# 代码包（tar/scp/rsync）里若混入开发机的 backend/.env，一旦"检测到就沿用"，
# 会把 Windows 模型路径、MED_MODEL_DEVICE=cuda、localhost 服务名直接带上生产，
# 表现为容器 import 期崩溃或连不上数据库。所以必须先识别并重建。
if [[ -f "$ENV_FILE" ]] && { grep -qE '^MED_MODEL_DEVICE="?cuda' "$ENV_FILE" \
    || grep -qE '^[A-Z_]+="?[A-Za-z]:'            "$ENV_FILE" \
    || grep -qE '^CHROMA_PATH='                   "$ENV_FILE"; }; then
  warn "检测到开发机 .env（Windows 路径 / cuda 设备），备份为 .env.dev-backup 并重建"
  mv "$ENV_FILE" "$ENV_FILE.dev-backup"
  chmod 600 "$ENV_FILE.dev-backup"
fi
if [[ -f "$ENV_FILE" ]]; then
  echo ".env 已存在且形态正常，保留现有配置（如需重建请先删除）"
else
  gen() { openssl rand -hex 24; }
  if [[ -z "$PUBLIC_HOST" ]]; then
    PUBLIC_HOST="$(curl -fsS --max-time 5 ifconfig.me || echo 127.0.0.1)"
    echo "未指定 PUBLIC_HOST，自动探测为 $PUBLIC_HOST"
  fi
  # 复用本机已有的模型密钥（若曾随代码一起上传了旧 .env）
  LEGACY_ENV="$APP_DIR/backend/.env.legacy"
  GLM_KEY=""; OPENCODE_KEY=""
  if [[ -f "$LEGACY_ENV" ]]; then
    GLM_KEY="$(grep -E '^GLM_API_KEY=' "$LEGACY_ENV" | head -1 | cut -d= -f2- | tr -d '"' || true)"
    OPENCODE_KEY="$(grep -E '^OPENCODE_API_KEY=' "$LEGACY_ENV" | head -1 | cut -d= -f2- | tr -d '"' || true)"
  fi
  [[ -n "$GLM_KEY" ]] || warn "GLM_API_KEY 为空，请稍后手工填入 $ENV_FILE"
  [[ -n "$OPENCODE_KEY" ]] || warn "OPENCODE_API_KEY 为空，请稍后手工填入 $ENV_FILE"

  POSTGRES_PASSWORD="$(gen)"; REDIS_PASSWORD="$(gen)"
  NEO4J_PASSWORD="$(gen)"; JWT_SECRET="$(openssl rand -hex 32)"

  sed -e "s|__POSTGRES_PASSWORD__|$POSTGRES_PASSWORD|g" \
      -e "s|__REDIS_PASSWORD__|$REDIS_PASSWORD|g" \
      -e "s|__NEO4J_PASSWORD__|$NEO4J_PASSWORD|g" \
      -e "s|__JWT_SECRET__|$JWT_SECRET|g" \
      -e "s|__GLM_API_KEY__|$GLM_KEY|g" \
      -e "s|__OPENCODE_API_KEY__|$OPENCODE_KEY|g" \
      -e "s|__PUBLIC_HOST__|$PUBLIC_HOST|g" \
      -e "s|__PUBMED_EMAIL__|$PUBMED_EMAIL|g" \
      "$APP_DIR/deploy/.env.production.example" > "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  echo "已生成 $ENV_FILE（随机强口令，已 chmod 600）"
fi

# compose 插值用的变量文件。必须**每次重新派生**：它和 backend/.env 是两份文件，
# 只生成一次的话，之后改动 backend/.env 的口令会让数据库容器仍按旧口令 initdb、
# 而应用按新口令连接，直接报 password authentication failed。
# 因此这里把 backend/.env 当作唯一事实来源，无条件重新生成并做一致性校验。
COMPOSE_ENV="$APP_DIR/deploy/.env.production"
{
  echo "POSTGRES_USER=mediatlas"
  echo "POSTGRES_DATABASE=medical_agentic_rag"
  grep -E '^POSTGRES_PASSWORD=' "$ENV_FILE"
  grep -E '^REDIS_PASSWORD='  "$ENV_FILE"
  grep -E '^MED_NEO4J_PASSWORD=' "$ENV_FILE" | sed 's/^MED_NEO4J_PASSWORD=/NEO4J_PASSWORD=/'
} > "$COMPOSE_ENV"
chmod 600 "$COMPOSE_ENV"
echo "已从 backend/.env 派生 $COMPOSE_ENV"

for pair in "POSTGRES_PASSWORD:POSTGRES_PASSWORD" "REDIS_PASSWORD:REDIS_PASSWORD" "MED_NEO4J_PASSWORD:NEO4J_PASSWORD"; do
  src="${pair%%:*}"; dst="${pair##*:}"
  a="$(grep -E "^$src=" "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"')"
  b="$(grep -E "^$dst=" "$COMPOSE_ENV" | head -1 | cut -d= -f2-)"
  [[ "$a" == "$b" && -n "$a" ]] || die "口令不一致：$src 与 $dst 不同，容器会认证失败"
done
echo "两份 .env 口令一致性校验通过"

# ---------------------------------------------------------------- 5. 内存检查
log "5/9 资源检查"
TOTAL_MEM_MB=$(awk '/MemTotal/{printf "%d", $2/1024}' /proc/meminfo)
echo "内存: ${TOTAL_MEM_MB} MiB | CPU: $(nproc) 核 | 磁盘: $(df -h / | awk 'NR==2{print $4}') 可用"
if (( TOTAL_MEM_MB < 7000 )); then
  warn "内存低于 7 GiB，模型 + Neo4j 可能 OOM；建议升配或关闭 Neo4j（MED_NEO4J_URI 置空）"
fi
if [[ "$(nproc)" -lt 2 ]]; then warn "CPU 少于 2 核，重排会明显变慢"; fi

# ---------------------------------------------------------------- 6. 构建启动
log "6/9 构建并启动容器"
cd "$APP_DIR"
docker compose --env-file deploy/.env.production -f deploy/docker-compose.yml build --pull
docker compose --env-file deploy/.env.production -f deploy/docker-compose.yml up -d

# ---------------------------------------------------------------- 7. 健康检查
log "7/9 等待就绪（首次加载模型约 2-4 分钟）"
for i in $(seq 1 60); do
  if curl -fsS --max-time 5 http://127.0.0.1:8010/api/health >/dev/null 2>&1; then
    echo "应用已就绪（第 $((i*10)) 秒）"
    break
  fi
  sleep 10
  (( i == 60 )) && { warn "健康检查超时，请查看日志："; docker compose -f deploy/docker-compose.yml logs --tail=80 app; }
done

COMPOSE="docker compose --env-file deploy/.env.production -f deploy/docker-compose.yml"

# ---------------------------------------------------------------- 8. 预热向量索引
# 向量索引是惰性构建的：第一个真实用户提问才会编码审核语料（2 vCPU 上约 5-7 分钟），
# 必然超过 MED_REQUEST_TIMEOUT 而失败。所以必须在外网开放前先跑一次。
# 用独立容器执行（先停 app），避免两个进程同时驻留 ~2.7 GB 权重撞上 4 GiB 内存上限。
log "8/9 预热向量索引（约 5-7 分钟，一次性成本）"
$COMPOSE stop app
if $COMPOSE run --rm -T -v "$APP_DIR/deploy:/warmup:ro" app python /warmup/warmup_index.py; then
  echo "索引预热完成"
else
  warn "索引预热失败；首个真实请求会因此超时，请手工重试第 8 步"
fi
$COMPOSE start app
for i in $(seq 1 30); do
  curl -fsS --max-time 5 http://127.0.0.1:8010/api/health >/dev/null 2>&1 && break
  sleep 10
done

# ---------------------------------------------------------------- 9. 管理员账户
# 对话接口对**所有**账户强制 BYOK：没有 user_model_settings 记录就抛 428。
# 平台侧 GLM_API_KEY/OPENCODE_API_KEY 不参与对话。管理员也需要在"模型设置"里配置。
log "9/9 创建管理员账户"
if $COMPOSE exec -T app test -f /app/.tools/admin-credentials.txt 2>/dev/null; then
  echo "管理员已存在，跳过"
else
  # 必须用 -m：直接跑脚本会让 sys.path[0] 变成脚本目录，import common 失败。
  $COMPOSE exec -T app python -m user.CreateAdmin --email "admin@mediatlas.local" || warn "管理员创建失败"
  mkdir -p "$APP_DIR/.tools" && chmod 700 "$APP_DIR/.tools"
  $COMPOSE exec -T app cat /app/.tools/admin-credentials.txt > "$APP_DIR/.tools/admin-credentials.txt" 2>/dev/null \
    && chmod 600 "$APP_DIR/.tools/admin-credentials.txt" \
    && echo "凭据已取出到 $APP_DIR/.tools/admin-credentials.txt"
fi

cat <<EOF

============================================================
部署完成
  访问地址 : http://${PUBLIC_HOST}:8010
  接口文档 : http://${PUBLIC_HOST}:8010/docs
  管理员   : cat $APP_DIR/.tools/admin-credentials.txt
  应用日志 : cd $APP_DIR && docker compose -f deploy/docker-compose.yml logs -f app
  停止服务 : cd $APP_DIR && docker compose -f deploy/docker-compose.yml down
  资源占用 : docker stats --no-stream
============================================================
安全提醒：
  1. 阿里云安全组只放行 8010（或 80/443）；5432/6379/7687 绝不要对公网开放。
     容器端口不受主机 ufw 管控（Docker 会自行改写 iptables），边界控制以安全组为准。
  2. 数据库与缓存已使用随机强口令；Neo4j 默认弱口令 12345678 已被替换。
  3. 当前为 HTTP + IP 访问，Cookie 未启用 Secure；上域名后须改 MED_SECURE_COOKIE=true。
     纯 HTTP 下登录口令与问诊内容均明文过网，医疗类内容请尽快上 HTTPS（deploy/nginx.conf 已备好）。
  4. POST /users/register 当前无邀请码、无审核；公网放行前建议关闭注册或加邀请码。

使用须知：
  * 对话强制 BYOK：任何账户（含管理员）都必须先在"模型设置"里填自己的 API Key，
    否则 /api/chat 直接返回 428。平台侧 GLM_API_KEY/OPENCODE_API_KEY 不参与对话。
  * 访客会话（/auth/guestLogin）不能对话，/api/chat 要求真实账户。
  * 同一账户同时只能有 1 个在途请求（runs 表按 session_id 加锁），并发测试需用不同账户。
  * mode=exploratory 需要全量语料向量索引（CPU 上 60-90 分钟一次性构建），当前未构建；
    需要时执行：$COMPOSE run --rm -T -v $APP_DIR/deploy:/warmup:ro app python /warmup/warmup_index.py --with-exploratory
EOF
