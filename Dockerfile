# 使用 uv 官方镜像进行极速构建
FROM ghcr.io/astral-sh/uv:python3.12-alpine AS builder

WORKDIR /app

# 仅复制依赖文件以利用缓存
COPY requirements.txt .
RUN uv pip install --no-cache -r requirements.txt

# 最终运行阶段
FROM python:3.12-alpine

WORKDIR /app

# 从构建阶段拷贝已安装的库
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# 拷贝项目文件
COPY . .

# 创建必要目录
RUN mkdir -p data logs

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# 启动命令
CMD ["python", "-m", "src.main"]
