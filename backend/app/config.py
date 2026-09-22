"""应用配置：从环境变量 / .env 文件 / 用户配置目录读取。"""
import json
import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 固定指向 backend/，避免因启动目录不同而找不到配置
_BACKEND_DIR = Path(__file__).resolve().parents[1]

# 用户配置目录：%APPDATA%\NetOpsAssistant（打包后用户可写，源码目录只读）
def user_config_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "NetOpsAssistant" / "config.json"


def _load_user_config() -> dict:
    r"""从 %APPDATA%\NetOpsAssistant\config.json 读用户首次填写的配置。"""
    p = user_config_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


# 把用户配置合并到环境变量（优先级高于 .env）
for _k, _v in _load_user_config().items():
    if _v:
        os.environ.setdefault(_k, str(_v))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 智谱 AI（对话 + 嵌入）
    zhipu_api_key: str = ""
    zhipu_model: str = "glm-4-flash"
    zhipu_embedding_model: str = "embedding-3"
    zhipu_base_url: str = "https://open.bigmodel.cn/api/paas/v4"

    # LLM Provider 切换：zhipu | doubao
    llm_provider: str = "zhipu"
    # 豆包（火山引擎 Ark，OpenAI 兼容协议）
    doubao_api_key: str = ""
    doubao_model: str = "doubao-pro-4k"
    doubao_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"

    # 开发模式：未配置 Key 时可模拟回复 + 本地哈希嵌入，便于调试
    mock_llm: bool = False

    # 生成参数
    max_tokens: int = 2048
    temperature: float = 0.7
    request_timeout: float = 120.0

    # RAG 检索参数
    rag_top_k: int = 5
    chunk_size: int = 500
    chunk_overlap: int = 60

    # Agent 设备工具参数
    # device_mode: simulate=内置仿真设备（默认，无需真实设备）；real=Netmiko 连接 EVE-NG 仿真设备
    device_mode: str = "simulate"
    agent_max_steps: int = 6
    # 仿真故障场景（仅 simulate 模式）：flapping/stp_loop/arp_poison/bgp_flap/acl_deny
    # 运行时可通过 POST /api/sim/scenario 切换（admin）
    sim_fault_scenario: str = "flapping"

    # 混合检索（M4）
    rerank_enabled: bool = True
    rerank_model: str = "rerank"
    rerank_weight: float = 0.0   # rerank 融合权重（评测驱动：领域内为负优化，默认 0=不参与）
    hybrid_bm25_k: int = 10      # BM25 候选数
    hybrid_vec_k: int = 10       # 向量候选数
    rrf_k: int = 60              # RRF 融合参数

    # 向量库后端（M5 工程化）：numpy=自研本地向量库（默认）；qdrant=Qdrant 适配器（需 pip install qdrant-client）
    vector_backend: str = "numpy"

    # 安全层（M4）
    auth_enabled: bool = True             # 默认开启：本机 loopback 自动信任为 admin；远程必须带 token
    api_tokens: dict[str, str] = {}       # 环境变量 JSON：{"<token>":"viewer|operator|admin"}
    rate_limit_per_min: int = 30          # /api/chat 每 IP 每分钟上限
    audit_enabled: bool = True            # 审计日志写入 backend/data/audit.jsonl


settings = Settings()

# 派生路径（固定在 backend/ 之下，不随启动目录变化）
KB_DIR: Path = _BACKEND_DIR / "knowledge_base"
DATA_DIR: Path = _BACKEND_DIR / "data"
DEVICES_FILE: Path = _BACKEND_DIR / "devices.json"
