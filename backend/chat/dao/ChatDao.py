import json
import time
import uuid


class ChatDao:
    """会话和已验证问答持久化；所有查询带 owner 条件。"""

    def __init__(self, database, request_timeout=90):
        self.database = database
        self.request_timeout = request_timeout

    def connect(self):
        return self.database.connect()

    def conversations(self, owner):
        with self.connect() as conn:
            return [
                dict(r)
                for r in conn.execute(
                    "SELECT id,title,created,updated FROM conversations WHERE session_id=? ORDER BY updated DESC",
                    (owner,),
                )
            ]

    def create_conversation(self, owner, title="新对话"):
        cid, now = str(uuid.uuid4()), time.time()
        with self.connect() as conn:
            conn.execute("INSERT INTO conversations VALUES (?,?,?,?,?)", (cid, owner, title, now, now))
        return {"id": cid, "title": title, "created": now, "updated": now}

    def conversation(self, owner, cid):
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id,title,created,updated FROM conversations WHERE id=? AND session_id=?", (cid, owner)
            ).fetchone()
            if not row:
                return None
            data = dict(row)
            data["runs"] = [
                self.parse_run(r)
                for r in conn.execute(
                    "SELECT * FROM runs WHERE conversation_id=? AND session_id=? ORDER BY created",
                    (cid, owner),
                )
            ]
            return data

    def update_conversation(self, owner, cid, title):
        with self.connect() as conn:
            return (
                conn.execute(
                    "UPDATE conversations SET title=?,updated=? WHERE id=? AND session_id=?",
                    (title, time.time(), cid, owner),
                ).rowcount
                > 0
            )

    def delete_conversation(self, owner, cid):
        with self.connect() as conn:
            if conn.execute(
                "SELECT 1 FROM runs WHERE conversation_id=? AND session_id=? AND status='running'",
                (cid, owner),
            ).fetchone():
                raise ValueError("请先停止当前回答，再删除对话")
            return (
                conn.execute("DELETE FROM conversations WHERE id=? AND session_id=?", (cid, owner)).rowcount
                > 0
            )

    @staticmethod
    def parse_run(row):
        data = dict(row)
        data.pop("session_id", None)
        data["result"] = json.loads(data["result"]) if data["result"] else None
        return data

    def find_request(self, owner, request_id):
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM runs WHERE session_id=? AND request_id=?", (owner, request_id)
            ).fetchone()
            return self.parse_run(row) if row else None

    def start_run(self, owner, cid, request_id, question, mode="authoritative"):
        rid = str(uuid.uuid4())
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if self.database.dialect != "sqlite":
                conn.execute("SELECT id FROM sessions WHERE id=? FOR UPDATE", (owner,))
            conn.execute(
                "UPDATE runs SET status='interrupted' WHERE session_id=? AND status='running' AND created<?",
                (owner, time.time() - self.request_timeout - 30),
            )
            if not conn.execute(
                "SELECT 1 FROM conversations WHERE id=? AND session_id=?", (cid, owner)
            ).fetchone():
                raise LookupError("Conversation not found")
            if conn.execute(
                "SELECT 1 FROM runs WHERE session_id=? AND request_id=?", (owner, request_id)
            ).fetchone():
                raise ValueError("请求已经提交")
            if conn.execute(
                "SELECT 1 FROM runs WHERE session_id=? AND status='running'", (owner,)
            ).fetchone():
                raise ValueError("当前会话已有正在处理的请求")
            conn.execute(
                "INSERT INTO runs (id,conversation_id,session_id,request_id,question,status,result,created,mode) VALUES (?,?,?,?,?,'running',NULL,?,?)",
                (rid, cid, owner, request_id, question, time.time(), mode),
            )
            conn.execute(
                "UPDATE conversations SET title=CASE WHEN title='新对话' THEN ? ELSE title END,updated=? WHERE id=? AND session_id=?",
                (question[:40], time.time(), cid, owner),
            )
        return rid

    def finish_run(self, owner, rid, result):
        with self.connect() as conn:
            conn.execute(
                "UPDATE runs SET status='completed',result=? WHERE id=? AND session_id=? AND status='running'",
                (json.dumps(result, ensure_ascii=False), rid, owner),
            )

    def mark_run(self, owner, rid, status):
        with self.connect() as conn:
            conn.execute(
                "UPDATE runs SET status=? WHERE id=? AND session_id=? AND status='running'",
                (status, rid, owner),
            )

    def run(self, owner, rid):
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id=? AND session_id=?", (rid, owner)).fetchone()
            return self.parse_run(row) if row else None

    def metrics(self):
        with self.connect() as conn:
            return {
                r["status"]: r["n"]
                for r in conn.execute("SELECT status,count(*) AS n FROM runs GROUP BY status")
            }
