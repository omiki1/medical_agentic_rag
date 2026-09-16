#!/usr/bin/env bash
# 查看服务器被谁使用：账户、会话、使用量、最近提问、当前连接。
#
# 数据来源说明：应用以 --no-access-log 启动，因此没有 HTTP 访问日志。
# 但所有真实使用行为都落库了：
#   runs         每次提问（提问内容、模式、状态、时间）
#   conversations 每段对话
#   sessions     每个会话（account_id 为空 = 访客私有设备会话）
#   users        注册账户
# 所以"谁在用、问了什么、结果如何"都能从数据库如实还原。
set -uo pipefail
cd /opt/mediatlas
COMPOSE="docker compose --env-file deploy/.env.production -f deploy/docker-compose.yml"
# 数据库存的是 UTC；PGTZ 让 psql 按北京时间渲染，避免看时间时差 8 小时。
Q() { $COMPOSE exec -T -e PGTZ=Asia/Shanghai postgres psql -U mediatlas -d medical_agentic_rag -tAc "$1" 2>/dev/null; }

echo "############ 一、账户与模型配置 ############"
printf '%-24s %-14s %-8s %-12s %s\n' "邮箱" "用户名" "角色" "模型已配置" "注册会话数"
Q "SELECT u.email, u.username, u.role_name,
          CASE WHEN m.account_id IS NULL THEN '否' ELSE '是' END,
          (SELECT count(*) FROM sessions s WHERE s.account_id=u.users_id)
   FROM users u LEFT JOIN user_model_settings m ON m.account_id=u.users_id
   ORDER BY u.users_id;" | while IFS='|' read -r a b c d e; do
  printf '%-24s %-14s %-8s %-12s %s\n' "$a" "$b" "$c" "$d" "$e"
done

echo
echo "############ 二、会话总览 ############"
TOTAL=$(Q "SELECT count(*) FROM sessions;")
ACCOUNT=$(Q "SELECT count(*) FROM sessions WHERE account_id IS NOT NULL;")
GUEST=$(Q "SELECT count(*) FROM sessions WHERE account_id IS NULL;")
ACTIVE=$(Q "SELECT count(*) FROM sessions WHERE expires > extract(epoch from now());")
echo "  会话总数      : $TOTAL"
echo "  账户会话      : $ACCOUNT"
echo "  访客设备会话  : $GUEST"
echo "  未过期会话    : $ACTIVE"

echo
echo "############ 三、按使用者统计使用量 ############"
printf '%-26s %7s %7s %8s %8s %7s  %s\n' "使用者" "对话" "提问" "已回答" "证据不足" "急诊" "最近活动"
Q "
SELECT coalesce(u.email, '访客(未登录)'),
       count(DISTINCT r.conversation_id),
       count(r.id),
       count(*) FILTER (WHERE r.result::json->>'status' = 'answered'),
       count(*) FILTER (WHERE r.result::json->>'status' = 'abstained'),
       count(*) FILTER (WHERE r.result::json->>'status' = 'emergency'),
       to_char(to_timestamp(max(r.created)), 'MM-DD HH24:MI')
FROM runs r
LEFT JOIN sessions s ON s.id = r.session_id
LEFT JOIN users u ON u.users_id = s.account_id
GROUP BY coalesce(u.email, '访客(未登录)')
ORDER BY count(r.id) DESC;" | while IFS='|' read -r a b c d e f g; do
  printf '%-26s %7s %7s %8s %8s %7s  %s\n' "$a" "$b" "$c" "$d" "$e" "$f" "$g"
done

echo
echo "############ 四、最近 15 次提问 ############"
printf '%-12s %-24s %-13s %-12s %9s  %s\n' "时间(北京)" "使用者" "模式" "状态" "耗时" "问题"
Q "
SELECT to_char(to_timestamp(r.created), 'MM-DD HH24:MI'),
       coalesce(u.email, '访客'),
       r.mode,
       r.status,
       coalesce(r.result::json->>'duration_ms', ''),
       left(r.question, 30)
FROM runs r
LEFT JOIN sessions s ON s.id = r.session_id
LEFT JOIN users u ON u.users_id = s.account_id
ORDER BY r.created DESC LIMIT 15;" | while IFS='|' read -r a b c d e f; do
  if [ -n "$e" ]; then e="$((e/1000)).$((e%1000/100))s"; fi
  printf '%-12s %-24s %-13s %-12s %9s  %s\n' "$a" "$b" "$c" "$d" "$e" "$f"
done

echo
echo "############ 五、今日概览 ############"
echo "  今日新增账户   : $(Q "SELECT count(*) FROM users WHERE users_id > 0;" ) （累计；本表无注册时间字段）"
echo "  今日提问数     : $(Q "SELECT count(*) FROM runs WHERE created >= extract(epoch from date_trunc('day', now()));")"
echo "  今日提问人数   : $(Q "SELECT count(DISTINCT session_id) FROM runs WHERE created >= extract(epoch from date_trunc('day', now()));")"
echo "  今日已回答     : $(Q "SELECT count(*) FROM runs WHERE created >= extract(epoch from date_trunc('day', now())) AND result::json->>'status' = 'answered';")"
echo "  今日弃答       : $(Q "SELECT count(*) FROM runs WHERE created >= extract(epoch from date_trunc('day', now())) AND result::json->>'status' = 'abstained';")"
echo "  今日急诊       : $(Q "SELECT count(*) FROM runs WHERE created >= extract(epoch from date_trunc('day', now())) AND result::json->>'status' = 'emergency';")"

echo
echo "############ 六、当前实时状态 ############"
INFLIGHT=$(Q "SELECT count(*) FROM runs WHERE status='running';")
echo "  正在生成的提问 : $INFLIGHT （上限 $(grep -E '^MED_MAX_CONCURRENT_CHATS=' backend/.env | cut -d= -f2)）"
echo "  8010 已建立连接: $(ss -tn state established '( sport = :8010 )' 2>/dev/null | tail -n +2 | wc -l)"
echo "  当前登录用户   : $(who | wc -l) 个 shell 会话"
echo "  负载/内存      : $(uptime | sed 's/.*load average/load/')"
free -m | sed -n 2p | awk '{printf "  内存           : 已用 %s MB / 共 %s MB\n", $3, $2}'

echo
echo "############ 七、最近错误 ############"
$COMPOSE logs --since 2h app 2>&1 | grep -iE 'error|traceback|exception' | grep -v GqlStatus | tail -8 || echo "  （近 2 小时无错误）"
