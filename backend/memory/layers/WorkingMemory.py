from dataclasses import dataclass, field

from memory.entity.MemoryEntity import RecentTurn


@dataclass
class WorkingMemory:
    """Created once per request; never shared between users or runs."""

    question: str
    recent: list[RecentTurn] = field(default_factory=list)
    semantic: list[dict] = field(default_factory=list)
    retrieved_from: str = "empty"
    conversation_state: object = None  # ConversationState: rules-extracted patient facts

    @property
    def previous_question(self):
        # Context resolution uses prior entity names, not prior instructions/answers.
        for turn in reversed(self.recent):
            if turn.entities and turn.outcome in {"answered", "abstained"}:
                return "、".join(turn.entities)
        return ""

    def trace(self):
        return {
            "layers": [
                {"layer": 1, "name": "工作记忆", "storage": "request", "items": 1},
                {"layer": 2, "name": "短期记忆", "storage": self.retrieved_from, "items": len(self.recent)},
                {"layer": 3, "name": "情节记忆", "storage": "durable_database", "items": len(self.recent)},
                {
                    "layer": 4,
                    "name": "长期语义记忆",
                    "storage": "confirmed_profile",
                    "items": len(self.semantic),
                },
            ],
            "context_policy": "active_conversation_only; no inferred diagnoses",
        }
