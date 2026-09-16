"""pytest 公共 fixtures：把 DATA_DIR 指向临时目录，避免污染真实运行数据。"""
import sys
from pathlib import Path

import pytest

# 让 tests 能 import app.*
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def temp_data_dir(tmp_path, monkeypatch):
    """把 app.config.DATA_DIR 及其下游模块重定向到临时目录。"""
    real_data = tmp_path / "data"
    real_data.mkdir()
    monkeypatch.setenv("DATA_DIR", str(real_data))

    # reload config 让 DATA_DIR 生效
    import importlib
    import app.config as cfg
    importlib.reload(cfg)
    monkeypatch.setattr("app.config.DATA_DIR", real_data, raising=False)

    # session_store 用的是模块级 SESSION_DIR，reload 它
    import app.session_store as ss
    importlib.reload(ss)
    monkeypatch.setattr(ss, "SESSION_DIR", real_data / "sessions", raising=False)

    import app.agent.fault_state as fs
    importlib.reload(fs)
    monkeypatch.setattr(fs, "_STATE_FILE", real_data / "fault_state.json", raising=False)

    yield real_data
