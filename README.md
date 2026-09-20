# NetOps AI Assistant · 网络运维智能助手

> 面向网络运维场景的 AI 全栈助手：自研 ReAct Agent + RAG 知识库 + 真实 FRR 实验室故障演练 + 桌面应用。

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110-009688)
![PyWebView](https://img.shields.io/badge/pywebview-5.x-green)
![Tests](https://img.shields.io/badge/tests-46%20passed-brightgreen)
![License](https://img.shields.io/badge/license-MIT-green)

---

## 中文

### 这是什么

NetOps AI Assistant 是一个**可落地的网络运维 AI 助手**，不是聊天玩具：

- **自研 ReAct Agent**：LLM 决策 → 调用设备工具 → 观察结果 → 再决策，最多 6 步循环。
- **双通道设备控制**：Netmiko SSH 读设备状态 + `docker exec` 在 FRR 容器上注入/恢复可逆故障（`link_down` / `ospf_cost` / `bgp_neighbor_down`）。
- **RAG 知识库**：BM25 + 向量（bge-small-zh 本地）+ RRF 混合检索，覆盖 200+ 篇网络排障手册。
- **思考过程可视化**：RAG 路径在检索后、回答前推送 `thinking` 事件，前端显示"💭 思考中…"动画，回答流式到达后自动消失。
- **安全层**：提示词注入检测、RBAC 四角色（viewer/operator/admin）、滑动窗口限流、全量审计留痕。
- **真实拓扑可视化**：3 台 FRR 容器跑 OSPF + eBGP，前端 5 秒轮询邻居/路由状态；Docker 未启动时拓扑页自动降级为"启动 Docker"引导界面，不写死假拓扑。

### 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11+ · FastAPI · Uvicorn · Pydantic Settings |
| 前端 | 原生 HTML/CSS/JS · SSE 流式 · 分栏布局 · 纳西妲 Q 版绿白主题 |
| LLM | 智谱 GLM-4.5-Air（OpenAI 兼容协议，可切豆包） |
| Embedding | BAAI/bge-small-zh-v1.5（本地 CPU，512 维）；无 torch 环境自动降级哈希向量 |
| 设备仿真 | Docker · FRR（Free Range Routing）· OSPF + eBGP |
| 设备交互 | Netmiko（SSH）· docker exec（带外 vtysh） |
| 应用壳 | pywebview（独立桌面窗口，非浏览器）· PyInstaller 打包 |
| 测试 | pytest · FastAPI TestClient（46 用例全绿） |

### 架构

```
┌─────────────────────────────────────────────────────────┐
│  Frontend (index.html)                                   │
│  纳西妲 Q 版绿白主题 · 分栏布局 · SSE 流式思考动画        │
└──────────────┬──────────────────────────────────────────┘
               │ HTTP / SSE
┌──────────────▼──────────────────────────────────────────┐
│  FastAPI (app/main.py → routers/)                        │
│  ├── chat.py      SSE + RAG + thinking + Agent 路由     │
│  ├── topology.py  FRR 实时拓扑（含 Docker 三态）         │
│  ├── docker.py    Docker 状态/启动                       │
│  ├── sessions.py 多会话持久化                            │
│  └── ...                                            │
├──────────────┬──────────────────────────────────────────┤
│  Agent (ReAct)              │  RAG Pipeline              │
│  ├── tool registry (装饰器) │  ├── bge embedding（本地）  │
│  ├── LLM provider 抽象     │  ├── BM25 + 向量 + RRF     │
│  └── RBAC 工具权限          │  └── 200+ 篇排障手册       │
├──────────────┴──────────────────────────────────────────┤
│  Device Layer                                           │
│  ├── Netmiko SSH → 设备 CLI                              │
│  └── docker exec → FRR 容器 vtysh                         │
├─────────────────────────────────────────────────────────┤
│  Docker: frr1 · frr2 · frr3 (OSPF + eBGP)               │
└─────────────────────────────────────────────────────────┘
```

### 快速开始

```bash
# 1. 克隆
git clone https://github.com/LJY20030728/netops-ai-assistant.git
cd netops-assistant

# 2. 后端依赖
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/Mac
pip install -r backend/requirements.txt

# 3. 配置
cp backend/.env.example backend/.env
# 编辑 backend/.env，填入 ZHIPU_API_KEY

# 4. 启动
python launcher.py
# 或手动：
cd backend
start_backend.bat   # Windows 一键启动（带日志）
```

### 测试

```bash
cd backend
pytest tests/ -v
```

覆盖：意图判定、会话持久化、故障状态机、路由冒烟、命令注入拦截、非法 session_id、空白消息、注入拦截、拓扑三态（46 用例）。

### 配置项（backend/.env）

| 变量 | 说明 | 默认 |
|---|---|---|
| `ZHIPU_API_KEY` | 智谱 API Key | 空 |
| `ZHIPU_MODEL` | 对话模型 | glm-4.5-air |
| `LLM_PROVIDER` | zhipu / doubao | zhipu |
| `ZHIPU_EMBEDDING_MODEL` | bge / local / embedding-3 | bge |
| `DEVICE_MODE` | real / simulate | real |
| `LLM_MOCK` | 无 Key 时模拟回复 | false |

### 项目结构

```
netops-assistant/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI 入口
│   │   ├── routers/           # 按功能拆分的路由
│   │   ├── agent/             # ReAct Agent + tool registry
│   │   ├── rag/               # 混合检索 + bge embedding
│   │   ├── llm/               # LLM provider 抽象
│   │   └── security/          # RBAC + 限流 + 注入检测 + 审计
│   ├── knowledge_base/       # 200+ 篇排障手册
│   └── tests/                # pytest（46 用例）
├── frontend/
│   ├── index.html            # 单页应用
│   └── assets/               # 图标 / 主题素材
├── docker-compose.frr.yml    # 3 台 FRR 容器
├── launcher.py               # pywebview 桌面启动器
└── start_backend.bat         # Windows 一键启动脚本
```

---

## English

### What is this

NetOps AI Assistant is a **production-oriented network operations AI copilot**, not a chat toy:

- **Custom ReAct Agent**: LLM reasons → calls device tools → observes → loops (up to 6 steps).
- **Dual-channel device control**: Netmiko SSH for read-only state, `docker exec` for reversible fault injection on FRR containers (`link_down` / `ospf_cost` / `bgp_neighbor_down`).
- **RAG knowledge base**: BM25 + vector (local bge-small-zh) + RRF hybrid retrieval over 200+ troubleshooting runbooks.
- **Thinking visualization**: RAG path pushes a `thinking` SSE event after retrieval, before streaming the answer; the UI shows a "💭 thinking…" breathing animation that fades when the first token arrives.
- **Security layer**: prompt-injection detection, RBAC (viewer/operator/admin), sliding-window rate limiter, full audit trail.
- **Real topology visualization**: 3 FRR containers running OSPF + eBGP, frontend polls neighbors/routes every 5s; when Docker is down the topology page gracefully degrades to a "start Docker" guide instead of rendering a fake topology.

### Quick start

```bash
git clone https://github.com/LJY20030728/netops-ai-assistant.git
cd netops-assistant
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env  # fill in ZHIPU_API_KEY
python launcher.py
```

### Notes

- Running from source with `ZHIPU_EMBEDDING_MODEL=bge` uses the local BAAI/bge-small-zh-v1.5 model (requires `sentence-transformers`).
- The PyInstaller package intentionally excludes torch/transformers; at runtime it automatically falls back to a dependency-free hash embedding so the packaged app stays small and starts fast.

### License

MIT
