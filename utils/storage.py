"""SQLite 持久层：用户与使用记录。"""
import hashlib
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from utils.path_tool import get_abs_path
from utils.logger_handler import logger
from utils.config_handler import agent_conf

DB_PATH = get_abs_path(agent_conf.get('db_path', 'data/app.db'))
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
    # 多进程（Streamlit + MCP server）共享同一 DB 文件：WAL 允许读写并发，busy_timeout 等待锁释放
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
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
        try:
            create_user(user_id, "123456", profile, user_id=user_id)
        except (ValueError, sqlite3.IntegrityError):
            # 并发播种：另一进程已抢先建好该种子用户，本次播种让路
            logger.warning(f"[seed] 种子用户 {user_id} 已存在，跳过本次播种")
            return
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
            "WHERE r.user_id = ? AND r.month = ? "
            "ORDER BY r.saved_at DESC, r.id DESC LIMIT 1",
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
