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


def test_get_current_month_returns_current_month():
    from datetime import datetime
    assert at.get_current_month.func() == datetime.now().strftime("%Y-%m")


def test_fetch_external_data_returns_formatted(db):
    uid = storage.create_user("user1", "pw", "画像")
    storage.save_record(uid, "覆盖率:88%", "主刷:30天", "优于60%", "2026-10")
    out = at.fetch_external_data.func(uid, "2026-10")
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
