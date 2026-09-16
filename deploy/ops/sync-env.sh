#!/usr/bin/env bash
# 统一口令来源：backend/.env 是唯一事实来源，deploy/.env.production 必须由它派生。
#
# 为什么需要这个脚本：compose 的 ${POSTGRES_PASSWORD} 来自 deploy/.env.production，
# 而应用连接的 POSTGRES_PASSWORD 来自 backend/.env。两份文件若不同步，
# 会出现 PostgreSQL/Neo4j 用旧口令 initdb、应用用新口令连接，
# 报 `password authentication failed for user "mediatlas"`，应用启动即失败。
#
# 用法：改完 backend/.env 后执行 `bash deploy/ops/sync-env.sh`。
# 注意：若改的是数据库口令，已存在的数据卷仍固化旧口令，需要
#       docker compose down -v 后重建（会清空业务数据）。
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

ENVF=backend/.env
PRODF=deploy/.env.production

[[ -f "$ENVF" ]] || { echo "缺少 $ENVF"; exit 1; }

val() { grep -E "^$1=" "$ENVF" | head -1 | cut -d= -f2- | tr -d '"'; }

PG_USER=$(grep -E '^POSTGRES_USER=' "$ENVF" | head -1 | cut -d= -f2- | tr -d '"' || echo mediatlas)
PG_DB=$(grep -E '^POSTGRES_DATABASE=' "$ENVF" | head -1 | cut -d= -f2- | tr -d '"' || echo medical_agentic_rag)
PG_PW=$(val POSTGRES_PASSWORD)
RD_PW=$(val REDIS_PASSWORD)
NJ_PW=$(val MED_NEO4J_PASSWORD)

for name in PG_PW RD_PW NJ_PW; do
  value="${!name}"
  [[ "${#value}" -ge 16 ]] || { echo "$name 过短（${#value}），拒绝写入"; exit 1; }
done

cat > "$PRODF" <<EOF
POSTGRES_USER=$PG_USER
POSTGRES_DATABASE=$PG_DB
POSTGRES_PASSWORD=$PG_PW
REDIS_PASSWORD=$RD_PW
NEO4J_PASSWORD=$NJ_PW
EOF
chmod 600 "$PRODF"

# 交叉校验：三组口令必须在两份文件里完全一致
check() {
  local a b
  a="$(grep -E "^$1=" "$PRODF" | head -1 | cut -d= -f2-)"
  b="$(val "$2")"
  [[ "$a" == "$b" ]] || { echo "$1 与 $2 不一致"; exit 1; }
  echo "  $1 == $2  OK"
}
echo "已从 $ENVF 派生 $PRODF 并校验："
check POSTGRES_PASSWORD POSTGRES_PASSWORD
check REDIS_PASSWORD REDIS_PASSWORD
check NEO4J_PASSWORD MED_NEO4J_PASSWORD
