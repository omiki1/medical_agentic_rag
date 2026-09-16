import json

from memory.entity.MemoryEntity import MemoryWindow, RecentTurn


class EpisodeMemory:
    """L3: canonical completed runs with citations and execution provenance."""

    def __init__(self, chat_dao, settings):
        self.dao, self.settings = chat_dao, settings

    def window(self, owner, conversation):
        completed = [r for r in conversation["runs"] if r["status"] == "completed" and r["result"]]
        return MemoryWindow(
            owner=owner,
            conversation_id=conversation["id"],
            revision=completed[-1]["id"] if completed else "empty",
            turns=[
                RecentTurn(
                    run_id=r["id"],
                    question=r["question"],
                    entities=r["result"]["analysis"]["entities"],
                    outcome=r["result"]["status"],
                )
                for r in completed[-self.settings.memory_recent_turns :]
            ],
        )

    def list(self, owner, limit=20):
        with self.dao.connect() as conn:
            rows = conn.execute(
                "SELECT id,conversation_id,question,result,created FROM runs WHERE session_id=? AND status='completed' ORDER BY created DESC LIMIT ?",
                (owner, limit),
            )
            return [
                {
                    "id": r["id"],
                    "conversation_id": r["conversation_id"],
                    "question": r["question"],
                    "status": json.loads(r["result"])["status"],
                    "created": r["created"],
                }
                for r in rows
            ]
