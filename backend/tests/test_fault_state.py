"""fault_state 故障注入状态测试。"""
from app.agent import fault_state as fs


def test_mark_inject_and_snapshot(temp_data_dir):
    fs.mark_inject("frr1", "ospf_cost", "eth0")
    snap = fs.snapshot()
    assert "frr1" in snap
    assert snap["frr1"]["ospf_cost"] == "eth0"


def test_recover_removes_entry(temp_data_dir):
    fs.mark_inject("frr2", "link_down", "eth0")
    fs.clear_recover("frr2", "link_down")
    snap = fs.snapshot()
    assert "frr2" not in snap or "link_down" not in snap.get("frr2", {})


def test_clear_all(temp_data_dir):
    fs.mark_inject("frr1", "ospf_cost", "eth0")
    fs.mark_inject("frr3", "bgp_flap", "eth0")
    fs.clear_all()
    snap = fs.snapshot()
    # clear_all 后只剩 updated 字段或空
    assert all(k not in ("frr1", "frr2", "frr3") for k in snap.keys())


def test_empty_snapshot_is_dict(temp_data_dir):
    snap = fs.snapshot()
    assert isinstance(snap, dict)
