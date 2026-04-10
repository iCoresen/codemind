# 使用 Python 3.12 的精简版作为基础镜像
FROM python:3.12-slim

# 设置 Python 环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \  # 防止 Python 写入 .pyc 文件
    PYTHONUNBUFFERED=1 \         # 禁用输出缓冲，确保日志实时输出
    PIP_NO_CACHE_DIR=1 \         # 禁用 pip 缓存
    UV_LINK_MODE=copy            # 设置 uv 链接模式为复制

# 设置工作目录
WORKDIR /app

# 安装 uv（快速的 Python 包管理器和解析器）
RUN pip install --no-cache-dir uv

# 首先复制依赖清单文件以最大化 Docker 构建缓存重用
# 这样当依赖不变时，可以复用之前的构建层
COPY pyproject.toml uv.lock ./
# 使用 uv 同步依赖（不安装开发依赖，使用冻结模式确保版本一致）
RUN uv sync --frozen --no-dev

# 复制应用程序源代码
COPY app ./app
COPY main.py ./main.py
COPY README.md ./README.md

# 创建必要的目录结构
RUN mkdir -p /app/logs /app/data/chroma

# 设置环境变量
ENV PATH="/app/.venv/bin:${PATH}" \  # 将虚拟环境添加到 PATH
    SERVER_HOST=0.0.0.0 \            # 服务器监听所有网络接口
    SERVER_PORT=8080                 # 服务器监听端口

# 暴露容器端口
EXPOSE 8080

# 容器启动时执行的命令
CMD ["python", "-m", "app.main"]
