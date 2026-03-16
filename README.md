# AI-crew

**🌐 Language: [English](README.md) | [Русский](README.ru.md) | [中文](README.zh-CN.md)**

**Multi-agent software development platform powered by LangGraph**

AI-crew orchestrates teams of AI agents that build software autonomously — from
discussing implementation details with the user to deploying the finished project
and delivering a live URL. The platform ships a growing collection of agent team
graphs tailored for different scenarios: full-cycle development teams, lightweight
coding assistants, and research crews.

## How It Works

1. **You describe the task** — via Web UI or Telegram bot
2. **AI manager discusses the plan** — clarifies requirements, proposes architecture, agrees on details
3. **Agent team executes** — analysts, architects, developers, reviewers, QA work together autonomously
4. **You watch it happen** — interactive graph visualization shows every agent step in real time
5. **You get the result** — deployed project with a live URL delivered to you

## Agent Teams

| Graph | Purpose |
|-------|---------|
| **dev_team** | Full development cycle — 7 agents (PM, Analyst, Architect, Developer, Security, Reviewer, QA). From requirements to Pull Request |
| **standard_dev** | Autonomous development for medium-complexity tasks. PM + Developer + Reviewer with limited review cycles |
| **simple_dev** | Fast code generation — single Developer agent, no review. Scripts, snippets, small features in seconds |
| **research** | Universal research on any topic — web search, source analysis, structured reports with citations |

## Key Features

- **Multiple agent team configurations** — pick the right team for the job, from a solo developer to a full 7-agent crew
- **End-to-end delivery** — the cycle doesn't stop at a PR; the project gets deployed and you receive a working URL
- **Human-in-the-Loop** — AI manager discusses implementation details with you before the team starts building
- **Interactive graph visualization** — watch every agent node execute in real time on a live visual graph
- **Telegram integration** — create and manage tasks directly from Telegram
- **Escalation ladder** — automatic escalation when Dev↔QA cycles get stuck
- **Observability** — full tracing and debugging via Langfuse
- **Docker ready** — dev (docker-compose) and prod (all-in-one image)

## Architecture

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

Open http://localhost:5173, enter a task and watch the agents work on the interactive graph.

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
| Telegram Bot | Python (aiogram) |
| LLM | OpenAI-compatible proxy (Claude, Gemini, GLM, etc.) |
| Deployment | Docker Compose / Dockerfile |

## Project Structure

```
AI-crew/
├── graphs/                   # Agent team graphs
│   ├── dev_team/             #   Full 7-agent development team
│   ├── standard_dev/         #   Medium-complexity development
│   ├── simple_dev/           #   Fast single-agent coding
│   ├── research/             #   Research & analysis
│   └── common/               #   Shared utilities, types, git, logging
├── frontend/                 # React Web UI with graph visualization
├── gateway/                  # API gateway (FastAPI)
├── telegram/                 # Telegram bot
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

- **Prompts** — `graphs/*/prompts/*.yaml`
- **Models** — env `LLM_MODEL_PM`, `LLM_MODEL_DEVELOPER`, etc.
- **New agent** — see [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)
- **New graph** — add a directory under `graphs/` with `graph.py` and `manifest.yaml`

## License

MIT
