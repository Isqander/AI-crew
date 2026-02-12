# Архитектура AI-crew

## Обзор

AI-crew — self-hosted мультиагентная платформа, в которой команда из 5 ИИ-агентов
(PM, Analyst, Architect, Developer, QA) совместно выполняет задачи по разработке ПО:
от сбора требований до создания Pull Request.

Система построена на **LangGraph** (оркестрация) и **Aegra** (API-сервер,
совместимый с LangGraph Platform).

---

## Стек технологий

| Слой | Технология | Назначение |
|------|-----------|------------|
| Оркестрация | **LangGraph** | Граф агентов, state management, conditional edges |
| API-сервер | **Aegra** (FastAPI) | Agent Protocol, REST, SSE streaming, HITL interrupts |
| Web UI | **React + Vite + Tailwind** | Создание задач, чат, панель уточнений |
| БД | **PostgreSQL 16 + pgvector** | Checkpoints, состояния, история |
| Observability | **Langfuse v2** | Трейсинг LLM-вызовов, стоимость токенов |
| LLM | OpenAI-совместимый прокси | Любые модели через единый endpoint |
| Деплой | **Docker / Docker Compose** | Dev: отдельные контейнеры, Prod: all-in-one |

---

## Системная диаграмма

```
┌─────────────────────────────────────────────────────────┐
│                     Пользователь                         │
│          (Web UI :5173  /  LangGraph Studio)             │
└────────────────────────┬────────────────────────────────┘
                         │ REST API / Agent Protocol
┌────────────────────────▼────────────────────────────────┐
│                    Aegra Server :8000                     │
│  ┌──────────┐  ┌───────────┐  ┌───────────────────────┐ │
│  │ REST API │  │ Streaming │  │ Interrupt / Resume     │ │
│  │ (CRUD)   │  │ (SSE)     │  │ (Human-in-the-Loop)   │ │
│  └────┬─────┘  └─────┬─────┘  └──────────┬────────────┘ │
│       └───────────────┴──────────────────┬┘              │
│                  LangGraph Runtime        │               │
└──────────────────────────┬───────────────┘───────────────┘
                           │
        ┌──────────────────▼──────────────────┐
        │        dev_team Graph (LangGraph)    │
        │                                      │
        │  PM ─► Analyst ─► Architect          │
        │                       │              │
        │              Developer ◄─► QA        │
        │                       │              │
        │               git_commit ─► END      │
        └──────┬───────────┬──────────┬────────┘
               │           │          │
        ┌──────▼──┐  ┌─────▼───┐  ┌──▼───────┐
        │ LLM API │  │ GitHub  │  │PostgreSQL│
        │ (proxy) │  │   API   │  │(states)  │
        └─────────┘  └─────────┘  └──────────┘
```

---

## Граф агентов (dev_team)

### Пошаговый поток

```
START
  │
  ▼
 PM              → Разбивает задачу на подзадачи
  │
  ▼
 Analyst         → Собирает требования, user stories
  │                (может запросить HITL-уточнение)
  ▼
 Architect       → Проектирует архитектуру, выбирает стек
  │                (может запросить HITL-одобрение)
  ▼
 Developer       → Реализует код
  │
  ▼
 QA              → Ревью кода
  │
  ├─ issues → Developer        (Dev↔QA цикл, до 3 итераций)
  ├─ issues → architect_escalation  (после 3 итераций без Architect)
  ├─ issues → human_escalation     (после Architect + ещё 3 итерации)
  ├─ approved → git_commit → END
  └─ no issues → pm_final → END
```

### Escalation Ladder (Dev↔QA)

1. **Итерации 1-3** — обычный Dev↔QA цикл
2. **После 3 итераций** — Architect анализирует, какие баги критичны,
   а какие можно принять. Может вернуть в Dev (сброс счётчика) или одобрить.
3. **После Architect + ещё 3 итерации** — Human escalation через HITL.

### Human-in-the-Loop (HITL)

Граф компилируется с `interrupt_before=["clarification", "human_escalation"]`.
При достижении этих узлов выполнение приостанавливается. Пользователь отвечает
через Web UI, и граф продолжается с обновлённым state.

---

## Агенты

| Агент | Файл | Роль | Температура |
|-------|------|------|-------------|
| PM | `agents/pm.py` | Декомпозиция, координация, финальный обзор | 0.7 |
| Analyst | `agents/analyst.py` | Сбор требований, user stories, HITL-уточнения | 0.7 |
| Architect | `agents/architect.py` | Проектирование, выбор стека, QA-эскалация | 0.7 |
| Developer | `agents/developer.py` | Генерация кода, исправление багов | 0.2 |
| QA | `agents/qa.py` | Code review, валидация, итерационный счётчик | 0.3 |

### Модели по умолчанию

Настраиваются через env-переменные `LLM_MODEL_<ROLE>` или `DEFAULT_MODELS` в `base.py`.

| Роль | Модель по умолчанию |
|------|---------------------|
| PM | `gemini-claude-sonnet-4-5-thinking` |
| Analyst | `gemini-claude-sonnet-4-5-thinking` |
| Architect | `gemini-claude-opus-4-5-thinking` |
| Developer | `glm-4.7` |
| QA | `glm-4.7` |

### Паттерн агента

Каждый агент-модуль содержит:
1. **Класс** (`ProjectManagerAgent(BaseAgent)`) — бизнес-логика
2. **Singleton getter** (`get_pm_agent()`) — ленивая инициализация
3. **Node function** (`pm_agent(state) -> dict`) — точка входа для LangGraph

---

## State (DevTeamState)

`DevTeamState` — это `TypedDict`, передаваемый между всеми узлами графа.

```python
class DevTeamState(TypedDict):
    # --- Вход ---
    task: str                          # Описание задачи (обязательное)
    repository: NotRequired[str]       # GitHub repo (owner/name)
    context: NotRequired[str]          # Доп. контекст

    # --- Выходы агентов ---
    requirements: list[str]
    user_stories: list[UserStory]
    architecture: dict
    tech_stack: list[str]
    architecture_decisions: list[ArchitectureDecision]
    code_files: list[CodeFile]
    implementation_notes: str
    review_comments: list[str]
    test_results: dict
    issues_found: list[str]

    # --- Финальный результат ---
    pr_url: NotRequired[str]
    commit_sha: NotRequired[str]
    summary: str

    # --- Управление ---
    messages: Annotated[list[BaseMessage], add_messages]
    current_agent: str
    needs_clarification: bool
    clarification_question: NotRequired[str]
    clarification_response: NotRequired[str]
    qa_iteration_count: int
    architect_escalated: bool
    error: NotRequired[str]
    retry_count: int
```

---

## Инструменты (Tools)

| Модуль | Инструменты | Назначение |
|--------|-------------|------------|
| `tools/github.py` | `create_pull_request`, `create_branch`, `commit_file`, `get_file_content`, `list_repository_files` | Работа с GitHub API через PyGithub |
| `tools/filesystem.py` | `write_file`, `read_file`, `list_files`, `delete_file`, `create_directory` | Локальная файловая система (workspace) |

> **Примечание:** Сейчас GitHub-тулзы используются только внутри `git_commit_node`.
> Для агентов они пока не подключены через `bind_tools()`.

---

## Инфраструктура

### Aegra Server

Aegra — open-source бэкенд, совместимый с LangGraph Platform API.
Ключевой конфиг — `aegra.json`:

```json
{
  "graphs": {
    "dev_team": "./graphs/dev_team/graph.py:graph"
  }
}
```

Aegra загружает граф через `importlib`, инжектит PostgreSQL checkpointer,
и предоставляет REST API для управления threads/runs/assistants.

### PostgreSQL

- **Checkpoints** — персистентное хранение state графа (через `AsyncPostgresSaver`)
- **Aegra metadata** — assistants, threads, runs (через SQLAlchemy + Alembic)
- **pgvector** — расширение для будущей vector memory

### Langfuse

Self-hosted observability (v2). Трейсинг всех LLM-вызовов, подсчёт
стоимости токенов, оценка качества.

---

## Промпты

Хранятся в YAML-файлах: `graphs/dev_team/prompts/<agent>.yaml`

Каждый файл содержит:
- `system` — системный промпт (роль, правила)
- Именованные шаблоны (`task_decomposition`, `code_review`, и т.д.)
  с `{placeholder}` переменными

Загружаются через `load_prompts(agent_name)` из `base.py`.

---

## Развёртывание

| Режим | Конфигурация | Назначение |
|-------|-------------|------------|
| **Development** | `docker-compose.yml` | Отдельные контейнеры: postgres, aegra, frontend, langfuse |
| **Production** | `Dockerfile` | Единый контейнер: aegra + nginx/frontend + langfuse + PostgreSQL |

Подробнее: [deployment.md](deployment.md)

---

## Дерево файлов (ключевые)

```
AI-crew/
├── aegra.json                    # Конфиг Aegra (dev)
├── aegra.prod.json               # Конфиг Aegra (prod)
├── docker-compose.yml            # Docker Compose для разработки
├── Dockerfile                    # Production all-in-one image
├── env.example                   # Шаблон переменных окружения
├── requirements.txt              # Python-зависимости
│
├── graphs/                       # LangGraph графы
│   └── dev_team/                 # Граф команды разработки
│       ├── graph.py              #   Граф: узлы, рёбра, роутеры
│       ├── state.py              #   DevTeamState (TypedDict)
│       ├── agents/               #   Агенты
│       │   ├── base.py           #     LLM factory, BaseAgent, load_prompts
│       │   ├── pm.py             #     Project Manager
│       │   ├── analyst.py        #     Business Analyst
│       │   ├── architect.py      #     Software Architect
│       │   ├── developer.py      #     Developer (code gen)
│       │   └── qa.py             #     QA Engineer
│       ├── prompts/              #   YAML-промпты для каждого агента
│       │   ├── pm.yaml
│       │   ├── analyst.yaml
│       │   ├── architect.yaml
│       │   ├── developer.yaml
│       │   └── qa.yaml
│       └── tools/                #   LangChain tools
│           ├── github.py         #     GitHub API (PRs, commits)
│           └── filesystem.py     #     Локальная ФС
│
├── frontend/                     # React Web UI
│   └── src/
│       ├── api/aegra.ts          #   API-клиент Aegra
│       ├── components/           #   Chat, TaskForm, ProgressTracker, etc.
│       ├── pages/                #   Home, TaskDetail
│       ├── hooks/useTask.ts      #   React hook для задач
│       └── types/index.ts        #   TypeScript типы
│
├── tests/                        # Тесты проекта
│   ├── conftest.py               #   Фикстуры, моки
│   ├── test_state.py
│   ├── test_agents.py
│   ├── test_graph.py
│   ├── test_tools.py
│   └── test_integration.py
│
├── scripts/                      # Вспомогательные скрипты
│   ├── entrypoint.sh             #   Docker entrypoint (supervisor)
│   ├── start_aegra.py            #   Запуск Aegra из Python
│   ├── setup.sh / setup.ps1      #   Скрипты инициализации
│   └── nginx-frontend.conf       #   nginx конфиг (prod)
│
├── vendor/aegra/                 # Aegra (vendored, installed as package)
│   ├── src/agent_server/         #   Исходники сервера
│   ├── graphs/                   #   Примеры графов
│   └── tests/                    #   Тесты Aegra
│
└── docs/                         # Документация
    ├── architecture.md           #   Этот файл
    ├── GETTING_STARTED.md        #   Быстрый старт
    ├── DEVELOPMENT.md            #   Руководство разработчика
    ├── TESTING.md                #   Тестирование
    ├── deployment.md             #   Развёртывание (dev / prod)
    └── IDEAS.md                  #   Roadmap и идеи
```
