import time
import uuid


class MemoryDao:
    def __init__(self, database):
        self.database = database

    def list(self, owner):
        with self.database.connect() as conn:
            return [
                dict(r)
                for r in conn.execute(
                    "SELECT id,kind,value,provenance,created,updated FROM semantic_memory WHERE session_id=? ORDER BY updated DESC",
                    (owner,),
                )
            ]

    def save(self, owner, kind, value, memory_id=None):
        now = time.time()
        with self.database.connect() as conn:
            if memory_id:
                changed = conn.execute(
                    "UPDATE semantic_memory SET kind=?,value=?,updated=? WHERE id=? AND session_id=?",
                    (kind, value, now, memory_id, owner),
                ).rowcount
                if not changed:
                    raise LookupError("Memory not found")
            else:
                if (
                    conn.execute(
                        "SELECT count(*) FROM semantic_memory WHERE session_id=?", (owner,)
                    ).fetchone()[0]
                    >= 50
                ):
                    raise ValueError("长期记忆最多保存 50 条，请先整理已有条目")
                memory_id = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO semantic_memory VALUES (?,?,?,?,?,?,?)",
                    (memory_id, owner, kind, value, "user_confirmed", now, now),
                )
        return next(m for m in self.list(owner) if m["id"] == memory_id)

    def delete(self, owner, memory_id):
        with self.database.connect() as conn:
            return (
                conn.execute(
                    "DELETE FROM semantic_memory WHERE id=? AND session_id=?", (memory_id, owner)
                ).rowcount
                > 0
            )
