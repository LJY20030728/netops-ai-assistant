# ===== Stage 1: builder（装依赖，产生 wheel）=====
FROM python:3.12-slim AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY backend/requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt


# ===== Stage 2: runtime（只带运行时，镜像更小）=====
FROM python:3.12-slim AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/root/.local/bin:$PATH

# 从 builder 拷已装好的 Python 包
COPY --from=builder /root/.local /root/.local

# 应用代码与资源
COPY backend/app ./app
COPY backend/knowledge_base ./knowledge_base
COPY backend/devices.json ./devices.json
COPY frontend ./frontend

EXPOSE 8000

# 启动前幂等入库，再启动服务
CMD ["sh", "-c", "python -m app.rag.ingest && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
