# CURSOR.md — AI-crew

> Контекст для Cursor IDE при работе с этим проектом.

## Проект

AI-crew — мультиагентная платформа на LangGraph. 5 ИИ-агентов (PM, Analyst,
Architect, Developer, QA) совместно выполняют задачи по разработке:
от требований до Pull Request.

## Где что лежит

```
graphs/dev_team/
  graph.py              ← Граф: узлы, рёбра, роутеры
  state.py              ← DevTeamState (TypedDict)
  agents/
    base.py             ← get_llm(), BaseAgent, load_prompts()
    pm.py               ← Project Manager
    analyst.py          ← Business Analyst
    architect.py        ← Software Architect
    developer.py        ← Developer (code gen)
    qa.py               ← QA Engineer
  prompts/
    *.yaml              ← YAML-промпты для каждого агента
  tools/
    github.py           ← GitHub API (PRs, branches, commits)
    filesystem.py       ← Локальная ФС (workspace)
frontend/src/           ← React + Vite + Tailwind UI
tests/                  ← pytest тесты
vendor/aegra/           ← Aegra server (не трогать!)
docs/                   ← Документация
```

## Основные команды

```bash
pytest tests/ -v                  # Тесты
docker-compose up -d              # Dev-окружение
docker-compose logs -f aegra      # Логи
ruff check graphs/                # Линтер
```

## Паттерны

- **Агенты** — каждый файл экспортирует `*_agent(state) -> dict` для LangGraph
- **LLM** — `get_llm(role="...", temperature=...)`, единый прокси (env `LLM_API_URL`)
- **Промпты** — YAML: `system` + шаблоны с `{placeholder}`, загрузка через `load_prompts()`
- **State** — `DevTeamState` TypedDict, `NotRequired` для optional полей
- **Imports** — в `graph.py` абсолютные (`from dev_team.*`), в agents — относительные

## Что НЕ трогать

- `vendor/aegra/` — внешняя зависимость, устанавливается как pip-пакет
- `vendor/aegra/CURSOR.md`, `CLAUDE.md`, `AGENTS.md` — файлы Aegra, не проекта

## Документация

- [docs/architecture.md](docs/architecture.md) — архитектура, state, диаграммы
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) — добавить агента, промпты, LLM
- [docs/TESTING.md](docs/TESTING.md) — тесты
- [docs/deployment.md](docs/deployment.md) — Docker
- [docs/IDEAS.md](docs/IDEAS.md) — roadmap
