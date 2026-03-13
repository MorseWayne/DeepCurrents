# 使用 uv 官方镜像进行极速构建
FROM ghcr.io/astral-sh/uv:python3.12-alpine AS builder

# 接收构建参数
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG ALL_PROXY
ARG NO_PROXY

# 设置环境变量供构建过程使用
ENV http_proxy=$HTTP_PROXY
ENV https_proxy=$HTTPS_PROXY
ENV all_proxy=$ALL_PROXY
ENV no_proxy=$NO_PROXY

WORKDIR /app

# 安装构建依赖 (如果 requirements 中有需要编译的包)
RUN apk add --no-cache gcc musl-dev libffi-dev g++

# 仅复制依赖文件以利用缓存
COPY requirements.txt .
# 使用虚拟环境以确保路径一致性
RUN uv venv /opt/venv && \
    . /opt/venv/bin/activate && \
    uv pip install --no-cache -r requirements.txt

# 最终运行阶段
FROM python:3.12-alpine

# 安装必要的运行时库 (Alpine 基础镜像较小，需补齐)
RUN apk add --no-cache libstdc++ libxml2 libxslt

WORKDIR /app

# 从构建阶段拷贝虚拟环境
COPY --from=builder /opt/venv /opt/venv

# 拷贝项目文件
COPY . .

# 创建必要目录
RUN mkdir -p data logs

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV PATH="/opt/venv/bin:$PATH"

# 启动命令
CMD ["python", "-m", "src.main"]
