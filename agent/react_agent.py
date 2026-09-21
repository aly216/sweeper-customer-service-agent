from langchain.agents import create_agent
from model.factory import chat_model_factory
from utils.prompt_loader import load_system_prompt
from agent.tools.agent_tools import (rag_summarize, get_weather, get_user_id,
                                     get_current_month, fetch_external_data, fill_context_for_report)
from agent.tools.middleware import monitor_tool, log_before_model, report_prompt_switch


def _extract_text(content) -> str:
    """从消息 content 提取纯文本。工具调用时 AIMessage.content 可能是 content block 列表，需兼容处理。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text", "")
                if isinstance(text, str):
                    parts.append(text)
                elif isinstance(text, dict):
                    parts.append(text.get("value", ""))
        return "".join(parts)
    return str(content)


class ReactAgent:
    def __init__(self):
        self.agent = create_agent(
            model=chat_model_factory.generator(),
            system_prompt=load_system_prompt(),
            tools=[
                rag_summarize,
                get_weather,
                get_user_id,
                get_current_month,
                fetch_external_data,
                fill_context_for_report,
            ],
            middleware=[
                monitor_tool,
                log_before_model,
                report_prompt_switch,
            ],
        )

    def execute_stream(self, messages: list):
        # 传入完整对话历史实现多轮记忆（LLM 无状态，靠每轮把历史重新喂给它来"记住"上下文）
        input_dict = {
            'messages': messages
        }

        for chunk in self.agent.stream(input_dict, stream_mode="values", context={'report': False}):
            latest_message = chunk['messages'][-1]
            text = _extract_text(latest_message.content)
            if text:
                yield text.strip() + "\n"
