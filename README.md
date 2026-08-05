# Customer Service Infra

一个基于 LangGraph、FastAPI、React 和 SQLite 构建的多智能体客服系统。系统会并行调用医疗、销售与情绪支持专家，由主智能体整合建议，并在返回用户前通过审核智能体检查回复。

> English: A full-stack, multi-agent customer service system built with LangGraph, FastAPI, React, and SQLite. Specialist agents collaborate in parallel, while a review agent validates the final response before it reaches the user.

## 功能亮点

- 多智能体并行协作：医疗、销售、情绪支持专家独立分析会话
- 回复审核：输出前检查回复是否符合服务规范
- 动态配置：用户、提示词和专家配置存储在 SQLite 中
- 管理接口：提供用户、提示词和专家的 REST CRUD API
- Web 聊天界面：基于 React、Vite 和 TypeScript
- OpenAI 兼容：支持配置兼容 OpenAI API 的模型服务
- 可观测性：支持接入 Langfuse 追踪调用链

## 系统架构

```text
React Web UI (:3000)
        │
        ▼
FastAPI App Backend (:8000)
        │
        ▼
LangGraph Agent (:2024)
        │
        ├── Medical Expert ───┐
        ├── Sales Expert ─────┼──► Synthesis ─► Review ─► Response
        └── Emotional Expert ─┘
        │
        ▼
Shared SQLite Store
```

## 项目结构

```text
customer-service-infra/
├── app-backend/              # FastAPI 接口与 LangGraph 代理服务
├── chat-board/               # React/Vite 前端（Git 子模块）
├── customer-service-agent/   # LangGraph 多智能体后端（Git 子模块）
├── db/                       # SQLite 初始化、迁移与提示词种子
├── docs/                     # 架构、数据库与项目文档
└── RUNNING.md                # 更详细的本地运行说明
```

## 技术栈

- Agent：LangGraph、LangChain、Python
- API：FastAPI、Uvicorn
- Frontend：React 19、TypeScript、Vite、Tailwind CSS
- Storage：SQLite
- Tooling：uv、npm
- Observability：Langfuse（可选）

## 快速开始

### 1. 环境要求

- Git
- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Node.js 20+ 与 npm
- 一个兼容 OpenAI API 的模型服务

### 2. 克隆项目

本项目包含 Git 子模块，请使用：

```bash
git clone --recurse-submodules https://github.com/yiqingxie830-coder/customer-service-infra.git
cd customer-service-infra
```

如果已经执行普通克隆，可补充初始化子模块：

```bash
git submodule update --init --recursive
```

### 3. 初始化数据库

```bash
cd db
uv run python migrate_schema.py --overwrite
cd ..
```

`--overwrite` 会使用 `db/prompts/` 中的文件重新写入默认提示词。已有数据环境请谨慎使用。

### 4. 配置并启动 LangGraph Agent

```bash
cd customer-service-agent
cp .env.example .env
```

编辑 `.env`，至少配置模型服务地址和密钥：

```ini
OPENAI_BASE_URL=https://your-openai-compatible-endpoint/v1
OPENAI_API_KEY=your-api-key
```

安装依赖并启动服务：

```bash
uv sync
uv run python scripts/dev.py dev --port 2024
```

### 5. 启动 FastAPI 服务

在新的终端中运行：

```bash
cd app-backend
cp .env.example .env
uv sync
uv run uvicorn app_backend.main:app --host 0.0.0.0 --port 8000 --reload
```

API 文档地址：<http://localhost:8000/docs>

### 6. 启动前端

在新的终端中运行：

```bash
cd chat-board
npm install
npm run dev
```

打开 <http://localhost:3000> 使用聊天界面。

## API 概览

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/chat` | 发送完整对话并获取智能体回复 |
| `GET/POST` | `/users` | 查询或创建用户 |
| `GET/PUT` | `/prompts` | 查询或更新系统提示词 |
| `GET/PUT/DELETE` | `/experts` | 管理专家配置 |

更完整的请求格式请查看 [`app-backend/README.md`](app-backend/README.md)。

## 测试与健康检查

```bash
# App Backend tests
cd app-backend && uv run pytest

# Agent tests
cd customer-service-agent && uv run pytest

# 服务启动后的端到端健康检查（在项目根目录运行）
uv run python app-backend/scripts/health_check.py --base-url http://localhost:8000
```

## 配置与安全

- 不要提交 `.env`、API 密钥、数据库生产数据或其他敏感信息
- 仓库只提供 `.env.example` 作为配置模板
- 公开部署前，请增加身份认证、访问控制、限流与日志脱敏
- 医疗专家的输出不应替代专业医疗诊断或治疗建议

## 更多文档

- [完整启动说明](RUNNING.md)
- [系统架构](docs/architecture.md)
- [数据库结构](docs/database_schema.md)
- [项目报告](docs/PROJECT_REPORT.md)
- [Agent API](customer-service-agent/docs/api.md)

## License

本项目目前未声明开源许可证。除非仓库所有者另行授权，否则默认保留所有权利。
