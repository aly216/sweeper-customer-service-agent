from langchain_chroma import Chroma
import os
from utils.config_handler import chroma_conf
from model.factory import embedding_factory, chat_model_factory
from langchain_text_splitters import RecursiveCharacterTextSplitter
from utils.path_tool import get_abs_path
from utils.file_handler import pdf_loader, text_loader, listdir_with_allowed_type, get_file_md5_hex
from utils.logger_handler import logger
from langchain_core.documents import Document


class VectorStoreService:
    def __init__(self):
        self.vector_store = Chroma(
            collection_name=chroma_conf['collection_name'],
            persist_directory=get_abs_path(chroma_conf['persist_directory']),
            embedding_function=embedding_factory.generator()
        )
        self.spliter = RecursiveCharacterTextSplitter(
            chunk_size=chroma_conf['chunk_size'],
            chunk_overlap=chroma_conf['chunk_overlap'],
            separators=chroma_conf['separators'],
            length_function=len,
        )

    def get_retriever(self):
        return self.vector_store.as_retriever(search_kwargs={"k": chroma_conf['k']})

    def load_documents(self, documents):
        def check_md5_hex(md5_for_check: str):
            if not os.path.exists(get_abs_path(chroma_conf['md5_hex_store'])):
                open(get_abs_path(chroma_conf['md5_hex_store']), 'w', encoding='utf-8').close()
                return False

            with open(get_abs_path(chroma_conf['md5_hex_store']), 'r', encoding='utf-8') as f:
                lines = f.readlines()
                for line in lines:
                    if line.strip() == md5_for_check:
                        return True
            return False

        def save_md5_hex(md5_for_check: str):
            with open(get_abs_path(chroma_conf['md5_hex_store']), 'a', encoding='utf-8') as f:
                f.write(md5_for_check + '\n')

        def get_file_documents(read_file_path: str):
            if read_file_path.endswith('.pdf'):
                return pdf_loader(read_file_path)
            elif read_file_path.endswith('.txt'):
                return text_loader(read_file_path)
            else:
                raise ValueError('不支持的文件类型')

        allowed_files_path = listdir_with_allowed_type(
            get_abs_path(chroma_conf['data_path']),
            tuple(chroma_conf['allow_knowledge_file_type'])
        )

        for path in allowed_files_path:
            md5_hex = get_file_md5_hex(path)

            if check_md5_hex(md5_hex):
                logger.info(f'文件已存在: {path}')
                continue

            try:
                documents = get_file_documents(path)

                if not documents:
                    logger.warning(f'文件加载失败: {path} - 无内容')
                    continue

                split_documents = self.spliter.split_documents(documents)

                if not split_documents:
                    logger.warning(f'文件加载失败: {path} - 无内容')
                    continue

                self.vector_store.add_documents(split_documents)
                save_md5_hex(md5_hex)
                logger.info(f'文件加载成功: {path}')
            except Exception as e:
                logger.error(f'文件加载失败: {path}:{str(e)}', exc_info=True)
                continue
