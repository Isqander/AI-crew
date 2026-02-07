# AGENTS.md — AI-crew

> Контекст для ИИ-агентов (Codex, GitHub Copilot Workspace, и т.д.)

## Что это за проект

AI-crew — мультиагентная платформа разработки на LangGraph.
5 ИИ-агентов (PM, Analyst, Architect, Developer, QA) совместно выполняют
задачи по разработке ПО — от сбора требований до создания Pull Request.

## Ключевые файлы

| Файл | Что делает |
|------|-----------|
| `graphs/dev_team/graph.py` | Главный граф: узлы, рёбра, роутеры |
| `graphs/dev_team/state.py` | `DevTeamState` — shared state (TypedDict) |
| `graphs/dev_team/agents/base.py` | LLM factory (`get_llm`), `BaseAgent`, `load_prompts` |
| `graphs/dev_team/agents/pm.py` | Project Manager |
| `graphs/dev_team/agents/analyst.py` | Business Analyst |
| `graphs/dev_team/agents/architect.py` | Software Architect |
| `graphs/dev_team/agents/developer.py` | Developer (code generation) |
| `graphs/dev_team/agents/qa.py` | QA Engineer (code review) |
| `graphs/dev_team/prompts/*.yaml` | YAML-промпты для каждого агента |
| `graphs/dev_team/tools/github.py` | GitHub API tools (PRs, commits) |
| `graphs/dev_team/tools/filesystem.py` | Local filesystem tools |
| `aegra.json` | Конфиг Aegra (регистрация графов) |
| `docker-compose.yml` | Development инфраструктура |
| `env.example` | Шаблон переменных окружения |

## Граф агентов (поток)

```
PM → Analyst → Architect → Developer → QA → git_commit → END
       ↕           ↕                    ↕
   clarification  clarification    Dev↔QA loop (≤3)
   (HITL)         (HITL)              ↓
                               architect_escalation
                                      ↓
                               human_escalation (HITL)
```

## Паттерн агента

Каждый модуль агента содержит:
1. **Класс** (наследует `BaseAgent`) — бизнес-логика
2. **Singleton getter** (`get_*_agent()`) — ленивая инициализация
3. **Node function** (`*_agent(state) -> dict`) — точка входа для LangGraph

## Команды

```bash
pytest tests/ -v                  # Запуск тестов
docker-compose up -d              # Запуск dev-окружения
docker-compose logs -f aegra      # Логи Aegra
```

## Полная документация

- [Архитектура](docs/architecture.md) — детальное описание системы
- [Разработка](docs/DEVELOPMENT.md) — как добавить агента, изменить промпты
- [Тестирование](docs/TESTING.md) — тесты, фикстуры
- [Развёртывание](docs/deployment.md) — Docker

## vendor/aegra/

Директория `vendor/aegra/` содержит Aegra server — open-source бэкенд,
совместимый с LangGraph Platform API. Устанавливается как pip-пакет
при сборке Docker-образа. Код Aegra **не модифицируется** напрямую.
