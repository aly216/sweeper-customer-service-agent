"""客服 Agent 工具集：RAG、天气、用户/月份、外部记录、报告上下文、记录保存。"""
from datetime import datetime
from typing import Annotated

from langchain_core.tools import tool, InjectedToolArg
from langgraph.prebuilt import ToolRuntime

from utils.logger_handler import logger
from utils import storage
from rag.rag_service import RagSummarizeService
from agent.tools.weather_tool import fetch_weather_by_city

rag = RagSummarizeService()


@tool(description="从向量数据库中检索与查询相关的内容，返回总结回复")
def rag_summarize(query: str) -> str:
    return rag.rag_summarize(query)


@tool(description="获取指定城市的实时天气与未来几小时预报，以消息字符串的形式返回")
def get_weather(city: str) -> str:
    return fetch_weather_by_city(city)


@tool(description="获取当前登录用户的ID，未登录时返回空字符串")
def get_user_id(runtime: Annotated[ToolRuntime, InjectedToolArg]) -> str:
    ctx = runtime.context or {}
    return ctx.get("user_id", "")


@tool(description="获取系统当前月份，格式 YYYY-MM")
def get_current_month() -> str:
    return datetime.now().strftime("%Y-%m")


@tool(description="从外部系统中获取指定用户在指定月份的使用记录，以纯字符串形式返回，未检索到返回空字符串")
def fetch_external_data(user_id: str, month: str) -> str:
    return storage.format_record(storage.fetch_record(user_id, month))


@tool(description="无入参，无返回值，调用后触发中间件自动为报告生成的场景动态注入上下文信息，为后续提示词切换提供上下文信息")
def fill_context_for_report():
    return "fill_context_for_report已调用"


@tool(description="把用户口述的使用数据（清洁效率、耗材、对比）保存到该用户的记录中；month 为空则存到当前月")
def save_record(efficiency: str, consumables: str, comparison: str, month: str = "",
                runtime: Annotated[ToolRuntime, InjectedToolArg] = None) -> str:
    ctx = (runtime.context or {}) if runtime else {}
    user_id = ctx.get("user_id", "")
    if not user_id:
        return "未登录，无法保存记录，请先登录"
    m = month or datetime.now().strftime("%Y-%m")
    try:
        storage.save_record(user_id, efficiency, consumables, comparison, m)
        return f"已保存用户 {user_id} 在 {m} 的使用记录"
    except Exception as e:
        logger.error(f"[save_record] 保存失败：{e}")
        return f"保存失败：{e}"
