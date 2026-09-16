import hashlib

from memory.entity.MemoryEntity import MemoryWindow


class RedisMemory:
    """L2: TTL-bounded, revision-checked conversation cache."""

    def __init__(self, settings):
        self.settings = settings
        self.client = None
        self.status = "disabled"
        if settings.redis_url:
            try:
                import redis

                self.client = redis.Redis.from_url(
                    settings.redis_url,
                    password=settings.redis_password or None,
                    socket_connect_timeout=1,
                    socket_timeout=1,
                    decode_responses=True,
                )
                self.client.ping()
                self.status = "connected"
            except Exception:
                self.status = "unavailable"

    @staticmethod
    def key(owner, cid):
        return "mediatlas:memory:v1:" + hashlib.sha256(owner.encode()).hexdigest()[:24] + ":" + cid

    def get(self, owner, cid, revision):
        if not self.client:
            return None
        try:
            value = self.client.get(self.key(owner, cid))
            self.status = "connected"
            if value:
                window = MemoryWindow.model_validate_json(value)
                if window.owner == owner and window.conversation_id == cid and window.revision == revision:
                    return window
        except Exception:
            self.status = "unavailable"
        return None

    def put(self, window):
        if self.client:
            try:
                self.client.setex(
                    self.key(window.owner, window.conversation_id),
                    self.settings.memory_ttl_seconds,
                    window.model_dump_json(),
                )
                self.status = "connected"
            except Exception:
                self.status = "unavailable"

    def delete(self, owner, cid):
        if self.client:
            try:
                self.client.delete(self.key(owner, cid))
            except Exception:
                self.status = "unavailable"

    def close(self):
        if self.client:
            self.client.close()
