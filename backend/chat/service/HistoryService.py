from fastapi import HTTPException


class HistoryService:
    def __init__(self, dao, memory):
        self.dao, self.memory = dao, memory

    def list(self, owner):
        return self.dao.conversations(owner)

    def create(self, owner):
        return self.dao.create_conversation(owner)

    def get(self, owner, cid):
        data = self.dao.conversation(owner, str(cid))
        if not data:
            raise HTTPException(404, "未找到对话")
        return data

    def rename(self, owner, cid, title):
        if not self.dao.update_conversation(owner, str(cid), title):
            raise HTTPException(404, "未找到对话")
        return {"ok": True}

    def delete(self, owner, cid):
        try:
            removed = self.dao.delete_conversation(owner, str(cid))
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
        if not removed:
            raise HTTPException(404, "未找到对话")
        self.memory.invalidate(owner, str(cid))
        return {"ok": True}

    def run(self, owner, rid):
        data = self.dao.run(owner, str(rid))
        if not data:
            raise HTTPException(404, "未找到记录")
        return data
