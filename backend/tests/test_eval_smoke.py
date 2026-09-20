"""RAG 评测集 smoke：验证评测集格式合法、期望命中文档都在知识库里。

不跑检索（加载 bge 模型太慢），只做静态校验：
- 每条必须有 q 和 expect
- expect 文件名必须能在 knowledge_base 里找到（大小写不敏感）
- variant_type 必须在允许集合内
"""
from pathlib import Path

from app.rag.evaluate import EVAL_SET

KB_DIR = Path(__file__).resolve().parents[1] / "knowledge_base"


def _kb_sources() -> set[str]:
    return {p.name.lower() for p in KB_DIR.rglob("*.md")}


def test_eval_set_nonempty():
    assert len(EVAL_SET) >= 60, f"评测集被误删？当前 {len(EVAL_SET)} 条"


def test_eval_set_fields():
    allowed = {"standard", "colloquial", "terse", "noisy", "shorthand"}
    for i, item in enumerate(EVAL_SET):
        assert "q" in item and item["q"].strip(), f"第 {i} 条缺 q"
        assert "expect" in item and item["expect"].strip(), f"第 {i} 条缺 expect: {item.get('q','')[:30]}"
        vt = item.get("variant_type", "standard")
        assert vt in allowed, f"第 {i} 条 variant_type={vt!r} 非法: {item['q'][:30]}"


def test_eval_expect_doc_exists():
    """expect 的文档必须真的在知识库里（防标注打错文件名）。"""
    sources = _kb_sources()
    missing = []
    for item in EVAL_SET:
        if item["expect"].lower() not in sources:
            missing.append(f"{item['expect']}  (q={item['q'][:30]})")
    assert not missing, f"评测集标注了不存在的文档：\n" + "\n".join(missing)
