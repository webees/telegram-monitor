# 使用轻量级 Python 3.10 镜像
FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量，防止 Python 产生 .pyc 文件并确保输出直接打印
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 安装系统依赖 (如有必要处理图片或加密库)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目所有文件
COPY . .

# 如果没有 .env 文件，则使用示例配置作为模板
RUN if [ ! -f .env ]; then cp config.example.env .env; fi

# 暴露 Web 界面端口 (该项目默认使用 FastAPI，通常为 8000 或由程序指定)
EXPOSE 8000

# 运行启动脚本
# --public 参数通常用于允许外部访问 Web UI
CMD ["python", "web_app_launcher.py"]