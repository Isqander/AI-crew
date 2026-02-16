# AI-crew: План рефакторинга

> Рабочий документ. Содержит выполненные и оставшиеся задачи рефакторинга.
>
> Дата: 15 февраля 2026
> Связанные: [ARCHITECTURE_V2.md](ARCHITECTURE_V2.md), [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)

---

## Принципы рефакторинга

1. **Уменьшение хрупкости** — устранение критических багов, защита от регрессий
2. **Устранение дублирования** — DRY: общие модули вместо copy-paste
3. **Консистентность** — единые паттерны и сигнатуры во всей кодовой базе
4. **Читаемость** — файлы разумного размера, понятная структура модулей
5. **Подготовка к расширению** — архитектура, которая хорошо масштабируется с ростом функционала

---

## Выполнено (Фазы 1-7)

### Фаза 1: Критические баги [DONE]

| # | Проблема | Исправление | Файл |
|---|----------|-------------|------|
| 1 | `architect.py` использует `qa_iteration_count` вместо `review_iteration_count` | Заменено на `review_iteration_count` во всех 3 местах | `agents/architect.py` |
| 2 | Clarification всегда ведёт в analyst, даже если architect спросил | Добавлен `route_after_clarification()` с маршрутизацией по `clarification_context` | `graph.py` |
| 3 | `architect_agent()` не принимает `config` — без retry и callbacks | Добавлен `config` во все методы + `_invoke_chain` вместо `chain.invoke` | `agents/architect.py` |
| 4 | `SecurityAgent` не экспортируется в `agents/__init__.py` | Добавлен импорт и экспорт | `agents/__init__.py` |
| 5 | `web_tools` не экспортируются в `tools/__init__.py` | Добавлен импорт, экспорт, и `web_tools` bundle | `tools/__init__.py` |
| 6 | `DEFAULT_MODELS` не содержит `reviewer`, `security`, `router` | Добавлены все роли | `agents/base.py` |

### Фаза 2: Общий модуль `graphs/common/` [DONE]

**Создано:**
- `graphs/common/__init__.py` — экспорт всего общего
- `graphs/common/types.py` — `CodeFile`, `UserStory`, `ArchitectureDecision`
- `graphs/common/utils.py` — `build_code_summary()`, `format_code_files()`
- `graphs/common/git.py` — `make_git_commit_node()` (фабрика)
- `graphs/common/logging.py` — `configure_logging()` (идемпотентная)

**Обновлено:**
- `dev_team/state.py` — импорт типов из `common.types`
- `dev_team/graph.py` — `git_commit_node = make_git_commit_node("dev_team")`
- `dev_team/logging_config.py` — реэкспорт из `common.logging`
- `simple_dev/state.py` — импорт `CodeFile` из `common.types`
- `simple_dev/graph.py` — используют `common.git`, `common.logging`
- `standard_dev/state.py` — импорт `CodeFile` из `common.types`
- `standard_dev/graph.py` — используют `common.git`, `common.logging`
- `qa_agent_test/state.py` — импорт `CodeFile` из `common.types`

**Устранённое дублирование:**
- `CodeFile` TypedDict: было 4 копии → 1 источник
- `_build_code_summary()`: было 3 копии → 1 источник
- `git_commit_node()`: было 3 копии → 1 фабрика
- `configure_logging()`: теперь идемпотентная (safe to call multiple times)

### Фаза 3: Gateway cleanup [DONE]

**Создано:**
- `gateway/graph_loader.py` — единый модуль загрузки манифестов, конфигов, промптов

**Обновлено:**
- `gateway/endpoints/graph.py` — используют `graph_loader` вместо собственных `_load_*`
- `gateway/router.py` — используют `graph_loader.load_manifests()` вместо `_load_graph_manifests()`

**Устранённое дублирование:**
- Загрузка манифестов: было 2 реализации → 1 источник
- Пути к `graphs/`, `config/`: стандартизированы в `graph_loader`

### Фаза 4: Консистентность агентов [DONE]

- Все node functions имеют сигнатуру `(state, config=None) -> dict`
- Все LLM-вызовы проходят через `_invoke_chain()` (retry + callbacks)
- `DEFAULT_MODELS` содержит все 7 ролей + `router`

### Фаза 6.1: Frontend API централизация [DONE]

- Добавлены методы `login()`, `register()`, `getGraphConfig()`, `getGraphTopology()`, `createStreamResponse()` в `aegraClient`
- Добавлен `getBaseUrl()` для отображения URL в UI
- `streamRun()` переписан через `createStreamResponse()` (устранение дублирования)
- `useAuth.ts` — использует `aegraClient` вместо raw `fetch`
- `useStreamingTask.ts` — использует `aegraClient.createStreamResponse()` вместо raw `fetch`, `DevTeamState` импортируется из `types/`
- `Settings.tsx` — использует `aegraClient.getGraphConfig()` вместо raw `fetch`
- `GraphVisualization.tsx` — использует `aegraClient.getGraphTopology()` вместо raw `fetch`
- Убраны дублированные `API_URL`, `useAuthStore.getState().accessToken` из всех файлов кроме `aegra.ts`

---

## Оставшиеся задачи

### ~~Фаза 5: Разбиение QA-агента~~ [DONE]

**~1235 строк → 5 модулей:**

```
agents/
├── qa.py               # ~180 строк: оркестратор + backward-compat wrappers
├── qa_helpers.py        # ~170 строк: parse_verdict, parse_issues, parse_defects, extract_json, ...
├── qa_sandbox.py        # ~250 строк: detect_language, build_commands, run_sandbox_tests
├── qa_browser.py        # ~260 строк: has_ui, run_browser_tests, UI_INDICATORS
└── qa_exploration.py    # ~310 строк: run_exploration_tests, validation, report parsing
```

- Подмодули принимают `agent: QAAgent` через `TYPE_CHECKING` (без circular imports)
- `QAAgent` содержит backward-compatible static wrappers для тестов
- Все тесты работают без изменений (та же API на `QAAgent`)

### Фаза 6: Frontend (оставшееся)

**Приоритет: СРЕДНИЙ | Сложность: 4/10 | Время: 3-5 часов**

#### ~~6.1 Устранение остатков raw fetch~~ [DONE]

#### ~~6.2 Token refresh~~ [DONE]
- Добавлен `tryRefreshToken()` с coalescing concurrent запросов
- Interceptor в `fetch()` и `createStreamResponse()`: 401 → refresh → retry
- Если refresh не удался → `logout()`

#### ~~6.3 Типобезопасность~~ [DONE]
- `ThreadMetadata` — типизирована `metadata.task`, `metadata.graph_id` (убрано `as any` из Tasks.tsx, Home.tsx)
- `StateMessage` — типизированы сообщения из LangGraph state (убрано `any` из useTask.ts)
- `GraphTopology`, `TopologyNode`, `TopologyEdge`, `AgentConfig`, `PromptInfo` — полная типизация GraphVisualization
- `AgentNodeData` — типизирован data prop AgentNode
- Zero `any` в frontend/src/**

#### ~~6.4 Общие компоненты (частично)~~ [DONE]
- `ErrorBanner` — создан переиспользуемый компонент (simple и rich mode), заменено 5 вхождений в Login, Register, Home, Tasks, TaskDetail
- _Осталось:_ `FormInput`, конфигурируемый `ProgressTracker`

#### ~~6.5 Error Boundary~~ [DONE]
- `ErrorBoundary` — class component, оборачивает всё приложение в `App.tsx`
- `ErrorFallback` UI с "Перезагрузить" / "Выйти"

### Фаза 7: Тесты

**Приоритет: ВЫСОКИЙ | Сложность: 3/10 | Время: 2-4 часа**

#### ~~7.1 Убрать дублирование path setup~~ [DONE]
- Удалён `sys.path.insert` из 6 тестовых файлов (оставлен только в conftest.py)
- Удалены неиспользуемые импорты `sys`, `Path`, `os` где применимо
- Переменные `_GRAPHS_DIR` заменены на inline `Path` конструкции где нужны (test_reviewer_and_qa, test_new_graphs)

#### ~~7.2 Обновить тесты после рефакторинга~~ [DONE]
- `_parse_approved` → `_parse_verdict` (test_reviewer_and_qa.py) — исправлены имена методов и сигнатуры
- `dev_team.graph.commit_and_create_pr` → `dev_team.tools.git_workspace.commit_and_create_pr` (test_new_graphs.py, test_graph.py)
- `gateway.router._load_graph_manifests` → `gateway.graph_loader.load_manifests` (test_router.py, test_new_graphs.py)
- `dev_team.agents.qa.EXPLORATION_MAX_STEPS` → `dev_team.agents.qa_exploration.EXPLORATION_MAX_STEPS` (test_qa_exploration.py)

#### 7.3 Структурирование тестов (будущее)
```
tests/
├── conftest.py              # ЕДИНСТВЕННЫЙ path setup + общие fixtures
├── common/                  # Тесты для graphs/common/
│   ├── test_types.py
│   ├── test_utils.py
│   └── test_git.py
├── test_gateway/
│   ├── test_graph_loader.py # Новый: тесты для единого загрузчика
│   └── ...
└── ...
```

### Фаза 8: Парсинг LLM-ответов (будущее)

**Приоритет: НИЗКИЙ | Сложность: 5/10 | Время: 5-8 часов**

Несколько агентов (analyst, reviewer, architect, qa) используют хрупкий string-based парсинг:
- `"approve_with_notes" in content.lower()` (architect)
- Парсинг по ключевым словам и заголовкам (reviewer, qa)

**Цель:** Переход на structured output (`.with_structured_output()`) где это возможно, без ломки промптов.

**Шаги:**
1. Определить Pydantic-модели для ответов агентов
2. Использовать `llm.with_structured_output(model)` вместо raw string parsing
3. Оставить fallback на string parsing для моделей, не поддерживающих structured output

### Фаза 9: Telegram — устойчивость (будущее)

**Приоритет: НИЗКИЙ | Сложность: 2/10 | Время: 1-2 часа**

- Заменить глобальный `_active_tasks` на dict с TTL (или persistence)
- Добавить retry при создании задачи (при ошибке Gateway)
- Убрать хрупкий `bot.__dict__["gateway"]` → dependency injection через middleware

---

## Обновление файловой структуры (целевая после рефакторинга)

```
graphs/
├── common/                     # NEW: общий код для всех графов
│   ├── __init__.py
│   ├── types.py                # CodeFile, UserStory, ArchitectureDecision
│   ├── utils.py                # build_code_summary, format_code_files
│   ├── git.py                  # make_git_commit_node (фабрика)
│   └── logging.py              # configure_logging (идемпотентная)
├── dev_team/
│   ├── state.py                # UPDATED: imports from common.types
│   ├── graph.py                # UPDATED: uses common.git, common.logging
│   ├── logging_config.py       # UPDATED: re-export from common.logging
│   ├── agents/
│   │   ├── __init__.py         # UPDATED: exports SecurityAgent
│   │   ├── base.py             # UPDATED: all roles in DEFAULT_MODELS
│   │   ├── architect.py        # FIXED: review_iteration_count, config, _invoke_chain
│   │   ├── qa.py               # TODO: split into submodules (Phase 5)
│   │   └── ...
│   └── tools/
│       ├── __init__.py         # UPDATED: exports web_tools
│       └── ...
├── simple_dev/                 # UPDATED: uses common
├── standard_dev/               # UPDATED: uses common
├── research/
└── qa_agent_test/              # UPDATED: uses common.types

gateway/
├── graph_loader.py             # NEW: единая загрузка манифестов/конфигов
├── endpoints/graph.py          # UPDATED: uses graph_loader
├── router.py                   # UPDATED: uses graph_loader
└── ...

frontend/src/
├── api/aegra.ts                # UPDATED: centralized client + token refresh + streaming
├── types/index.ts              # UPDATED: ThreadMetadata, StateMessage, GraphTopology, AgentConfig, ...
├── hooks/
│   ├── useAuth.ts              # UPDATED: uses aegraClient
│   └── useStreamingTask.ts     # UPDATED: uses aegraClient.createStreamResponse
├── components/
│   ├── ErrorBanner.tsx         # NEW: reusable error display (simple + rich mode)
│   ├── ErrorBoundary.tsx       # NEW: React Error Boundary
│   └── GraphVisualization.tsx  # UPDATED: typed topology, uses aegraClient
├── pages/
│   ├── Tasks.tsx               # UPDATED: typed metadata, ErrorBanner
│   ├── Home.tsx                # UPDATED: ErrorBanner
│   ├── TaskDetail.tsx          # UPDATED: ErrorBanner
│   ├── Login.tsx               # UPDATED: ErrorBanner
│   ├── Register.tsx            # UPDATED: ErrorBanner
│   └── Settings.tsx            # UPDATED: uses aegraClient.getGraphConfig
└── App.tsx                     # UPDATED: wrapped in ErrorBoundary
```

---

## Приоритеты (рекомендуемый порядок оставшихся задач)

1. **Фаза 7.3** — структурирование тестов (отдельные папки для common, gateway)
2. **Фаза 6 (minor)** — `FormInput`, конфигурируемый `ProgressTracker`
3. **Фаза 8** — structured output парсинг (надёжность)
4. **Фаза 9** — telegram устойчивость (minor)
