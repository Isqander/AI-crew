# AI-crew

**Мультиагентная платформа разработки на базе LangGraph**

Команда из 5 ИИ-агентов (PM, Analyst, Architect, Developer, QA) совместно
выполняет задачи по разработке — от сбора требований до создания Pull Request.

## Возможности

- **5 специализированных агентов** с разными LLM-моделями
- **Human-in-the-Loop** — агенты задают уточняющие вопросы через Web UI
- **Полный цикл разработки** — от идеи до PR в GitHub
- **Escalation ladder** — автоматическая эскалация при зацикливании Dev↔QA
- **Web UI** — React-интерфейс для управления задачами
- **Observability** — трейсинг через Langfuse
- **Docker ready** — dev (docker-compose) и prod (all-in-one image)

## Архитектура

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

## Быстрый старт

```bash
# 1. Настроить окружение
cp env.example .env
# Заполнить LLM_API_KEY в .env

# 2. Запустить все сервисы
docker-compose up -d

# 3. Запустить frontend
cd frontend && npm install && npm run dev
```

Откройте http://localhost:5173, введите задачу и наблюдайте за работой агентов.

**Подробнее:** [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)

## Документация

| Документ | Описание |
|----------|----------|
| [Быстрый старт](docs/GETTING_STARTED.md) | Установка и запуск за 10 минут |
| [Архитектура](docs/architecture_old.md) | Детальное описание системы, граф агентов, state-модель |
| [Разработка](docs/DEVELOPMENT.md) | Как добавить агента, изменить промпты, настроить LLM |
| [Тестирование](docs/TESTING.md) | Запуск тестов, фикстуры, CI/CD |
| [Развёртывание](docs/deployment.md) | Docker Compose (dev) и Dockerfile (prod) |
| [Roadmap](docs/IDEAS.md) | Идеи для развития проекта |

## Стек

| Компонент | Технология |
|-----------|-----------|
| Оркестрация | LangGraph |
| API | Aegra (FastAPI) |
| БД | PostgreSQL + pgvector |
| Observability | Langfuse |
| Web UI | React + Vite + Tailwind |
| LLM | OpenAI-совместимый прокси (Claude, Gemini, GLM, etc.) |
| Деплой | Docker Compose / Dockerfile |

## Структура проекта

```
AI-crew/
├── graphs/dev_team/          # LangGraph граф команды
│   ├── graph.py              #   Узлы, рёбра, роутеры
│   ├── state.py              #   DevTeamState
│   ├── agents/               #   PM, Analyst, Architect, Developer, QA
│   ├── prompts/              #   YAML-промпты
│   └── tools/                #   GitHub, Filesystem
├── frontend/                 # React Web UI
├── tests/                    # Тесты (pytest)
├── vendor/aegra/             # Aegra server (vendored)
├── scripts/                  # Docker entrypoint, setup, nginx
├── docs/                     # Документация
├── docker-compose.yml        # Development
├── Dockerfile                # Production (all-in-one)
├── aegra.json                # Конфиг Aegra
└── env.example               # Шаблон .env
```

## Тестирование

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## Кастомизация

- **Промпты** — `graphs/dev_team/prompts/*.yaml`
- **Модели** — env `LLM_MODEL_PM`, `LLM_MODEL_DEVELOPER`, etc.
- **Новый агент** — см. [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)
- **Граф** — `graphs/dev_team/graph.py`

## Лицензия

MIT
