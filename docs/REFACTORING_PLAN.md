# AI-crew: План рефакторинга

> Рабочий документ. Содержит выполненные и оставшиеся задачи рефакторинга.
>
> Дата: 16 февраля 2026
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

### Фаза 9: Telegram — устойчивость (частично выполнено)

**Приоритет: НИЗКИЙ | Сложность: 2/10 | Время: 1-2 часа**

- Заменить глобальный `_active_tasks` на dict с TTL (или persistence)
- Добавить retry при создании задачи (при ошибке Gateway)
- ~~Убрать хрупкий `bot.__dict__["gateway"]` → dependency injection через middleware~~ [DONE в Фазе 13]

---

## Выполнено (Фазы 10-14) — 16 февраля 2026

### Фаза 10: Хрупкие зависимости [DONE]

| # | Проблема | Исправление | Файл |
|---|----------|-------------|------|
| 1 | `DEFAULT_MODELS` не содержит `researcher` — подбирается fallback | Добавлен `"researcher": "gemini-claude-sonnet-4-5-thinking"` | `agents/base.py` |
| 2 | Хрупкий путь `Path(__file__).parent.parent.parent.parent` к `config/` | Создан `PROJECT_ROOT` в `common/__init__.py` через поиск маркеров `config/` + `graphs/` | `common/__init__.py`, `agents/base.py` |
| 3 | Импорт `from dev_team.logging_config` в `research/` и `qa_agent_test/` | Заменён на `from common.logging import configure_logging` | `research/graph.py`, `qa_agent_test/graph.py` |
| 4 | Мёртвый код `process_clarification` в `graph.py` | Удалён (clarification обрабатывается внутри агентов) | `dev_team/graph.py` |
| 5 | Тест `test_logging_config_exists` проверял `structlog` в реэкспорт-файле | Тест обновлён: проверяет `common/logging.py` | `tests/test_wave1_verification.py` |

### Фаза 11: Устранение дублирования [DONE]

| # | Проблема | Исправление | Файл |
|---|----------|-------------|------|
| 1 | Дублирование `format_code_files` (ручной join) в 3 агентах | Импорт и использование `format_code_files` из `common.utils` | `reviewer.py`, `security.py`, `architect.py` |
| 2 | Мёртвый `_PROXY_PREFIXES` в Gateway | Удалён | `gateway/main.py` |
| 3 | Дублирование логики `build_agent_configs` в 2 эндпоинтах | Вынесено в `graph_loader.build_agent_configs()` | `gateway/graph_loader.py`, `gateway/endpoints/graph.py` |

### Фаза 12: Gateway cleanup [DONE]

- `build_agent_configs()` — объединяет `manifest.agents` с глобальным `agents.yaml`, возвращает готовые конфиги
- Оба эндпоинта (`graph_topology`, `graph_config`) используют единый хелпер

### Фаза 13: Telegram DI [DONE]

| # | Проблема | Исправление | Файл |
|---|----------|-------------|------|
| 1 | Хрупкий `bot.__dict__["gateway"]` для DI | Заменён на `dp["gateway"]` (aiogram 3 Dispatcher context) | `telegram/bot.py` |
| 2 | Все хендлеры тянули gateway через `message.bot.__dict__` | Хендлеры принимают `gateway: GatewayClient` через aiogram DI | `telegram/handlers.py` |
| 3 | Дефолтный пароль не предупреждается | Добавлен `logger.warning` при `TELEGRAM_BOT_PASSWORD == "botpassword123"` | `telegram/bot.py` |

### Фаза 14: Frontend cleanup [DONE]

| # | Проблема | Исправление | Файл |
|---|----------|-------------|------|
| 1 | Дублирование маппинга `StateMessage → Message` в 2 файлах | Вынесен `mapStateMessages()` в `types/index.ts` | `types/index.ts`, `aegra.ts`, `useTask.ts` |
| 2 | Неиспользуемый импорт `AGENTS` в `Chat.tsx` | Убран из импорта | `components/Chat.tsx` |
| 3 | 6 мёртвых CSS-классов (`.glow-magenta`, `.cursor-blink`, `.agent-*`) | Удалены из `index.css` | `frontend/src/index.css` |
| 4 | `useStreamingTask` — неиспользуемый хук без пояснений | Добавлен JSDoc-комментарий о назначении (резерв для Wave 2 SSE) | `hooks/useStreamingTask.ts` |

---

## Обновление файловой структуры (целевая после рефакторинга)

```
graphs/
├── common/                     # Общий код для всех графов
│   ├── __init__.py             # Экспорт + PROJECT_ROOT (динамический поиск корня)
│   ├── types.py                # CodeFile, UserStory, ArchitectureDecision
│   ├── utils.py                # build_code_summary, format_code_files
│   ├── git.py                  # make_git_commit_node (фабрика)
│   └── logging.py              # configure_logging (идемпотентная)
├── dev_team/
│   ├── state.py                # imports from common.types
│   ├── graph.py                # uses common.git, common.logging; без мёртвого process_clarification
│   ├── logging_config.py       # re-export from common.logging
│   ├── agents/
│   │   ├── __init__.py         # exports SecurityAgent
│   │   ├── base.py             # all roles in DEFAULT_MODELS (incl. researcher), PROJECT_ROOT для config
│   │   ├── architect.py        # FIXED: review_iteration_count, config, _invoke_chain; uses format_code_files
│   │   ├── reviewer.py         # uses format_code_files from common.utils
│   │   ├── security.py         # uses format_code_files from common.utils
│   │   └── ...
│   └── tools/
│       ├── __init__.py         # exports web_tools
│       └── ...
├── simple_dev/                 # uses common
├── standard_dev/               # uses common
├── research/                   # uses common.logging (не dev_team.logging_config)
└── qa_agent_test/              # uses common.types, common.logging

gateway/
├── graph_loader.py             # Единая загрузка манифестов/конфигов + build_agent_configs()
├── main.py                     # Без мёртвого _PROXY_PREFIXES
├── endpoints/graph.py          # uses graph_loader.build_agent_configs()
├── router.py                   # uses graph_loader
└── ...

telegram/
├── bot.py                      # dp["gateway"] вместо bot.__dict__; warning при дефолтном пароле
├── handlers.py                 # gateway через aiogram DI (параметр функции)
└── ...

frontend/src/
├── api/aegra.ts                # centralized client + token refresh + streaming; uses mapStateMessages
├── types/index.ts              # ThreadMetadata, StateMessage, mapStateMessages(), GraphTopology, AgentConfig, ...
├── hooks/
│   ├── useAuth.ts              # uses aegraClient
│   ├── useTask.ts              # uses mapStateMessages
│   └── useStreamingTask.ts     # JSDoc: зарезервирован для Wave 2 SSE
├── components/
│   ├── Chat.tsx                # без неиспользуемого импорта AGENTS
│   ├── ErrorBanner.tsx         # reusable error display (simple + rich mode)
│   ├── ErrorBoundary.tsx       # React Error Boundary
│   └── GraphVisualization.tsx  # typed topology, uses aegraClient
├── pages/
│   ├── Tasks.tsx               # typed metadata, ErrorBanner
│   ├── Home.tsx                # ErrorBanner
│   ├── TaskDetail.tsx          # ErrorBanner
│   ├── Login.tsx               # ErrorBanner
│   ├── Register.tsx            # ErrorBanner
│   └── Settings.tsx            # uses aegraClient.getGraphConfig
├── index.css                   # без мёртвых CSS-классов (.glow-magenta, .cursor-blink, .agent-*)
└── App.tsx                     # wrapped in ErrorBoundary
```

---

## Приоритеты (рекомендуемый порядок оставшихся задач)

1. **Фаза 7.3** — структурирование тестов (отдельные папки для common, gateway)
2. **Фаза 6 (minor)** — `FormInput`, конфигурируемый `ProgressTracker`
3. **Фаза 8** — structured output парсинг (надёжность)
4. **Фаза 9 (остаток)** — `_active_tasks` с TTL, retry создания задач
