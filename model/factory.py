from abc import ABC, abstractmethod
from typing import Optional
from langchain.chat_models import BaseChatModel
from langchain.embeddings import Embeddings
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from utils.config_handler import rag_conf


class BaseModelFactory(ABC):
    @abstractmethod
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        """生成模型/向量化模型实例"""
        pass


class ChatModelFactory(BaseModelFactory):
    def generator(self) -> BaseChatModel:
        chat = rag_conf['chat']
        return ChatOpenAI(
            model=chat['model'],
            api_key=chat['api_key'],
            base_url=chat['base_url'],
            temperature=chat['temperature'],
        )


class EmbeddingFactory(BaseModelFactory):
    def generator(self) -> Embeddings:
        emb = rag_conf['embedding']
        return OpenAIEmbeddings(
            model=emb['model'],
            base_url=emb['base_url'],
            api_key=emb['api_key'],
            check_embedding_ctx_length=emb['check_embedding_ctx_length'],
            chunk_size=emb['chunk_size'],
        )


chat_model_factory = ChatModelFactory()
embedding_factory = EmbeddingFactory()
