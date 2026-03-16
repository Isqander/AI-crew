# AI-crew

**🌐 语言: [English](README.md) | [Русский](README.ru.md) | [中文](README.zh-CN.md)**

**基于 LangGraph 的多智能体软件开发平台**

AI-crew 编排 AI 智能体团队自主构建软件 — 从与用户讨论实现细节到部署完成的项目并
交付可用的访问链接。平台提供不断增长的智能体团队图集合，适用于不同场景：完整的
开发团队、轻量级编码助手和研究小组。

## 工作原理

1. **描述任务** — 通过 Web UI 或 Telegram 机器人
2. **AI 经理讨论方案** — 澄清需求、提出架构方案、协商细节
3. **智能体团队执行** — 分析师、架构师、开发人员、审查员、QA 自主协作
4. **实时观察** — 交互式图形可视化实时展示每个智能体步骤
5. **获取成果** — 已部署的项目，工作链接直接发送给您

## 智能体团队

| 图 | 用途 |
|----|------|
| **dev_team** | 完整开发周期 — 7 个智能体（PM、Analyst、Architect、Developer、Security、Reviewer、QA）。从需求到 Pull Request |
| **standard_dev** | 中等复杂度任务的自主开发。PM + Developer + Reviewer，有限的审查周期 |
| **simple_dev** | 快速代码生成 — 单个 Developer 智能体，无需审查。脚本、代码片段、小功能，秒级完成 |
| **research** | 任意主题的通用研究 — 网络搜索、来源分析、带引用的结构化报告 |

## 核心特性

- **多种团队配置** — 根据任务选择合适的团队：从单个开发者到完整的 7 智能体团队
- **端到端交付** — 流程不止于 PR；项目会被部署，您将收到可用的 URL
- **Human-in-the-Loop** — AI 经理在团队开始构建之前与您讨论实现细节
- **交互式图形可视化** — 在实时可视图上观察每个智能体节点的执行过程
- **Telegram 集成** — 直接从 Telegram 创建和管理任务
- **升级梯度** — Dev↔QA 循环卡住时自动升级处理
- **可观测性** — 通过 Langfuse 进行完整的链路追踪和调试
- **Docker 就绪** — 开发环境 (docker-compose) 和生产环境 (all-in-one 镜像)

## 架构

```
  Telegram ─────┐
                ▼
  Web UI ──► Gateway API ──► LangGraph Engine
                                    │
          ┌─────────────────────────┤
          ▼                         ▼
   ┌─ dev_team ──────┐     ┌─ research ──────┐
   │ PM → Analyst →  │     │ Researcher →    │
   │ Architect →     │     │ Web Search →    │
   │ Developer →     │     │ Report          │
   │ Security →      │     └─────────────────┘
   │ Reviewer → QA   │
   └──────┬──────────┘     ┌─ simple_dev ────┐
          │                │ Developer →     │
          ▼                │ Commit          │
   CI/CD → Deploy          └─────────────────┘
          │
          ▼
   Live URL → User

   PostgreSQL  │  Langfuse  │  GitHub
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

打开 http://localhost:5173，输入任务并在交互式图形上观察智能体工作。

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
| Telegram 机器人 | Python (aiogram) |
| LLM | OpenAI 兼容代理（Claude、Gemini、GLM 等）|
| 部署 | Docker Compose / Dockerfile |

## 项目结构

```
AI-crew/
├── graphs/                   # 智能体团队图
│   ├── dev_team/             #   完整 7 智能体开发团队
│   ├── standard_dev/         #   中等复杂度开发
│   ├── simple_dev/           #   快速单智能体编码
│   ├── research/             #   研究与分析
│   └── common/               #   共享工具、类型、git、日志
├── frontend/                 # React Web UI 含图形可视化
├── gateway/                  # API 网关 (FastAPI)
├── telegram/                 # Telegram 机器人
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

- **提示词** — `graphs/*/prompts/*.yaml`
- **模型** — 环境变量 `LLM_MODEL_PM`、`LLM_MODEL_DEVELOPER` 等
- **新智能体** — 参见 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)
- **新图** — 在 `graphs/` 下添加目录，包含 `graph.py` 和 `manifest.yaml`

## 许可证

MIT
