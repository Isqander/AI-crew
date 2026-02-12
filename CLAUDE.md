# CLAUDE.md — AI-crew

## Критические правила

1. **Язык** — всегда отвечай на **русском языке**
2. Если есть вопросы/уточнения - сразу спрашивай у пользователя!

## Что это за проект

AI-crew — мультиагентная платформа разработки на LangGraph.
Команды ИИ-агентов выполняют задачи по разработке ПО: от сбора требований до создания PR и деплоя.
При этом возможны задачи и любого другого направления.

Проект включает:
- `graphs/dev_team/` — основной LangGraph-граф команды
- `frontend/` — Web UI (React + Vite)
- `gateway/` — API-шлюз (FastAPI)
- `telegram/` — Telegram-бот для работы с системой

## Ключевые файлы

- `graphs/dev_team/graph.py` — узлы, рёбра, роутинг графа
- `graphs/dev_team/state.py` — `DevTeamState` (shared state)
- `graphs/dev_team/agents/base.py` — `BaseAgent`, `get_llm`, загрузка промптов
- `graphs/dev_team/agents/{pm,analyst,architect,developer,qa}.py` — агенты
- `graphs/dev_team/prompts/*.yaml` — YAML-промпты агентов
- `graphs/dev_team/tools/{filesystem,github,web}.py` — инструменты агентов
- `graphs/dev_team/manifest.yaml` — манифест графа для запуска
- `aegra.json` / `aegra.prod.json` — конфиги регистрации графов
- `docker-compose.yml` / `docker-compose.prod.yml` — dev/prod инфраструктура
- `env.example` — шаблон переменных окружения

## Текущее дерево (сокращённо)

```text
AI-crew/
├── graphs/
│   └── dev_team/
│       ├── agents/
│       ├── prompts/
│       ├── tools/
│       ├── graph.py
│       ├── state.py
│       ├── manifest.yaml
│       └── logging_config.py
├── frontend/
├── gateway/
├── telegram/
├── tests/
├── docs/
├── scripts/
├── vendor/aegra/
├── aegra.json
├── aegra.prod.json
├── docker-compose.yml
├── docker-compose.prod.yml
├── Dockerfile
├── Dockerfile.aegra
└── env.example
```

## Документация (`docs/`)

- [GETTING_STARTED](docs/GETTING_STARTED.md) — быстрый старт
- [architecture](docs/architecture.md) — базовая архитектура (старая)
- [ARCHITECTURE_V2](docs/ARCHITECTURE_V2.md) — обновлённая архитектура
- [DEVELOPMENT](docs/DEVELOPMENT.md) — разработка и расширение
- [TESTING](docs/TESTING.md) — тестирование
- [deployment](docs/deployment.md) — развёртывание
- [IMPLEMENTATION_PLAN](docs/IMPLEMENTATION_PLAN.md) — план реализации
- [EVOLUTION_PLAN_V3](docs/EVOLUTION_PLAN_V3.md) — план эволюции
- [IDEAS](docs/IDEAS.md) — backlog идей
