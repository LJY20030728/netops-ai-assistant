# -*- coding: utf-8 -*-
"""启动带 auth 的测试实例（port 8001），供 RBAC 端到端验证。"""
import os
import sys

os.environ["AUTH_ENABLED"] = "true"
os.environ["API_TOKENS"] = '{"viewer-tok":"viewer","op-tok":"operator","admin-tok":"admin"}'

import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8001, app_dir="backend")
