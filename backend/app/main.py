"""网络运维智能助手（NetOps AI Assistant）· FastAPI 入口。

路由按功能拆到 app/routers/，本文件只负责：
- 创建 FastAPI app
- 注册中间件
- include 各 router
- 挂载前端静态文件
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.routers import (
    alert,
    chat,
    docker,
    events,
    kb,
    report,
    sessions,
    sim,
    system,
    topology,
)

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

app = FastAPI(
    title="NetOps AI Assistant",
    description="面向网络运维场景的 AI 全栈助手",
    version="0.7.1",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (system, kb, topology, docker, sessions, sim, chat, report, alert, events):
    app.include_router(r.router)


@app.get("/")
async def index():
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")
