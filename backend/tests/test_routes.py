"""HTTP 路由冒烟测试：health、auth/me、sessions。"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["service"] == "netops-assistant"
    assert "model" in data
    assert "security" in data


def test_auth_me_returns_role():
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    data = r.json()
    assert "role" in data
    assert "authenticated" in data


def test_sessions_list_returns_ok():
    r = client.get("/api/sessions")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "sessions" in data


def test_index_html_served():
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
