"""应用配置：从环境变量 / .env 文件读取。"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 固定指向 backend/，避免因启动目录不同而找不到配置
_BACKEND_DIR = Path(__file__).resolve().parents[1]


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
    hybrid_bm25_k: int = 10      # BM25 候选数
    hybrid_vec_k: int = 10       # 向量候选数
    rrf_k: int = 60              # RRF 融合参数

    # 安全层（M4）
    auth_enabled: bool = False            # true 时要求 Authorization: Bearer <token>，角色由 api_tokens 决定
    api_tokens: dict[str, str] = {}       # 环境变量 JSON：{"<token>":"viewer|operator|admin"}
    rate_limit_per_min: int = 30          # /api/chat 每 IP 每分钟上限
    audit_enabled: bool = True            # 审计日志写入 backend/data/audit.jsonl


settings = Settings()

# 派生路径（固定在 backend/ 之下，不随启动目录变化）
KB_DIR: Path = _BACKEND_DIR / "knowledge_base"
DATA_DIR: Path = _BACKEND_DIR / "data"
DEVICES_FILE: Path = _BACKEND_DIR / "devices.json"
