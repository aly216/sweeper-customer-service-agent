"""
天气查询工具：基于 Open-Meteo 免费 API 获取真实天气。
流程：城市名 -> 地理编码(经纬度) -> 实时天气 + 未来几小时预报 -> 拼成字符串返回给 LLM。
"""
import openmeteo_requests
import requests
from datetime import datetime

from utils.logger_handler import logger

# Open-Meteo 客户端（自带缓存与重试机制）
openmeteo = openmeteo_requests.Client()


def get_coordinate_by_city(city_name: str):
    """城市名 -> 经纬度（Open-Meteo 地理编码 API），查不到返回 None"""
    geo_url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {
        "name": city_name,
        "count": 1,
        "language": "zh",
    }
    try:
        res = requests.get(geo_url, params=params, timeout=10)
        data = res.json()
        if "results" not in data or len(data["results"]) == 0:
            return None
        result = data["results"][0]
        return {
            "name": result["name"],
            "latitude": result["latitude"],
            "longitude": result["longitude"],
        }
    except Exception as e:
        logger.warning(f"[weather_tool] 地理编码查询失败：{e}")
        return None


def fetch_weather_by_city(city: str) -> str:
    """城市名 -> 实时天气 + 未来几小时预报字符串（给 LLM 用），失败返回提示语"""
    location = get_coordinate_by_city(city)
    if location is None:
        return f"未找到城市「{city}」的天气信息，请确认城市名称是否正确"

    city_name = location["name"]
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": location["latitude"],
        "longitude": location["longitude"],
        "hourly": ["temperature_2m", "precipitation", "wind_speed_10m"],
        "current": ["temperature_2m", "relative_humidity_2m"],
    }
    try:
        response = openmeteo.weather_api(url, params=params)[0]
    except Exception as e:
        logger.error(f"[weather_tool] 天气查询失败：{e}")
        return f"查询{city_name}天气失败，请稍后再试"

    # 实时天气
    current = response.Current()
    current_temp = current.Variables(0).Value()
    current_hum = current.Variables(1).Value()

    # 未来 5 小时预报
    hourly = response.Hourly()
    hourly_temp = hourly.Variables(0).ValuesAsNumpy()
    hourly_precip = hourly.Variables(1).ValuesAsNumpy()
    hourly_wind = hourly.Variables(2).ValuesAsNumpy()

    lines = [f"【{city_name}天气】"]
    lines.append(f"实时：温度{current_temp:.1f}℃，相对湿度{current_hum:.0f}%")
    lines.append("未来5小时预报：")
    for i in range(5):
        t = datetime.fromtimestamp(hourly.Time() + i * 3600)
        lines.append(
            f"{t.strftime('%m-%d %H:%M')} 温度{hourly_temp[i]:.1f}℃ "
            f"降水{hourly_precip[i]:.1f}mm 风速{hourly_wind[i]:.1f}m/s"
        )
    return "\n".join(lines)
