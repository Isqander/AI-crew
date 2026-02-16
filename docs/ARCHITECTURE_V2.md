# AI-crew: Целевая системная архитектура v2

> Полное описание целевой архитектуры после Волн 1 и 2.
> Включает: компоненты, API-контракты, модели данных, протоколы, безопасность.
> 
> Дата: 15 февраля 2026 (обновлено: QA & Testing Evolution)
> Основан на: [EVOLUTION_PLAN_V3.md](EVOLUTION_PLAN_V3.md)

---

## Содержание

1. [Обзор системы](#1-обзор-системы)
2. [Каталог компонентов](#2-каталог-компонентов)
3. [Сетевая архитектура](#3-сетевая-архитектура)
4. [Gateway API — контракт](#4-gateway-api)
5. [CLI Runner API — контракт](#5-cli-runner-api)
6. [Общие модели данных](#6-общие-модели-данных)
7. [Конфигурационные схемы](#7-конфигурационные-схемы)
8. [Протоколы взаимодействия](#8-протоколы-взаимодействия)
9. [Безопасность](#9-безопасность)
10. [Data Layer](#10-data-layer)
11. [Observability и мониторинг](#11-observability)
12. [Решённые вопросы](#12-открытые-вопросы)
- [Приложение A: Docker Compose](#приложение-a)
- [Приложение B: Структура файлов](#приложение-b)
- [Приложение C: Архитектура Visual QA Testing](#appendix-c-visual-qa)
- [Приложение D: Эволюция QA & Testing](#appendix-d-qa-evolution)

---

## 1. Обзор системы

AI-crew — self-hosted мультиагентная платформа. Команды ИИ-агентов выполняют
задачи по разработке ПО: от сбора требований до создания PR и деплоя.

**Ключевые принципы:**
- **Python-first графы** — LangGraph графы определяются в Python, экспортируются в JSON для визуализации
- **Gateway-first доступ** — все внешние запросы через FastAPI Gateway (auth, routing, proxy)
- **Git-as-truth** — код передаётся через GitHub branches, не через файловую систему
- **Pluggable graphs** — система поддерживает несколько графов (dev_team, research_team, ...) через `manifest.yaml` + Aegra
- **HITL опционален** — каждый граф сам определяет, где нужен Human-in-the-Loop

---

## 2. Каталог компонентов

### 2.1 Сводная таблица

| Компонент | Тип | Порт (внешний) | Порт (внутренний) | Описание |
|-----------|-----|----------------|-------------------|----------|
| **Gateway** | FastAPI | 8081 | 8081 | Auth, routing, proxy к Aegra, расширенные endpoints |
| **Aegra** | FastAPI (LangGraph) | — | 8000 | LangGraph Runtime, Agent Protocol API |
| **Frontend** | React + Vite | 5173 | 5173 | Web UI |
| **PostgreSQL** | Database | 5433 | 5433 | Checkpoints, users, metadata |
| **Langfuse** | NextJS | 3001 | 3001 | LLM tracing, costs |
| **Telegram Bot** | Python (aiogram) | — | — | Telegram-интерфейс (polling) |
| **Sandbox** | FastAPI + Docker | — | 8002 | Code execution (DinD), QA sandbox testing |
| **CLI Runner** | FastAPI | — | 8001 | Отдельная VPS для CLI-агентов |
| **Prefect Server** | Prefect | — | 4200 | Мониторинг деплоев (на VPS деплоя) |

### 2.2 Ответственности компонентов

**Gateway** — единственная внешняя точка входа для API:
- JWT-аутентификация (register, login, refresh)
- Switch-Agent (авто-маршрутизация задач по графам)
- Прокси к Aegra (REST + SSE streaming)
- Собственные endpoints (graph topology, graph list, analytics)
- Rate limiting, CORS

**Aegra** — LangGraph Runtime:
- Управление threads, runs, assistants (Agent Protocol)
- Выполнение LangGraph графов
- PostgreSQL checkpointing
- SSE streaming состояния
- Langfuse интеграция (callbacks)

**Frontend** — пользовательский интерфейс:
- Аутентификация (Login/Register)
- Создание задач с выбором графа
- Real-time streaming чат
- Визуализация графа (React Flow)
- HITL-ответы на уточнения

**Telegram Bot** — альтернативный интерфейс:
- Создание задач
- Получение статуса
- HITL-ответы
- Уведомления о завершении

**Sandbox** — безопасное выполнение кода:
- Docker-in-Docker
- Timeout + resource limits
- Запуск тестов, lint-проверок
- Возврат stdout/stderr/exit_code
- Используется QA-агентом для проверки сгенерированного кода
- Два типа образов: стандартные (python, node) и browser-образы (Playwright + Chromium)
- Постоянные сервисы: PostgreSQL и Redis для проектов, Nexus proxy для кэша пакетов (см. [Приложение D, §D.2](#appendix-d-qa-evolution))
- Инструменты анализа: lighthouse, axe-core, pip-audit (в browser-образах)

**CLI Runner** — мощные CLI-агенты (отдельная VPS):
- Claude Code (`-p` headless mode) / Codex
- Git clone → execute → commit → push
- Любая роль (developer, architect, researcher)
- API-обёртка для вызова из графов

**Prefect Server** (на VPS деплоя, не на основной):
- Визуализация запущенных deployment-задач
- Не влияет на цикл деплоя, работает рядом
- UI для мониторинга того, что развёрнуто

---

## 3. Сетевая архитектура

### 3.1 Основная VPS (AI-crew платформа)

```
                        Интернет
                           │
          ┌────────────────┼────────────────┐
          │                │                │
          ▼                ▼                ▼
    ┌──────────┐   ┌───────────┐   ┌───────────┐
    │ Gateway  │   │ Frontend  │   │ Langfuse  │
    │  :8081   │   │  :5173    │   │  :3001    │
    │ (JWT)    │   │ (React)   │   │ (свой auth)│
    └────┬─────┘   └───────────┘   └───────────┘
         │
    ─────┼──── docker internal network (aicrew-network) ────
         │
    ┌────┼─────────────────────────────────┐
    │    ▼           │            │        │
    │  Aegra      Telegram    Sandbox     │
    │  :8000      (polling)   :8002       │
    │  (no auth)  (no ports)  (no ports)  │
    └────┬──────────────────────┬─────────┘
         │                      │
    ┌────▼──────────────────────▼─────────┐
    │          PostgreSQL :5433             │
    │  (checkpoints, users, langfuse)      │
    └──────────────────────────────────────┘
```

**Порты наружу:**
| Порт | Сервис | Доступ | Комментарий |
|------|--------|--------|-------------|
| 8081 | Gateway | JWT-protected | Единственный API-вход |
| 5173 | Frontend | Открыт | Статика (в проде через nginx) |
| 3001 | Langfuse | Свой auth | NextAuth |
| 5433 | PostgreSQL | Открыт | Для прямого доступа (позже закроем) |

### 3.2 VPS для деплоя (целевые приложения)

```
    ┌─────────────────────────────────────────┐
    │  VPS Deploy                              │
    │                                          │
    │  Traefik (reverse proxy, Let's Encrypt)  │
    │  ├── app1.31.59.58.143.nip.io           │
    │  ├── app2.31.59.58.143.nip.io           │
    │  └── ...                                 │
    │                                          │
    │  Prefect Server :4200 (мониторинг)      │
    │                                          │
    │  GitHub Actions self-hosted runner        │
    └─────────────────────────────────────────┘
```

### 3.3 VPS для CLI-агентов (отдельная от деплоя)

```
    ┌─────────────────────────────────────────┐
    │  VPS CLI                                 │
    │                                          │
    │  CLI Runner API :8001                    │
    │  ├── Claude Code (installed)            │
    │  ├── Codex (installed)                  │
    │  └── /workspace/{job_id}/ (temp dirs)   │
    │                                          │
    │  Auth: API key или mTLS                  │
    └─────────────────────────────────────────┘
```

---

## 4. Gateway API — контракт {#4-gateway-api}

### 4.1 Аутентификация

```
POST /auth/register
  Body: { email: str, password: str, display_name: str }
  Response 201: { user: User, access_token: str, refresh_token: str }
  Errors: 400 (validation), 409 (email exists)

POST /auth/login
  Body: { email: str, password: str }
  Response 200: { user: User, access_token: str, refresh_token: str }
  Errors: 401 (invalid credentials)

POST /auth/refresh
  Body: { refresh_token: str }
  Response 200: { access_token: str, refresh_token: str }
  Errors: 401 (token expired/invalid)

GET /auth/me
  Headers: Authorization: Bearer <access_token>
  Response 200: User
  Errors: 401 (unauthorized)
```

**Модель User:**
```python
class User(BaseModel):
    id: str                # UUID
    email: str
    display_name: str
    created_at: datetime
    is_active: bool
```

**JWT payload:**
```json
{
  "sub": "<user_id>",
  "email": "<email>",
  "exp": "<expiration>",
  "iat": "<issued_at>",
  "type": "access"        // "access" | "refresh"
}
```

**Параметры JWT:**
- Access token TTL: 30 минут
- Refresh token TTL: 7 дней
- Алгоритм: HS256
- Secret: `JWT_SECRET` env var

### 4.2 Граф-endpoints

```
GET /graph/list
  Headers: Authorization: Bearer <token>
  Response 200: GraphListResponse
  Описание: Список доступных графов из manifest.yaml файлов

GET /graph/topology/{graph_id}
  Headers: Authorization: Bearer <token>
  Response 200: GraphTopologyResponse
  Описание: Полная информация о графе для визуализации

GET /graph/config/{graph_id}
  Headers: Authorization: Bearer <token>
  Response 200: GraphConfigResponse
  Описание: Конфигурация агентов графа (модели, температуры)
```

**Модели ответов:**

```python
class AgentBrief(BaseModel):
    id: str                    # "pm"
    display_name: str          # "Project Manager"

class GraphListItem(BaseModel):
    graph_id: str              # "dev_team"
    display_name: str          # "Development Team"
    description: str
    version: str
    task_types: list[str]      # ["new_project", "feature", "bugfix"]
    agents: list[AgentBrief]   # [{id, display_name}]
    features: list[str]        # ["hitl_clarification", "git_commit"]

class GraphListResponse(BaseModel):
    graphs: list[GraphListItem]

class GraphTopologyResponse(BaseModel):
    graph_id: str
    topology: dict                  # LangGraph to_json() output
    agents: dict[str, AgentConfig]  # Модели, температуры
    prompts: dict[str, PromptInfo]  # System prompts (обрезанные)
    manifest: dict                  # Полный manifest.yaml

class AgentConfig(BaseModel):
    model: str
    temperature: float
    fallback_model: str | None
    endpoint: str                   # "default" | "backup"

class PromptInfo(BaseModel):
    system: str                     # Первые 500 символов system prompt
    templates: list[str]            # Названия шаблонов
```

### 4.3 Switch-Agent (Router)

```
POST /api/run
  Headers: Authorization: Bearer <token>
  Body: CreateRunRequest
  Response 200: RunResponse
  Описание: Создание run с автоматическим или ручным выбором графа
```

```python
class CreateRunRequest(BaseModel):
    thread_id: str | None = None    # Если None — создаём новый thread
    task: str
    repository: str | None = None
    context: str | None = None
    graph_id: str | None = None     # Если None — Switch-Agent выбирает автоматически
    execution_mode: str = "auto"    # "auto" | "internal" | "cli"

class RunResponse(BaseModel):
    thread_id: str
    run_id: str
    graph_id: str                   # Какой граф выбран
    classification: TaskClassification | None  # Если Switch-Agent выбирал

class TaskClassification(BaseModel):
    graph_id: str
    complexity: int                 # 1-10
    reasoning: str
```

### 4.4 Прокси к Aegra

Все остальные пути проксируются к Aegra с JWT-проверкой:

```
# Threads
GET    /threads                    → proxy Aegra
POST   /threads                    → proxy Aegra
GET    /threads/{thread_id}        → proxy Aegra
GET    /threads/{thread_id}/state  → proxy Aegra
POST   /threads/{thread_id}/state  → proxy Aegra

# Runs
POST   /threads/{thread_id}/runs          → proxy Aegra
GET    /threads/{thread_id}/runs           → proxy Aegra
GET    /threads/{thread_id}/runs/{run_id}  → proxy Aegra

# Streaming (SSE)
POST   /threads/{thread_id}/runs/stream   → streaming proxy Aegra

# Assistants
GET    /assistants                  → proxy Aegra
POST   /assistants                  → proxy Aegra
GET    /assistants/{assistant_id}   → proxy Aegra

# Store
GET    /store/{path:path}           → proxy Aegra
POST   /store/{path:path}           → proxy Aegra
PUT    /store/{path:path}           → proxy Aegra

# Health (без auth)
GET    /health                      → { status: "ok", aegra: "ok"|"error" }
```

**Streaming proxy:** Для SSE-эндпоинтов Gateway использует `httpx.AsyncClient.stream()`,
пробрасывая chunks as-is. Content-Type: `text/event-stream`.
Timeout: 600 секунд (длинные LLM-вызовы).

### 4.6 Sandbox API — контракт

> Sandbox — отдельный сервис в docker-compose (Волна 2).

```
POST /execute
  Body: SandboxExecuteRequest
  Response 200: SandboxExecuteResponse
  Описание: Выполнить код в изолированном Docker-контейнере

GET /health
  Response 200: { status: "ok", docker_available: bool }
```

```python
class SandboxExecuteRequest(BaseModel):
    language: str                       # "python", "javascript", "go", etc.
    code_files: list[dict]              # [{path, content}]
    commands: list[str]                 # ["pip install -r requirements.txt", "pytest"]
    timeout: int = 60                   # Секунды
    memory_limit: str = "256m"          # Docker memory limit
    network: bool = False               # Разрешить сеть (default: нет)

class SandboxExecuteResponse(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    duration_seconds: float
    tests_passed: bool | None = None    # Если запускались тесты
    files_output: list[dict] = []       # [{path, content}] — если код создал файлы
```

### 4.5 Webhook для Telegram

```
POST /webhook/telegram
  Body: Telegram Update (JSON)
  Response 200: ok
  Описание: Webhook для Telegram Bot (альтернатива polling)
  Auth: проверка Telegram secret token
```

> **Примечание:** На первом этапе Telegram Bot использует polling, не webhook.
> Endpoint добавляется про запас.

---

## 5. CLI Runner API — контракт {#5-cli-runner-api}

Работает на отдельной VPS. Авторизация — по API-ключу в заголовке.

### 5.1 Endpoints

```
POST /jobs
  Headers: X-API-Key: <cli_runner_api_key>
  Body: CLIJobRequest
  Response 202: CLIJobAccepted
  Описание: Создание задачи для CLI-агента (async)

GET /jobs/{job_id}
  Headers: X-API-Key: <cli_runner_api_key>
  Response 200: CLIJobStatus
  Описание: Статус выполнения задачи

GET /jobs/{job_id}/stream
  Headers: X-API-Key: <cli_runner_api_key>
  Response: SSE stream
  Описание: Streaming вывода CLI-агента

DELETE /jobs/{job_id}
  Headers: X-API-Key: <cli_runner_api_key>
  Response 200: { cancelled: true }
  Описание: Отмена задачи (kill процесса)

GET /health
  Response 200: { status: "ok", active_jobs: int, cli_tools: {...} }
```

### 5.2 Модели данных

```python
class CLIJobRequest(BaseModel):
    """Запрос на выполнение CLI-задачи."""
    repo: str | None = None               # "owner/repo" — если есть, клонируем
    branch: str | None = None             # Ветка для checkout
    instructions: str                      # Инструкции для CLI-агента
    cli_tool: Literal["claude", "codex"] = "claude"
    timeout: int = 600                     # Секунды
    github_token: str | None = None        # Для clone/push
    env_vars: dict[str, str] = {}          # Доп. переменные окружения
    working_directory: str | None = None   # Подпапка в репо

class CLIJobAccepted(BaseModel):
    """Подтверждение принятия задачи."""
    job_id: str                            # UUID
    status: Literal["accepted"] = "accepted"
    estimated_timeout: int

class CLIJobStatus(BaseModel):
    """Текущий статус задачи."""
    job_id: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    output: str = ""                       # Последние N символов вывода
    exit_code: int | None = None
    files_changed: list[str] = []
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None
```

### 5.3 Жизненный цикл задачи

```
POST /jobs → accepted
    ↓
queued (ожидание свободного слота)
    ↓
running
    ├── 1. git clone (если repo указан)
    ├── 2. git checkout branch (если указан)
    ├── 3. Запуск CLI-агента (claude -p / codex)
    ├── 4. git add + commit + push (если repo указан)
    └── 5. Cleanup workspace
    ↓
completed / failed
```

**Конкурентность:** Максимум 2 одновременных задачи (ограничение ресурсов VPS).
Остальные ставятся в очередь.

**Claude Code headless mode:**
```bash
claude -p "<instructions>" \
  --output-format stream-json \
  --allowedTools "Edit,Write,Bash" \
  --max-turns 50
```

---

## 6. Общие модели данных {#6-общие-модели-данных}

### 6.1 Python — Gateway (Pydantic)

```python
# gateway/models.py

from pydantic import BaseModel, EmailStr
from datetime import datetime

# --- Auth ---
class UserCreate(BaseModel):
    email: EmailStr
    password: str              # min 8 chars
    display_name: str          # min 2 chars

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class User(BaseModel):
    id: str
    email: str
    display_name: str
    created_at: datetime
    is_active: bool

class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class AuthResponse(BaseModel):
    user: User
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

# --- Graph ---
class GraphListItem(BaseModel):
    graph_id: str
    display_name: str
    description: str
    version: str
    task_types: list[str]
    agents: list[AgentBrief]
    features: list[str]

class TaskClassification(BaseModel):
    graph_id: str
    complexity: int             # 1-10
    reasoning: str
```

### 6.2 Python — DevTeamState (расширенный TypedDict)

```python
# graphs/dev_team/state.py — целевое состояние после Волн 1+2

class DevTeamState(TypedDict):
    # === Input ===
    task: str
    repository: NotRequired[str]
    context: NotRequired[str]

    # === Волна 1: Task classification ===
    task_type: NotRequired[str]           # "new_project", "bugfix", "feature", "refactor"
    task_complexity: NotRequired[int]     # 1-10 (от router)

    # === Agent outputs (существующие) ===
    requirements: list[str]
    user_stories: list[UserStory]
    architecture: dict
    tech_stack: list[str]
    architecture_decisions: list[ArchitectureDecision]
    code_files: list[CodeFile]
    implementation_notes: str
    review_comments: list[str]              # From Reviewer agent
    test_results: dict                      # From Reviewer + QA agents
    issues_found: list[str]                 # From Reviewer or QA

    # === Final Output ===
    pr_url: NotRequired[str]
    commit_sha: NotRequired[str]
    summary: str

    # === Conversation ===
    messages: Annotated[list[BaseMessage], add_messages]

    # === Control Flow ===
    current_agent: str
    next_agent: NotRequired[str]
    needs_clarification: bool
    clarification_question: NotRequired[str]
    clarification_context: NotRequired[str]
    clarification_response: NotRequired[str]
    review_iteration_count: int               # Dev↔Reviewer/QA loop counter
    architect_escalated: bool
    error: NotRequired[str]
    retry_count: int

    # === Волна 2: Git-based workflow ===
    working_branch: NotRequired[str]      # "ai/task-20260208-123456"
    working_repo: NotRequired[str]        # "owner/repo"
    file_manifest: NotRequired[list[str]] # Файлы в ветке

    # === Волна 2: Sandbox ===
    sandbox_results: NotRequired[dict]    # {stdout, stderr, exit_code, tests_passed}

    # === Волна 2: Security ===
    security_review: NotRequired[dict]    # {critical: [], warnings: [], info: []}

    # === Волна 2: Deploy ===
    deploy_url: NotRequired[str]          # "https://app.31.59.58.143.nip.io"
    infra_files: NotRequired[list[dict]]  # [{path, content}]

    # === Волна 2: CLI ===
    cli_agent_output: NotRequired[str]
    cli_agent_role: NotRequired[str]      # "developer", "architect", etc.
    execution_mode: NotRequired[str]      # "auto" | "internal" | "cli"
    cli_tool: NotRequired[str]            # "claude" | "codex"
```

### 6.3 TypeScript — Frontend (обновлённые типы)

```typescript
// types/index.ts — целевое состояние

// --- Auth ---
export interface User {
  id: string
  email: string
  display_name: string
  created_at: string
  is_active: boolean
}

export interface AuthState {
  user: User | null
  accessToken: string | null
  refreshToken: string | null
  isAuthenticated: boolean
}

// --- Graph ---
export interface GraphListItem {
  graph_id: string
  display_name: string
  description: string
  version: string
  task_types: string[]
  agents: { id: string; display_name: string }[]
  features: string[]
}

export interface GraphTopology {
  graph_id: string
  topology: {
    nodes: { id: string; type: string; data: unknown }[]
    edges: { source: string; target: string; conditional?: boolean; data?: string }[]
  }
  agents: Record<string, AgentConfig>
  prompts: Record<string, PromptInfo>
  manifest: Record<string, unknown>
}

export interface AgentConfig {
  model: string
  temperature: number
  fallback_model: string | null
}

export interface PromptInfo {
  system: string          // Обрезанный system prompt
  templates: string[]     // Названия шаблонов
}

// --- Task creation (обновлённый) ---
export interface CreateTaskInput {
  task: string
  repository?: string
  context?: string
  graph_id?: string         // Если null — Switch-Agent
  execution_mode?: 'auto' | 'internal' | 'cli'
}

// --- DevTeamState (расширенный) ---
export interface DevTeamState {
  // Существующие поля...
  task: string
  repository?: string
  context?: string
  requirements: string[]
  user_stories: UserStory[]
  architecture: Record<string, unknown>
  tech_stack: string[]
  code_files: CodeFile[]
  review_comments: string[]
  issues_found: string[]
  pr_url?: string
  summary: string
  messages: Message[]
  current_agent: string
  needs_clarification: boolean
  clarification_question?: string
  clarification_context?: string

  // Новые поля Волна 1
  task_type?: string
  task_complexity?: number

  // Новые поля Волна 2
  working_branch?: string
  working_repo?: string
  deploy_url?: string
  sandbox_results?: {
    stdout: string
    stderr: string
    exit_code: number
    tests_passed?: boolean
  }
  security_review?: {
    critical: string[]
    warnings: string[]
    info: string[]
  }
  execution_mode?: 'auto' | 'internal' | 'cli'
}
```

---

## 7. Конфигурационные схемы {#7-конфигурационные-схемы}

### 7.1 config/agents.yaml

Центральная конфигурация LLM для всех агентов. Env-переменные имеют приоритет.

```yaml
# config/agents.yaml — Schema

defaults:
  endpoint: default           # Имя endpoint из секции endpoints
  temperature: 0.7
  max_tokens: 4096
  timeout: 120                # Секунды на один LLM-вызов

endpoints:
  default:
    url: ${LLM_API_URL}       # Переменные окружения подставляются при загрузке
    api_key: ${LLM_API_KEY}
  backup:
    url: ${LLM_BACKUP_URL}
    api_key: ${LLM_BACKUP_KEY}

agents:
  <agent_name>:               # pm, analyst, architect, developer, reviewer, qa, router, security, devops
    model: <string>           # Имя модели
    temperature: <float>      # 0.0 — 2.0
    max_tokens: <int>         # Override defaults
    fallback_model: <string>  # Модель для fallback chain
    endpoint: <string>        # Override defaults
    timeout: <int>            # Override defaults
```

**Порядок приоритетов:**
1. `LLM_MODEL_<ROLE>` env var (высший приоритет)
2. `agents.<role>.model` в agents.yaml
3. `LLM_DEFAULT_MODEL` env var
4. Хардкод в DEFAULT_MODELS

**Python API для загрузки:**
```python
# agents/base.py
def load_agent_config() -> dict:
    """Load config/agents.yaml with env var substitution."""

def get_model_for_role(role: str) -> str:
    """Get model name respecting priority chain."""

def get_llm_with_fallback(role: str, **kwargs) -> BaseChatModel:
    """Get LLM with fallback chain from config."""
```

### 7.2 manifest.yaml (для каждого графа)

Метаданные графа для UI и роутинга. Лежит рядом с `graph.py`.

```yaml
# graphs/<graph_name>/manifest.yaml — Schema

name: <string>                # ID графа (= имя директории)
display_name: <string>        # Для UI
description: <string>         # Описание для UI и Switch-Agent
version: <string>             # Semver
task_types:                   # Для Switch-Agent классификации
  - <string>                  # "new_project", "feature", "bugfix", "refactor", "research"

agents:                       # Список агентов в графе
  - id: <string>              # Имя узла в графе
    display_name: <string>    # Для UI
    role: <string>            # Опционально: роль для LLM config

features:                     # Флаги возможностей
  - <string>                  # "hitl_clarification", "hitl_escalation", "qa_loop",
                              # "git_commit", "sandbox", "security_check", "deploy"

parameters:                   # Настраиваемые параметры графа
  <key>: <value>              # Произвольные key-value

# Примеры параметров:
#   max_qa_iterations: 3
#   use_security_agent: false
#   deploy_after_commit: false
#   hitl_mode: "optional"     # "required" | "optional" | "none"
```

### 7.3 Environment Variables (финальный список)

```bash
# ╔══════════════════════════════════════════╗
# ║        ОСНОВНАЯ VPS (AI-crew)            ║
# ╚══════════════════════════════════════════╝

# --- LLM ---
LLM_API_URL=https://clipapi4me.31.59.58.143.nip.io/v1
LLM_API_KEY=<key>
LLM_BACKUP_URL=                      # Резервный endpoint (опционально)
LLM_BACKUP_KEY=
LLM_DEFAULT_MODEL=                   # Global override (опционально)
# LLM_MODEL_PM=                      # Per-agent override (опционально)

# --- Database ---
POSTGRES_USER=aicrew
POSTGRES_PASSWORD=<strong-password>
POSTGRES_DB=aicrew
POSTGRES_PORT=5433                   # Порт наружу (позже закроем)

# --- Gateway ---
JWT_SECRET=<32-char-secret>
JWT_ACCESS_TTL=1800                  # 30 минут (секунды)
JWT_REFRESH_TTL=604800               # 7 дней (секунды)
GATEWAY_URL=http://localhost:8081    # Для фронтенда (VITE_API_URL)
AEGRA_URL=http://aegra:8000          # Для gateway (internal)

# --- GitHub ---
GITHUB_TOKEN=ghp_xxx
GITHUB_DEFAULT_REPO=                 # Опционально

# --- Langfuse ---
LANGFUSE_ENABLED=true
LANGFUSE_SECRET_KEY=sk-xxx
LANGFUSE_PUBLIC_KEY=pk-xxx
LANGFUSE_HOST=http://langfuse:3001   # Internal
LANGFUSE_NEXTAUTH_SECRET=<secret>
LANGFUSE_SALT=<salt>

# --- Telegram ---
TELEGRAM_BOT_TOKEN=123456:ABC-DEF
TELEGRAM_ADMIN_CHAT_ID=              # Для уведомлений

# --- Web Search ---
SEARCH_API_URL=                      # Пусто = DuckDuckGo

# --- CLI Runner ---
CLI_RUNNER_URL=http://<cli-vps-ip>:8001
CLI_RUNNER_API_KEY=<key>

# --- Logging ---
LOG_LEVEL=DEBUG                      # DEBUG | INFO | WARNING | ERROR
ENV_MODE=LOCAL                       # LOCAL | PRODUCTION

# --- Frontend ---
VITE_API_URL=${GATEWAY_URL}          # Для Vite (compile-time)

# ╔══════════════════════════════════════════╗
# ║        VPS CLI Runner                    ║
# ╚══════════════════════════════════════════╝
CLI_RUNNER_API_KEY=<same-key>
GITHUB_TOKEN=<token>                 # Для clone/push
MAX_CONCURRENT_JOBS=2
WORKSPACE_DIR=/workspace

# ╔══════════════════════════════════════════╗
# ║        VPS Deploy                        ║
# ╚══════════════════════════════════════════╝
# Секреты хранятся в .env файлах на VPS деплоя (GitHub Free план)
# Человек вносит вручную: VPS_SSH_KEY, DATABASE_URL и т.д.
# + Prefect Server (отдельный docker-compose)
```

### 7.4 Вариативность агентов (Agent Variants) {#7-4-agent-variability}

Каждый граф определяет собственный набор агентов/узлов, и **один и тот же тип агента может отличаться от графа к графу**. Это ключевой архитектурный принцип, обеспечивающий гибкость платформы.

**Примеры вариантов Developer-агента:**

| Вариант | Описание | Используется в |
|---------|----------|---------------|
| `developer_simple` | Только код, без тестов | `simple_dev` граф |
| `developer_with_tests` | Код + unit-тесты + CI-конфиг | `dev_team` граф (подход A, см. [Приложение D, §D.6](#appendix-d-qa-evolution)) |
| `developer_tdd` | Код по тестам от Architect'а | Будущий TDD-граф (подход B) |

**Примеры вариантов QA-агента:**

| Вариант | Описание | Используется в |
|---------|----------|---------------|
| `qa_sandbox` | Sandbox-based тестирование | `dev_team` граф |
| `qa_cli` | QA через CLI-агент (Claude Code) | Дорогие/сложные графы |
| `qa_minimal` | Только LLM-ревью без sandbox | `standard_dev` граф |

**Реализация вариативности:**

1. **Разные промпты** — один и тот же `developer.py`, но разные `prompts/developer.yaml` в разных графах
2. **Разные реализации** — разные Python-классы (`DeveloperAgent` vs `DeveloperTDDAgent`) в разных графах
3. **Коллекция агентов** — общая библиотека вариантов (`agents/variants/developer_simple.py`, `developer_with_tests.py` и т.п.), из которых граф выбирает нужный

При создании нового графа можно комбинировать агенты из существующей коллекции или создавать новые варианты. Manifest.yaml описывает конкретный набор агентов, используемый в данном графе (см. [§7.2](#7-конфигурационные-схемы)).

> **Пример:** два графа для разработки могут использовать один и тот же PM, Analyst и Architect, но разные варианты Developer (один пишет тесты сам, другой — получает тесты от Architect'а). Аналогично, QA-агент в "лёгком" графе может быть минимальным (только LLM-ревью), а в "тяжёлом" — полноценным sandbox + CLI.

---

## 8. Протоколы взаимодействия {#8-протоколы-взаимодействия}

### 8.1 Основной поток: создание и выполнение задачи

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ Frontend │    │ Gateway  │    │  Aegra   │    │  Graph   │
└────┬─────┘    └────┬─────┘    └────┬─────┘    └────┬─────┘
     │               │               │               │
     │ POST /api/run │               │               │
     │ {task, ...}   │               │               │
     │──────────────>│               │               │
     │               │               │               │
     │               │ validate JWT  │               │
     │               │───────┐       │               │
     │               │<──────┘       │               │
     │               │               │               │
     │               │ graph_id=null?│               │
     │               │ classify_task │               │
     │               │───────┐       │               │
     │               │<──────┘       │               │
     │               │ graph_id="dev_team"           │
     │               │               │               │
     │               │ POST /threads │               │
     │               │──────────────>│               │
     │               │    thread_id  │               │
     │               │<──────────────│               │
     │               │               │               │
     │               │ POST /threads/│               │
     │               │ {id}/runs     │               │
     │               │──────────────>│               │
     │               │               │ invoke graph  │
     │               │               │──────────────>│
     │               │               │               │ PM → Analyst → ...
     │               │               │               │
     │ { thread_id,  │               │               │
     │   run_id,     │               │               │
     │   graph_id }  │               │               │
     │<──────────────│               │               │
     │               │               │               │
     │ SSE: POST     │               │               │
     │ /threads/{id}/│               │               │
     │ runs/stream   │               │               │
     │──────────────>│               │               │
     │               │──────────────>│               │
     │               │    SSE events │               │
     │               │<──────────────│               │
     │   SSE events  │               │               │
     │<──────────────│               │               │
```

### 8.2 HITL: уточнение от пользователя

```
     │               │               │               │
     │               │               │  interrupt!   │
     │               │               │<──────────────│ needs_clarification=true
     │               │               │               │
     │ SSE: state    │               │               │
     │ update        │               │               │
     │<──────────────│               │               │
     │               │               │               │
     │ [User types   │               │               │
     │  answer in UI]│               │               │
     │               │               │               │
     │ POST /threads/│               │               │
     │ {id}/state    │               │               │
     │ command:update│               │               │
     │──────────────>│               │               │
     │               │──────────────>│               │
     │               │               │ resume graph  │
     │               │               │──────────────>│
     │               │               │               │ продолжает с
     │               │               │               │ clarification_response
```

**Важно:** HITL реализован через `interrupt_before` в LangGraph.
Фронтенд определяет HITL по `needs_clarification: true` в state.
Ответ пользователя записывается через `command: { update: { ... } }`.

### 8.3 Streaming (SSE)

Формат SSE-событий от Aegra (проксируются через Gateway as-is):

```
event: metadata
data: {"run_id": "xxx", "thread_id": "yyy"}

event: values
data: {"current_agent": "pm", "requirements": [...], ...}

event: values
data: {"current_agent": "analyst", ...}

event: updates
data: {"pm": {"requirements": [...], "current_agent": "analyst"}}

event: end
data: null
```

Frontend подписывается на SSE, обновляет state и UI в реальном времени.

### 8.4 CLI Agent — протокол вызова из графа

```
┌──────────┐    ┌──────────┐    ┌──────────┐
│ Graph    │    │ Aegra    │    │CLI Runner│
│ (node)   │    │          │    │  (VPS)   │
└────┬─────┘    └──────────┘    └────┬─────┘
     │                               │
     │ cli_agent_node()              │
     │ route_to_executor → "cli"     │
     │                               │
     │ POST /jobs                    │
     │ { repo, branch, instructions, │
     │   cli_tool, timeout }         │
     │──────────────────────────────>│
     │          { job_id }           │
     │<──────────────────────────────│
     │                               │
     │ [polling GET /jobs/{id}]      │
     │──────────────────────────────>│
     │          { status: running }  │
     │<──────────────────────────────│
     │                               │
     │ ...                           │
     │                               │
     │ GET /jobs/{id}                │
     │──────────────────────────────>│
     │  { status: completed,         │
     │    output, files_changed }    │
     │<──────────────────────────────│
     │                               │
     │ return {                      │
     │   cli_agent_output: output,   │
     │   current_agent: "qa" }       │
```

**Альтернатива polling:** SSE streaming через `GET /jobs/{id}/stream`.

### 8.5 Deployment flow (DevOps Agent)

```
DevOps Agent (узел графа):
    │
    ├── 1. Анализирует state: tech_stack, code_files, architecture
    │
    ├── 2. Генерирует infra_files:
    │       ├── Dockerfile
    │       ├── docker-compose.yml
    │       ├── .github/workflows/deploy.yml
    │       ├── .pre-commit-config.yaml
    │       └── traefik labels
    │
    ├── 3. Определяет параметры деплоя:
    │       ├── AUTO: APP_NAME, DOMAIN → прописывает в конфиг деплоя
    │       └── Серверные секреты (VPS_SSH_KEY, DATABASE_URL)
    │           → предполагаются уже настроенными на VPS деплоя
    │           (по умолчанию без DevOps HITL)
    │
    ├── 4. Коммитит infra_files в рабочую ветку
    │
    ├── 5. Генерирует инструкцию: какие .env переменные нужны на VPS
    │       (если ещё не настроены — уведомление пользователю)
    │
    └── 6. Возвращает { deploy_url, infra_files }

GitHub Actions (вне графа, CI/CD pipeline):
    │
    ├── Trigger: push to branch
    ├── Steps: lint → test → build → deploy to VPS
    └── Result: app доступен по deploy_url
```

### 8.6 Telegram Bot — протокол

```
Telegram User                   Telegram Bot               Gateway
      │                              │                         │
      │ /task Create calculator     │                         │
      │─────────────────────────────>│                         │
      │                              │ POST /auth/login        │
      │                              │ (bot service account)   │
      │                              │────────────────────────>│
      │                              │      { token }          │
      │                              │<────────────────────────│
      │                              │                         │
      │                              │ POST /api/run           │
      │                              │ Authorization: Bearer   │
      │                              │────────────────────────>│
      │                              │  { thread_id, run_id }  │
      │                              │<────────────────────────│
      │                              │                         │
      │ "Задача создана: #abc123"   │                         │
      │<─────────────────────────────│                         │
      │                              │                         │
      │                              │ [polling thread state]  │
      │                              │────────────────────────>│
      │                              │  { needs_clarification }│
      │                              │<────────────────────────│
      │                              │                         │
      │ "Агент спрашивает: ..."     │                         │
      │<─────────────────────────────│                         │
      │                              │                         │
      │ "REST API с FastAPI"        │                         │
      │─────────────────────────────>│                         │
      │                              │ POST /threads/{id}/state│
      │                              │ command: update          │
      │                              │────────────────────────>│
      │                              │                         │
```

**Маппинг Telegram → пользователь:**
- Бот работает от **сервисного аккаунта** (единый бот-пользователь в AI-crew)
- Все задачи из Telegram создаются от имени сервисного аккаунта
- Per-user привязка (Telegram user_id ↔ AI-crew аккаунт) — возможна позже

---

## 9. Безопасность {#9-безопасность}

### 9.1 Аутентификация

**JWT через Gateway.** Aegra работает без auth (`AUTH_TYPE=noop`) во внутренней сети.

Поток:
1. Пользователь регистрируется/логинится через `/auth/*`
2. Получает access_token (30 мин) + refresh_token (7 дней)
3. Все запросы к Gateway несут `Authorization: Bearer <access_token>`
4. Gateway проверяет JWT, извлекает user_id, проксирует запрос к Aegra
5. При истечении access_token — клиент вызывает `/auth/refresh`

**Хранение на фронте:**
- access_token: в памяти (zustand store) + localStorage (для персистентности)
- refresh_token: httpOnly cookie (предпочтительно) или localStorage

### 9.2 Управление секретами — двухуровневая модель

Упрощённая модель. GitHub Free план — Organization Secrets для private repos
недоступны, поэтому секреты целевых проектов хранятся на VPS деплоя.

```
┌─────────────────────────────────────────────────────────────┐
│  Уровень 1: Платформенные секреты AI-crew                   │
│  ─────────────────────────────────────────                   │
│  LLM_API_KEY, GITHUB_TOKEN, JWT_SECRET, CLI_RUNNER_API_KEY  │
│                                                              │
│  Где: .env на хосте AI-crew (не в Git, не в GitHub)          │
│  Кто вносит: Человек (один раз при установке)               │
│  ИИ использует: ДА (runtime env vars), видит: НЕТ           │
│  Риск: НИЗКИЙ (стандартная практика)                         │
├─────────────────────────────────────────────────────────────┤
│  Уровень 2: Секреты целевых проектов                        │
│  ─────────────────────────────────────                       │
│  VPS_SSH_KEY, DATABASE_URL, API_KEYS клиента                 │
│                                                              │
│  Где: .env файлы на VPS деплоя (не в Git, не в GitHub)      │
│  Кто вносит: Человек вручную (SSH → VPS → .env)             │
│  ИИ доступ: НЕТ (не имеет SSH-доступа к VPS деплоя)        │
│  CI/CD видит: ДА (docker-compose подтягивает .env с диска)  │
│  Риск: НИЗКИЙ                                               │
│                                                              │
│  Примечание: GitHub Free не поддерживает Organization       │
│  Secrets для private repos. Поэтому секреты целевых         │
│  проектов хранятся как .env на VPS. При деплое              │
│  docker-compose / GitHub Actions self-hosted runner          │
│  читают .env файлы непосредственно с диска VPS.             │
│  Некритичные параметры (APP_NAME, DOMAIN) DevOps Agent      │
│  прописывает сам в конфиг деплоя.                           │
└─────────────────────────────────────────────────────────────┘
```

### 9.3 Docker-сетевая изоляция

```yaml
# Принципы:
# 1. Aegra — НЕ доступен снаружи (только expose, не ports)
# 2. Sandbox — НЕ доступен снаружи
# 3. Telegram — НЕ доступен снаружи (polling)
# 4. Все сервисы в одной docker-сети (aicrew-network)
# 5. Gateway — единственная API-точка входа
```

### 9.4 CLI Runner — безопасность

- Авторизация: API-ключ в заголовке `X-API-Key`
- Workspace: каждая задача в изолированной директории, удаляется после завершения
- Timeout: жёсткий лимит (default 600s)
- Ресурсы: ограничение CPU/RAM через cgroups или Docker (будущее)
- Git: токен передаётся per-request, не хранится на диске

---

## 10. Data Layer {#10-data-layer}

### 10.1 PostgreSQL — схема

Одна БД `aicrew`, несколько схем/таблиц:

**Aegra-managed (не трогаем):**
- `checkpoints` — LangGraph state checkpoints
- `checkpoint_blobs` — Бинарные данные checkpoints
- `checkpoint_writes` — Журнал записей
- Aegra metadata tables (assistants, threads, runs)

**Gateway-managed (наши):**
```sql
-- Таблица пользователей
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Индексы
CREATE INDEX idx_users_email ON users(email);
```

**Langfuse-managed (не трогаем):**
- Langfuse создаёт свои таблицы при первом запуске
- Отдельный набор таблиц в той же БД

**Миграции:**
- Gateway: простые SQL-скрипты (или Alembic если потребуется)
- Aegra и Langfuse: управляют своими миграциями сами

### 10.2 pgvector (заготовка)

PostgreSQL уже с расширением pgvector. Не используется в Волнах 1-2,
но готов для будущей vector memory (Meta-Agent, Self-Improvement).

```sql
-- Будущее: таблица для vector memory
-- CREATE EXTENSION IF NOT EXISTS vector;
-- CREATE TABLE task_embeddings (
--     id UUID PRIMARY KEY,
--     task_text TEXT,
--     embedding vector(1536),
--     metadata JSONB,
--     created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
-- );
```

### 10.3 Langfuse — что хранится

После Langfuse-fix (callbacks в агентах):

| Сущность | Что содержит |
|----------|-------------|
| **Trace** | Один run = один trace. `thread_id` + `run_id` в метаданных |
| **Span** | Каждый node (pm, analyst, ...) = один span |
| **Generation** | Каждый LLM-вызов: промпт, ответ, модель, токены, стоимость, latency |
| **Score** | Будущее: оценки качества (от QA, от пользователя) |

**Доступ к данным:**
- UI: `http://localhost:3001` (свой auth)
- API: `GET /api/public/traces?limit=50` с `Authorization: Bearer <LANGFUSE_PUBLIC_KEY>`

### 10.4 Prefect Server (на VPS деплоя)

Prefect Server на VPS деплоя для визуализации. Рядом с приложениями, не влияет на pipeline.

```yaml
# docker-compose.prefect.yml (на VPS деплоя)
services:
  prefect-server:
    image: prefecthq/prefect:3-latest
    command: prefect server start --host 0.0.0.0
    ports:
      - "4200:4200"
    environment:
      PREFECT_SERVER_API_HOST: 0.0.0.0
      PREFECT_API_DATABASE_CONNECTION_URL: sqlite+aiosqlite:///./prefect.db
    volumes:
      - prefect_data:/root/.prefect

volumes:
  prefect_data:
```

DevOps Agent может регистрировать deployment flows в Prefect через API,
чтобы на UI (`:4200`) было видно что развёрнуто и когда.

---

## 11. Observability и мониторинг {#11-observability}

### 11.1 Logging (structlog)

**Формат:**
- LOCAL: цветной консольный вывод (`ConsoleRenderer`)
- PRODUCTION: JSON (`JSONRenderer`)

**Контекст:**
```python
import structlog
logger = structlog.get_logger()

# В каждом LLM-вызове:
logger.info("llm.invoke",
    agent=self.name,
    model=model_name,
    tokens_prompt=usage.prompt_tokens,
    tokens_completion=usage.completion_tokens,
    latency_ms=elapsed_ms,
    task_id=state.get("task_id"),
)

# В каждом node:
logger.info("node.enter", node="pm", thread_id=config.get("thread_id"))
logger.info("node.exit", node="pm", duration_ms=elapsed)
```

**Куда идут логи:**
- stdout (Docker → `docker-compose logs`)
- Будущее: Loki + Grafana (если понадобится централизация)

### 11.2 Langfuse Tracing

**Что записывается:**
- Каждый graph run = trace
- Каждый agent node = span
- Каждый LLM-вызов = generation (промпт, ответ, модель, токены, cost)
- State на каждом шаге

**Как подключено:**
- Aegra передаёт Langfuse callbacks через `config["callbacks"]`
- Агенты передают callbacks в `chain.invoke()` (после Langfuse-fix)
- Автоматически: модель, токены, cost, latency

### 11.3 Health Checks

```python
# Gateway /health
{
    "status": "ok",
    "aegra": "ok",        # проверяет GET aegra:8000/health
    "postgres": "ok",     # проверяет SELECT 1
    "langfuse": "ok",     # проверяет GET langfuse:3001
}

# CLI Runner /health
{
    "status": "ok",
    "active_jobs": 0,
    "cli_tools": {
        "claude": true,   # which claude → exists
        "codex": false,
    }
}
```

---

## 12. Решённые вопросы {#12-открытые-вопросы}

### Зафиксированные решения (все вопросы закрыты)

| # | Вопрос | Решение | Обоснование |
|---|--------|---------|-------------|
| 1 | **GitHub план** | **Free** | Секреты целевых проектов хранятся на VPS деплоя (.env файлы), не в GitHub Secrets. Organization Secrets недоступны на Free для private repos — не проблема |
| 2 | **Telegram** | **Service account** | Единый бот-пользователь в AI-crew. Все задачи из Telegram от его имени. Per-user привязка — возможна позже |
| 3 | **CLI Runner** | **REST API** | Проще, универсальнее. MCP — исследовать отдельно позже |
| 4 | **Frontend** | **SPA** (Vite) | Остаёмся на текущем стеке. SSR не нужен |
| 5 | **Gateway БД** | **Общая БД** | Одна PostgreSQL, Gateway создаёт свою таблицу `users`. Меньше инфраструктуры |
| 6 | **Sandbox** | **DinD** (Docker-in-Docker) | Проще в настройке. Требует privileged mode. Sysbox — если будет проблема с безопасностью |

### Замечания по EVOLUTION_PLAN_V3

| # | Тема | Комментарий | Решение |
|---|------|-------------|---------|
| 1 | PostgreSQL :5433 | Не ограничиваем по IP сейчас, закроем порт позже | Принято. Порт открыт, в проде — закроем firewall |
| 2 | Branch protection | ИИ имеет полный набор возможностей. Может деплоить из dev-ветки. HITL — опционально per-graph | Принято. `hitl_mode` в manifest.yaml |
| 3 | Секреты L2+L3 | Упрощаем до двух уровней (платформенные + проектные) | Принято. Описано в §9.2 |
| 4 | DevOps HITL | По умолчанию без DevOps HITL. Секреты уже на VPS | Принято. DevOps HITL не нужен по умолчанию. Секреты готовы на VPS деплоя (.env). Если чего-то не хватает — уведомление пользователю, но не блокировка |
| 5 | CLI agent API | Claude Code имеет MCP by design | Начинаем с REST API. MCP исследуем отдельно (см. вопрос #3) |
| 6 | Callbacks / контекст | Не грузить контекст ненужным | Callbacks — это механизм вызова, в контекст LLM ничего лишнего не попадает. Langfuse перехватывает вызовы через callback hooks, промпт и ответ сохраняются в Langfuse, а не в state |
| 7 | Prefect Server | На VPS деплоя для визуализации | Принято. Отдельный docker-compose на VPS деплоя. Описано в §10.4 |

### Информационные (не блокируют)

- **Стоимость CLI-агентов:** CLI-агенты дороже внутренних агентов. Учёт токенов обязателен. Мониторинг через Langfuse. Не заморачиваемся на точных ценах — просто знаем, что CLI дороже.
- **Масштабирование:** Текущая архитектура рассчитана на одного активного пользователя (или нескольких с небольшой нагрузкой). Для масштабирования — горизонтальное масштабирование Aegra + Gateway.
- **Версионирование графов:** Через Git. manifest.yaml содержит `version`. Aegra загружает граф из Python-файла при старте.

---

## Приложение A: Docker Compose (целевой после Волны 1)

```yaml
version: "3.8"

services:
  # === Core ===
  postgres:
    image: pgvector/pgvector:pg16
    ports: ["${POSTGRES_PORT:-5433}:5433"]
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-aicrew}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB:-aicrew}
    volumes: [postgres_data:/var/lib/postgresql/data]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-aicrew}"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks: [aicrew]

  aegra:
    build: .
    expose: ["8000"]               # Только внутренняя сеть!
    depends_on:
      postgres: { condition: service_healthy }
    environment:
      AUTH_TYPE: noop
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER:-aicrew}:${POSTGRES_PASSWORD}@postgres:5433/${POSTGRES_DB:-aicrew}
      LANGFUSE_ENABLED: "true"
      LANGFUSE_HOST: http://langfuse:3001
      LANGFUSE_SECRET_KEY: ${LANGFUSE_SECRET_KEY}
      LANGFUSE_PUBLIC_KEY: ${LANGFUSE_PUBLIC_KEY}
      LLM_API_URL: ${LLM_API_URL}
      LLM_API_KEY: ${LLM_API_KEY}
      GITHUB_TOKEN: ${GITHUB_TOKEN}
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
      ENV_MODE: ${ENV_MODE:-PRODUCTION}
    networks: [aicrew]

  gateway:
    build: ./gateway
    ports: ["8081:8081"]
    depends_on:
      aegra: { condition: service_started }
      postgres: { condition: service_healthy }
    environment:
      AEGRA_URL: http://aegra:8000
      DATABASE_URL: postgresql://${POSTGRES_USER:-aicrew}:${POSTGRES_PASSWORD}@postgres:5433/${POSTGRES_DB:-aicrew}
      JWT_SECRET: ${JWT_SECRET}
      JWT_ACCESS_TTL: ${JWT_ACCESS_TTL:-1800}
      JWT_REFRESH_TTL: ${JWT_REFRESH_TTL:-604800}
      LLM_API_URL: ${LLM_API_URL}
      LLM_API_KEY: ${LLM_API_KEY}
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
      ENV_MODE: ${ENV_MODE:-PRODUCTION}
    networks: [aicrew]

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile.dev
    ports: ["5173:5173"]
    environment:
      VITE_API_URL: ${GATEWAY_URL:-http://localhost:8081}
    networks: [aicrew]

  # === Observability ===
  langfuse:
    image: langfuse/langfuse:latest
    ports: ["3001:3001"]
    depends_on:
      postgres: { condition: service_healthy }
    environment:
      DATABASE_URL: postgresql://${POSTGRES_USER:-aicrew}:${POSTGRES_PASSWORD}@postgres:5433/${POSTGRES_DB:-aicrew}
      NEXTAUTH_SECRET: ${LANGFUSE_NEXTAUTH_SECRET}
      SALT: ${LANGFUSE_SALT}
      NEXTAUTH_URL: http://localhost:3001
    networks: [aicrew]

  # === Interfaces (Волна 1) ===
  telegram:
    build: ./telegram
    depends_on:
      gateway: { condition: service_started }
    environment:
      TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN}
      GATEWAY_URL: http://gateway:8081
      TELEGRAM_ADMIN_CHAT_ID: ${TELEGRAM_ADMIN_CHAT_ID:-}
    networks: [aicrew]
    # Нет портов наружу — polling

volumes:
  postgres_data:

networks:
  aicrew:
    name: aicrew-network
```

---

## Приложение B: Структура файлов (целевая)

```
AI-crew/
├── config/
│   └── agents.yaml                    # LLM конфигурация
│
├── gateway/                           # FastAPI Gateway
│   ├── main.py
│   ├── auth.py                        # JWT auth
│   ├── proxy.py                       # Прокси к Aegra (REST + SSE)
│   ├── router.py                      # Switch-Agent (classify_task)
│   ├── graph_loader.py                # Единая загрузка манифестов и конфигов
│   ├── config.py                      # Settings (pydantic-settings)
│   ├── models.py                      # Pydantic models
│   ├── database.py                    # Async PostgreSQL (users)
│   ├── endpoints/
│   │   ├── graph.py                   # /graph/topology, /graph/list, /graph/config
│   │   └── run.py                     # /api/run (с auto-routing)
│   ├── Dockerfile
│   └── requirements.txt
│
├── graphs/
│   ├── __init__.py
│   ├── common/                        # Общий код для всех графов
│   │   ├── __init__.py
│   │   ├── types.py                   # CodeFile, UserStory, ArchitectureDecision
│   │   ├── utils.py                   # build_code_summary, format_code_files
│   │   ├── git.py                     # make_git_commit_node (фабрика)
│   │   └── logging.py                 # configure_logging (идемпотентная)
│   └── dev_team/
│       ├── __init__.py
│       ├── graph.py                   # LangGraph граф
│       ├── state.py                   # DevTeamState
│       ├── manifest.yaml              # Метаданные графа
│       ├── logging_config.py          # structlog setup
│       ├── agents/
│       │   ├── __init__.py
│       │   ├── base.py                # LLM factory, retry, fallback, callbacks
│       │   ├── pm.py
│       │   ├── analyst.py
│       │   ├── architect.py
│       │   ├── developer.py
│       │   ├── reviewer.py              # Code review (бывший qa.py)
│       │   ├── qa.py                   # QA оркестратор (Волна 2)
│       │   ├── qa_helpers.py           # Shared parsing: verdict, issues, defects
│       │   ├── qa_sandbox.py           # Sandbox code testing
│       │   ├── qa_browser.py           # Playwright E2E testing (Phase 1)
│       │   ├── qa_exploration.py       # Guided Exploration (Phase 2)
│       │   ├── security.py            # Волна 2
│       │   ├── devops.py              # Волна 2
│       │   └── cli_agent.py           # Волна 2
│       ├── prompts/
│       │   ├── pm.yaml
│       │   ├── analyst.yaml
│       │   ├── architect.yaml
│       │   ├── developer.yaml
│       │   ├── reviewer.yaml           # Code review prompts
│       │   ├── qa.yaml                 # Sandbox testing prompts
│       │   ├── security.yaml          # Волна 2
│       │   └── devops.yaml            # Волна 2
│       └── tools/
│           ├── __init__.py
│           ├── github.py
│           ├── filesystem.py
│           ├── web.py                 # Волна 1: DuckDuckGo + fetch
│           ├── git_workspace.py       # Волна 2
│           ├── github_actions.py      # Волна 2
│           ├── sandbox.py             # Волна 2
│           └── cli_runner.py          # Волна 2
│
├── telegram/                          # Telegram Bot
│   ├── bot.py
│   ├── handlers.py
│   ├── gateway_client.py
│   ├── Dockerfile
│   └── requirements.txt
│
├── sandbox/                           # Волна 2: Code Execution
│   ├── server.py
│   ├── Dockerfile
│   └── requirements.txt
│
├── cli_runner/                        # Волна 2: CLI Agent Runner (для VPS)
│   ├── server.py
│   ├── Dockerfile
│   └── requirements.txt
│
├── config/
│   ├── agents.yaml
│   └── linters/                       # Волна 2
│       ├── python.yaml
│       ├── javascript.yaml
│       └── typescript.yaml
│
├── frontend/
│   └── src/
│       ├── api/
│       │   └── aegra.ts               # Обновлённый: JWT headers, gateway URL
│       ├── components/
│       │   ├── Chat.tsx
│       │   ├── ClarificationPanel.tsx
│       │   ├── Layout.tsx
│       │   ├── ProgressTracker.tsx
│       │   ├── TaskForm.tsx           # Обновлённый: выбор графа
│       │   └── GraphVisualization.tsx # Новый: React Flow
│       ├── hooks/
│       │   ├── useTask.ts
│       │   ├── useStreamingTask.ts    # Новый: SSE hook
│       │   └── useAuth.ts            # Новый: JWT auth hook
│       ├── pages/
│       │   ├── Home.tsx
│       │   ├── TaskDetail.tsx         # Обновлённый: + graph visualization
│       │   ├── Login.tsx              # Новый
│       │   └── Register.tsx           # Новый
│       ├── store/
│       │   └── authStore.ts           # Новый: zustand auth state
│       ├── types/
│       │   └── index.ts              # Обновлённый: + auth, graph types
│       └── App.tsx                    # Обновлённый: protected routes
│
├── tests/
│   ├── conftest.py
│   ├── test_state.py
│   ├── test_agents.py
│   ├── test_graph.py
│   ├── test_tools.py
│   ├── test_integration.py
│   ├── test_gateway/                  # Новые
│   │   ├── test_auth.py
│   │   ├── test_proxy.py
│   │   ├── test_router.py
│   │   └── test_graph_endpoints.py
│   └── test_telegram/                 # Новые
│       └── test_handlers.py
│
├── docker-compose.yml
├── requirements.txt
├── aegra.json
├── env.example
└── docs/
    ├── architecture.md → ARCHITECTURE_V2.md (замена)
    ├── EVOLUTION_PLAN_V3.md
    ├── IMPLEMENTATION_PLAN.md         # Новый
    ├── DEVELOPMENT.md
    ├── TESTING.md
    ├── GETTING_STARTED.md
    ├── deployment.md
    └── VISUAL_QA_PLAN.md              # План Visual QA Testing
```

---

## Приложение C: Архитектура Visual QA Testing {#appendix-c-visual-qa}

> Расширение QA-агента для визуального тестирования UI через Playwright.
> Фазы: **Scripted E2E** (Фаза 1) → **Guided Exploration** (Фаза 2).
> Фаза 3 (Autonomous Loop) — **отложена на неопределённый срок** (см. [VISUAL_QA_PLAN.md §7](VISUAL_QA_PLAN.md#7-целесообразность)).
>
> **Текущий статус (2026-02-15):**
> - Фаза 1 (Scripted E2E) — **реализована и проверена**. QA-агент генерирует Playwright E2E-тесты, запускает в sandbox-browser контейнере, собирает скриншоты и анализирует результаты через LLM.
> - Фаза 2 (Guided Exploration) — **реализована**. LLM генерирует JSON-план обхода UI, exploration runner выполняет весь план в одном прогоне через Playwright, LLM пакетно анализирует результаты. 2 LLM-вызова вместо 20-50. 53 unit-теста.
>
> Связанный документ: [VISUAL_QA_PLAN.md](VISUAL_QA_PLAN.md)

### C.1 Обзор и мотивация

Текущий QA-агент умеет:
- Запускать код в sandbox (pytest, jest, go test, cargo test)
- Проверять синтаксис и компиляцию
- Анализировать stdout/stderr/exit_code через LLM

**Чего не хватает:** проверки того, что UI **выглядит и работает правильно** —
кнопки кликабельны, формы отправляются, страницы рендерятся без ошибок,
визуал соответствует требованиям.

### C.2 Архитектурное решение: три фазы

```
┌──────────────────────────────────────────────────────────────────────┐
│                        QA Agent — Testing Pipeline                   │
│                                                                      │
│  ┌─────────────┐   ┌─────────────────┐   ┌───────────────────────┐  │
│  │  test_code() │   │   test_ui()     │   │  test_explore()       │  │
│  │  (Фаза 0)   │   │   (Фаза 1)     │   │  (Фаза 2)             │  │
  │  │             │   │                 │   │                       │  │
  │  │ Unit/Integ  │   │ Scripted E2E    │   │ Guided Exploration    │  │
  │  │ pytest/jest │   │ Playwright      │   │ (batch)               │  │
│  │ (sandbox)   │   │ (browser-       │   │ (browser-sandbox)     │  │
│  │             │   │  sandbox)       │   │                       │  │
│  └──────┬──────┘   └──────┬──────────┘   └──────┬────────────────┘  │
│         │                 │                      │                   │
│         ▼                 ▼                      ▼                   │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                   Итоговый Verdict (pass/fail)                │   │
│  └──────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

**Политика запуска:**

1. `test_code()` — **всегда** (unit / integration / syntax check)
2. `test_ui()` — **если проект имеет UI** (определяется по tech_stack: React, Vue, Angular, Next.js, HTML и т.д.)
3. `test_explore()` — **только при явном включении** (`USE_BROWSER_EXPLORATION=true`)

### C.3 Sandbox: Browser Mode

Расширение существующего sandbox-сервиса для поддержки Playwright.

**Изменения в Sandbox API:**

```python
class SandboxExecuteRequest(BaseModel):
    language: str
    code_files: list[dict]
    commands: list[str]
    timeout: int = 60
    memory_limit: str = "256m"
    network: bool = False
    # === Новые поля ===
    browser: bool = False               # Использовать образ с Playwright
    collect_screenshots: bool = False   # Собирать скриншоты из /screenshots/
    app_start_command: str | None = None  # Команда запуска приложения (фоном)
    app_ready_timeout: int = 30          # Секунды на ожидание готовности приложения

class SandboxExecuteResponse(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    duration_seconds: float
    tests_passed: bool | None = None
    files_output: list[dict] = []
    # === Новые поля ===
    screenshots: list[dict] = []         # [{name: str, base64: str}]
    browser_console: str = ""            # Console output из браузера
    network_errors: list[str] = []       # Failed requests
```

**Docker-образ `sandbox-browser`:**

```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.50.0-noble
# Включает: Chromium, Firefox, WebKit + Python 3.x

RUN pip install pytest pytest-playwright
# + Node.js runtime для JS-приложений
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs
```

**Выбор образа:** При `browser: true` sandbox executor использует `sandbox-browser`
вместо стандартного языкового образа. Приложение и тесты запускаются в одном контейнере.

### C.4 QA Agent: расширенный pipeline

```python
# Расширенный QA node function (концепт)

def qa_agent(state, config=None):
    agent = get_qa_agent()
    
    # Фаза 0: Unit / Integration tests (существующий)
    code_result = agent.test_code(state, config)
    
    # Фаза 1: Browser E2E tests (если проект имеет UI)
    if agent.has_ui(state) and USE_BROWSER_TESTING:
        browser_result = agent.test_ui(state, config)
        code_result = agent.merge_results(code_result, browser_result)
    
    # Фаза 2/3: Exploration (если включено)
    if USE_BROWSER_EXPLORATION and agent.has_ui(state):
        explore_result = agent.test_explore(state, config)
        code_result = agent.merge_results(code_result, explore_result)
    
    return code_result
```

**Метод `test_ui()` — Scripted E2E (Фаза 1):**

```
QA Agent                    LLM                      Sandbox
    │                        │                          │
    │ 1. Собирает контекст:  │                          │
    │    user_stories         │                          │
    │    tech_stack           │                          │
    │    code_files           │                          │
    │                        │                          │
    │ 2. Генерирует тест ───>│                          │
    │    (промпт: generate_  │                          │
    │     browser_test)      │                          │
    │                        │                          │
    │ <── Playwright скрипт  │                          │
    │     (Python / TS)      │                          │
    │                        │                          │
    │ 3. Отправляет в sandbox ─────────────────────────>│
    │    code_files +                                   │
    │    playwright_test.py +                            │
    │    browser=true                                    │
    │                                                    │
    │    Sandbox:                                        │
    │    a) Устанавливает зависимости                   │
    │    b) Запускает приложение (фоном)                │
    │    c) Ждёт готовности (healthcheck)               │
    │    d) Запускает Playwright тесты                  │
    │    e) Собирает скриншоты                          │
    │                                                    │
    │ <── {stdout, stderr, exit_code, screenshots,      │
    │      browser_console, network_errors}              │
    │                        │                          │
    │ 4. Анализирует ───────>│                          │
    │    (промпт: analyse_   │                          │
    │     browser_results)   │                          │
    │    + скриншоты (base64) │                          │
    │                        │                          │
    │ <── Verdict + Issues   │                          │
```

**Метод `test_explore()` — Guided Exploration (Фаза 2):**

```
QA Agent                    LLM                      Sandbox
    │                        │                          │
    │ 1. Генерирует план ──>│                          │
    │    обхода              │                          │
    │    (промпт: generate_ │                          │
    │     exploration_plan)  │                          │
    │                        │                          │
    │ <── exploration.json   │                          │
    │  [{url, actions,       │                          │
    │    assertions}]        │                          │
    │                        │                          │
    │ 2. Отправляет план ──────────────────────────────>│
    │    + exploration_      │                          │
    │      runner.py         │                          │
    │    + browser=true      │                          │
    │                        │                          │
    │    Runner выполняет    │                          │
    │    весь план за один   │                          │
    │    прогон, на каждом   │                          │
    │    шаге: screenshot +  │                          │
    │    console + result    │                          │
    │                        │                          │
    │ <── report.json +      │                          │
    │     screenshots[]      │                          │
    │                        │                          │
    │ 3. Пакетный анализ ──>│                          │
    │    (промпт: analyse_   │                          │
    │     exploration)       │                          │
    │    + все скриншоты     │                          │
    │                        │                          │
    │ <── Defects + Score    │                          │
```

### C.5 State: новые поля

```python
class DevTeamState(TypedDict):
    # ... существующие поля ...

    # === Visual QA ===
    browser_test_results: NotRequired[dict]
    # Структура:
    # {
    #     "mode": "scripted_e2e" | "guided_exploration" | "autonomous",
    #     "screenshots": [{"name": str, "step": str}],
    #     "console_logs": str,
    #     "network_errors": [str],
    #     "test_status": "pass" | "fail" | "partial",
    #     "steps_executed": int,
    #     "urls_visited": [str],
    #     "defects_found": [{"description": str, "severity": str, "screenshot": str}],
    #     "duration_seconds": float,
    # }
```

### C.6 Переменные окружения

```bash
# Browser testing
USE_BROWSER_TESTING=true         # Включить Scripted E2E (Фаза 1)
USE_BROWSER_EXPLORATION=false    # Включить Guided Exploration (Фаза 2)
# USE_AUTONOMOUS_TESTING=false   # Фаза 3 — отложена на неопределённый срок
BROWSER_TEST_TIMEOUT=120         # Таймаут на browser тесты (секунды)
BROWSER_MAX_SCREENSHOTS=20       # Лимит скриншотов за один прогон
BROWSER_EXPLORATION_MAX_STEPS=30 # Лимит шагов для exploration
```

### C.7 Артефакты и хранение

Скриншоты возвращаются как base64 в `SandboxExecuteResponse.screenshots`.
Для LLM-анализа передаются как image content в multimodal message.
Не хранятся на диске долгосрочно — только на время одного run.

**Будущее:** если потребуется baseline-сравнение (visual regression),
скриншоты будут сохраняться в Git-репозиторий проекта или в S3-совместимое хранилище.

### C.8 Безопасность и лимиты

| Параметр | Значение | Обоснование |
|----------|----------|-------------|
| Timeout на browser-тесты | 120s | Достаточно для E2E, не слишком долго |
| Memory limit | 512m | Chromium требует больше RAM, чем CLI |
| Network | Только localhost | Приложение и тесты в одном контейнере |
| Max screenshots | 20 | Ограничение объёма данных для LLM |
| Max exploration steps | 30 | Предотвращение зацикливания |
| Domain allowlist | localhost only | Фаза 1-2; настраиваемый в Фазе 3 |

### C.9 Потоковая диаграмма в графе

```
Developer → Security → Reviewer → QA ─────────────→ git_commit
                                   │                    ↑
                                   │  test_code()       │
                                   │  test_ui()         │ (pass)
                                   │  test_explore()    │
                                   │                    │
                                   └── (fail) ─→ developer
```

QA node остаётся одним узлом в графе. Внутри он последовательно
запускает доступные тестовые режимы. Итоговый verdict — AND:
все режимы должны пройти для общего PASS.

---

## Приложение D: Эволюция QA & Testing {#appendix-d-qa-evolution}

> Стратегия развития QA-пайплайна: инфраструктура, sandbox, CI/CD, тестирование, распределение ролей.
> Дополняет [Приложение C](#appendix-c-visual-qa) (Visual QA Testing).
>
> Дата: 15 февраля 2026
> Фокус стека: **Python + Frontend (HTML/CSS/JS) + PostgreSQL + Redis**

Улучшения разделены на две плоскости:

- **Архитектура и инструменты** — инфраструктура, sandbox, CI-интеграция. Строим сейчас.
- **Графы и промпты** — кто пишет тесты, какие промпты, логика роутинга. Проектируем позже, но идеи фиксируем.

### D.1 Текущее состояние

```
PM → Analyst → Architect → Developer → Security → Reviewer → QA → Git Commit
                                          ↑                          |
                                          └────── fix loop ──────────┘
```

| Агент | Инструменты | Пишет тесты? |
|-------|-------------|--------------|
| Developer | LLM | Нет |
| Security | LLM (без сканеров) | Нет |
| Reviewer | LLM (без линтеров) | Нет |
| QA | LLM + Sandbox + Browser | Нет (exploration plan) |

**Проблема:** QA тратит токены на всё — от понимания кода до запуска. Многое можно сдвинуть раньше или в CI/CD.

### D.2 Sandbox: расширения

#### Образы (фокус-стек)

```
aicrew-sandbox-browser-base    (Python 3.12 + Playwright + Chromium)
  ├── browser-python            (pip, pytest)           ~1.5 GB
  └── browser-node              (+Node.js 20, npm)      ~1.5 GB
```

Другие стеки (Java, Go, Ruby) — на будущее.

#### Постоянные сервисы

| Сервис | Зачем | RAM | Негативное влияние |
|--------|-------|-----|--------------------|
| PostgreSQL | Django/FastAPI проекты | ~100 MB | Низкое: стабилен |
| Redis | Кэш, очереди, сессии | ~30 MB | Низкое: стабилен |
| Nexus proxy | Кэш pip/npm пакетов | ~500 MB | Среднее: JVM, конфигурация |

> **Примечание:** Это **не** основной PostgreSQL платформы (§2.1), а отдельные инстансы для sandbox-проектов.

#### Инструменты в образах

| Инструмент | Зачем | Добавить в |
|-----------|-------|-----------|
| lighthouse | Performance audit | browser-node |
| axe-core | Accessibility (WCAG) | browser-node |
| pip-audit | CVE в Python-зависимостях | browser-python |

#### Расширения подключений

| Возможность | Описание | Сложность | Негативное влияние |
|------------|----------|-----------|-------------------|
| PG-подключение | Sandbox видит PostgreSQL-сервис | Средняя | Низкое |
| Redis-подключение | Sandbox видит Redis-сервис | Средняя | Низкое |
| Lighthouse/axe | Пакеты предустановлены в образе | Низкая | Низкое |
| Visual regression | pixelmatch: скриншоты до/после | Средняя | Среднее: хранение, false positives |

### D.3 CI/CD интеграция

#### Механизм CI-лупа

```
Git Commit → Push → GitHub Actions
     ├── lint (ruff/pylint + eslint)
     ├── typecheck (mypy)
     ├── test (pytest + jest)
     ├── build (docker)
     ├── security (pip-audit, CodeQL)
     └── coverage
         ↓
CI FAIL → Developer на доработку (автоматический луп)
CI PASS → QA
```

**Принцип:** к моменту, когда код попадает к QA, стандартные проверки уже пройдены. QA не дублирует CI.

#### Компоненты для реализации

| Компонент | Описание | Сложность | Негативное влияние |
|-----------|----------|-----------|-------------------|
| CI-конфиг генерация | Developer генерирует `.github/workflows/ci.yml` | Низкая | Низкое |
| CI-луп в графе | Роутинг: CI FAIL → Developer, CI PASS → QA | Средняя | Среднее: логика роутинга |
| CI-результат парсинг | Чтение статуса GitHub Actions из графа | Средняя | Среднее: API-интеграция |

#### Pre-commit sandbox — роль при наличии CI

При работающем CI-лупе sandbox в QA — это **не тестирование**, а **подготовка среды** для exploration: подтверждение, что приложение стартует и доступно. Собственно тесты прогоняет CI.

### D.4 QA-CLI-агент

QA-CLI-агент вводится как отдельный узел графа. CLI-агент (Claude Code / Codex на отдельной VPS) получает полный доступ к файловой системе, сети, терминалу. Работает агентно: сам читает код, запускает приложение, ходит по UI, тестирует security.

**Ключевое:** заменяет / существенно отодвигает необходимость Фазы 3 (Agentic Testing, см. [Приложение C](#appendix-c-visual-qa)). То, для чего нужно было бы строить сложный screenshot → LLM → action loop — CLI-агент делает из коробки.

| Параметр | QA Internal (текущий) | QA-CLI-агент |
|----------|-----------------------|--------------|
| Токены | 2-3 LLM-вызова | 10-50 вызовов |
| Время | 30-60 сек | 2-10 мин |
| Контроль | Высокий (JSON plan) | Низкий (агентик сам) |
| Code-aware | Нет | Да (из коробки) |
| Security pen-test | Промпт-driven | Полный (curl, файлы, всё) |
| Инфраструктура | Sandbox (есть) | VPS CLI Runner (строим) |

**Использование:** отдельные "дорогие" графы, сложные проекты (full-stack, auth, БД). Текущий QA Internal остаётся для быстрых проверок.

**Зависимость:** CLI Runner API ([§5](#5-cli-runner-api), [IMPLEMENTATION_PLAN §3.6](IMPLEMENTATION_PLAN.md#3-волна-2)).

### D.5 Масштаб проектов (готовность)

| Масштаб | Пример | Готовность | Блокер |
|---------|--------|------------|--------|
| Один компонент | "Кнопка на React" | ~90% | — |
| Простое приложение | "TODO на Flask/Express" | ~70% | — |
| Full-stack | "FastAPI + React" | ~40% | CI-луп, тесты |
| С БД | "Django + PostgreSQL" | ~10% | PG-контейнер |
| С кэшем | "FastAPI + Redis + Celery" | ~5% | PG + Redis |

### D.6 Стратегия тестирования: кто пишет тесты

#### Проблема

Developer пишет код + тесты = конфликт интересов: подгонка, удаление непроходящих тестов, пустые assert'ы.

#### Подходы

**A. Developer пишет всё** (минимальная сложность)
```
Developer → код + тесты + CI → Reviewer проверяет качество тестов
```
Митигация: Reviewer в промпте ищет подгонку. Просто, дёшево, но ненадёжно.

**B. Architect пишет тесты ДО кода** (Test-First)
```
Architect → тесты-контракты → Developer пишет код → CI проверяет
```
Developer не может менять тесты. Надёжнее, но дороже (+1 LLM-вызов, изменение пайплайна).

**C. Отдельный Test-агент**
```
Developer → код → TestWriter → тесты → CI
```
Полная независимость, но новый агент = новые промпты, токены, усложнение графа.

**D. QA дополняет тесты из exploration**
```
QA exploration → находит баг → генерирует тест → Developer фиксит
```
Покрывает неочевидное, но поздно и дорого.

**План:** этап 1 — подход A, этап 2 — подход B.

> **Важно: вариативность агентов.** Developer-агент может быть разным от графа к графу — в одном графе developer сам пишет тесты (подход A), в другом тесты заранее написал architect (подход B). Это касается любых агентов/узлов — они могут отличаться между графами. Подробнее о концепции вариативности — см. [§7.4](#7-4-agent-variability).

### D.7 Промпт-изменения агентов

| Агент | Изменение | Влияние |
|-------|-----------|---------|
| Developer | Генерировать тесты + CI-конфиг + Dockerfile | Очень высокое |
| Reviewer | Проверять покрытие тестов, искать подгонку | Высокое |
| QA | Security pen-testing: SQL injection, XSS, auth bypass | Очень высокое |
| QA | Code-aware exploration: план на основе реального кода | Высокое |

### D.8 QA exploration: подходы

| Подход | Описание | Статус |
|--------|----------|--------|
| Guided Exploration | JSON-план → runner → анализ (2 LLM-вызова) | **Готово** (Фаза 2) |
| Code-aware | Exploration plan учитывает код (`@login_required` → тест auth) | Промпт |
| Multi-pass | Разведка → таргет → edge cases (3 прохода) | Идея |
| Agentic (Фаза 3) | LLM управляет браузером real-time | **Заменяется QA-CLI-агентом** |
| Regression | git diff → тест изменённого → diff скриншотов | Идея |
| Респонсив | 3 viewport в exploration plan | Промпт |

### D.9 Целевое распределение ролей

```
РАННИЕ ЭТАПЫ (LLM)        CI/CD (GitHub Actions)    QA (уникальная ценность)
─────────────────────      ──────────────────────    ─────────────────────────
Developer:                 ruff / pylint / eslint    Visual exploration
  код + тесты + CI         mypy                     Security pen-testing
Security:                  pytest / jest             Performance / a11y
  SAST + pip-audit         build                    Оценка качества тестов
Reviewer:                  pip-audit
  code review              coverage
  + проверка тестов        ↓
                           FAIL → Developer
                           PASS → QA
```

### D.10 Приоритеты

Параметры: **влияние** / **сложность** / **негативное влияние** (хрупкость, усложнение, ресурсы).

#### P0 — Архитектура: минимальные инфра-изменения

| # | Улучшение | Влияние | Сложность | Негатив |
|---|-----------|---------|-----------|---------|
| 1 | PostgreSQL контейнер для проектов | Высокое | Средняя | Низкий |
| 2 | Lighthouse + axe-core в образе | Высокое | Низкая | Низкий |
| 3 | pip-audit в sandbox | Высокое | Низкая | Низкий |

#### P1 — Архитектура: CI-луп + CLI Runner

| # | Улучшение | Влияние | Сложность | Негатив |
|---|-----------|---------|-----------|---------|
| 4 | CI-луп (FAIL → Developer) | Очень высокое | Средняя | Средний |
| 5 | CI-результат парсинг | Высокое | Средняя | Средний |
| 6 | CLI Runner API (для QA-CLI) | Высокое | Высокая | Средний |

#### P2 — Архитектура: расширение

| # | Улучшение | Влияние | Сложность | Негатив |
|---|-----------|---------|-----------|---------|
| 7 | Redis контейнер | Среднее | Средняя | Низкий |
| 8 | Nexus proxy (кэш пакетов) | Высокое | Средняя | Средний |
| 9 | Visual regression (pixelmatch) | Высокое | Средняя | Средний |

#### G0 — Графы: промпт-инжиниринг (0 кода)

| # | Улучшение | Влияние | Сложность | Негатив |
|---|-----------|---------|-----------|---------|
| 10 | Developer пишет тесты + CI конфиг | Очень высокое | Низкая | Низкий |
| 11 | Security pen-testing промпт QA | Очень высокое | Низкая | Минимальный |
| 12 | Code-aware exploration | Высокое | Нулевая | Минимальный |
| 13 | Reviewer проверяет тесты | Высокое | Низкая | Минимальный |

#### G1 — Графы: пайплайн-изменения

| # | Улучшение | Влияние | Сложность | Негатив |
|---|-----------|---------|-----------|---------|
| 14 | Architect пишет тесты (TDD) | Высокое | Средняя | Средний |
| 15 | Multi-pass testing | Высокое | Средняя | Средний |
| 16 | QA-CLI-агент граф (дорогие задачи) | Высокое | Средняя | Средний |

#### Вне фокуса (на будущее)

- Другие стеки (Java, Go, Ruby) — новые образы
- N+1 query detection — сложная инструментация PG
- Отдельный Test-агент — усложнение графа
- MinIO, WireMock — расширенная инфраструктура
