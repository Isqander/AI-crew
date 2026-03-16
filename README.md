# AI-crew

**🌐 Language: [English](README.md) | [Русский](README.ru.md) | [中文](README.zh-CN.md)**

**Multi-agent development platform powered by LangGraph**

A team of 5 AI agents (PM, Analyst, Architect, Developer, QA) collaboratively
handles software development tasks — from requirements gathering to Pull Request creation.

## Features

- **5 specialized agents** with different LLM models
- **Human-in-the-Loop** — agents ask clarifying questions via Web UI
- **Full development cycle** — from idea to GitHub PR
- **Escalation ladder** — automatic escalation when Dev↔QA cycles get stuck
- **Web UI** — React interface for task management
- **Observability** — tracing via Langfuse
- **Docker ready** — dev (docker-compose) and prod (all-in-one image)

## Architecture

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

## Quick Start

```bash
# 1. Set up environment
cp env.example .env
# Fill in LLM_API_KEY in .env

# 2. Start all services
docker-compose up -d

# 3. Start the frontend
cd frontend && npm install && npm run dev
```

Open http://localhost:5173, enter a task and watch the agents work.

**More details:** [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)

## Documentation

| Document | Description |
|----------|-------------|
| [Quick Start](docs/GETTING_STARTED.md) | Installation and launch in 10 minutes |
| [Architecture](docs/architecture_old.md) | Detailed system description, agent graph, state model |
| [Development](docs/DEVELOPMENT.md) | How to add an agent, modify prompts, configure LLM |
| [Testing](docs/TESTING.md) | Running tests, fixtures, CI/CD |
| [Deployment](docs/deployment.md) | Docker Compose (dev) and Dockerfile (prod) |
| [VPS Bootstrap (Ansible)](docs/DEPLOY_VPS_ANSIBLE.md) | Server preparation for automated app deployment |
| [Roadmap](docs/IDEAS.md) | Ideas for project development |

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Orchestration | LangGraph |
| API | Aegra (FastAPI) |
| Database | PostgreSQL + pgvector |
| Observability | Langfuse |
| Web UI | React + Vite + Tailwind |
| LLM | OpenAI-compatible proxy (Claude, Gemini, GLM, etc.) |
| Deployment | Docker Compose / Dockerfile |

## Project Structure

```
AI-crew/
├── graphs/dev_team/          # LangGraph team graph
│   ├── graph.py              #   Nodes, edges, routers
│   ├── state.py              #   DevTeamState
│   ├── agents/               #   PM, Analyst, Architect, Developer, QA
│   ├── prompts/              #   YAML prompts
│   └── tools/                #   GitHub, Filesystem
├── frontend/                 # React Web UI
├── tests/                    # Tests (pytest)
├── vendor/aegra/             # Aegra server (vendored)
├── scripts/                  # Docker entrypoint, setup, nginx
├── docs/                     # Documentation
├── docker-compose.yml        # Development
├── Dockerfile                # Production (all-in-one)
├── aegra.json                # Aegra config
└── env.example               # .env template
```

## Testing

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## Customization

- **Prompts** — `graphs/dev_team/prompts/*.yaml`
- **Models** — env `LLM_MODEL_PM`, `LLM_MODEL_DEVELOPER`, etc.
- **New agent** — see [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)
- **Graph** — `graphs/dev_team/graph.py`

## License

MIT
