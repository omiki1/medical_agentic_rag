class SemanticMemory:
    """L4: explicitly confirmed profile facts; never inferred diagnoses."""

    def __init__(self, dao):
        self.dao = dao

    def retrieve(self, owner):
        return self.dao.list(owner)

    def remember(self, owner, kind, value, memory_id=None):
        if kind == "response_style" and value not in {"简洁", "详细"}:
            raise ValueError("回答偏好请选择简洁或详细")
        return self.dao.save(owner, kind, value, memory_id)

    def forget(self, owner, memory_id):
        return self.dao.delete(owner, memory_id)
