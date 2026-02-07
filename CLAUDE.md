# CLAUDE.md — AI-crew

> Контекст для Claude Code / Claude при работе с этим проектом.

## Проект

AI-crew — мультиагентная платформа на LangGraph. Команда из 5 ИИ-агентов
(PM, Analyst, Architect, Developer, QA) выполняет задачи по разработке ПО:
от требований до Pull Request в GitHub.

## Структура

```
graphs/dev_team/          # Основной код проекта
  graph.py                # LangGraph граф (узлы, рёбра, роутеры)
  state.py                # DevTeamState (TypedDict — shared state)
  agents/                 # 5 агентов + base.py (LLM factory)
  prompts/                # YAML-промпты для каждого агента
  tools/                  # GitHub API + filesystem tools
frontend/                 # React + Vite + Tailwind Web UI
tests/                    # pytest тесты
vendor/aegra/             # Aegra server (vendored, не модифицировать)
docs/                     # Документация
```

## Ключевые файлы для редактирования

- `graphs/dev_team/graph.py` — граф: добавление узлов, рёбер, роутеров
- `graphs/dev_team/state.py` — state: добавление полей
- `graphs/dev_team/agents/*.py` — логика агентов
- `graphs/dev_team/prompts/*.yaml` — промпты
- `graphs/dev_team/agents/base.py` — LLM конфигурация, BaseAgent

## Команды

```bash
# Тесты
pytest tests/ -v
pytest tests/test_graph.py -v       # Только тесты графа

# Docker (development)
docker-compose up -d                # Запуск всех сервисов
docker-compose logs -f aegra        # Логи бэкенда
docker-compose down                 # Остановка

# Линтинг
ruff check graphs/
```

## Паттерны кода

- **Агенты:** каждый модуль экспортирует node function `*_agent(state) -> dict`
- **LLM:** все модели через `get_llm(role=..., temperature=...)` из `base.py`,
  используют единый OpenAI-совместимый прокси (env `LLM_API_URL` / `LLM_API_KEY`)
- **Промпты:** YAML-файлы с `system` + именованными шаблонами, загружаются через `load_prompts()`
- **State:** `DevTeamState` — `TypedDict` с `NotRequired` для optional-полей
- **Singleton:** каждый агент — lazy singleton через `get_*_agent()`
- **Логирование:** `logging.getLogger(__name__)` в каждом модуле

## Важно

- `vendor/aegra/` — внешняя зависимость, НЕ редактировать
- `graph.py` использует абсолютные импорты (`from dev_team.*`), не относительные —
  это связано с тем, как Aegra загружает графы через importlib
- Граф компилируется с `interrupt_before=["clarification", "human_escalation"]`
  для Human-in-the-Loop

## Документация

- [docs/architecture.md](docs/architecture.md) — полная архитектура, state-модель, диаграммы
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) — как добавить агента, изменить промпты, настроить LLM
- [docs/TESTING.md](docs/TESTING.md) — тесты, фикстуры, CI/CD
- [docs/deployment.md](docs/deployment.md) — Docker Compose (dev) и Dockerfile (prod)
- [docs/IDEAS.md](docs/IDEAS.md) — roadmap
