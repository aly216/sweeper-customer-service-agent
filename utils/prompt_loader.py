from utils.config_handler import prompt_conf
from utils.path_tool import get_abs_path
from utils.logger_handler import logger
from langchain_core.prompts import ChatPromptTemplate


def load_system_prompt():
    try:
        system_prompt_path=get_abs_path(prompt_conf['main_prompt_path'])
    except Exception as e:
        logger.error(f"加载系统提示失败失败: {e}")
        raise e
    try:
        return open(system_prompt_path,'r',encoding='utf-8').read()
    except Exception as e:
        logger.error(f"加载系统提示失败失败: {e}")
        raise e





def load_rag_prompt():
    try:
        rag_prompt_path=get_abs_path(prompt_conf['rag_prompt_path'])
    except Exception as e:
        logger.error(f"加载系统提示失败失败: {e}")
        raise e
    try:
        return open(rag_prompt_path,'r',encoding='utf-8').read()
    except Exception as e:
        logger.error(f"加载rag提示失败失败: {e}")
        raise e


def load_report_prompt():
    try:
        report_prompt_path=get_abs_path(prompt_conf['report_prompt_path'])
    except Exception as e:
        logger.error(f"加载report提示失败失败: {e}")
        raise e
    try:
        return open(report_prompt_path,'r',encoding='utf-8').read()
    except Exception as e:
        logger.error(f"加载报告提示失败失败: {e}")
        raise e