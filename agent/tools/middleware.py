from typing import Callable
from utils.prompt_loader import load_system_prompt, load_report_prompt
from langchain.agents import AgentState
from langchain.agents.middleware import wrap_tool_call, before_model, dynamic_prompt, ModelRequest
from langchain.tools.tool_node import ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.runtime import Runtime
from langgraph.types import Command
from utils.logger_handler import logger



@wrap_tool_call
def monitor_tool(
    request: ToolCallRequest,           # 工具调用请求
    handler: Callable[[ToolCallRequest], ToolMessage|Command],  # 工具调用处理函数       
)->ToolMessage|Command:
    """
    监控工具调用，记录工具调用信息
    """
    logger.info(f"工具调用: {request.tool_call['name']}")
    logger.info(f"工具调用参数: {request.tool_call['args']}]")
    try:
        result = handler(request)
        logger.info(f"工具调用成功: {request.tool_call['name']}")

        if request.tool_call['name'] == 'fill_context_for_report':
            request.runtime.context['report']=True
        return result
    except Exception as e:
        logger.error(f"工具{request.tool_call['name']}调用失败: {e}")
        return ToolMessage(content=f"工具调用失败: {e}", tool_call_id=request.tool_call.get('id', ''))



@before_model
def log_before_model(
    state: AgentState,           
    runtime: Runtime,           
):
    logger.info(f"{log_before_model}即将调用模型,带有{len(state['messages'])}个外部数据")
    logger.debug(f"[log_before_model] {type(state['messages'][-1]).__name__}| {state['messages'][-1].content.strip()}")
    return None


@dynamic_prompt
def report_prompt_switch(request: ModelRequest):
    is_report = request.runtime.context.get('report', False)
    if is_report:
        return load_report_prompt()
    else:
        return load_system_prompt()

