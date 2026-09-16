from agent.MedicalAgent import MedicalAgent
from ai.Neo4jService import Neo4jService
from auth.dao.AuthDao import AuthDao
from auth.service.AuthService import AuthService
from chat.dao.ChatDao import ChatDao
from chat.service.ChatService import ChatService
from chat.service.HistoryService import HistoryService
from memory.dao.MemoryDao import MemoryDao
from memory.layers.EpisodeMemory import EpisodeMemory
from memory.layers.RedisMemory import RedisMemory
from memory.layers.SemanticMemory import SemanticMemory
from memory.service.MemoryService import MemoryService
from rag.corpus.MedicalCorpus import MedicalCorpus
from rag.retriever.HybridRetriever import HybridRetriever
from rag.service.KnowledgeService import KnowledgeService
from user.dao.UsersDao import UsersDao
from user.service.UserService import UserService
from user.service.UserModelService import UserModelService

from common.Database import Database
from common.Schema import Schema
from common.TranslationService import TranslationService


class ApplicationContext:
    """One dependency composition root; models/connections are reused per process."""

    def __init__(self, settings, corpus=None, retriever=None):
        self.settings = settings
        self.database = Database(settings)
        Schema.initialize(self.database)
        self.chat_dao = ChatDao(self.database, settings.request_timeout)
        self.users_dao = UsersDao(self.database)
        self.auth_dao = AuthDao(self.database, settings.session_days)
        self.auth_service = AuthService(self.auth_dao, self.users_dao, settings)
        self.user_service = UserService(self.users_dao)
        self.user_model_service = UserModelService(self.database, settings)
        self.memory_service = MemoryService(
            self.chat_dao,
            RedisMemory(settings),
            EpisodeMemory(self.chat_dao, settings),
            SemanticMemory(MemoryDao(self.database)),
            settings,
        )
        self.corpus = corpus or MedicalCorpus(settings.data_dir)
        self.retriever = retriever or HybridRetriever(self.corpus, settings)
        self.neo4j = Neo4jService(settings)
        self.translator = TranslationService(settings)
        self.agent = MedicalAgent(self.corpus, self.retriever, settings, self.neo4j, translator=self.translator)
        self.chat_service = ChatService(
            self.chat_dao, self.agent, self.memory_service, settings, translator=self.translator
        )
        self.history_service = HistoryService(self.chat_dao, self.memory_service)
        self.knowledge_service = KnowledgeService(self.corpus, self.retriever.qa)

    def close(self):
        self.neo4j.close()
        self.memory_service.close()
