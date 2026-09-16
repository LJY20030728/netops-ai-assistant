"""排障报告导出路由。"""
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.config import settings
from app import session_store
from app import report as report_svc
from app.rag import store as kb_store
from app.security import audit
from app.security.auth import require_role

router = APIRouter(prefix="/api/report", tags=["report"])


@router.get("/{session_id}")
async def report_get(session_id: str, role: str = Depends(require_role("viewer"))):
    try:
        msgs = session_store.load(session_id)
    except ValueError:
        return {"ok": False, "message": "非法 session_id"}
    if not msgs:
        return {"ok": False, "message": "会话为空，无法生成报告"}
    meta = {
        "会话 ID": session_id,
        "消息数": len(msgs),
        "服务版本": "0.7.1",
        "模型": settings.zhipu_model,
        "知识库 Chunk": kb_store.count(),
        "设备模式": settings.device_mode,
    }
    path = report_svc.build_html_report(session_id, msgs, meta)
    audit.log("report", actor=role, action="report.export", detail=session_id)
    return {"ok": True, "session_id": session_id, "file": str(path),
            "report_url": f"/api/report/{session_id}/file"}


@router.get("/{session_id}/file")
async def report_file(session_id: str, role: str = Depends(require_role("viewer"))):
    p = report_svc.REPORT_DIR / f"{session_id}.html"
    if not p.exists():
        return {"ok": False, "message": "报告不存在，请先导出"}
    return FileResponse(p, media_type="text/html", filename=f"netops-report-{session_id}.html")
