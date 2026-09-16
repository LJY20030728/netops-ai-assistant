"""知识库入库：文档解析 → 文本切分 → 向量化 → 写入向量库。

支持 .md / .txt / .pdf。运行方式（在 backend 目录下）：
    python -m app.rag.ingest
"""
import hashlib
import re
from pathlib import Path

import pymupdf

from app.config import KB_DIR, settings
from app.rag.store import add_chunks

SUPPORTED = {".md", ".txt", ".pdf"}

# 案例文件头部对齐字段：用于 L2 案例层告警类型标注（与 alert_map.json 的 alarm_type 对齐）
_ALARM_TYPE_RE = re.compile(r"【告警类型】\s*([A-Z_][A-Z0-9_]*)")


def read_file(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        with pymupdf.open(path) as doc:
            return "\n".join(p.get_text("text", sort=True) for p in doc)
    return path.read_text(encoding="utf-8")


def _layer_of(kb_dir: Path, path: Path) -> str:
    """按知识库子目录判定层：cases/ → case，其余 → manual。"""
    rel = path.relative_to(kb_dir)
    if rel.parts and rel.parts[0] == "cases":
        return "case"
    return "manual"


def _alarm_type_of(text: str) -> str:
    m = _ALARM_TYPE_RE.search(text or "")
    return m.group(1) if m else ""


def chunk_text(
    text: str, size: int = settings.chunk_size, overlap: int = settings.chunk_overlap
) -> list[str]:
    """按段落感知切分：优先在换行处断开，保留重叠避免上下文断裂。"""
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    chunks: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        end = min(i + size, n)
        if end < n:
            nl = text.rfind("\n", i + int(size * 0.5), end)
            if nl != -1:
                end = nl
        chunk = text[i:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:  # 已到达文本末尾，避免末尾重叠导致 +1 步进产生碎片
            break
        i = max(end - overlap, i + 1)
    return chunks


def ingest_dir(kb_dir: Path = KB_DIR) -> dict:
    chunks: list[dict] = []
    files: list[str] = []
    for path in sorted(kb_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED:
            continue
        text = read_file(path)
        layer = _layer_of(kb_dir, path)
        alarm_type = _alarm_type_of(text) if layer == "case" else ""
        for j, c in enumerate(chunk_text(text)):
            cid = hashlib.md5(f"{path.name}:{j}".encode()).hexdigest()
            meta: dict = {"source": path.name, "chunk": j, "layer": layer}
            if alarm_type:
                meta["alarm_type"] = alarm_type
            chunks.append({"id": cid, "text": c, "metadata": meta})
        files.append(path.name)
    added = add_chunks(chunks) if chunks else 0
    return {"files": files, "chunks": added}


if __name__ == "__main__":
    result = ingest_dir()
    print(f"入库完成：文件 {len(result['files'])} 个，chunk {result['chunks']} 个")
    for f in result["files"]:
        print("  -", f)
