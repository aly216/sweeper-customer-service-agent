import hashlib,os
from langchain_community.document_loaders import PyPDFLoader,TextLoader
from utils.logger_handler import logger



def get_file_md5_hex(file_path:str):
    if not os.path.exists(file_path):
        logger.error(f"文件不存在: {file_path}")
        return None
    if not os.path.isfile(file_path):
        logger.error(f"文件不是普通文件: {file_path}")
        return None
    md5_obj=hashlib.md5()
    chunk_size=4096
    try:
        with open(file_path,'rb') as f:
            while chunk:=f.read(chunk_size):
                md5_obj.update(chunk)

            md5_hex=md5_obj.hexdigest()
            return md5_hex
    except Exception as e:
        logger.error(f"计算文件MD5值失败: {file_path} - {e}")
        return None



def listdir_with_allowed_type(path:str,allowed_types:tuple[str]):
    files=[]
    if not os.path.isdir(path):
        logger.error(f"路径不是目录: {path}")
        return []
    for f in os.listdir(path):
        if f.endswith(allowed_types):
            files.append(os.path.join(path,f))
    return tuple(files)


def pdf_loader(file_path:str,password:str=None):
    return PyPDFLoader(file_path,password=password).load()

def text_loader(file_path:str):
    return TextLoader(file_path,encoding='utf-8').load()
