"""故障注入 dry-run gate 单测：不连真实 FRR，只验证安全门逻辑。

- 没 dry_run 直接 inject 必须被拦
- dry_run 后 inject 放行
- 60 秒窗口外重新拦截
"""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.agent import fault_state
from app.agent.devices import DeviceError
from app.agent.tools import _frr_fault_inject


@pytest.fixture(autouse=True)
def _clean_gate(tmp_path, monkeypatch):
    """每个测试前后清掉 dry_run 记录。"""
    state_file = tmp_path / "fault_state.json"
    monkeypatch.setattr(fault_state, "_STATE_FILE", state_file, raising=False)
    yield


def _fake_device(name="frr1"):
    from app.agent.devices import Device
    return Device(name=name, host="127.0.0.1", port=22, device_type="frr", username="root", password="x", role="tester")


def test_inject_without_dry_run_rejected():
    with patch("app.agent.tools._require_device", return_value=_fake_device()), \
         patch("app.agent.tools.FrrLab"):
        with pytest.raises(DeviceError, match="dry_run"):
            asyncio.run(_frr_fault_inject({"device": "frr1", "action": "inject", "fault": "ospf_cost", "iface": "eth0"}))


def test_dry_run_then_inject_passes():
    fake_lab = AsyncMock()
    fake_lab.inject.return_value = "INJECTED OK"
    fake_lab.dry_run = lambda fault, iface: "[DRY-RUN] ok"
    with patch("app.agent.tools._require_device", return_value=_fake_device()), \
         patch("app.agent.tools.FrrLab", return_value=fake_lab):
        # 先 dry_run
        dry_out = asyncio.run(_frr_fault_inject({"device": "frr1", "action": "dry_run", "fault": "ospf_cost", "iface": "eth0"}))
        assert "[DRY-RUN]" in dry_out
        # 再 inject 应通过
        inj_out = asyncio.run(_frr_fault_inject({"device": "frr1", "action": "inject", "fault": "ospf_cost", "iface": "eth0"}))
        assert "INJECTED OK" in inj_out
        fake_lab.inject.assert_awaited_once()


def test_dry_run_expires_after_window():
    """手动把 dry_run 时间戳改成 120 秒前，应重新拦截。"""
    fault_state.mark_dry_run("frr1", "ospf_cost", "eth0")
    # 手动改老时间
    state = fault_state._load()
    state["dry_runs"]["frr1:ospf_cost:eth0"] -= 120
    fault_state._save(state)

    with patch("app.agent.tools._require_device", return_value=_fake_device()), \
         patch("app.agent.tools.FrrLab"):
        with pytest.raises(DeviceError, match="dry_run"):
            asyncio.run(_frr_fault_inject({"device": "frr1", "action": "inject", "fault": "ospf_cost", "iface": "eth0"}))
