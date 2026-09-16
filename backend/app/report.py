"""故障报告导出：把一次排障会话（对话 + 元信息）导出为自包含 HTML。

- 用于复盘/工单附件/面试演示：展示 AI 助手完整处理一个故障的过程；
- 报告含：生成时间、服务版本、知识库规模、会话消息流。
"""
import html
import time
from pathlib import Path

from app.config import DATA_DIR

REPORT_DIR = DATA_DIR / "reports"


def _escape(text: str) -> str:
    return html.escape(text or "")


def build_html_report(session_id: str, messages: list[dict], meta: dict) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    blocks = []
    for m in messages:
        role = m.get("role", "")
        content = m.get("content", "")
        if role == "user":
            blocks.append(
                f'<div class="msg user"><div class="tag">用户</div><div class="body">{_escape(content)}</div></div>'
            )
        else:
            blocks.append(
                f'<div class="msg ai"><div class="tag">AI 助手</div><div class="body">{_escape(content)}</div></div>'
            )
    msg_html = "\n".join(blocks) if blocks else "<p class='empty'>（会话暂无消息）</p>"
    meta_rows = "".join(
        f"<tr><td>{_escape(k)}</td><td>{_escape(str(v))}</td></tr>" for k, v in meta.items()
    )
    doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>NetOps AI Assistant · 故障排障报告</title>
<style>
  body {{ font-family: 'PingFang SC','Microsoft YaHei',sans-serif; margin: 0; background: #F4F3EE; color: #1A1B1C; }}
  .wrap {{ max-width: 860px; margin: 0 auto; padding: 32px 20px 64px; }}
  h1 {{ font-size: 22px; border-bottom: 2px solid #9EACEA; padding-bottom: 12px; }}
  .meta {{ background: #fff; border: 1px solid #E4E3DD; border-radius: 12px; padding: 14px 18px; margin: 18px 0; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  td {{ padding: 5px 8px; border-bottom: 1px solid #EEEDE7; }}
  td:first-child {{ color: #6B7280; width: 130px; }}
  .msg {{ margin: 14px 0; display: flex; gap: 10px; }}
  .tag {{ flex: 0 0 64px; height: fit-content; font-size: 12px; padding: 4px 8px; border-radius: 6px; text-align: center; }}
  .user .tag {{ background: #9EACEA; color: #fff; }}
  .ai .tag {{ background: #94D8C3; color: #1A1B1C; }}
  .body {{ flex: 1; background: #fff; border: 1px solid #E4E3DD; border-radius: 12px; padding: 12px 16px; white-space: pre-wrap; word-break: break-word; font-size: 14px; line-height: 1.6; }}
  .empty {{ color: #6B7280; }}
  .foot {{ margin-top: 28px; color: #9AA0A6; font-size: 12px; text-align: center; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>NetOps AI Assistant · 故障排障报告</h1>
  <div class="meta"><table>{meta_rows}</table></div>
  {msg_html}
  <div class="foot">由 NetOps AI Assistant 自动生成 · 仅供复盘参考</div>
</div>
</body>
</html>"""
    out = REPORT_DIR / f"{session_id}.html"
    out.write_text(doc, encoding="utf-8")
    return out
