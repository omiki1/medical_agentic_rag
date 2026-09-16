#!/usr/bin/env bash
# MediAtlas ECS 状态速查：容器、索引、资源、健康。
# 用法：bash deploy/ops/status.sh
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.." || exit 1
COMPOSE="docker compose --env-file deploy/.env.production -f deploy/docker-compose.yml"

echo "--- 容器 ---"
docker ps -a --format '{{.Names}}\t{{.Status}}'

echo "--- 向量索引 ---"
ls -la data/indexes/ 2>/dev/null || echo "  (无 indexes 目录，首个请求会触发编码)"
du -sh data/indexes 2>/dev/null || true

echo "--- 资源 ---"
uptime
free -m | head -2
df -h / | tail -1
docker stats --no-stream --format '{{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}' 2>/dev/null | head -6

echo "--- 健康 ---"
printf '  /api/health : '; curl -s -m 10 -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8010/api/health
printf '  /           : '; curl -s -m 10 -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8010/

echo "--- 最近错误 ---"
$COMPOSE logs --tail=200 app 2>&1 | grep -iE 'error|traceback|exception' | tail -10 || echo "  （无）"
