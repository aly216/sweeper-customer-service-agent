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
    uid = storage.create_user("carol", "secret-pw-123", "画像")
    user = storage.get_user(uid)
    assert "secret-pw-123" not in user["password_hash"]
    assert ":" in user["password_hash"]  # salt:hash 结构


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


def test_default_db_path_reads_agent_config(monkeypatch):
    import importlib
    from utils.path_tool import get_abs_path
    import utils.config_handler as ch
    import utils.storage as storage
    monkeypatch.setattr(ch, "agent_conf", {"db_path": "data/custom.db"})
    importlib.reload(storage)
    assert storage.DB_PATH == get_abs_path("data/custom.db")


def test_init_db_enables_wal(tmp_path):
    import sqlite3
    storage.configure(str(tmp_path / "wal.db"))
    storage.init_db()
    conn = sqlite3.connect(str(tmp_path / "wal.db"))
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    assert mode.lower() == "wal"


def test_init_db_survives_concurrent_duplicate(tmp_path, monkeypatch):
    import sqlite3
    storage.configure(str(tmp_path / "seed.db"))

    def _duplicate(*args, **kwargs):
        raise sqlite3.IntegrityError("UNIQUE constraint failed: users.username")

    monkeypatch.setattr(storage, "create_user", _duplicate)
    storage.init_db()  # 并发播种者已抢先插入种子用户 → 不应抛异常
