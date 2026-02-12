# AI 编程指南

> 本文档定义项目的编码规范，所有 AI 辅助编程必须遵循。

## 命名规范

### 文件 & 文件夹

- 名称尽量控制在 **2 个单词以内**（优先单词，必要时 2 个单词）
- 使用 `snake_case`，如 `image_button.py`
- 禁止自创缩写，允许行业通用缩写（`ai`, `log`, `app`, `config`, `db`, `api`, `http`, `msg`, `auth`）
- 文件夹使用单数形式：`monitor/` 而非 `monitors/`

### 变量 & 函数

- 名称控制在 **2 个单词以内**
- 使用 `snake_case`
- 相邻变量命名尽量 **字母数一致**，保持视觉对齐：

```python
# ✅ 好
host = "127.0.0.1"
port = 8000
user = "admin"

# ✅ 好
src_path = "/data/input"
dst_path = "/data/output"
log_path = "/data/logs"

# ❌ 差
hostname = "127.0.0.1"
p = 8000
username = "admin"
```

### 常量

- 全大写 `UPPER_SNAKE_CASE`

```python
MAX_RETRY   = 3
TIMEOUT_SEC = 30
BASE_URL    = "https://api.example.com"
```

### 类名

- `PascalCase`，控制在 2 个单词以内
- 如 `WebApp`, `AIService`, `BaseMonitor`

## 项目结构

目标：**3 个源码文件夹 + 入口**

```
core/        — 核心逻辑 + 数据模型 + 服务 + 工具
monitor/     — 监控器实现（策略模式）
web/         — Web 界面 + 模板
app.py       — 入口
```

### 原则

- 文件夹层级尽量扁平，不超过 2 层
- 相关模块合并到同一文件夹，减少目录数量
- 每个文件职责单一，但避免过度拆分

## 核心原则

> **以最少的代码实现最完整的功能，但不能牺牲可读性。**
> 更少的代码意味着更容易检查和审核。

### 代码风格

- **极简**：能用 1 行写完的不用 3 行
- **直接**：减少不必要的中间变量和嵌套
- **清晰**：宁可名字长一点，也不要自创缩写
- **紧凑**：合并可合并的逻辑，但保持每行可读
- **少即是多**：删除冗余注释、空行、死代码，代码本身就是文档
