# AI-crew

**🌐 语言: [English](README.md) | [Русский](README.ru.md) | [中文](README.zh-CN.md)**

**基于 LangGraph 的多智能体开发平台**

由 5 个 AI 智能体（PM、Analyst、Architect、Developer、QA）组成的团队
协同完成软件开发任务 — 从需求收集到创建 Pull Request。

## 功能特性

- **5 个专业智能体** — 使用不同的 LLM 模型
- **Human-in-the-Loop** — 智能体通过 Web UI 向用户提出澄清问题
- **完整开发周期** — 从创意到 GitHub PR
- **升级梯度** — Dev↔QA 循环卡住时自动升级处理
- **Web UI** — 基于 React 的任务管理界面
- **可观测性** — 通过 Langfuse 进行链路追踪
- **Docker 就绪** — 开发环境 (docker-compose) 和生产环境 (all-in-one 镜像)

## 架构

```
  Web UI (:5173)  ──►  Aegra API (:8000)  ──►  LangGraph
                                                    │
    PM ─► Analyst ─► Architect ─► Developer ─► QA ──┤
              │           │                    │    │
         clarify?     clarify?            Dev↔QA   git_commit
                                         cycle     ─► PR
                            │
        PostgreSQL (:5433)  │  Langfuse (:3001)
```

## 快速开始

```bash
# 1. 配置环境
cp env.example .env
# 在 .env 中填写 LLM_API_KEY

# 2. 启动所有服务
docker-compose up -d

# 3. 启动前端
cd frontend && npm install && npm run dev
```

打开 http://localhost:5173，输入任务并观察智能体工作。

**详细说明：** [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)

## 文档

| 文档 | 描述 |
|------|------|
| [快速开始](docs/GETTING_STARTED.md) | 10 分钟内完成安装和启动 |
| [架构](docs/architecture_old.md) | 系统详细描述、智能体图、状态模型 |
| [开发](docs/DEVELOPMENT.md) | 如何添加智能体、修改提示词、配置 LLM |
| [测试](docs/TESTING.md) | 运行测试、夹具、CI/CD |
| [部署](docs/deployment.md) | Docker Compose（开发）和 Dockerfile（生产）|
| [VPS 引导部署 (Ansible)](docs/DEPLOY_VPS_ANSIBLE.md) | 为应用自动部署准备服务器 |
| [路线图](docs/IDEAS.md) | 项目发展构想 |

## 技术栈

| 组件 | 技术 |
|------|------|
| 编排 | LangGraph |
| API | Aegra (FastAPI) |
| 数据库 | PostgreSQL + pgvector |
| 可观测性 | Langfuse |
| Web UI | React + Vite + Tailwind |
| LLM | OpenAI 兼容代理（Claude、Gemini、GLM 等）|
| 部署 | Docker Compose / Dockerfile |

## 项目结构

```
AI-crew/
├── graphs/dev_team/          # LangGraph 团队图
│   ├── graph.py              #   节点、边、路由器
│   ├── state.py              #   DevTeamState
│   ├── agents/               #   PM、Analyst、Architect、Developer、QA
│   ├── prompts/              #   YAML 提示词
│   └── tools/                #   GitHub、文件系统
├── frontend/                 # React Web UI
├── tests/                    # 测试 (pytest)
├── vendor/aegra/             # Aegra 服务器（内置）
├── scripts/                  # Docker 入口脚本、设置、nginx
├── docs/                     # 文档
├── docker-compose.yml        # 开发环境
├── Dockerfile                # 生产环境 (all-in-one)
├── aegra.json                # Aegra 配置
└── env.example               # .env 模板
```

## 测试

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## 自定义配置

- **提示词** — `graphs/dev_team/prompts/*.yaml`
- **模型** — 环境变量 `LLM_MODEL_PM`、`LLM_MODEL_DEVELOPER` 等
- **新智能体** — 参见 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)
- **图** — `graphs/dev_team/graph.py`

## 许可证

MIT
