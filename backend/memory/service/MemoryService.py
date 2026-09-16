from memory.layers.ConversationState import ContextResolver, ConversationState
from memory.layers.WorkingMemory import WorkingMemory


class MemoryService:
    """Coordinate four layers; a question is never promoted to a clinical fact."""

    def __init__(self, chat_dao, short_term, episodes, semantic, settings):
        self.store = chat_dao
        self.short_term = short_term
        self.episode_layer = episodes
        self.semantic_layer = semantic
        self.settings = settings
        self.resolver = ContextResolver()

    @property
    def redis_status(self):
        return self.short_term.status

    def resolve(self, owner, conversation, question):
        canonical = self.episode_layer.window(owner, conversation)
        cached = self.short_term.get(owner, conversation["id"], canonical.revision)
        source = "redis" if cached else self.settings.database_backend + "_fallback"
        if not cached:
            self.short_term.put(canonical)
        # Rebuild the rules-extracted patient context from durable turn history (L3)
        # on every request so a Redis/DB miss cannot lose facts. The state records
        # only what the user said; it never upgrades retrieval hits into diagnoses.
        state = ConversationState()
        for turn in canonical.turns:
            if turn.question:
                self.resolver.update(state, turn.question, turn.run_id)
        return WorkingMemory(
            question=question,
            recent=(cached or canonical).turns,
            semantic=self.semantic_layer.retrieve(owner),
            retrieved_from=source,
            conversation_state=state,
        )

    def refresh(self, owner, cid):
        conversation = self.store.conversation(owner, cid)
        if conversation:
            self.short_term.put(self.episode_layer.window(owner, conversation))

    def invalidate(self, owner, cid):
        self.short_term.delete(owner, cid)

    def semantic(self, owner):
        return self.semantic_layer.retrieve(owner)

    def remember(self, owner, kind, value, memory_id=None):
        return self.semantic_layer.remember(owner, kind, value, memory_id)

    def forget(self, owner, memory_id):
        return self.semantic_layer.forget(owner, memory_id)

    def episodes(self, owner):
        return self.episode_layer.list(owner)

    def close(self):
        self.short_term.close()
