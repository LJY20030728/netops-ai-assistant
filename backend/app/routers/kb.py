"""知识库路由：统计与重新入库。"""
import asyncio
import json

from fastapi import APIRouter, Depends

from app.config import KB_DIR, settings
from app.rag import ingest as kb_ingest
from app.rag import store as kb_store
from app.security import audit
from app.security.auth import require_role

router = APIRouter(prefix="/api/kb", tags=["kb"])


@router.get("/stats")
async def kb_stats(role: str = Depends(require_role("viewer"))):
    return {
        "chunks": kb_store.count(),
        "kb_dir": str(KB_DIR),
        "embedding_model": settings.zhipu_embedding_model,
        "rerank_model": settings.rerank_model,
    }


@router.post("/ingest")
async def kb_ingest_endpoint(role: str = Depends(require_role("admin"))):
    result = await asyncio.to_thread(kb_ingest.ingest_dir)
    result["total_chunks"] = kb_store.count()
    audit.log("ingest", actor=role, action="kb.ingest", detail=json.dumps(result, ensure_ascii=False))
    return result
