"""MCP 服务端：把无会话依赖的工具暴露给外部应用（如 Claude Code）。"""
from datetime import datetime

from mcp.server.fastmcp import FastMCP

from agent.tools.weather_tool import fetch_weather_by_city
from utils import storage

mcp = FastMCP("robot-vacuum-tools")
storage.init_db()


@mcp.tool()
def get_weather(city: str) -> str:
    return fetch_weather_by_city(city)


@mcp.tool()
def get_current_month() -> str:
    return datetime.now().strftime("%Y-%m")


@mcp.tool()
def fetch_external_data(user_id: str, month: str) -> str:
    return storage.format_record(storage.fetch_record(user_id, month))


@mcp.tool()
def save_record(user_id: str, efficiency: str, consumables: str, comparison: str, month: str = "") -> str:
    m = month or datetime.now().strftime("%Y-%m")
    try:
        storage.save_record(user_id, efficiency, consumables, comparison, m)
        return f"已保存用户 {user_id} 在 {m} 的使用记录"
    except Exception as e:
        return f"保存失败：{e}"


if __name__ == "__main__":
    mcp.run()
