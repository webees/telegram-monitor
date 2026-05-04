# TG 监控系统

> Telegram 消息监控和自动化平台。多账号管理、AI 分析、自动回复、定时消息、无来源标记转发。
> 基于 **Telethon** + **FastAPI**，模块化策略模式架构。

[![Docker](https://img.shields.io/badge/Docker-Multi--Arch-blue?logo=docker)](https://ghcr.io)
[![Python](https://img.shields.io/badge/Python-3.8+-3776AB?logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 功能概览

### 六种监控策略

| 类型 | 匹配方式 | 场景 |
|-----|---------|-----|
| **关键词** | 精确 / 包含 / 正则 | 品牌监控、敏感词、正则提取转发 |
| **文件** | 扩展名 + 大小过滤 | 文档收集、资源归档 |
| **AI** | GPT 语义 + 置信度 | 复杂语义、情感识别 |
| **按钮** | 手动关键词 / AI 选择 | Bot 签到、自动交互 |
| **图片按钮** | AI 视觉分析 | 验证码识别、图片问答 |
| **全量** | 匹配所有消息 | 数据备份、全面监控 |

### 核心能力

- **AI 集成** — OpenAI 兼容端点，语义分析、视觉识别、动态回复、AI 定时消息
- **通知转发** — 邮件通知、无来源标记复制、媒体组保持、禁转内容下载重发
- **智能追加** — 转发前保留原文，调用 AI 识别主题，并按页面里的追加模板拼接内容
- **转发列表** — SQLite 保存最新 500 条转发记录，失败项可在 Web 页面重试
- **自动化** — Cron/间隔调度、随机延迟、执行限制、优先级排序、三种执行模式
- **Web UI** — FastAPI + Jinja2、Session 认证、配置向导、实时仪表板、配置导入导出

---

## 快速开始

```bash
# 克隆 & 安装
git clone https://github.com/webees/telegram-monitor.git
cd telegram-monitor
pip install -r requirements.txt

# 配置
cp config.example.env .env
nano .env  # 至少配置 TG_API_ID + TG_API_HASH

# 启动
python3 app.py --check-config
python3 app.py --check-imports
python3 app.py
python3 app.py --public   # 公网访问
python3 app.py --debug    # 调试模式
```

访问 `http://localhost:8000`，默认账号 `admin` / `admin123`（请立即修改）。

---

## Docker 部署

```bash
docker run -d --name tg-monitor -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/.env:/app/.env \
  ghcr.io/webees/telegram-monitor:latest
```

CI/CD: `ghcr.yml` 自动构建多架构镜像 (amd64/arm64)，`ghcr-cleanup.yml` 每日清理过期镜像。

---

## Kubernetes 部署要点

程序默认把 Telegram 登录态保存到 `DATA_DIR/sessions`，转发列表保存到 `DATA_DIR/forward_queue.db`。你的 Deployment 已经把 PVC 挂载到 `/app/data`，所以不需要额外挂载 `*.session` 或 SQLite 文件；Pod 重建后登录态和转发列表都会保留。

建议在现有 YAML 的 `env` 里显式补齐目录配置，避免相对路径受工作目录影响：

```yaml
- name: DATA_DIR
  value: /app/data
- name: LOGS_DIR
  value: /app/logs
- name: DOWNLOADS_DIR
  value: /app/downloads
```

你现有的 volumeMounts 可以保持：

```yaml
volumeMounts:
  - mountPath: /app/data
    name: monitor
    subPath: data
  - mountPath: /app/logs
    name: monitor
    subPath: logs
  - mountPath: /app/downloads
    name: monitor
    subPath: downloads
```

升级后如果旧账号配置里还是 `session_手机号` 这种相对路径，程序会在启动时迁移到 `/app/data/sessions/session_手机号.session`。

---

## 配置

```env
# Telegram API (必须)
TG_API_ID=your_api_id
TG_API_HASH=your_api_hash

# OpenAI (可选)
OPENAI_API_KEY=sk-xxx
OPENAI_MODEL=gpt-3.5-turbo
OPENAI_BASE_URL=https://api.openai.com/v1

# 邮件 (可选)
EMAIL_SMTP_SERVER=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_USERNAME=your@email.com
EMAIL_FROM=your@email.com
EMAIL_PASSWORD=your_app_password
EMAIL_TO=notify@email.com

# Web
WEB_HOST=127.0.0.1
WEB_PORT=8000
WEB_USERNAME=admin        # ⚠️ 生产环境务必修改
WEB_PASSWORD=admin123     # ⚠️ 生产环境务必修改

# 数据目录
DATA_DIR=./data
LOGS_DIR=./logs
DOWNLOADS_DIR=./data/dl
```

---

## 转发说明

自动转发优先使用复制发送，目标群不会显示“转发自”。源消息是多图媒体组时，会按一个媒体组发送到目标群，避免拆成多条消息。每个目标群会写入一条 SQLite 转发记录，仅保留最新 500 条，失败记录可在“转发列表”页面重试。

启用智能追加后，程序会保留原消息正文不变，只调用 OpenAI 兼容接口识别主题等模板变量，并使用配置向导中的“追加内容模板”生成最终文案。如果 OpenAI key 用完、接口不可用或没有返回有效内容，这条消息会标记为失败并进入转发列表，不会用原文兜底转发。

模板变量：

| 变量 | 含义 |
|-----|------|
| `{topic}` | AI 识别出的新闻/消息主题 |
| `{original_text}` | 原始消息正文 |
| `{clean_text}` | 原始消息正文，兼容旧模板 |

追加内容模板示例：

```text
更多{topic}资讯，请关注 @your_channel
```

```text
整理发布：我的频道
```

```text
{original_text}

关注我们，获取更多{topic}消息。
```

主题提取提示词示例：

```text
只提取新闻主题，不要总结正文。
```

```text
主题控制在8个字以内，例如：股市行情、国际冲突、科技新品。
```

```text
如果原文是公告，主题写成公告核心事件。
```

---

## 架构

```
Telegram → Telethon Event → MonitorEngine → BaseMonitor 子类 → 动作执行
                                  │
                          按 priority 排序
                          按 execution_mode 分组
                          (merge / all / first_match)
```

### 设计模式

| 模式 | 应用 |
|-----|------|
| **Singleton** | AccountManager, MonitorEngine, AIService, EnhancedForwardService |
| **Strategy** | BaseMonitor → 6 种监控器子类 |
| **Factory** | MonitorFactory 根据类型创建监控器 |
| **Template Method** | BaseMonitor.process_message() 固定处理流程 |

---

## 项目结构

```
telegram-monitor/
├── core/                    # 核心 (逻辑 + 模型 + 服务 + 工具)
│   ├── account.py            # 账号管理 (AccountManager)
│   ├── engine.py             # 监控引擎 (MonitorEngine)
│   ├── model.py              # 数据模型 (Account, Config, Message)
│   ├── ai.py                 # AI 服务 (AIService)
│   ├── forward.py            # 增强转发 (EnhancedForwardService)
│   ├── forward_store.py      # SQLite 转发记录和重试状态
│   ├── config.py             # 环境配置 (.env 加载)
│   ├── log.py                # 日志 (控制台+文件双输出)
│   ├── storage.py            # JSON 原子读写
│   ├── singleton.py          # 线程安全单例元类
│   └── validator.py          # 验证器 (手机/邮箱/Cron)
├── monitor/                  # 监控器 (策略模式)
│   ├── base.py               # 抽象基类
│   ├── factory.py            # 工厂
│   ├── keyword.py            # 关键词 (精确/包含/正则)
│   ├── ai.py                 # AI 语义
│   ├── file.py               # 文件类型
│   ├── button.py             # 按钮点击
│   ├── image_button.py       # 图片+按钮
│   └── all.py                # 全量消息
├── web/                      # Web 界面
│   ├── app.py                # FastAPI 主应用
│   ├── wizard.py             # 配置向导
│   ├── status.py             # 系统状态监控
│   └── templates/            # Jinja2 模板
├── app.py                    # 入口
├── GUIDE.md                  # AI 编程指南
├── Dockerfile
├── requirements.txt
└── config.example.env
```

---

## 安全

```bash
# 生产环境
WEB_USERNAME=your_username
WEB_PASSWORD=strong_password
WEB_HOST=127.0.0.1            # 不对外暴露

chmod 600 .env *.session
```

| 文件 | 风险 |
|-----|------|
| `.env` | 🔴 高 — API Key、密码 |
| `*.session` | 🔴 高 — Telegram 登录凭证 |
| `data/*.json` | 🟡 中 — 账号和监控配置 |
| `data/forward_queue.db` | 🟡 中 — 转发记录和源消息定位 |

---

## 测试

```bash
python3 -m compileall -q core monitor web app.py tests
python3 -m pytest -q
```

---

## 故障排除

| 问题 | 检查 |
|-----|------|
| 无法连接账号 | TG_API_ID/HASH 配置、网络/代理 |
| AI 不工作 | OPENAI_API_KEY、API 额度 |
| 邮件失败 | SMTP 配置、应用专用密码 |
| 监控不触发 | 账号连接状态、chats 过滤、黑名单、max_executions |
| 自动转发失败 | auto_forward/enhanced_forward 开关、目标 ID、账号权限 |
| 智能追加失败 | OPENAI_API_KEY、额度、接口连通性；失败项可在转发列表重试 |
| 媒体过大 | max_download_size_mb、DOWNLOADS_DIR 权限和磁盘空间 |

---

## 许可证

[MIT License](LICENSE)

## 免责声明

仅供学习和合法用途。请遵守 Telegram 服务条款和当地法律法规。
