# 登录鉴权 + 数据持久化 + 工具改造 + MCP 服务端 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为「智扫通机器人智能客服」加入注册登录、SQLite 持久化、真实会话工具、`save_record` 保存工具，并把无会话工具包装成 MCP server。

**Architecture:** 新增 `utils/storage.py` 作为唯一持久层（SQLite，`users` + `records` 两表）；工具层改造为读登录态/真实时间/写库；`app.py` 加侧边栏登录注册；`agent/mcp_server.py` 复用 storage 与天气工具暴露 MCP 工具。`get_user_id` 通过 `ToolRuntime.context` 读取会话用户（与现有 `report` context 同一机制）。

**Tech Stack:** Python 3.13、LangChain 1.4 / langchain-core 1.6.3、Streamlit、SQLite（`sqlite3` 标准库）、FastMCP（`mcp` SDK v1.26.0）、pytest。

**Spec:** [docs/superpowers/specs/2026-10-09-agent-mcp-auth-design.md](../specs/2026-10-09-agent-mcp-auth-design.md)

## Global Constraints

- Python 3.13；依赖 `mcp`（已装 v1.26.0）、`sqlite3`（stdlib）；新增 `pytest` 用于测试。
- 密码用 `hashlib.pbkdf2_hmac` 加盐哈希，禁止存明文。
- `records.month` 与 `get_current_month` 返回值格式严格为 `YYYY-MM`。
- 未登录时 `get_user_id` 返回空串 `""`；`save_record` 未登录返回提示、不写库。
- 同一 `(user_id, month)` 多条记录时取 `saved_at` 最新一条。
- 预置 12 个用户 `1001`~`1012`，用户名=user_id，密码统一 `123456`，各带近 12 个月记录；新注册用户 user_id 自动递增。
- 工作须在特性分支上进行（仓库当前在 `main`），每个 Task 结束提交一次。

## Review Focus

以下输入/条件最可能让使用者在实际使用时踩坑，逐一配测试：

1. **同月多条记录**：同一用户同月保存多次 → 查询返回最新一条，不返回旧数据。
2. **未登录调用保存/查询**：context 无 `user_id` → 返回提示或空串，不抛异常、不写库。
3. **用户名重复注册**：重复用户名 → 明确报错，不静默覆盖既有用户。
4. **密码校验**：错误密码返回 `None`（不泄露 user_id）；哈希可重复校验、不含明文。
5. **月份边界/格式**：`get_current_month` 与 `records.month` 均为 `YYYY-MM`，跨月（月末/年初）计算正确。

---

## 文件结构

- 新增 `utils/storage.py`：SQLite 持久层（建表、播种、用户 CRUD、记录读写、格式化）。
- 新增 `tests/test_storage.py`：storage 单元测试。
- 新增 `tests/test_tools.py`：工具层单元测试。
- 修改 `agent/tools/agent_tools.py`：`get_user_id`/`get_current_month`/`fetch_external_data` 改造 + 新增 `save_record`，删除随机与 CSV 读取。
- 修改 `agent/react_agent.py`：`execute_stream` 传 `user_id`，tools 列表加 `save_record`。
- 修改 `config/agent.yml`：加 `db_path: data/app.db`。
- 修改 `app.py`：侧边栏登录/注册/退出。
- 修改 `prompt/main_prompt.txt`：新增 `save_record` 说明 + 提醒保存 + 登录引导规则。
- 新增 `agent/mcp_server.py`：FastMCP 服务端。
- 新增 `.mcp.json`：Claude Code 接入配置。
- 修改 `requirements.txt`：加 `pytest`、`mcp`。

---

### Task 1: 持久层 `utils/storage.py`（TDD）

**Files:**
- Create: `utils/storage.py`
- Test: `tests/test_storage.py`
- Modify: `requirements.txt`（加 `pytest`）、`config/agent.yml`（加 `db_path: data/app.db`）

**Interfaces:**
- Consumes: `utils.path_tool.get_abs_path`、`utils.logger_handler.logger`
- Produces:
  - `configure(db_path: str) -> None`
  - `init_db(db_path: str | None = None) -> None`
  - `create_user(username: str, password: str, profile: str, user_id: str | None = None) -> str`
  - `verify_user(username: str, password: str) -> str | None`
  - `get_user(user_id: str) -> dict | None`
  - `save_record(user_id: str, efficiency: str, consumables: str, comparison: str, month: str | None = None) -> None`
  - `fetch_record(user_id: str, month: str) -> dict | None`（返回含 `特征/效率/耗材/对比` 的 dict）
  - `format_record(record: dict | None) -> str`

- [ ] **Step 1: 写失败测试**

`tests/test_storage.py`：

```python
import re
import pytest
import utils.storage as storage


@pytest.fixture()
def db(tmp_path):
    storage.configure(str(tmp_path / "test.db"))
    storage.init_db()
    return storage


def test_create_user_and_verify_password(db):
    uid = storage.create_user("alice", "secret", "65㎡公寓 | 单身 | 木地板")
    assert uid is not None
    assert storage.verify_user("alice", "secret") == uid
    assert storage.verify_user("alice", "wrong") is None


def test_create_duplicate_username_raises(db):
    storage.create_user("bob", "pw", "画像")
    with pytest.raises(ValueError):
        storage.create_user("bob", "pw2", "另一个画像")


def test_password_not_stored_in_plaintext(db):
    storage.create_user("carol", "pw", "画像")
    user = storage.get_user(storage.verify_user("carol", "pw"))
    assert "pw" not in user["password_hash"] if "password_hash" in user else True


def test_save_and_fetch_record(db):
    uid = storage.create_user("dave", "pw", "画像")
    storage.save_record(uid, "覆盖率:88%", "主刷:剩余30天", "优于60%", "2026-10")
    rec = storage.fetch_record(uid, "2026-10")
    assert rec == {"特征": "画像", "效率": "覆盖率:88%", "耗材": "主刷:剩余30天", "对比": "优于60%"}


def test_fetch_record_returns_latest_for_month(db):
    uid = storage.create_user("eve", "pw", "画像")
    storage.save_record(uid, "旧", "旧", "旧", "2026-10")
    storage.save_record(uid, "新", "新", "新", "2026-10")
    rec = storage.fetch_record(uid, "2026-10")
    assert rec["效率"] == "新"


def test_fetch_missing_returns_none(db):
    uid = storage.create_user("frank", "pw", "画像")
    assert storage.fetch_record(uid, "2099-01") is None


def test_save_record_defaults_to_current_month(db):
    uid = storage.create_user("grace", "pw", "画像")
    storage.save_record(uid, "效率", "耗材", "对比")
    from datetime import datetime
    month = datetime.now().strftime("%Y-%m")
    assert storage.fetch_record(uid, month)["效率"] == "效率"


def test_format_record_empty_and_full():
    assert storage.format_record(None) == ""
    out = storage.format_record({"特征": "画像", "效率": "88", "耗材": "30", "对比": "60"})
    assert "特征:画像" in out and "效率:88" in out and "耗材:30" in out and "对比:60" in out


def test_seed_creates_12_users_with_records(tmp_path):
    storage.configure(str(tmp_path / "seed.db"))
    storage.init_db()
    for i in range(1, 13):
        uid = f"{1000 + i}"
        assert storage.verify_user(uid, "123456") == uid
    from datetime import datetime
    month = datetime.now().strftime("%Y-%m")
    assert storage.fetch_record("1001", month) is not None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_storage.py -v`
Expected: 全部 FAIL（`utils.storage` 模块不存在）。

- [ ] **Step 3: 实现 `utils/storage.py`**

```python
"""SQLite 持久层：用户与使用记录。"""
import hashlib
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from utils.path_tool import get_abs_path
from utils.logger_handler import logger

DB_PATH = get_abs_path('data/app.db')
_PBKDF2_ITERATIONS = 100_000

_SEED_PROFILES = [
    "65㎡公寓 | 单身 | 木地板",
    "70㎡公寓 | 情侣 | 瓷砖",
    "90㎡ | 1狗 | 短毛地毯",
    "85㎡ | 2猫 | 混合地面",
    "120㎡ | 老人 | 防滑砖",
    "150㎡别墅 | 儿童 | 多层",
    "55㎡一居 | 独居 | 复合地板",
    "100㎡三居 | 三口之家 | 大理石",
    "80㎡两居 | 养宠 | 仿实木",
    "130㎡四居 | 三代同堂 | 通体砖",
    "60㎡ | 双人合租 | 强化地板",
    "110㎡ | 三口之家 | 地暖地砖",
]


def configure(db_path: str) -> None:
    global DB_PATH
    DB_PATH = db_path


@contextmanager
def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    if salt is None:
        salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, _PBKDF2_ITERATIONS)
    return digest.hex(), salt.hex()


def _verify_password(password: str, salt_hex: str, expected_hex: str) -> bool:
    digest, _ = _hash_password(password, bytes.fromhex(salt_hex))
    return secrets.compare_digest(digest, expected_hex)


def _next_user_id(conn) -> str:
    row = conn.execute("SELECT MAX(CAST(user_id AS INTEGER)) AS m FROM users").fetchone()
    return str((row['m'] or 1000) + 1)


def _month_offset(months_back: int) -> str:
    d = datetime.now()
    total = d.year * 12 + (d.month - 1) - months_back
    y, m = divmod(total, 12)
    return f"{y}-{m + 1:02d}"


def init_db(db_path: str | None = None) -> None:
    if db_path is not None:
        configure(db_path)
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with _db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       TEXT NOT NULL UNIQUE,
            username      TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            profile       TEXT,
            registered_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS records (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     TEXT NOT NULL,
            month       TEXT NOT NULL,
            efficiency  TEXT,
            consumables TEXT,
            comparison  TEXT,
            saved_at    TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_records_user_month ON records(user_id, month);
        """)
    _seed_if_empty()


def _seed_if_empty() -> None:
    with _db() as conn:
        if conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()['c'] > 0:
            return
    for i, profile in enumerate(_SEED_PROFILES, start=1):
        user_id = f"{1000 + i}"
        create_user(user_id, "123456", profile, user_id=user_id)
        for back in range(11, -1, -1):
            month = _month_offset(back)
            coverage = 80 + (i + back) % 10
            efficiency = f"覆盖率:{coverage}%\n日均清扫:{40 + (i + back) % 8}㎡"
            consumables = f"主刷寿命:剩余{20 + (i * 3 + back) % 40}天\nHEPA滤网:剩余{30 + back % 30}%"
            comparison = f"优于{(i + back) % 30 + 50}%同面积用户"
            save_record(user_id, efficiency, consumables, comparison, month)


def create_user(username: str, password: str, profile: str, user_id: str | None = None) -> str:
    digest, salt = _hash_password(password)
    with _db() as conn:
        if conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
            raise ValueError("用户名已存在")
        if user_id is None:
            user_id = _next_user_id(conn)
        conn.execute(
            "INSERT INTO users (user_id, username, password_hash, profile, registered_at) VALUES (?,?,?,?,?)",
            (user_id, username, f"{salt}:{digest}", profile, datetime.now().isoformat()),
        )
    return user_id


def verify_user(username: str, password: str) -> str | None:
    with _db() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if row is None:
        return None
    salt_hex, expected_hex = row['password_hash'].split(':', 1)
    if _verify_password(password, salt_hex, expected_hex):
        return row['user_id']
    return None


def get_user(user_id: str) -> dict | None:
    with _db() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        return None
    return {
        "user_id": row['user_id'],
        "username": row['username'],
        "profile": row['profile'],
        "password_hash": row['password_hash'],
        "registered_at": row['registered_at'],
    }


def save_record(user_id: str, efficiency: str, consumables: str, comparison: str,
                month: str | None = None) -> None:
    if month is None:
        month = datetime.now().strftime('%Y-%m')
    with _db() as conn:
        conn.execute(
            "INSERT INTO records (user_id, month, efficiency, consumables, comparison, saved_at) "
            "VALUES (?,?,?,?,?,?)",
            (user_id, month, efficiency, consumables, comparison, datetime.now().isoformat()),
        )


def fetch_record(user_id: str, month: str) -> dict | None:
    with _db() as conn:
        row = conn.execute(
            "SELECT r.efficiency, r.consumables, r.comparison, u.profile "
            "FROM records r JOIN users u ON u.user_id = r.user_id "
            "WHERE r.user_id = ? AND r.month = ? ORDER BY r.saved_at DESC LIMIT 1",
            (user_id, month),
        ).fetchone()
    if row is None:
        return None
    return {"特征": row['profile'], "效率": row['efficiency'], "耗材": row['consumables'], "对比": row['comparison']}


def format_record(record: dict | None) -> str:
    if record is None:
        return ""
    return "\n".join([f"特征:{record['特征']}", f"效率:{record['效率']}",
                      f"耗材:{record['耗材']}", f"对比:{record['对比']}"])
```

- [ ] **Step 4: 改配置与依赖**

`config/agent.yml` 追加一行：

```yaml
db_path: data/app.db
```

`requirements.txt` 末尾追加：

```
pytest
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_storage.py -v`
Expected: 全部 PASS。

- [ ] **Step 6: Commit**

```bash
git add utils/storage.py tests/test_storage.py config/agent.yml requirements.txt
git commit -m "feat(storage): SQLite 持久层（用户+记录，含播种与单元测试）"
```

---

### Task 2: 工具改造 `agent/tools/agent_tools.py`

**Files:**
- Modify: `agent/tools/agent_tools.py`
- Test: `tests/test_tools.py`

**Interfaces:**
- Consumes: Task 1 的 `storage.save_record` / `storage.fetch_record` / `storage.format_record`；`langgraph.prebuilt.ToolRuntime`；`langchain_core.tools.InjectedToolArg`
- Produces: 工具函数 `get_user_id` / `get_current_month` / `fetch_external_data` / `save_record`（保持 `@tool` 装饰，供 `react_agent.py` 使用）

- [ ] **Step 1: 写失败测试**

`tests/test_tools.py`：

```python
import re
import pytest
import utils.storage as storage
import agent.tools.agent_tools as at


class RuntimeStub:
    def __init__(self, context):
        self.context = context


@pytest.fixture()
def db(tmp_path):
    storage.configure(str(tmp_path / "test.db"))
    storage.init_db()
    return storage


def test_get_user_id_reads_context(db):
    assert at.get_user_id.func(RuntimeStub({"user_id": "1001"})) == "1001"


def test_get_user_id_empty_when_not_logged_in(db):
    assert at.get_user_id.func(RuntimeStub({})) == ""


def test_get_current_month_format():
    assert re.fullmatch(r"\d{4}-\d{2}", at.get_current_month.func())


def test_fetch_external_data_returns_formatted(db):
    uid = storage.create_user("user1", "pw", "画像")
    storage.save_record(uid, "覆盖率:88%", "主刷:30天", "优于60%", "2026-10")
    out = at.fetch_external_data.func("user1", "2026-10")
    assert "特征:画像" in out and "覆盖率:88%" in out


def test_fetch_external_data_empty_when_missing(db):
    assert at.fetch_external_data.func("nobody", "2099-01") == ""


def test_save_record_requires_login(db):
    assert "未登录" in at.save_record.func("88", "30", "60", "", RuntimeStub({}))


def test_save_record_writes_and_confirms(db):
    uid = storage.create_user("user2", "pw", "画像")
    msg = at.save_record.func("覆盖率:88%", "主刷:30天", "优于60%", "2026-10", RuntimeStub({"user_id": uid}))
    assert "已保存" in msg
    assert storage.fetch_record(uid, "2026-10")["效率"] == "覆盖率:88%"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_tools.py -v`
Expected: 全部 FAIL（函数/模块行为未改）。

- [ ] **Step 3: 改造 `agent/tools/agent_tools.py`**

将文件整体替换为：

```python
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_tools.py -v`
Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add agent/tools/agent_tools.py tests/test_tools.py
git commit -m "feat(tools): 真实会话工具 + save_record，移除随机占位与 CSV 读取"
```

---

### Task 3: Agent 装配传 user_id（`agent/react_agent.py`）

**Files:**
- Modify: `agent/react_agent.py`

**Interfaces:**
- Consumes: Task 2 的工具函数（含 `save_record`）。
- Produces: `ReactAgent.execute_stream(self, messages: list, user_id: str = "")`（`context={'report': False, 'user_id': user_id}`）。

- [ ] **Step 1: 修改 imports**

`agent/react_agent.py` 顶部 import 改为：

```python
from agent.tools.agent_tools import (rag_summarize, get_weather, get_user_id,
                                     get_current_month, fetch_external_data, fill_context_for_report, save_record)
```

- [ ] **Step 2: tools 列表加 save_record**

`ReactAgent.__init__` 中 `tools=[...]` 追加 `save_record`（共 7 个）。

- [ ] **Step 3: execute_stream 传 user_id**

```python
def execute_stream(self, messages: list, user_id: str = ""):
    input_dict = {'messages': messages}
    for chunk in self.agent.stream(input_dict, stream_mode="values",
                                   context={'report': False, 'user_id': user_id}):
        latest_message = chunk['messages'][-1]
        text = _extract_text(latest_message.content)
        if text:
            yield text.strip() + "\n"
```

- [ ] **Step 4: 冒烟测试**

Run: `python -c "from agent.react_agent import ReactAgent; a = ReactAgent(); print('ok')"`
Expected: 输出 `ok`，无导入/装配错误。

- [ ] **Step 5: Commit**

```bash
git add agent/react_agent.py
git commit -m "feat(agent): execute_stream 传递 user_id 并注册 save_record"
```

---

### Task 4: 登录/注册 UI（`app.py`）

**Files:**
- Modify: `app.py`

**Interfaces:**
- Consumes: Task 1 的 `storage.init_db` / `create_user` / `verify_user` / `get_user`；Task 3 的 `execute_stream(messages, user_id)`。
- Produces: Streamlit 侧边栏登录态（`st.session_state.user_id` / `st.session_state.logged_in`）。

- [ ] **Step 1: 启动时建库并初始化登录态**

`app.py` 顶部 import 改为：

```python
import time
import streamlit as st
from agent.react_agent import ReactAgent
from utils import storage

storage.init_db()
```

`if "agent" not in st.session_state:` 块之前初始化登录态：

```python
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "user_id" not in st.session_state:
    st.session_state["user_id"] = ""
```

- [ ] **Step 2: 加侧边栏登录/注册**

在 `st.divider()` 之后插入：

```python
with st.sidebar:
    st.subheader("账户")
    if st.session_state["logged_in"]:
        user = storage.get_user(st.session_state["user_id"])
        profile = (user or {}).get("profile", "")
        st.write(f"当前用户：{st.session_state['user_id']} · {profile}")
        if st.button("退出登录"):
            st.session_state["logged_in"] = False
            st.session_state["user_id"] = ""
            st.rerun()
    else:
        mode = st.radio("模式", ["登录", "注册"], horizontal=True)
        username = st.text_input("用户名")
        password = st.text_input("密码", type="password")
        if mode == "注册":
            profile = st.text_input("画像（如：65㎡公寓 | 单身 | 木地板）")
            if st.button("注册并登录"):
                if not username or not password:
                    st.warning("用户名和密码不能为空")
                else:
                    try:
                        uid = storage.create_user(username, password, profile)
                        st.session_state["logged_in"] = True
                        st.session_state["user_id"] = uid
                        st.success("注册成功")
                        st.rerun()
                    except ValueError as e:
                        st.warning(str(e))
        else:
            if st.button("登录"):
                uid = storage.verify_user(username, password)
                if uid is None:
                    st.warning("用户名或密码错误")
                else:
                    st.session_state["logged_in"] = True
                    st.session_state["user_id"] = uid
                    st.rerun()
```

- [ ] **Step 3: 聊天提交传 user_id**

将 `res_stream = st.session_state['agent'].execute_stream(history)` 改为：

```python
res_stream = st.session_state['agent'].execute_stream(
    history, user_id=st.session_state.get("user_id", ""))
```

- [ ] **Step 4: 手动验证**

Run: `streamlit run app.py`
验证：① 未登录聊 RAG 问答正常；② 注册新用户 → 自动登录 → 侧边栏显示当前用户；③ 退出登录 → 恢复登录/注册表单；④ 用 `1001 / 123456` 登录预置用户成功。

- [ ] **Step 5: Commit**

```bash
git add app.py
git commit -m "feat(app): 侧边栏注册登录，聊天传递当前 user_id"
```

---

### Task 5: 提示词改造（`prompt/main_prompt.txt`）

**Files:**
- Modify: `prompt/main_prompt.txt`

**Interfaces:**
- Consumes: Task 2 的工具（含 `save_record`）。
- Produces: 系统提示词含 `save_record` 说明 + 提醒保存 + 登录引导规则。

- [ ] **Step 1: 新增 save_record 工具说明**

在 `main_prompt.txt` 的「可使用工具及能力边界」末尾（`fill_context_for_report` 之后）追加：

```text
7. save_record：
   - 核心能力：入参为 efficiency（清洁效率）、consumables（耗材）、comparison（对比）、month（月份，可空）；把用户口述的使用数据保存到该用户对应月份的记录中；
   - 出参：字符串类型的保存结果提示；
   - 使用场景：当用户在对话中提供了自己的使用数据（覆盖率、耗材、清洁情况等）并同意保存时，调用此工具把数据写库；
   - 调用规则：efficiency/consumables/comparison 为纯文本字符串，month 严格遵循"YYYY-MM"格式，可为空（空则保存到当前月）。
```

- [ ] **Step 2: 新增「保存提醒规则」小节**

在「输出规则」小节前插入：

```text
### 保存提醒规则
1. 当用户在对话中主动提供/分享了自己的使用数据（覆盖率、耗材、清洁情况等），在回答末尾主动询问「是否需要我帮你保存这份记录？」；仅当用户明确同意后，才调用 save_record 工具保存；用户未同意或未提及使用数据时，禁止擅自保存。
2. 当用户请求查询使用记录、生成报告或保存记录，但 get_user_id 返回空串（未登录）时，先提示用户「请先在左侧登录或注册」，不要继续调用 fetch_external_data 或 save_record。
```

- [ ] **Step 3: 手动验证**

Run: `streamlit run app.py`
验证：登录 1001 后，输入「我这个月覆盖率 88%，主刷寿命还剩 30 天」，Agent 应主动询问是否保存；回复「保存」后，Agent 调用 `save_record`；再问「查一下我 2026-XX 的使用记录」应能查到刚保存的数据。

- [ ] **Step 4: Commit**

```bash
git add prompt/main_prompt.txt
git commit -m "feat(prompt): 新增 save_record 说明与保存提醒、登录引导规则"
```

---

### Task 6: MCP 服务端（`agent/mcp_server.py` + `.mcp.json`）

**Files:**
- Create: `agent/mcp_server.py`
- Create: `.mcp.json`
- Modify: `requirements.txt`（加 `mcp`）

**Interfaces:**
- Consumes: Task 1 的 `storage`；`agent/tools/weather_tool.fetch_weather_by_city`。
- Produces: FastMCP 应用 `mcp`，暴露 `get_weather` / `get_current_month` / `fetch_external_data` / `save_record`。

- [ ] **Step 1: 实现 `agent/mcp_server.py`**

```python
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
```

- [ ] **Step 2: 新增 `.mcp.json`**

项目根目录：

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

- [ ] **Step 3: 依赖加 mcp**

`requirements.txt` 追加一行：`mcp`。

- [ ] **Step 4: 手动验证**

Run: `python agent/mcp_server.py`（应能启动 stdio server、无报错）。
再用一个最小 MCP 客户端冒烟：`python -c "from agent.mcp_server import mcp; print([t.name for t in mcp._tool_manager.list_tools()])"`（输出应含 `get_weather` / `get_current_month` / `fetch_external_data` / `save_record`）。

- [ ] **Step 5: Commit**

```bash
git add agent/mcp_server.py .mcp.json requirements.txt
git commit -m "feat(mcp): 暴露天气/月份/记录查询/保存为 MCP server"
```

---

## 自检记录

- **Spec 覆盖**：spec §5（数据模型）→ Task 1；§6.2/6.3 → Task 2/3；§6.4 → Task 4；§6.7 → Task 5；§6.5/6.6 → Task 6；§6.8 → Task 1/6 的 requirements/config 改动。§8 验证 → 各 Task 的 Step 4/5 手动验证。
- **占位符扫描**：无 TBD/TODO；所有代码步骤均给出实际代码。
- **类型一致性**：`configure`/`init_db`/`create_user`/`verify_user`/`get_user`/`save_record`/`fetch_record`/`format_record` 签名在 Task 1 定义，Task 2/6 一致引用；`execute_stream(messages, user_id="")` 在 Task 3 定义，Task 4 一致调用。
- **Review Focus**：5 项分别由 `test_fetch_record_returns_latest_for_month`、`test_get_user_id_empty_when_not_logged_in`/`test_save_record_requires_login`、`test_create_duplicate_username_raises`、`test_create_user_and_verify_password`/`test_password_not_stored_in_plaintext`、`test_save_record_defaults_to_current_month`/`test_get_current_month_format` 覆盖。
