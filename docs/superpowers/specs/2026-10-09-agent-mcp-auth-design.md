# 设计文档：登录鉴权 + 数据持久化 + 工具改造 + MCP 服务端

日期：2026-10-09
状态：待评审

## 1. 概述

给「智扫通机器人智能客服」这个 LangChain ReAct Agent 项目增加四块能力，串成一条完整链路：

> **注册登录 → 会话身份 → Agent 工具写库 → 工具做成 MCP server 供外部应用复用**

- **登录鉴权**：轻量密码登录 + 注册（新用户自行注册）。
- **数据持久化**：把「使用记录」从静态只读 CSV 迁到 SQLite，支持写入。
- **工具改造**：`get_user_id` 返回真实登录用户、`get_current_month` 返回真实当前月、新增 `save_record` 工具，并让 Agent 主动提醒用户保存。
- **MCP 服务端**：把无会话依赖的工具包装成 MCP server，供 Claude Code 等外部应用调用。

**明确不做**（非目标）：MCP 客户端（本 Agent 不挂外部 MCP server）、OAuth/第三方登录、RAG 检索逻辑改动。

## 2. 现状

- Agent：`agent/react_agent.py` 用 `create_agent` 注册 6 个工具（`rag_summarize` / `get_weather` / `get_user_id` / `get_current_month` / `fetch_external_data` / `fill_context_for_report`），已用 `context={'report': False}` 传递运行时上下文，middleware 通过 `request.runtime.context` 读取。
- 工具：`agent/tools/agent_tools.py` 中 `get_user_id`/`get_current_month` 是 `random.choice` 占位实现；`fetch_external_data` 从 `data/external/records.csv` 只读加载到内存字典。
- 模型：`ChatOpenAI` 指向 DeepSeek（`config/rag.yml`）。
- 应用：`app.py` 是 Streamlit 单页聊天，无登录、无用户身份。
- 提示词：`prompt/main_prompt.txt`（系统）、`prompt/report_prompt.txt`（报告场景，由 middleware 动态切换）。
- 依赖：已有 `mcp` SDK（v1.26.0）；未装 `langchain-mcp-adapters`（本设计不再需要）。

## 3. 关键设计决策

| # | 决策 |
|---|------|
| D1 | 数据存 SQLite（`users` + `records`），**从 0 建库**，预置 12 个用户各带近 12 个月真实月份记录；新注册用户从 0 积累 |
| D2 | 登录用轻量密码登录 + 注册表单；密码用 `hashlib.pbkdf2_hmac` 加盐哈希（stdlib，无新依赖） |
| D3 | `get_user_id` 返回登录用户（通过 `ToolRuntime.context` 注入）；`get_current_month` 返回真实当前月 `YYYY-MM` |
| D4 | 新增 `save_record` 工具；系统提示词加「主动提醒保存」行为；新用户不自动建首条记录 |
| D5 | MCP 服务端暴露 `get_weather` / `fetch_external_data` / `get_current_month` / `save_record`；会话相关的 `get_user_id`、依赖 Chroma 的 `rag_summarize`、依赖 middleware 的 `fill_context_for_report` 不进 server |
| D6 | 记录时间 = 真实事件时间（`saved_at` / `registered_at`），不写死年份，杜绝「数据过期」 |

## 4. 架构总览

```
┌───────────── Streamlit app.py ─────────────┐
│  侧边栏：登录 / 注册 / 当前用户 / 退出        │
│  st.session_state.user_id ──────────────┐  │
└──────────────────────────────────────────│──┘
                                           ▼
                ReactAgent.execute_stream(messages, user_id)
                          │ context={'report': False, 'user_id': ...}
                          ▼
        ┌──────── create_agent(tools=[...7 个工具]) ────────┐
        │  rag_summarize / get_weather / get_user_id /       │
        │  get_current_month / fetch_external_data /         │
        │  fill_context_for_report / save_record             │
        └───────────────┬─────────────────────┬─────────────┘
                        │ 读写                │ get_user_id 读 context
                        ▼                     ▼
              utils/storage.py (SQLite)   ToolRuntime.context
                        ▲
                        │ 复用同一套 storage
        ┌───────────────┴───────────────┐
        │ agent/mcp_server.py (FastMCP) │ ←── Claude Code 经 MCP 调用
        └───────────────────────────────┘
```

## 5. 数据模型（SQLite）

数据库文件：`data/app.db`（路径由 `config/agent.yml` 的 `db_path` 配置）。

```sql
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       TEXT NOT NULL UNIQUE,   -- 数字字符串 "1001"；注册时自动生成
    username      TEXT NOT NULL UNIQUE,   -- 登录名
    password_hash TEXT NOT NULL,
    profile       TEXT,                   -- 画像，如 "65㎡公寓 | 单身 | 木地板"
    registered_at TEXT NOT NULL           -- ISO 日期
);

CREATE TABLE IF NOT EXISTS records (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,            -- 关联 users.user_id
    month       TEXT NOT NULL,            -- "YYYY-MM"（由 saved_at 推导）
    efficiency  TEXT,                     -- 清洁效率
    consumables TEXT,                     -- 耗材
    comparison  TEXT,                     -- 对比
    saved_at    TEXT NOT NULL             -- 真实保存时间戳
);
CREATE INDEX IF NOT EXISTS idx_records_user_month ON records(user_id, month);
```

约定：
- 同一 `(user_id, month)` 可有多条；查询时取 `saved_at` 最新一条。
- `records` 不存「特征/画像」，`fetch_external_data` 输出时从 `users.profile` join 得到，保证画像唯一、可随注册更新。

**预置数据**：建库时若 `users` 为空，播种 12 个用户（`1001`~`1012`），用户名 = user_id，统一密码 `123456`，画像沿用原 CSV 风格；每个用户播种近 12 个真实月份（以运行当天为终点向前推 12 个月）的记录，内容为合成数据。播种逻辑幂等（表非空则跳过）。

## 6. 模块设计

### 6.1 `utils/storage.py`（新增，共享持久层）

对外函数：

- `init_db()` — 建表 + 按需播种（幂等）。
- `create_user(username, password, profile) -> user_id` — 注册，自动生成不重复的 `user_id`，返回之。
- `verify_user(username, password) -> user_id | None` — 校验密码，成功返回 user_id，失败返回 None。
- `get_user(user_id) -> dict | None` — 取用户信息（含 profile）。
- `save_record(user_id, efficiency, consumables, comparison, month=None)` — month 缺省取当前月；写入 records。
- `fetch_record(user_id, month) -> dict | None` — 取该用户该月最新一条记录，合并 `users.profile` 作为「特征」字段返回。
- 内部：`_hash_password` / `_verify_password`（`hashlib.pbkdf2_hmac` + 随机盐）。

所有函数用 `sqlite3` 标准库，连接用 `sqlite3.Row` + 上下文管理；写操作异常向上抛，由调用方（工具）捕获并返回友好提示。

### 6.2 `agent/tools/agent_tools.py`（改造）

- 删除：`user_ids`、`month_arr`、`external_data` 字典、`generate_external_data()`、CSV 读取、`random` 导入。
- 保留：`rag_summarize`、`fill_context_for_report` 不变。
- 修改：
  - `get_user_id(runtime: Annotated[ToolRuntime, InjectedToolArg]) -> str`：返回 `runtime.context.get('user_id', '')`。
  - `get_current_month() -> str`：返回 `datetime.now().strftime('%Y-%m')`。
  - `fetch_external_data(user_id: str, month: str) -> str`：改从 `storage.fetch_record` 读取，无结果返回空串 `""`；有结果拼接 `特征/效率/耗材/对比` 为字符串（格式与原输出一致）。
- 新增：
  - `save_record(efficiency: str, consumables: str, comparison: str, month: str = "", runtime: Annotated[ToolRuntime, InjectedToolArg]) -> str`：`user_id` 取 `runtime.context['user_id']`（为空则返回「未登录」提示）；`month` 为空则用当前月；调用 `storage.save_record`，返回成功/失败提示文本。

### 6.3 `agent/react_agent.py`（改造）

- `__init__` 的 `tools=[...]` 增加 `save_record`（共 7 个）。
- `execute_stream(self, messages, user_id: str = "")`：`context={'report': False, 'user_id': user_id}`。

### 6.4 `app.py`（改造）

- 启动时 `storage.init_db()`。
- 侧边栏：
  - 未登录：显示登录表单（用户名 + 密码 + 登录按钮），可切换「注册」（用户名 + 密码 + 画像 profile + 注册按钮）。注册成功即自动登录。
  - 已登录：显示「当前用户：{user_id} · {profile}」+「退出登录」。
  - 登录态存 `st.session_state.user_id` / `st.session_state.logged_in`。
- 聊天提交时：`execute_stream(history, user_id=st.session_state.get('user_id', ''))`。

### 6.5 `agent/mcp_server.py`（新增，MCP 服务端）

- `mcp = FastMCP("robot-vacuum-tools")`。
- 暴露 4 个工具（复用 `weather_tool.fetch_weather_by_city` 与 `utils/storage`）：
  - `get_weather(city: str) -> str`
  - `get_current_month() -> str`
  - `fetch_external_data(user_id: str, month: str) -> str`
  - `save_record(user_id: str, efficiency: str, consumables: str, comparison: str, month: str = "") -> str`（MCP 场景无会话，显式传 user_id）
- 入口：`if __name__ == "__main__": mcp.run()`（stdio 传输）。

### 6.6 `.mcp.json`（新增，供 Claude Code 接入）

放在项目根目录，`command`/`args` 相对项目根解析（`cwd` 可省略，默认即项目根）：

```json
{
  "mcpServers": {
    "robot-vacuum-tools": {
      "command": "python",
      "args": ["agent/mcp_server.py"]
    }
  }
}
```

### 6.7 提示词改造

`prompt/main_prompt.txt`：
1. 在「可使用工具及能力边界」新增 `save_record` 的说明：入参 `efficiency/consumables/comparison/month`（month 可空），用途 = 把用户口述的使用数据保存入库。
2. 新增一条**行为规则**（放在「输出规则」或新增「保存提醒规则」小节）：当用户在对话中主动提供/分享了使用数据（覆盖率、耗材、清洁情况等），在回答末尾主动询问「是否需要我帮你保存这份记录？」，经用户明确同意后调用 `save_record`；未获同意或用户未提及使用数据时不得擅自保存。
3. 新增一条**登录引导规则**：当用户请求查询使用记录/生成报告/保存记录，但 `get_user_id` 返回空串（未登录）时，先提示用户「请先在左侧登录或注册」，不要继续调用 `fetch_external_data` 或 `save_record`。

`prompt/report_prompt.txt`：报告场景不变（`save_record` 不属于报告生成流程，无需加入）。

### 6.8 配置与依赖

- `config/agent.yml` 新增 `db_path: data/app.db`。
- `requirements.txt` 新增 `mcp`（`sqlite3` 为 stdlib，无需声明）。

## 7. 错误处理

- 登录：用户名不存在 / 密码错误 → 侧边栏提示，不抛异常。
- 注册：用户名重复 → 提示换一个。
- `save_record`：未登录（context 无 user_id）→ 返回「未登录」提示；DB 写失败 → 捕获并返回失败提示（不抛给模型）。
- **未登录聊天**：RAG 问答不强制登录；但报告/保存功能依赖 user_id，未登录时 `get_user_id` 返回空串，提示词需引导 Agent 请用户先登录（在 6.7 中一并加入）。
- `fetch_external_data`：无记录 → 返回空串（沿用现有语义）。
- MCP server 工具：入参缺失/非法 → 返回可读错误字符串。

## 8. 验证方式

按阶段逐步验证，每步可独立演示：

| 阶段 | 验证点 |
|------|--------|
| 1 数据层 | 启动后 `data/app.db` 生成；`storage.fetch_record('1001', <当前月>)` 有结果 |
| 2 认证 | 注册新用户 → 登录成功 → 侧边栏显示当前用户；用 1001/123456 登录预置用户 |
| 3 保存 | 登录后说「我这个月覆盖率 88%、主刷剩 30 天」，Agent 提醒保存，同意后写库，再查能取到 |
| 4 MCP 服务端 | Claude Code 经 `.mcp.json` 调 `get_weather` / `fetch_external_data` 返回正常 |

## 9. 实施顺序

1. 数据层：`utils/storage.py` + `config/agent.yml` 的 `db_path` + 建库/播种。
2. 认证：`app.py` 登录/注册 UI + `storage` 认证函数。
3. 工具改造 + `save_record` + 提示词「提醒保存」+ `react_agent.py` 传 user_id。
4. MCP 服务端：`agent/mcp_server.py` + `.mcp.json`。
5. 依赖：`requirements.txt` 补 `mcp`。
6. 端到端验证。

## 10. 风险与说明

- **`ToolRuntime` 注入**：已确认 `langgraph.prebuilt.ToolRuntime` 提供 `context`，与现有 `report` context 同一机制；实现时以最小示例先验证一次。
- **密码存储**：demo 用 `pbkdf2_hmac`，够用且零依赖；如日后要生产化可换 `bcrypt`。
- **预置数据为合成数据**：仅作演示，画像/记录内容为程序生成。
- **旧 `data/external/records.csv`**：迁移后不再读取，文件保留不删（如需删除另行确认）。
