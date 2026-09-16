import os

import yaml
from dotenv import load_dotenv

from utils.path_tool import get_abs_path

# 从项目根目录 .env 加载 API Key，避免在代码中硬编码密钥
load_dotenv(get_abs_path('.env'))


def _load_yaml(path: str) -> dict:
    with open(path, 'r', encoding='utf-8') as f:
        data = yaml.load(f, Loader=yaml.FullLoader)
    return data if data is not None else {}


def load_rag_config(config_file: str = get_abs_path('config/rag.yml')):
    return _load_yaml(config_file)


def load_chroma_config(config_file: str = get_abs_path('config/chroma.yml')):
    return _load_yaml(config_file)


def load_prompt_config(config_file: str = get_abs_path('config/prompts.yml')):
    return _load_yaml(config_file)


def load_agent_config(config_file: str = get_abs_path('config/agent.yml')):
    return _load_yaml(config_file)


rag_conf = load_rag_config()
chroma_conf = load_chroma_config()
prompt_conf = load_prompt_config()
agent_conf = load_agent_config()

# 用环境变量覆盖 YAML 中的空 api_key
rag_conf['chat']['api_key'] = os.environ.get('DEEPSEEK_API_KEY', '')
rag_conf['embedding']['api_key'] = os.environ.get('DASHSCOPE_API_KEY', '')
