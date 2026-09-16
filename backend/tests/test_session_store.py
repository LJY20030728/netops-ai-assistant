"""session_store 会话持久化测试。"""
import json

import pytest

from app import session_store as ss


def test_append_and_load(temp_data_dir):
    ss.append("sess-001", "user", "你好")
    ss.append("sess-001", "assistant", "你好，有什么可以帮你")
    msgs = ss.load("sess-001")
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "你好"
    assert msgs[1]["role"] == "assistant"


def test_load_empty_session_returns_list(temp_data_dir):
    assert ss.load("nonexistent") == []


def test_invalid_session_id_rejected(temp_data_dir):
    with pytest.raises(ValueError):
        ss._path("../etc/passwd")
    with pytest.raises(ValueError):
        ss._path("a/b")
    with pytest.raises(ValueError):
        ss._path("")


def test_list_sessions(temp_data_dir):
    ss.append("s-aaa", "user", "消息1")
    ss.append("s-bbb", "user", "消息2")
    sessions = ss.list_sessions(limit=10)
    ids = {s["session_id"] for s in sessions}
    assert {"s-aaa", "s-bbb"}.issubset(ids)


def test_delete_session_file(temp_data_dir):
    ss.append("s-del", "user", "临时")
    p = ss._path("s-del")
    assert p.exists()
    p.unlink()
    assert not p.exists()
