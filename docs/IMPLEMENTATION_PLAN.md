# AI-crew: План реализации

> Помодульная разбивка реализации, тестирование, критерии приёмки.
> Рабочий документ для автономной реализации каждого модуля.
>
> Дата: 16 февраля 2026 (обновлено: рефакторинг фазы 10-14, принцип Scripts-over-manual)
> Связанные документы:
> - [ARCHITECTURE_V2.md](ARCHITECTURE_V2.md) — целевая архитектура, API-контракты, модели данных
> - [EVOLUTION_PLAN_V3.md](EVOLUTION_PLAN_V3.md) — решения и обоснования
> - [ARCHITECTURE_V2.md — Приложение D](ARCHITECTURE_V2.md#appendix-d-qa-evolution) — архитектура QA-улучшений

---

## Содержание

1. [Принципы реализации](#1-принципы)
2. [Волна 1: Помодульная разбивка](#2-волна-1)
3. [Волна 2: Помодульная разбивка](#3-волна-2)
4. [Стратегия тестирования](#4-тестирование)
5. [CI/CD для AI-crew](#5-cicd)
6. [Чеклист готовности](#6-чеклист)
7. [Риски и митигации](#7-риски)
8. [Глоссарий зависимостей между модулями](#8-зависимости)

---

## 1. Принципы реализации {#1-принципы}

### 1.1 Порядок работы

1. **Каждый модуль — один PR** (или логическая группа, если модули тесно связаны)
2. **Сначала backend, потом frontend** — для каждой фичи
3. **Тесты пишутся вместе с кодом** — не откладываем
4. **Не ломаем существующее** — все изменения обратно совместимы до переключения
5. **Feature flags** — для постепенного включения (env vars)
6. **Scripts-over-manual** *(предложение, ожидает одобрения)* — всё, что может выполняться скриптами (деплой, миграции, проверки здоровья, генерация конфигов, seed данных), должно быть автоматизировано. Это снижает ошибки при ручном выполнении и уменьшает потребление токенов агентами. Примеры: `scripts/deploy.sh`, `scripts/health_check.py`, `scripts/seed_db.py`, `scripts/generate_manifests.py`

### 1.2 Ветвление

```
main
  └── feat/wave1-foundation          # structlog, agents.yaml, retry, langfuse
  └── feat/wave1-gateway             # Gateway + auth
  └── feat/wave1-frontend-auth       # Login, Register, JWT
  └── feat/wave1-graph-viz           # React Flow визуализация
  └── feat/wave1-streaming           # SSE streaming hook
  └── feat/wave1-web-tools           # DuckDuckGo + fetch
  └── feat/wave1-telegram            # Telegram bot
  └── feat/wave1-manifest            # manifest.yaml + graph list
```

### 1.3 Контракт между модулями

Все межмодульные интерфейсы описаны в [ARCHITECTURE_V2.md §4-5](ARCHITECTURE_V2.md#4-gateway-api).
При реализации модуля — сначала реализуем интерфейс (endpoint, модели), потом логику.

---

## 2. Волна 1: Помодульная разбивка {#2-волна-1}

---

### 2.1 Модуль: structlog (логирование)

**Цель:** Заменить `logging.getLogger` на `structlog` во всех модулях.

**Файлы:**

| Действие | Файл | Что делать |
|----------|------|-----------|
| Создать | `graphs/dev_team/logging_config.py` | Конфигурация structlog (ConsoleRenderer/JSONRenderer) |
| Изменить | `graphs/dev_team/graph.py` | Заменить `configure_logging()` на импорт из `logging_config` |
| Изменить | `graphs/dev_team/agents/base.py` | `import structlog; logger = structlog.get_logger()` |
| Изменить | `graphs/dev_team/agents/pm.py` | Заменить logger |
| Изменить | `graphs/dev_team/agents/analyst.py` | Заменить logger |
| Изменить | `graphs/dev_team/agents/architect.py` | Заменить logger |
| Изменить | `graphs/dev_team/agents/developer.py` | Заменить logger |
| Изменить | `graphs/dev_team/agents/qa.py` | Заменить logger |
| Изменить | `requirements.txt` | Добавить `structlog>=24.0.0` |

**Внешние зависимости:** Нет (самостоятельный модуль)

**Реализация:**

```python
# graphs/dev_team/logging_config.py
import logging
import os
import structlog

def configure_logging():
    """Configure structlog for the application."""
    env_mode = os.getenv("ENV_MODE", "LOCAL").upper()
    log_level = os.getenv("LOG_LEVEL", "DEBUG" if env_mode == "LOCAL" else "INFO")

    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(message)s",
    )

    # Подавляем шумные библиотеки
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if env_mode == "LOCAL":
        processors.append(structlog.dev.ConsoleRenderer(colors=True))
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level, logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
```

**Паттерн замены в агентах:**
```python
# Было:
import logging
logger = logging.getLogger(__name__)
logger.info("Agent initialized: name=%s", self.name)

# Стало:
import structlog
logger = structlog.get_logger()
logger.info("agent.initialized", agent=self.name)
```

**Тестирование:**
- Unit: проверить что `configure_logging()` не падает в LOCAL и PRODUCTION режимах
- Smoke: запустить граф, убедиться что логи выходят в нужном формате

**Критерии приёмки:**
- [ ] Все модули используют structlog
- [ ] В LOCAL-режиме — цветной вывод
- [ ] В PRODUCTION — JSON
- [ ] Шумные библиотеки подавлены
- [ ] Существующие тесты проходят

**Сложность: 1/10 | 0.5-1 день**

---

### 2.2 Модуль: LLM Config (agents.yaml)

**Цель:** Вынести конфигурацию моделей из кода в `config/agents.yaml`.

**Файлы:**

| Действие | Файл | Что делать |
|----------|------|-----------|
| Создать | `config/agents.yaml` | Конфигурация моделей (см. ARCHITECTURE_V2 §7.1) |
| Изменить | `graphs/dev_team/agents/base.py` | `load_agent_config()`, обновить `get_llm()`, `get_model_for_role()` |

**Внешние зависимости:** Нет

**Реализация:**

```python
# base.py — новые функции

import yaml
from pathlib import Path
from string import Template

_agent_config_cache: dict | None = None

def load_agent_config() -> dict:
    """Load config/agents.yaml with env var substitution. Cached."""
    global _agent_config_cache
    if _agent_config_cache is not None:
        return _agent_config_cache

    config_path = Path(__file__).parent.parent.parent.parent / "config" / "agents.yaml"
    if not config_path.exists():
        logger.warning("config.not_found", path=str(config_path))
        return {"defaults": {}, "endpoints": {}, "agents": {}}

    raw = config_path.read_text(encoding="utf-8")
    # Подстановка ${ENV_VAR} из окружения
    substituted = Template(raw).safe_substitute(os.environ)
    config = yaml.safe_load(substituted)
    _agent_config_cache = config
    return config

def get_model_for_role(role: str) -> str:
    """Get model respecting priority: env > yaml > defaults."""
    # 1. Env override
    env_model = os.getenv(f"LLM_MODEL_{role.upper()}")
    if env_model:
        return env_model

    # 2. agents.yaml
    config = load_agent_config()
    yaml_model = config.get("agents", {}).get(role, {}).get("model")
    if yaml_model:
        return yaml_model

    # 3. Global env
    default_env = os.getenv("LLM_DEFAULT_MODEL")
    if default_env:
        return default_env

    # 4. Hardcoded defaults
    return DEFAULT_MODELS.get(role, DEFAULT_MODELS["default"])
```

**Тестирование:**
- Unit: `load_agent_config()` с фикстурным YAML
- Unit: `get_model_for_role()` — проверить приоритет (env > yaml > defaults)
- Unit: env var подстановка в YAML работает

**Критерии приёмки:**
- [ ] `config/agents.yaml` создан с правильными моделями
- [ ] Приоритет: env > yaml > hardcoded defaults
- [ ] `load_agent_config()` кэширует результат
- [ ] Env vars подставляются через `Template.safe_substitute`
- [ ] Существующие тесты проходят (обратная совместимость)

**Сложность: 2/10 | 0.5-1 день**

---

### 2.3 Модуль: Retry + Fallback

**Цель:** Добавить retry с exponential backoff и fallback chain для LLM-вызовов.

**Файлы:**

| Действие | Файл | Что делать |
|----------|------|-----------|
| Изменить | `graphs/dev_team/agents/base.py` | `invoke_with_retry()`, `get_llm_with_fallback()` |
| Изменить | Все агенты (pm, analyst, ...) | Заменить `chain.invoke()` → через retry |
| Изменить | `requirements.txt` | `tenacity>=8.2.0` (уже есть) |

**Зависимости:** Модуль 2.2 (agents.yaml — для fallback_model)

**Реализация:**

```python
# base.py

from tenacity import (
    retry, stop_after_attempt, wait_exponential,
    retry_if_exception_type, before_sleep_log, RetryError,
)

RETRYABLE_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    # httpx.ConnectError, httpx.ReadTimeout — если используем httpx
)

def invoke_with_retry(
    chain,
    inputs: dict,
    config: dict | None = None,
    max_attempts: int = 3,
    **kwargs,
):
    """Invoke LLM chain with exponential backoff retry."""
    callbacks = (config or {}).get("callbacks", [])

    @retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
        before_sleep=before_sleep_log(logger, "warning"),
        reraise=True,
    )
    def _invoke():
        invoke_config = {"callbacks": callbacks} if callbacks else {}
        return chain.invoke(inputs, config=invoke_config)

    try:
        return _invoke()
    except RetryError:
        logger.error("llm.retry_exhausted", attempts=max_attempts)
        raise

def get_llm_with_fallback(role: str, **kwargs) -> BaseChatModel:
    """Get LLM with fallback chain from config."""
    config = load_agent_config()
    primary = get_llm(role=role, **kwargs)

    fallback_model = config.get("agents", {}).get(role, {}).get("fallback_model")
    if fallback_model:
        fallback = get_llm(model=fallback_model, **kwargs)
        return primary.with_fallbacks([fallback])

    return primary
```

**Тестирование:**
- Unit: `invoke_with_retry` — мокаем chain, проверяем retry на ConnectionError
- Unit: `invoke_with_retry` — проверяем что non-retryable exceptions пробрасываются
- Unit: `get_llm_with_fallback` — проверяем что возвращает RunnableWithFallbacks

**Критерии приёмки:**
- [ ] Retry с exponential backoff (3 попытки, 4-60 сек)
- [ ] Fallback chain из agents.yaml
- [ ] Логирование каждой retry-попытки
- [ ] Non-retryable exceptions пробрасываются сразу
- [ ] Существующие тесты проходят

**Сложность: 1/10 | 0.5 дня**

---

### 2.4 Модуль: Langfuse Fix (callbacks)

**Цель:** Пробросить Langfuse callbacks из LangGraph config в LLM-вызовы агентов.

**Файлы:**

| Действие | Файл | Что делать |
|----------|------|-----------|
| Изменить | `graphs/dev_team/agents/base.py` | `_get_callbacks()`, `_invoke_chain()` в BaseAgent |
| Изменить | Все агенты | Добавить `config: RunnableConfig` параметр, использовать `_invoke_chain` |
| Изменить | `graphs/dev_team/graph.py` | Node functions: добавить `config` параметр |
| Изменить | `.env` / env.example | `LANGFUSE_ENABLED=true` |

**Зависимости:** Модуль 2.3 (retry — `invoke_with_retry` использует callbacks)

**Реализация:**

```python
# base.py — дополнение к BaseAgent
from langchain_core.runnables import RunnableConfig

class BaseAgent:
    # ... существующий код ...

    def _get_callbacks(self, config: RunnableConfig | None) -> list:
        """Extract callbacks from LangGraph config for Langfuse tracing."""
        if config and "callbacks" in config:
            return config["callbacks"]
        return []

    def _invoke_chain(self, chain, inputs: dict, config: RunnableConfig | None = None):
        """Invoke chain with retry + callbacks."""
        return invoke_with_retry(chain, inputs, config=config)
```

**Паттерн обновления агентов:**

```python
# Было (в каждом агенте):
def pm_agent(state: DevTeamState) -> dict:
    agent = get_pm_agent()
    return agent.invoke(state)

# Стало:
def pm_agent(state: DevTeamState, config: RunnableConfig = None) -> dict:
    agent = get_pm_agent()
    return agent.invoke(state, config=config)

# И внутри агента:
class ProjectManagerAgent(BaseAgent):
    def invoke(self, state: dict, config: RunnableConfig = None) -> dict:
        # ... формируем chain ...
        result = self._invoke_chain(chain, inputs, config=config)
        # ...
```

**LangGraph автоматически** передаёт `config` если node function его принимает.
Callbacks не загружают контекст LLM — это hooks, которые Langfuse перехватывает
на уровне вызова, сохраняя промпт/ответ/токены в свою БД.

**Тестирование:**
- Unit: `_get_callbacks` с и без callbacks в config
- Unit: `_invoke_chain` вызывает `invoke_with_retry` с правильными callbacks
- Integration: запустить граф с `LANGFUSE_ENABLED=true`, проверить traces в Langfuse UI

**Критерии приёмки:**
- [ ] Все node functions принимают `config: RunnableConfig = None`
- [ ] Все агенты используют `_invoke_chain()` вместо прямого `chain.invoke()`
- [ ] В Langfuse видны Generations (промпт, ответ, модель, токены)
- [ ] Контекст LLM НЕ загружен лишними данными

**Сложность: 2/10 | 0.5-1 день**

---

### 2.5 Модуль: manifest.yaml

**Цель:** Создать метаданные графа для UI и Switch-Agent.

**Файлы:**

| Действие | Файл | Что делать |
|----------|------|-----------|
| Создать | `graphs/dev_team/manifest.yaml` | Метаданные dev_team графа |
| Изменить | `aegra.json` | Подготовить к нескольким графам (без изменений пока) |

**Внешние зависимости:** Нет

**Реализация:**

```yaml
# graphs/dev_team/manifest.yaml
name: "dev_team"
display_name: "Development Team"
description: "Full software development: from requirements to Pull Request. 5 agents work together: PM, Analyst, Architect, Developer, QA."
version: "1.0.0"

task_types:
  - new_project
  - feature
  - bugfix
  - refactor

agents:
  - id: pm
    display_name: "Project Manager"
    role: pm
  - id: analyst
    display_name: "Business Analyst"
    role: analyst
  - id: architect
    display_name: "Software Architect"
    role: architect
  - id: developer
    display_name: "Developer"
    role: developer
  - id: qa
    display_name: "QA Engineer"
    role: qa

features:
  - hitl_clarification
  - hitl_escalation
  - qa_loop
  - git_commit

parameters:
  max_qa_iterations: 3
  use_security_agent: false
  deploy_after_commit: false
  hitl_mode: "optional"       # "required" | "optional" | "none"
```

**Тестирование:**
- Unit: проверить что YAML парсится корректно
- Unit: проверить обязательные поля (name, display_name, description, task_types)

**Критерии приёмки:**
- [ ] `manifest.yaml` создан для dev_team
- [ ] Содержит все поля из схемы (ARCHITECTURE_V2 §7.2)
- [ ] YAML валиден и парсится

**Сложность: 1/10 | 0.5 дня**

---

### 2.6 Модуль: Gateway (Auth + Proxy + Graph Endpoints)

**Цель:** Создать FastAPI Gateway с JWT auth, прокси к Aegra, и собственными endpoints.

Это **центральный модуль Волны 1** — от него зависят Frontend Auth, Graph Viz, Telegram.

**Файлы:**

| Действие | Файл | Что делать |
|----------|------|-----------|
| Создать | `gateway/` (вся директория) | FastAPI приложение |
| Создать | `gateway/main.py` | FastAPI app, маршрутизация |
| Создать | `gateway/config.py` | Pydantic Settings |
| Создать | `gateway/models.py` | Pydantic модели (User, Auth, Graph) |
| Создать | `gateway/database.py` | Async PostgreSQL (asyncpg) — users table |
| Создать | `gateway/auth.py` | JWT: register, login, refresh, get_current_user |
| Создать | `gateway/proxy.py` | Прокси к Aegra (REST + SSE streaming) |
| Создать | `gateway/endpoints/graph.py` | /graph/list, /graph/topology |
| Создать | `gateway/endpoints/run.py` | /api/run (с auto-routing) |
| Создать | `gateway/router.py` | Switch-Agent classify_task (заготовка) |
| Создать | `gateway/Dockerfile` | Python 3.11 + pip install |
| Создать | `gateway/requirements.txt` | fastapi, uvicorn, pyjwt, bcrypt, httpx, asyncpg |
| Изменить | `docker-compose.yml` | Добавить gateway сервис, убрать порт aegra |
| Изменить | `aegra.json` | Добавить gateway порт в CORS |
| Изменить | `env.example` | Добавить JWT_SECRET, GATEWAY_URL |

**Внешние зависимости:** PostgreSQL, Aegra

**Подробная разбивка на этапы:**

**Этап A: Скелет + Config (0.5 дня)**
```python
# gateway/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    aegra_url: str = "http://aegra:8000"
    database_url: str = "postgresql://aicrew:password@postgres:5433/aicrew"
    jwt_secret: str = "change-me-in-production"
    jwt_access_ttl: int = 1800       # 30 мин
    jwt_refresh_ttl: int = 604800    # 7 дней
    jwt_algorithm: str = "HS256"
    log_level: str = "INFO"
    env_mode: str = "LOCAL"
    llm_api_url: str = ""
    llm_api_key: str = ""

    class Config:
        env_file = ".env"

settings = Settings()
```

**Этап B: Database + Models (0.5 дня)**
```python
# gateway/database.py
import asyncpg
from gateway.config import settings

pool: asyncpg.Pool | None = None

async def init_db():
    """Initialize database pool and create tables."""
    global pool
    pool = await asyncpg.create_pool(settings.database_url)
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                display_name VARCHAR(100) NOT NULL,
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)"
        )

async def close_db():
    global pool
    if pool:
        await pool.close()
```

**Этап C: Auth (1 день)**
```python
# gateway/auth.py — ключевые функции
async def register(data: UserCreate) -> AuthResponse
async def login(data: UserLogin) -> AuthResponse
async def refresh_token(refresh_token: str) -> TokenPair
async def get_current_user(token: str = Depends(oauth2_scheme)) -> User
```

**Этап D: Proxy (0.5 дня)**
```python
# gateway/proxy.py — два метода
async def proxy_to_aegra(request: Request, user: User) -> Response
async def proxy_stream_to_aegra(request: Request, user: User) -> StreamingResponse
```

**Этап E: Graph Endpoints (0.5 дня)**
```python
# gateway/endpoints/graph.py
@router.get("/graph/list")
async def list_graphs() -> GraphListResponse
# Читает manifest.yaml из всех графов

@router.get("/graph/topology/{graph_id}")
async def graph_topology(graph_id: str) -> GraphTopologyResponse
# Собирает: topology (to_json) + agents (agents.yaml) + prompts (yaml)
```

**Этап F: Docker + интеграция (0.5 дня)**
- Dockerfile для gateway
- Добавление в docker-compose.yml
- Обновление CORS в aegra.json
- Обновление env.example

**Тестирование:**

```
tests/test_gateway/
├── test_auth.py               # register, login, refresh, invalid creds
├── test_proxy.py              # proxy to aegra (mock Aegra)
├── test_graph_endpoints.py    # /graph/list, /graph/topology
└── conftest.py                # fixtures: test client, test db
```

Подробнее:
- **test_auth.py:** register → login → получить me → refresh → invalid token → duplicate email
- **test_proxy.py:** mock Aegra httpx, проверить что headers/body проксируются, auth проверяется
- **test_graph_endpoints.py:** mock manifest.yaml + agents.yaml, проверить формат ответа

**Критерии приёмки:**
- [ ] `POST /auth/register` создаёт пользователя, возвращает JWT
- [ ] `POST /auth/login` возвращает JWT
- [ ] `GET /auth/me` возвращает текущего пользователя
- [ ] `POST /auth/refresh` обновляет токены
- [ ] Все `/threads/*`, `/runs/*`, `/assistants/*` проксируются к Aegra с проверкой JWT
- [ ] `POST /threads/{id}/runs/stream` проксирует SSE stream
- [ ] `POST /api/run` создаёт thread+run (с auto-routing заготовкой)
- [ ] `GET /graph/list` возвращает список графов из manifest.yaml
- [ ] `GET /graph/topology/{graph_id}` возвращает topology + agents + prompts
- [ ] `GET /graph/config/{graph_id}` возвращает конфигурацию агентов
- [ ] `GET /health` работает без auth
- [ ] Aegra НЕ доступна снаружи (только expose, не ports)
- [ ] Тесты покрывают auth flow, proxy, graph endpoints, /api/run

**Сложность: 4/10 | 3-4 дня**

---

### 2.7 Модуль: Frontend Auth

**Цель:** Добавить аутентификацию: Login, Register, protected routes, JWT в API-клиенте.

**Файлы:**

| Действие | Файл | Что делать |
|----------|------|-----------|
| Создать | `frontend/src/pages/Login.tsx` | Страница входа |
| Создать | `frontend/src/pages/Register.tsx` | Страница регистрации |
| Создать | `frontend/src/store/authStore.ts` | Zustand store для auth state |
| Создать | `frontend/src/hooks/useAuth.ts` | Hook для auth операций |
| Изменить | `frontend/src/api/aegra.ts` | JWT в headers, обновить baseURL на gateway |
| Изменить | `frontend/src/App.tsx` | Protected routes, redirect на /login |
| Изменить | `frontend/src/components/Layout.tsx` | Navbar: user info, logout button |

**Зависимости:** Модуль 2.6 (Gateway)

**Реализация:**

```typescript
// store/authStore.ts
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface AuthState {
  user: User | null
  accessToken: string | null
  refreshToken: string | null
  isAuthenticated: boolean
  setAuth: (user: User, accessToken: string, refreshToken: string) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      setAuth: (user, accessToken, refreshToken) =>
        set({ user, accessToken, refreshToken, isAuthenticated: true }),
      logout: () =>
        set({ user: null, accessToken: null, refreshToken: null, isAuthenticated: false }),
    }),
    { name: 'ai-crew-auth' }
  )
)
```

```typescript
// api/aegra.ts — обновления
class AegraClient {
  private getHeaders(): Record<string, string> {
    const token = useAuthStore.getState().accessToken
    return {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    }
  }

  // Все методы используют getHeaders()
  // baseURL = import.meta.env.VITE_API_URL || 'http://localhost:8081'
}
```

```typescript
// App.tsx — protected routes
function App() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)

  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/" element={isAuthenticated ? <Home /> : <Navigate to="/login" />} />
          <Route path="/task/:threadId" element={isAuthenticated ? <TaskDetail /> : <Navigate to="/login" />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  )
}
```

**Тестирование:**
- Manual: register → login → protected route → logout → redirect
- Проверить что API-запросы несут JWT header
- Проверить что refresh работает при истечении access token

**Критерии приёмки:**
- [ ] Login/Register страницы с формами
- [ ] JWT хранится в zustand + localStorage (persist)
- [ ] Все API-запросы несут `Authorization: Bearer <token>`
- [ ] Protected routes: без токена → redirect на /login
- [ ] Logout: очистка state + redirect
- [ ] Navbar показывает имя пользователя и кнопку Logout
- [ ] `VITE_API_URL` указывает на Gateway (не на Aegra напрямую)

**Сложность: 3/10 | 1-2 дня**

---

### 2.8 Модуль: Frontend Graph Visualization

**Цель:** Визуализация графа через React Flow: узлы, связи, модели, промпты, статус.

**Файлы:**

| Действие | Файл | Что делать |
|----------|------|-----------|
| Создать | `frontend/src/components/GraphVisualization.tsx` | React Flow компонент |
| Изменить | `frontend/src/pages/TaskDetail.tsx` | Вкладка/панель с графом |
| Изменить | `frontend/package.json` | `@xyflow/react`, `dagre` |

**Зависимости:** Модуль 2.6 (Gateway — `/graph/topology` endpoint)

**npm зависимости:**
```bash
npm install @xyflow/react dagre @types/dagre
```

**Реализация:**

```typescript
// components/GraphVisualization.tsx — структура
import { ReactFlow, Background, Controls, MiniMap } from '@xyflow/react'
import dagre from 'dagre'

interface Props {
  graphId: string
  currentAgent?: string   // Для подсветки активного узла
}

export function GraphVisualization({ graphId, currentAgent }: Props) {
  // 1. Fetch topology: GET /graph/topology/{graphId}
  // 2. Convert topology → React Flow nodes + edges
  // 3. Auto-layout via dagre
  // 4. Custom nodes: AgentNode (показывает model, status badge)
  // 5. Custom edges: ConditionalEdge (пунктир + label)
  // 6. По клику на узел: sidebar с system prompt + params
}

// Custom node: показывает
// - Название агента (display_name)
// - Модель (badge: "glm-4.7")
// - Fallback model (мелким шрифтом)
// - Статус (цвет бордера): active=cyan, completed=lime, pending=slate
function AgentNode({ data }: { data: AgentNodeData }) { ... }
```

**Маппинг topology → React Flow:**
```typescript
function topologyToReactFlow(
  topology: GraphTopology,
  currentAgent: string
): { nodes: Node[], edges: Edge[] } {
  const nodes = topology.topology.nodes
    .filter(n => n.id !== '__start__' && n.id !== '__end__')
    .map(n => ({
      id: n.id,
      type: 'agentNode',
      data: {
        label: topology.manifest?.agents?.find(a => a.id === n.id)?.display_name || n.id,
        model: topology.agents[n.id]?.model,
        fallbackModel: topology.agents[n.id]?.fallback_model,
        status: getNodeStatus(n.id, currentAgent),
        systemPrompt: topology.prompts[n.id]?.system,
        templates: topology.prompts[n.id]?.templates,
      },
      position: { x: 0, y: 0 },  // dagre расставит
    }))

  const edges = topology.topology.edges.map(e => ({
    id: `${e.source}-${e.target}`,
    source: e.source,
    target: e.target,
    animated: e.source === currentAgent,
    style: e.conditional ? { strokeDasharray: '5,5' } : {},
    label: e.data || '',
  }))

  return layoutWithDagre(nodes, edges)
}
```

**Тестирование:**
- Manual: открыть TaskDetail, проверить что граф отрисовывается
- Проверить что активный узел подсвечен
- Проверить клик на узел → sidebar с промптом и параметрами

**Критерии приёмки:**
- [ ] React Flow отрисовывает граф dev_team
- [ ] Узлы показывают: название, модель (badge), статус (цвет)
- [ ] Связи: обычные (сплошные) и conditional (пунктир + label)
- [ ] Auto-layout через dagre (сверху вниз)
- [ ] По клику: system prompt + параметры (модель, температура, fallback)
- [ ] Активный узел анимирован (pulsing border)
- [ ] Zoom, pan, minimap

**Сложность: 3/10 | 2-3 дня**

---

### 2.9 Модуль: Frontend Streaming

**Цель:** Заменить polling на SSE streaming для real-time обновлений.

**Файлы:**

| Действие | Файл | Что делать |
|----------|------|-----------|
| Создать | `frontend/src/hooks/useStreamingTask.ts` | SSE streaming hook |
| Изменить | `frontend/src/pages/TaskDetail.tsx` | Переключить на streaming |
| Изменить | `frontend/src/components/Chat.tsx` | Real-time сообщения |
| Изменить | `frontend/src/components/ProgressTracker.tsx` | Мгновенные обновления |

**Зависимости:** Модуль 2.6 (Gateway — SSE proxy)

**Реализация:**

```typescript
// hooks/useStreamingTask.ts
export function useStreamingTask(threadId: string) {
  const [state, setState] = useState<DevTeamState | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const startStream = useCallback(async (input: CreateTaskInput) => {
    setIsStreaming(true)
    setError(null)

    try {
      // 1. Создать run
      const run = await aegraClient.createRun(threadId, input)

      // 2. Подключиться к SSE stream
      const response = await fetch(
        `${API_URL}/threads/${threadId}/runs/stream`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${getToken()}`,
          },
          body: JSON.stringify({ assistant_id: input.graph_id || 'dev_team' }),
        }
      )

      const reader = response.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = JSON.parse(line.slice(6))
            // Обновляем state
            if (data.values) {
              setState(prev => ({ ...prev, ...data.values }))
            }
          }
        }
      }
    } catch (err) {
      setError(err as Error)
    } finally {
      setIsStreaming(false)
    }
  }, [threadId])

  return { state, isStreaming, error, startStream }
}
```

**Обратная совместимость:** `useTask` (polling) остаётся как fallback.
`useStreamingTask` используется на TaskDetail, когда run активен.

**Тестирование:**
- Manual: создать задачу, наблюдать real-time обновления в UI
- Проверить что ProgressTracker обновляется мгновенно (не каждые 2 сек)
- Проверить что Chat показывает сообщения по мере их появления

**Критерии приёмки:**
- [ ] SSE stream работает через Gateway proxy
- [ ] State обновляется в реальном времени
- [ ] ProgressTracker: мгновенная смена активного агента
- [ ] Chat: сообщения появляются по мере генерации
- [ ] Fallback на polling если SSE недоступен
- [ ] Корректная обработка разрыва соединения

**Сложность: 3/10 | 1-2 дня**

---

### 2.10 Модуль: Web Tools

**Цель:** Дать агентам доступ в интернет: поиск, скачивание страниц, загрузка файлов.

**Файлы:**

| Действие | Файл | Что делать |
|----------|------|-----------|
| Создать | `graphs/dev_team/tools/web.py` | web_search, fetch_url, download_file |
| Изменить | `requirements.txt` | `duckduckgo-search>=6.0.0`, `trafilatura>=1.8.0` |
| Изменить | Агенты (по необходимости) | Подключить tools через bind_tools |

**Внешние зависимости:** Нет (интернет-доступ)

**Реализация:**

```python
# tools/web.py
from langchain_core.tools import tool
from duckduckgo_search import DDGS
import httpx
import trafilatura

@tool
def web_search(query: str, max_results: int = 5) -> str:
    """Search the web using DuckDuckGo. Returns titles, URLs, and snippets."""
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=max_results))
    return "\n\n".join(
        f"**{r['title']}**\n{r['href']}\n{r['body']}"
        for r in results
    )

@tool
def fetch_url(url: str) -> str:
    """Fetch a web page and extract its main text content."""
    response = httpx.get(url, timeout=30, follow_redirects=True)
    response.raise_for_status()
    text = trafilatura.extract(response.text) or response.text[:5000]
    return text[:10000]  # Ограничение чтобы не забить контекст

@tool
def download_file(url: str, filename: str | None = None) -> str:
    """Download a file from URL. Returns the content as string (for text files)."""
    response = httpx.get(url, timeout=60, follow_redirects=True)
    response.raise_for_status()
    if len(response.content) > 1_000_000:  # 1MB limit
        return f"File too large: {len(response.content)} bytes"
    return response.text[:10000]
```

**Подключение к агентам (НЕ сейчас — когда агенты будут использовать tools):**
```python
# Пример будущего использования в analyst.py:
from dev_team.tools.web import web_search, fetch_url
llm_with_tools = llm.bind_tools([web_search, fetch_url])
```

**Тестирование:**
- Unit: `web_search` — mock DDGS, проверить формат вывода
- Unit: `fetch_url` — mock httpx, проверить trafilatura extraction
- Unit: ограничения (max size, timeout)
- Integration (manual): реальный поиск + fetch

**Критерии приёмки:**
- [ ] `web_search` возвращает результаты DuckDuckGo
- [ ] `fetch_url` извлекает текст из HTML
- [ ] `download_file` скачивает и возвращает текст
- [ ] Ограничения: timeout, max size, max chars
- [ ] Tools совместимы с LangChain `@tool` (можно bind_tools)

**Сложность: 3/10 | 1-2 дня**

---

### 2.11 Модуль: Telegram Bot

**Цель:** Альтернативный интерфейс через Telegram: создание задач, HITL, статус.

**Файлы:**

| Действие | Файл | Что делать |
|----------|------|-----------|
| Создать | `telegram/bot.py` | Aiogram bot setup + polling |
| Создать | `telegram/handlers.py` | Обработчики: /start, /task, /status, /help |
| Создать | `telegram/gateway_client.py` | HTTP-клиент к Gateway API |
| Создать | `telegram/Dockerfile` | Python 3.11 + aiogram |
| Создать | `telegram/requirements.txt` | aiogram, httpx |
| Изменить | `docker-compose.yml` | Добавить telegram сервис |
| Изменить | `env.example` | TELEGRAM_BOT_TOKEN |

**Зависимости:** Модуль 2.6 (Gateway)

**Реализация:**

```python
# telegram/gateway_client.py
class GatewayClient:
    """HTTP client for Gateway API."""

    def __init__(self, gateway_url: str, token: str | None = None):
        self.gateway_url = gateway_url
        self.token = token
        self.client = httpx.AsyncClient(timeout=300)

    async def login(self, email: str, password: str) -> str:
        """Login and get JWT token."""
        resp = await self.client.post(
            f"{self.gateway_url}/auth/login",
            json={"email": email, "password": password},
        )
        resp.raise_for_status()
        self.token = resp.json()["access_token"]
        return self.token

    async def create_run(self, task: str, **kwargs) -> dict:
        """Create a new task run."""
        resp = await self.client.post(
            f"{self.gateway_url}/api/run",
            json={"task": task, **kwargs},
            headers={"Authorization": f"Bearer {self.token}"},
        )
        resp.raise_for_status()
        return resp.json()

    async def get_thread_state(self, thread_id: str) -> dict:
        """Get current thread state."""
        resp = await self.client.get(
            f"{self.gateway_url}/threads/{thread_id}/state",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        resp.raise_for_status()
        return resp.json()

    async def send_clarification(self, thread_id: str, response: str) -> dict:
        """Send HITL clarification response."""
        resp = await self.client.post(
            f"{self.gateway_url}/threads/{thread_id}/state",
            json={
                "values": {
                    "clarification_response": response,
                    "needs_clarification": False,
                },
                "command": {"update": True},
            },
            headers={"Authorization": f"Bearer {self.token}"},
        )
        resp.raise_for_status()
        return resp.json()
```

```python
# telegram/handlers.py — ключевые команды
/start          → Приветствие + привязка к аккаунту (или сервисный)
/task <текст>   → Создание задачи (POST /api/run)
/status <id>    → Статус задачи (GET /threads/{id}/state)
/help           → Список команд

# HITL:
# Когда needs_clarification=true — бот отправляет вопрос
# Пользователь отвечает текстом → бот вызывает send_clarification

# Notifications:
# Polling thread state каждые 10 сек для активных задач
# При смене current_agent → уведомление
# При завершении → финальное сообщение с PR URL
```

**Тестирование:**
- Unit: `GatewayClient` — mock httpx
- Unit: handlers — mock GatewayClient
- Manual: реальный бот в Telegram

**Критерии приёмки:**
- [ ] `/task` создаёт задачу и возвращает thread_id
- [ ] `/status` показывает текущее состояние задачи
- [ ] HITL: бот отправляет вопрос, принимает ответ
- [ ] Уведомления о завершении (PR URL)
- [ ] Работает через Docker (polling, не webhook)
- [ ] Graceful shutdown при SIGTERM

**Сложность: 4/10 | 3-5 дней**

---

### 2.12 Модуль: State расширение (task_type, task_complexity)

**Цель:** Добавить поля для классификации задач.

**Файлы:**

| Действие | Файл | Что делать |
|----------|------|-----------|
| Изменить | `graphs/dev_team/state.py` | Добавить `task_type`, `task_complexity` |

**Зависимости:** Нет

**Реализация:**
```python
# Добавить в DevTeamState:
task_type: NotRequired[str]           # "new_project", "bugfix", "feature", "refactor"
task_complexity: NotRequired[int]     # 1-10 (от router)
```

**Тестирование:**
- Unit: `create_initial_state` — проверить что новые поля опциональны
- Существующие тесты — убедиться что не ломаются

**Критерии приёмки:**
- [ ] Новые поля NotRequired
- [ ] Обратная совместимость
- [ ] Тесты проходят

**Сложность: 1/10 | 0.5 дня**

---

## 3. Волна 2: Помодульная разбивка {#3-волна-2}

> Модули Волны 2 описаны менее детально — конкретизация при приближении к реализации.

---

### 3.1 Модуль: Git-based Workflow

**Цель:** Работа с кодом через GitHub ветки вместо `code_files` в state.

**Файлы:**
- Создать: `graphs/dev_team/tools/git_workspace.py`
- Изменить: `graphs/dev_team/state.py` — `working_branch`, `working_repo`, `file_manifest`
- Изменить: все агенты — адаптация к git-based
- Изменить: `graphs/dev_team/graph.py` — обновить git_commit_node

**Ключевые tools:**
```python
@tool
def create_working_branch(repo: str, base_branch: str = "main") -> str:
    """Create a new working branch for the task."""

@tool
def read_file_from_branch(repo: str, branch: str, path: str) -> str:
    """Read a file from a specific branch."""

@tool
def write_file_to_branch(repo: str, branch: str, path: str, content: str, message: str) -> str:
    """Write/update a file on a branch (commit)."""

@tool
def list_files_on_branch(repo: str, branch: str, path: str = "") -> list[str]:
    """List files in a directory on a branch."""

@tool
def create_pull_request(repo: str, branch: str, title: str, body: str) -> str:
    """Create a PR from the working branch."""
```

**Логика:**
- Задача с repo → PM создаёт working_branch → все работают через git tools
- Задача без repo → code_files в state (как сейчас)

**Зависимости:** Нет (может реализовываться параллельно)

**Тестирование:**
- Unit: все tools с mock PyGithub
- Integration: реальный GitHub (test repo)

**Сложность: 5/10 | 3-5 дней**

---

### 3.2 Модуль: Switch-Agent (Router)

**Цель:** Автоматическая маршрутизация задач по графам через LLM.

**Файлы:**
- Изменить: `gateway/router.py` — `classify_task()` (сейчас заготовка → реализация)
- Изменить: `gateway/endpoints/run.py` — использовать router
- Изменить: `frontend/src/components/TaskForm.tsx` — выбор графа / авто

**Ключевая логика:**
```python
async def classify_task(task: str, available_graphs: list[dict]) -> TaskClassification:
    llm = get_llm_with_fallback(role="router", temperature=0.1)
    structured_llm = llm.with_structured_output(TaskClassification)
    # ... prompt с описаниями графов ...
    return await structured_llm.ainvoke(prompt)
```

**Зависимости:** Модуль 2.6 (Gateway), Модуль 2.5 (manifest.yaml), второй граф (для тестирования)

**Тестирование:**
- Unit: classify_task с mock LLM
- Integration: реальный LLM → проверить что выбирает правильный граф

**Сложность: 4/10 | 2-3 дня**

---

### 3.3 Модуль: Code Execution Sandbox

**Цель:** Безопасное выполнение сгенерированного кода (тесты, lint).

**Файлы:**
- Создать: `sandbox/server.py` — FastAPI сервер
- Создать: `sandbox/Dockerfile` — Docker-in-Docker
- Создать: `graphs/dev_team/tools/sandbox.py` — клиент
- Изменить: `graphs/dev_team/graph.py` — `sandbox_check` node
- Изменить: `docker-compose.yml` — сервис sandbox

**API Sandbox:**
```
POST /execute
  Body: { language, code_files, commands, timeout, memory_limit }
  Response: { stdout, stderr, exit_code, duration }
```

**Зависимости:** Нет (самостоятельный модуль)

**Тестирование:**
- Unit: sandbox client с mock
- Integration: реальный Docker — запуск Python-скрипта

**Сложность: 6/10 | 3-5 дней**

---

### 3.4 Модуль: Security Agent

**Цель:** Статический анализ безопасности + runtime-проверки.

**Файлы:**
- Создать: `graphs/dev_team/agents/security.py`
- Создать: `graphs/dev_team/prompts/security.yaml`
- Изменить: `graphs/dev_team/graph.py` — node + conditional edge

**Два режима:**
- `security_static_review` — после Developer: SAST, secrets, deps
- `security_runtime_check` — после Deploy: HTTPS, headers, image scan

**Зависимости:** Модуль 3.3 (Sandbox — для запуска SAST-инструментов)

**Тестирование:**
- Unit: security agent с mock LLM
- Integration: реальный код с известными уязвимостями

**Сложность: 4/10 | 2-3 дня**

---

### 3.5 Модуль: DevOps Agent

**Цель:** Генерация инфраструктурных файлов, CI/CD, деплой.

**Файлы:**
- Создать: `graphs/dev_team/agents/devops.py`
- Создать: `graphs/dev_team/prompts/devops.yaml`
- Создать: `graphs/dev_team/tools/github_actions.py`
- Создать: `config/linters/` — конфигурации линтеров по стекам
- Изменить: `graphs/dev_team/graph.py` — devops_agent node
- Изменить: `graphs/dev_team/state.py` — `deploy_url`, `infra_files`

**Что генерирует:**
1. Dockerfile
2. docker-compose.yml (для деплоя)
3. `.github/workflows/deploy.yml`
4. Traefik labels для nip.io
5. `.pre-commit-config.yaml`
6. Branch protection rules (через GitHub API)

**Secrets workflow:**
- AUTO (APP_NAME, DOMAIN) → прописывает в конфиг деплоя
- Серверные секреты (VPS_SSH_KEY, DATABASE_URL) → предполагаются уже настроенными на VPS (.env)
- По умолчанию **без DevOps HITL** — секреты готовы на VPS деплоя
- Если чего-то не хватает — уведомление пользователю (не блокировка)

**Prefect integration (опционально):**
- Регистрирует deployment flow в Prefect Server на VPS деплоя
- Через Prefect API (REST)

**Зависимости:** Модуль 3.1 (Git-based), Модуль 3.3 (Sandbox — для проверки Dockerfile)

**Тестирование:**
- Unit: генерация Dockerfile для разных стеков
- Unit: генерация CI/CD pipeline
- Integration: реальный GitHub repo + Actions

**Сложность: 7/10 | 5-10 дней**

---

### 3.6 Модуль: CLI Agents

**Цель:** Интеграция мощных CLI-агентов (Claude Code, Codex) как узлов графа.

**Файлы:**
- Создать: `graphs/dev_team/agents/cli_agent.py` — node function
- Создать: `graphs/dev_team/tools/cli_runner.py` — клиент к CLI Runner API
- Создать: `cli_runner/` (для VPS) — server.py, Dockerfile
- Изменить: `graphs/dev_team/graph.py` — node + conditional edge (route_to_executor)

**CLI Runner Server (на отдельной VPS):**
- API: см. ARCHITECTURE_V2 §5
- Claude Code: `claude -p "<instructions>" --output-format stream-json`
- Codex: `codex --approval-mode full-auto "<instructions>"`
- Workspace: `/workspace/{job_id}/` — изолированные директории
- Конкурентность: max 2 задачи

**Роутинг: internal vs CLI:**
```python
def route_to_executor(state: DevTeamState) -> str:
    mode = state.get("execution_mode", "auto")
    if mode == "cli":     return "cli_agent"
    if mode == "internal": return "developer"
    # Auto: CLI для сложных задач с существующим репо
    complexity = state.get("task_complexity", 5)
    has_repo = bool(state.get("working_repo"))
    if complexity >= 7 and has_repo:
        return "cli_agent"
    return "developer"
```

**Зависимости:** Модуль 3.1 (Git-based), отдельная VPS с установленными CLI tools

**Тестирование:**
- Unit: cli_runner.py client с mock
- Unit: route_to_executor — разные state
- Integration: реальный CLI Runner (на VPS) с тестовым repo

**Сложность: 6/10 | 3-7 дней**

---

### 3.7 Модуль: Sandbox инфраструктура (PostgreSQL, Redis, инструменты)

**Цель:** Расширить sandbox-среду постоянными сервисами и инструментами анализа.

> Приоритет: P0 (минимальные инфра-изменения) + P2 (расширение).
> Архитектура: [ARCHITECTURE_V2.md — Приложение D, §D.2](ARCHITECTURE_V2.md#appendix-d-qa-evolution)

**Файлы:**

| Действие | Файл | Что делать |
|----------|------|-----------|
| Изменить | `sandbox/Dockerfile.browser` | Добавить pip-audit |
| Создать | `sandbox/Dockerfile.browser-node` | Образ с Node.js 20 + lighthouse + axe-core |
| Изменить | `docker-compose.yml` | sandbox-postgres, sandbox-redis сервисы |
| Изменить | `sandbox/executor.py` | Подключение к PG/Redis сети, выбор образа |

**Подэтапы:**

| # | Этап | Приоритет | Сложность |
|---|------|-----------|-----------|
| 1 | PostgreSQL контейнер для sandbox (видимость из sandbox) | P0 | Средняя |
| 2 | pip-audit в sandbox-образе | P0 | Низкая |
| 3 | Lighthouse + axe-core в browser-node образе | P0 | Низкая |
| 4 | Redis контейнер для sandbox | P2 | Средняя |
| 5 | Nexus proxy (кэш pip/npm) | P2 | Средняя |
| 6 | Visual regression (pixelmatch) | P2 | Средняя |

**Зависимости:** Модуль 3.3 (Sandbox — базовая реализация)

**Тестирование:**
- Integration: sandbox видит PostgreSQL, может создать таблицу
- Integration: sandbox видит Redis, может set/get
- Unit: новые образы билдятся корректно

**Критерии приёмки:**
- [ ] PostgreSQL-контейнер запускается и доступен из sandbox
- [ ] pip-audit предустановлен в browser-python образе
- [ ] lighthouse + axe-core предустановлены в browser-node образе
- [ ] Redis-контейнер (P2) запускается и доступен из sandbox
- [ ] Nexus proxy (P2) кэширует pip/npm пакеты

**Сложность: 4/10 | 2-4 дня**

---

### 3.8 Модуль: CI/CD интеграция (CI-луп в графе)

**Цель:** Добавить CI/CD-луп: после git commit → GitHub Actions → FAIL → Developer, PASS → QA.

> Приоритет: P1.
> Архитектура: [ARCHITECTURE_V2.md — Приложение D, §D.3](ARCHITECTURE_V2.md#appendix-d-qa-evolution)

**Файлы:**

| Действие | Файл | Что делать |
|----------|------|-----------|
| Создать | `graphs/dev_team/tools/github_actions.py` | Клиент GitHub Actions API (trigger, wait, logs) |
| Изменить | `graphs/dev_team/graph.py` | CI-луп роутинг: post-commit → CI check → route |
| Изменить | `graphs/dev_team/state.py` | `ci_status: NotRequired[dict]`, `ci_log: NotRequired[str]` |
| Изменить | `graphs/dev_team/prompts/developer.yaml` | Генерация CI-конфига в промпте |

**Ключевые tools:**
```python
# tools/github_actions.py
@tool
def trigger_ci(repo: str, branch: str) -> str:
    """Trigger CI workflow and return run ID."""

@tool
def wait_for_ci(repo: str, run_id: str, timeout: int = 300) -> dict:
    """Wait for CI completion, return status + logs."""

@tool
def get_ci_logs(repo: str, run_id: str) -> str:
    """Get CI run logs for analysis."""
```

**Роутинг CI-лупа:**
```python
# graph.py — CI-луп
def route_after_ci(state: DevTeamState) -> str:
    ci_status = state.get("ci_status", {}).get("conclusion")
    if ci_status == "success":
        return "qa_agent"
    return "developer"  # CI fail → developer fixes
```

**Принцип:** к моменту, когда код попадает к QA, все стандартные проверки (lint, typecheck, tests, build, security) уже пройдены через CI. QA фокусируется на уникальной ценности: visual exploration, security pen-testing, performance/a11y.

**Зависимости:** Модуль 3.1 (Git-based), Модуль 3.5 (DevOps — генерация CI-конфига)

**Тестирование:**
- Unit: github_actions tools с mock
- Unit: route_after_ci routing logic
- Integration: реальный GitHub Actions workflow

**Критерии приёмки:**
- [ ] `trigger_ci` запускает GitHub Actions workflow
- [ ] `wait_for_ci` ждёт завершения и возвращает статус + логи
- [ ] CI FAIL → Developer получает CI-логи и фиксит
- [ ] CI PASS → QA (стандартные проверки пройдены)
- [ ] State содержит `ci_status` и `ci_log`

**Сложность: 5/10 | 3-5 дней**

---

### 3.9 Модуль: QA промпт-инжиниринг

**Цель:** Улучшить промпты агентов для повышения качества тестирования без изменений кода.

> Приоритет: G0 (0 кода, только промпты).
> Архитектура: [ARCHITECTURE_V2.md — Приложение D, §D.7-D.8](ARCHITECTURE_V2.md#appendix-d-qa-evolution)

**Файлы:**

| Действие | Файл | Что делать |
|----------|------|-----------|
| Изменить | `graphs/dev_team/prompts/developer.yaml` | Генерация тестов + CI-конфиг + Dockerfile |
| Изменить | `graphs/dev_team/prompts/reviewer.yaml` | Проверка покрытия тестов, поиск подгонки |
| Изменить | `graphs/dev_team/prompts/qa.yaml` | Security pen-testing, code-aware exploration |
| Изменить | `graphs/dev_team/prompts/architect.yaml` | (опционально) тесты-контракты для TDD |

**Изменения по агентам:**

| Агент | Изменение промпта | Приоритет |
|-------|-------------------|-----------|
| Developer | Генерировать тесты + CI-конфиг + Dockerfile | G0 (#10) |
| Reviewer | Проверять покрытие тестов, искать подгонку | G0 (#13) |
| QA | Security pen-testing: SQL injection, XSS, auth bypass | G0 (#11) |
| QA | Code-aware exploration: план на основе реального кода | G0 (#12) |

> **Примечание о вариативности:** промпты привязаны к конкретному графу. Разные графы могут использовать разные варианты промптов для одного и того же типа агента. Например, developer в `dev_team` пишет тесты (подход A), а developer в будущем TDD-графе получает тесты от architect'а (подход B). См. [ARCHITECTURE_V2 §7.4](ARCHITECTURE_V2.md#7-4-agent-variability).

**Зависимости:** Нет (только изменение YAML-файлов)

**Тестирование:**
- Smoke: запуск графа с обновлёнными промптами, проверка что Developer генерирует тесты
- Manual: ревью качества сгенерированных тестов
- Manual: проверка что QA exploration учитывает код

**Критерии приёмки:**
- [ ] Developer генерирует unit-тесты к своему коду
- [ ] Developer генерирует CI-конфиг (`.github/workflows/ci.yml`)
- [ ] Reviewer проверяет покрытие тестов и ищет подгонку (пустые assert'ы, тесты без утверждений)
- [ ] QA промпт включает security pen-testing сценарии
- [ ] QA exploration plan учитывает код (декораторы, роуты, модели)

**Сложность: 2/10 | 1-3 дня**

---

### 3.10 Модуль: Пайплайн-изменения графов (TDD, Multi-pass, QA-CLI)

**Цель:** Структурные изменения графов: TDD-подход, multi-pass testing, QA-CLI-агент.

> Приоритет: G1 (пайплайн-изменения).
> Архитектура: [ARCHITECTURE_V2.md — Приложение D, §D.4, D.6](ARCHITECTURE_V2.md#appendix-d-qa-evolution)

**Подмодули:**

#### 3.10a: Architect пишет тесты (TDD, подход B)

```
Architect → тесты-контракты → Developer пишет код → CI проверяет
```

| Действие | Файл | Что делать |
|----------|------|-----------|
| Изменить | `graphs/dev_team/prompts/architect.yaml` | Генерация тестов-контрактов |
| Изменить | `graphs/dev_team/graph.py` | Architect output включает тесты |
| Изменить | `graphs/dev_team/state.py` | `architect_tests: NotRequired[list[CodeFile]]` |

> **Примечание:** Это пример вариативности агентов (см. [ARCHITECTURE_V2 §7.4](ARCHITECTURE_V2.md#7-4-agent-variability)). TDD-подход может быть реализован как отдельный граф с вариантом `developer_tdd`, где Developer получает тесты от Architect'а и не имеет права их изменять.

#### 3.10b: Multi-pass testing

```
QA разведка → QA таргет → QA edge cases (3 прохода)
```

| Действие | Файл | Что делать |
|----------|------|-----------|
| Изменить | `graphs/dev_team/agents/qa.py` | Multi-pass logic (3 прохода) |
| Изменить | `graphs/dev_team/prompts/qa.yaml` | Промпты для каждого прохода |

#### 3.10c: QA-CLI-агент (граф)

| Действие | Файл | Что делать |
|----------|------|-----------|
| Создать | Новый граф или узел | QA-CLI-агент для сложных проектов |
| Зависимость | Модуль 3.6 (CLI Runner) | CLI Runner API должен быть готов |

**Зависимости:** Модуль 3.6 (CLI Agents), Модуль 3.9 (обновлённые промпты)

**Тестирование:**
- Unit: TDD-пайплайн (architect → developer с тестами)
- Unit: multi-pass QA logic
- Integration: QA-CLI-агент с реальным CLI Runner

**Критерии приёмки:**
- [ ] Architect генерирует тесты-контракты (3.10a)
- [ ] Developer реализует код, проходящий тесты Architect'а
- [ ] Multi-pass QA: 3 прохода с разным фокусом (3.10b)
- [ ] QA-CLI-агент работает через CLI Runner (3.10c)

**Сложность: 5/10 | 5-10 дней (все подмодули)**

---

## 4. Стратегия тестирования {#4-тестирование}

### 4.1 Уровни тестирования

```
┌─────────────────────────────────────────────┐
│  E2E Tests (manual + будущие Playwright)     │
│  Весь путь: Frontend → Gateway → Aegra →    │
│  Agents → Git → результат                    │
│  Количество: 3-5 сценариев                   │
├─────────────────────────────────────────────┤
│  Integration Tests                           │
│  Gateway + Aegra, Gateway + DB,              │
│  Agents + real LLM (smoke tests)             │
│  Количество: 10-15 тестов                    │
├─────────────────────────────────────────────┤
│  Unit Tests                                  │
│  Routing logic, auth, proxy, models,         │
│  agent helpers, tools                        │
│  Количество: 30-50 тестов                    │
└─────────────────────────────────────────────┘
```

### 4.2 Что тестируем по модулям

| Модуль | Unit | Integration | E2E |
|--------|------|-------------|-----|
| structlog | configure_logging() | — | Проверка формата логов |
| agents.yaml | load_agent_config, get_model_for_role | — | — |
| Retry + Fallback | invoke_with_retry, get_llm_with_fallback | LLM smoke test | — |
| Langfuse fix | _get_callbacks, _invoke_chain | Langfuse traces visible | — |
| Gateway auth | register, login, refresh, JWT validation | DB operations | Login → task flow |
| Gateway proxy | proxy_to_aegra (mock) | Gateway → Aegra | — |
| Graph endpoints | /graph/list, /topology (mock) | Real manifest parsing | — |
| Frontend auth | — | — | Register → Login → Task |
| Graph viz | — | — | Visual check |
| Streaming | — | Gateway SSE proxy | Stream run → UI updates |
| Web tools | web_search, fetch_url (mock) | Real DuckDuckGo | — |
| Telegram | handlers (mock) | Bot → Gateway | Real Telegram test |
| Git-based | git tools (mock PyGithub) | Real GitHub API | — |
| Sandbox | — | Real Docker execution | — |
| CLI agents | cli_runner client (mock) | Real CLI Runner | — |

### 4.3 Моки и фикстуры

**Что мокаем (всегда):**
- LLM API вызовы (в unit-тестах)
- GitHub API (в unit-тестах)
- External HTTP (DuckDuckGo, etc.)

**Что НЕ мокаем (в integration):**
- PostgreSQL (используем test DB)
- Gateway → Aegra (поднимаем оба)
- Langfuse (опционально, если нужны traces)

**Новые фикстуры для Gateway:**

```python
# tests/test_gateway/conftest.py
import pytest
from httpx import AsyncClient, ASGITransport
from gateway.main import app
from gateway.database import init_db, close_db

@pytest.fixture
async def gateway_client():
    """Async test client for Gateway."""
    await init_db()  # Test DB
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await close_db()

@pytest.fixture
async def auth_headers(gateway_client):
    """Create test user and return auth headers."""
    await gateway_client.post("/auth/register", json={
        "email": "test@test.com",
        "password": "testpassword123",
        "display_name": "Test User",
    })
    resp = await gateway_client.post("/auth/login", json={
        "email": "test@test.com",
        "password": "testpassword123",
    })
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
```

### 4.4 Тестовая конфигурация

```python
# pytest.ini (обновлённый)
[pytest]
testpaths = tests
asyncio_mode = auto
markers =
    slow: marks tests as slow
    integration: marks integration tests
    e2e: marks end-to-end tests
```

```bash
# Команды
pytest tests/ -v                              # Все тесты
pytest tests/ -v -m "not slow"                # Быстрые
pytest tests/ -v -m "not integration"         # Только unit
pytest tests/test_gateway/ -v                 # Только Gateway
pytest tests/ -v --cov=graphs --cov=gateway   # С coverage
```

---

## 5. CI/CD для AI-crew {#5-cicd}

### 5.1 GitHub Actions Workflow

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install ruff mypy
      - run: ruff check graphs/ gateway/
      - run: mypy graphs/ gateway/ --ignore-missing-imports

  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: test_aicrew
        ports: ["5433:5433"]
        options: >-
          --health-cmd "pg_isready -U test"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r requirements.txt
      - run: pip install -r gateway/requirements.txt
      - run: pytest tests/ -v -m "not slow and not e2e"
        env:
          DATABASE_URL: postgresql://test:test@localhost:5433/test_aicrew
          LLM_API_URL: http://mock
          LLM_API_KEY: test

  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20" }
      - run: npm ci
        working-directory: frontend
      - run: npm run lint
        working-directory: frontend
      - run: npm run build
        working-directory: frontend
```

---

## 6. Чеклист готовности {#6-чеклист}

### Волна 1 — Definition of Done

> Дата верификации: 13 февраля 2026 — 142 теста Волны 1 + 72 Волны 2 + 49 новые графы + 80 Sandbox/Security = **343 total** (tests/)

#### Фундамент
- [x] structlog: все модули переведены, LOCAL/PRODUCTION форматы (включая github.py)
- [x] agents.yaml: создан, загружается, env overrides работают
- [x] Retry: exponential backoff, 3 попытки, логирование (invoke_with_retry)
- [x] Fallback: get_llm_with_fallback() реализован (agents пока используют get_llm напрямую — fallback подключить при необходимости)
- [x] Langfuse: callbacks пробрасываются через _invoke_chain, config parameter во всех node functions
- [x] manifest.yaml: создан для dev_team (5 агентов, 4 task_types, features)
- [x] State: task_type, task_complexity добавлены как NotRequired

#### Gateway
- [x] Auth: register, login, refresh, JWT validation (bcrypt + HS256)
- [x] Proxy: REST + SSE streaming к Aegra (proxy.py)
- [x] Graph endpoints: /graph/list, /graph/topology, /graph/config
- [x] Health: /health без auth (с проверкой Aegra)
- [x] Switch-Agent: заготовка classify_task() (всегда dev_team)
- [x] /api/run: создание задач с auto-routing
- [x] Docker: отдельный Dockerfile + Dockerfile.aegra, Aegra закрыт (expose only)
- [x] Тесты: JWT, пароли, модели, конфиг, роутер (tests/test_wave1_verification.py)

#### Frontend
- [x] Login/Register страницы (dark theme, cyan accents)
- [x] JWT в API-клиенте (Zustand store + persist), protected routes
- [x] Graph Visualization (React Flow): узлы, связи, модели, промпты (dagre layout) — интегрирована в TaskDetail (раскрыта по умолчанию)
- [x] Graph Visualization: исправлен импорт графа (graphs/ → sys.path в gateway), fallback на manifest-based topology, warning-level логирование ошибок
- [x] SSE Streaming: real-time обновления (hooks/useStreamingTask.ts)
- [x] Выбор графа в TaskForm (dropdown + "Выбор ЛЛМ" по умолчанию + детали графа)
- [x] Страница «Задачи» (/tasks): список тредов с поиском, фильтрацией по статусу, бейджами графов
- [x] Страница «Настройки» (/settings): профиль, статус системы, графы/модели (read-only), информация о системе

#### Tools & Interfaces
- [x] Web tools: web_search, fetch_url, download_file (как LangChain @tool)
- [ ] Web tools: привязать к агентам (bind_tools) — по необходимости
- [x] Telegram: /task, /status, /start, /help, HITL (aiogram + gateway_client) — исправлен Dockerfile (COPY . ./telegram/)
- [x] Telegram: авто-регистрация бот-аккаунта при старте (ensure_authenticated), авто-реlogin при истечении JWT

#### Рефакторинг (15 февраля 2026)
- [x] **Критические баги**: architect `qa_iteration_count` → `review_iteration_count`, clarification routing, architect config+retry+callbacks
- [x] **Общий модуль `graphs/common/`**: types, utils, git (make_git_commit_node), logging (idempotent)
- [x] **Gateway `graph_loader.py`**: единая загрузка манифестов/конфигов
- [x] **Консистентность агентов**: единые сигнатуры `(state, config=None)`, все роли в DEFAULT_MODELS
- [x] **Frontend API**: login/register/getGraphConfig/getGraphTopology в aegraClient
- [x] **Экспорт**: SecurityAgent в agents/__init__, web_tools в tools/__init__
- [ ] QA-агент: разбиение на подмодули — см. [REFACTORING_PLAN.md](REFACTORING_PLAN.md)
- [ ] Frontend: token refresh, типы, общие компоненты — см. [REFACTORING_PLAN.md](REFACTORING_PLAN.md)
- [ ] Тесты: обновить под рефакторинг — см. [REFACTORING_PLAN.md](REFACTORING_PLAN.md)

#### Инфраструктура
- [x] docker-compose.yml обновлён (postgres, aegra, gateway, langfuse, frontend, telegram)
- [x] Aegra healthcheck: interval 1200s (20 мин) — снижение шума в логах
- [x] Structured logging: тайминг в proxy, agent _invoke_chain, graph nodes (enter/exit/elapsed_ms)
- [x] HTTP request middleware logging в gateway (метод, путь, статус, время)
- [x] Dockerfile.aegra — отдельный образ для Aegra (LangGraph Runtime)
- [x] frontend/Dockerfile — production build (nginx + static)
- [x] docker-compose.prod.yml — production override
- [x] env.example обновлён (CORS_ORIGINS, LANGFUSE_NEXTAUTH_URL, FRONTEND_DOCKERFILE)
- [x] CORS настроен через gateway (CORS_ORIGINS env — JSON array или comma-separated)
- [x] Все 449 тестов проходят (0 failures)

### Волна 2 — Definition of Done

> Дата обновления: 14 февраля 2026 — 449 тестов passed (tests/)

#### Git-based Workflow (Module 3.1)
- [x] State расширен: working_branch, working_repo, file_manifest + все поля Wave 2
- [x] tools/git_workspace.py: 8 LangChain tools (create_working_branch, read/write file, batch write, list files, diff, create PR, delete branch)
- [x] Safety: delete_working_branch отказывает удалять не-ai/ ветки
- [x] Batch commit через Git tree API (атомарные операции)
- [x] 40 unit-тестов (tests/test_git_workspace.py)
- [x] commit_and_create_pr: высокоуровневая функция для атомарного коммита + PR
- [x] git_commit_node обновлён: использует commit_and_create_pr (атомарный коммит, working_branch в state)
- [ ] Git tools привязаны к агентам (bind_tools) — при интеграции с tool-calling агентами

#### Switch-Agent Router (Module 3.2)
- [x] classify_task: полная LLM-based реализация (OpenAI-compatible API через httpx)
- [x] Fast path: 1 граф → без LLM-вызова
- [x] Fallback: LLM недоступен → первый граф по умолчанию
- [x] JSON parsing: plain, markdown-wrapped, surrounded by text
- [x] Validation: invalid graph_id → fallback, complexity 1-10 нормализация
- [x] Manifest loading + prompt generation для LLM
- [x] run.py обновлён: передаёт available_graphs в classify_task
- [x] 32 unit-теста (tests/test_router.py)
- [x] Роутер обнаруживает все 4 графа из manifest.yaml

#### Новые графы (Module 3.3 — New Graphs)
- [x] simple_dev: Developer → git_commit → END (без HITL, 1 агент)
- [x] standard_dev: PM → Developer → QA → git_commit → END (без HITL, QA loop max 2)
- [x] research: Researcher (web search + synthesis) → END (без HITL, web tools)
- [x] Все графы зарегистрированы в aegra.json (4 графа)
- [x] Все manifest.yaml созданы и обнаруживаются роутером
- [x] Researcher agent: web_search + fetch_url + LLM synthesis
- [x] 49 unit-тестов для новых графов (tests/test_new_graphs.py)

#### Выбор графа в интерфейсах (Module 3.4 — Graph Selection UI)
- [x] Frontend: TaskForm с выпадающим списком графов (/graph/list)
- [x] Frontend: "Предоставить выбор ЛЛМ" по умолчанию (graph_id=null)
- [x] Frontend: Детали выбранного графа (агенты, описание)
- [x] Frontend: useTask hook обновлён — использует /api/run с graph_id
- [x] Frontend: API клиент — getGraphList() + createTaskRun()
- [x] Frontend: типы — GraphListItem, graph_id в CreateTaskInput
- [x] Telegram: двухшаговый диалог (FSM — task → graph selection)
- [x] Telegram: /task <text> — пропуск шага 1, сразу выбор графа
- [x] Telegram: нумерованный список + "Выбор сделает ЛЛМ"
- [x] Telegram: gateway_client.get_graph_list()
- [x] 11 unit-тестов для Telegram (tests/test_telegram_graph_selection.py)

#### Code Execution Sandbox (Module 3.3)
- [x] sandbox/server.py: FastAPI сервер (POST /execute, GET /health)
- [x] sandbox/executor.py: Docker-based execution engine (language images, tar archive, timeout, memory limits)
- [x] sandbox/models.py: Pydantic models (SandboxExecuteRequest/Response, HealthResponse)
- [x] sandbox/Dockerfile: Docker CLI + Python dependencies
- [x] sandbox/requirements.txt: fastapi, docker, structlog
- [x] tools/sandbox.py: LangChain @tool wrappers (run_code, run_tests, run_lint)
- [x] tools/sandbox.py: SandboxClient HTTP клиент + auto-detection (команды, тест-раннеры, линтеры)
- [x] docker-compose.yml: sandbox сервис (Docker socket mount, expose 8002)
- [x] SANDBOX_URL env var в Aegra container
- [x] 51 unit-тест (tests/test_sandbox.py): models, executor, server, client, auto-detection, formatting
- [x] tools/__init__.py: sandbox tools экспортированы (run_code, run_tests, run_lint, SandboxClient)

#### QA → Reviewer + QA (Sandbox) Refactoring
- [x] Переименование: QA agent → Reviewer agent (код-ревью, не тестирование)
- [x] agents/reviewer.py: ReviewerAgent (review_code, verify_fixes, final_approval)
- [x] prompts/reviewer.yaml: system + code_review + verify_fixes + final_approval
- [x] agents/qa.py: Новый QAAgent (sandbox-based testing)
- [x] prompts/qa.yaml: system + analyse_sandbox
- [x] QAAgent: _detect_language, _build_commands, _parse_approved, _parse_issues
- [x] QAAgent: SandboxClient интеграция + LLM-анализ sandbox output
- [x] graph.py: Developer → Security → Reviewer → QA (sandbox) → git_commit
- [x] route_after_reviewer: escalation ladder (Developer → Architect → Human)
- [x] route_after_qa: pass → git_commit, fail → Developer
- [x] USE_QA_SANDBOX env var (default: true) — включение/выключение
- [x] state.py: qa_iteration_count → review_iteration_count
- [x] manifest.yaml: 7 агентов (PM, Analyst, Architect, Developer, Security, Reviewer, QA)
- [x] manifest.yaml: features: review_loop + sandbox_testing
- [x] standard_dev: QA → Reviewer (переименование, без sandbox)
- [x] prompts/developer.yaml + architect.yaml: "QA" → "Reviewer" в текстах
- [x] agents/__init__.py: экспорт ReviewerAgent + QAAgent
- [x] ARCHITECTURE_V2.md: обновлена (Reviewer + QA роли, DevTeamState fields)
- [x] 51 unit-тест (tests/test_reviewer_and_qa.py): оба агента, routing, prompts, graph
- [x] 4 интеграционных теста (tests/test_reviewer_qa_integration.py): happy path, QA fail, reviewer reject, skip
- [x] Все существующие тесты обновлены (398 passed, 0 failures)

#### Security Agent (Module 3.4)
- [x] agents/security.py: SecurityAgent (static_review, runtime_check, parse, extract_deps)
- [x] prompts/security.yaml: system prompt + security_static_review + security_runtime_check + dependency_check
- [x] graph.py: security_review node + route_after_developer (conditional edge)
- [x] Security review: первый проход (review_iteration_count=0) → security_review → Reviewer
- [x] Security review: fix loops (review_iteration_count>0) → прямо в Reviewer (без повторного скана)
- [x] USE_SECURITY_AGENT env var (default: true) — включение/выключение
- [x] manifest.yaml: security агент + security_check feature
- [x] _parse_security_review: парсинг risk_level, critical/warnings/info из LLM-ответа
- [x] _extract_dependencies: автоопределение requirements.txt, package.json, go.mod, etc.
- [x] 29 unit-тестов (tests/test_security_agent.py): agent, parsing, routing, graph integration
- [x] Integration tests обновлены (security_agent мок добавлен)

#### Visual QA Testing (Browser)
> Подробный план: [VISUAL_QA_PLAN.md](VISUAL_QA_PLAN.md)
> Архитектура: [ARCHITECTURE_V2.md — Приложение C](ARCHITECTURE_V2.md#appendix-c-visual-qa)

**Фаза 1: Scripted E2E (Playwright в Sandbox) — MVP** `[DONE]`
- [x] `sandbox/Dockerfile.browser`: образ с Playwright + Chromium + Node.js
- [x] `sandbox/models.py`, `executor.py`, `server.py`: browser mode (выбор образа, скриншоты)
- [x] `graphs/dev_team/tools/browser_runner.py`: runner-скрипт для sandbox-контейнера
- [x] `graphs/dev_team/agents/qa.py`: `has_ui()`, `test_ui()`, `merge_results()`
- [x] `graphs/dev_team/prompts/qa.yaml`: `generate_browser_test`, `analyse_browser_results`
- [x] `graphs/dev_team/state.py`: `browser_test_results: NotRequired[dict]`
- [x] `USE_BROWSER_TESTING` env var (default: true)
- [x] 51 unit-тест (tests/test_visual_qa.py): модели, executor, runner, QA agent, node, state
- [x] Все 449 тестов проходят (0 failures)

**Фаза 2: Guided Exploration (Batch)** `[DONE]`
- [x] `tools/exploration_runner.py`: batch exploration runner (template + validation + report extraction)
- [x] `agents/qa.py`: `test_explore()`, `_generate_exploration_plan()`, `_analyse_exploration()`, `_extract_json()`
- [x] `prompts/qa.yaml`: `generate_exploration_plan`, `analyse_exploration`
- [x] `USE_BROWSER_EXPLORATION` env var (default: false)
- [x] `BROWSER_EXPLORATION_MAX_STEPS` env var (default: 30)
- [x] Exploration plan JSON validation (`validate_exploration_plan()`)
- [x] Report extraction from sandbox stdout (`extract_exploration_report()`)
- [x] `qa_agent()` node: Phase 0 → Phase 1 → Phase 2 pipeline
- [x] 53 unit-тестов (tests/test_qa_exploration.py)
- [x] Все 104 Visual QA теста проходят (51 Phase 1 + 53 Phase 2)
- [ ] Integration тесты с реальным sandbox

**Фаза 3: Autonomous Loop (Experimental)** `[DEFERRED — отложено на неопределённый срок]`
> Решение: Фаза 3 отложена в долгосрочный бэклог. Scripted E2E (Фаза 1) + Guided Exploration (Фаза 2)
> покрывают 95% потребностей визуального QA. Autonomous Loop целесообразен только если Фазы 1-2
> окажутся недостаточными. См. анализ в [VISUAL_QA_PLAN.md §7](VISUAL_QA_PLAN.md#7-целесообразность).
- [ ] `sandbox/session_manager.py`: stateful browser sessions
- [ ] Session API: POST /sessions, POST /action, GET /state, DELETE
- [ ] `agents/qa.py`: `autonomous_test()`, guardrails, explainability
- [ ] `USE_AUTONOMOUS_TESTING` env var (default: false)
- [ ] Unit + Integration тесты

#### Sandbox инфраструктура (Module 3.7) `[NOT STARTED]`
- [ ] PostgreSQL контейнер для sandbox-проектов (P0)
- [ ] pip-audit в sandbox browser-python образе (P0)
- [ ] Lighthouse + axe-core в browser-node образе (P0)
- [ ] Redis контейнер для sandbox-проектов (P2)
- [ ] Nexus proxy — кэш pip/npm пакетов (P2)
- [ ] Visual regression — pixelmatch (P2)

#### CI/CD интеграция (Module 3.8) `[NOT STARTED]`
- [ ] tools/github_actions.py: trigger_ci, wait_for_ci, get_ci_logs
- [ ] graph.py: CI-луп роутинг (CI FAIL → Developer, CI PASS → QA)
- [ ] state.py: ci_status, ci_log
- [ ] developer.yaml: генерация CI-конфига в промпте

#### QA промпт-инжиниринг (Module 3.9) `[NOT STARTED]`
- [ ] developer.yaml: генерация тестов + CI-конфиг + Dockerfile (G0 #10)
- [ ] reviewer.yaml: проверка покрытия тестов, поиск подгонки (G0 #13)
- [ ] qa.yaml: security pen-testing (SQL injection, XSS, auth bypass) (G0 #11)
- [ ] qa.yaml: code-aware exploration (G0 #12)

#### Пайплайн-изменения графов (Module 3.10) `[NOT STARTED]`
- [ ] Architect пишет тесты-контракты — TDD подход B (G1 #14)
- [ ] Multi-pass testing — 3 прохода QA (G1 #15)
- [ ] QA-CLI-агент граф для сложных проектов (G1 #16)

#### Остальные модули (не начаты)
- [ ] DevOps Agent: Dockerfile, CI/CD, secrets, branch protection
- [ ] CLI Agents: CLI Runner API, node в графе, route_to_executor
- [ ] Prefect: deployment на VPS деплоя (рядом)
- [ ] E2E: полный цикл от задачи до PR (и деплоя)

---

## 7. Риски и митигации {#7-риски}

| # | Риск | Вероятность | Влияние | Митигация |
|---|------|-------------|---------|-----------|
| 1 | **Aegra несовместимость** при SSE proxy | Средняя | Высокое | Тестировать proxy рано. При проблемах — модифицировать Aegra (мораторий снят) |
| 2 | **LLM rate limits** при retry | Высокая | Среднее | Exponential backoff + fallback chain. Мониторинг через Langfuse |
| 3 | **Сложность Gateway proxy** для всех Aegra API | Средняя | Среднее | Начать с минимума (threads, runs, stream). Остальное — по мере надобности |
| 4 | **Docker-in-Docker безопасность** | Средняя | Высокое | Privileged mode на старте. Sysbox или gVisor — если проблема. Timeout + resource limits |
| 5 | **CLI Runner доступность** (отдельная VPS) | Низкая | Среднее | Health check, auto-restart. Fallback на internal agents |
| 6 | **Стоимость LLM** при CLI-агентах | Высокая | Среднее | Мониторинг через Langfuse. Лимиты per-task. Дешёвые модели для простых задач |
| 7 | **Frontend усложнение** (auth + streaming + graph viz) | Средняя | Среднее | Поэтапное добавление. Feature flags. Fallback на polling |
| 8 | **Langfuse performance** при большом количестве traces | Низкая | Низкое | Отдельная БД для Langfuse если нужно. Retention policy |
| 9 | **Prefect Server на deploy VPS** — доп. нагрузка | Низкая | Низкое | SQLite backend (не PostgreSQL). Минимальные ресурсы |

---

## 8. Глоссарий зависимостей между модулями {#8-зависимости}

```
Модуль                  │ Зависит от            │ Блокирует
────────────────────────┼───────────────────────┼─────────────────────
2.1  structlog          │ —                     │ ничего (но лучше первым)
2.2  agents.yaml        │ —                     │ 2.3 (fallback config)
2.3  retry+fallback     │ 2.2 (fallback_model)  │ 2.4 (invoke_with_retry)
2.4  langfuse fix       │ 2.3 (retry)           │ ничего
2.5  manifest.yaml      │ —                     │ 2.6 (graph endpoints)
2.6  Gateway            │ 2.5 (manifest)        │ 2.7, 2.8, 2.9, 2.11
2.7  Frontend auth      │ 2.6 (auth API)        │ ничего
2.8  Graph viz          │ 2.6 (topology API)    │ ничего
2.9  Streaming          │ 2.6 (SSE proxy)       │ ничего
2.10 Web tools          │ —                     │ ничего
2.11 Telegram           │ 2.6 (Gateway API)     │ ничего
2.12 State расширение   │ —                     │ ничего
────────────────────────┼───────────────────────┼─────────────────────
3.1  Git-based          │ —                     │ 3.5, 3.6
3.2  Switch-Agent       │ 2.6, 2.5             │ ничего
3.3  Sandbox            │ —                     │ 3.4, 3.5 (опционально)
3.4  Security Agent     │ 3.3 (опционально)    │ ничего
3.5  DevOps Agent       │ 3.1                   │ 3.8 (CI-конфиг)
3.6  CLI Agents         │ 3.1, VPS             │ 3.10c (QA-CLI)
────────────────────────┼───────────────────────┼─────────────────────
3.7  Sandbox инфра      │ 3.3 (Sandbox)         │ ничего
3.8  CI/CD интеграция   │ 3.1 (Git), 3.5 (DevOps)│ ничего
3.9  QA промпты         │ —                     │ 3.10 (пайплайн)
3.10 Пайплайн QA        │ 3.6 (CLI), 3.9 (промпты)│ ничего
```

### Рекомендуемый порядок реализации Волны 1

```
Параллельный поток A (backend):
  2.1 structlog → 2.2 agents.yaml → 2.3 retry → 2.4 langfuse fix

Параллельный поток B (infrastructure):
  2.5 manifest.yaml → 2.6 Gateway (этапы A-F)

Параллельный поток C (после Gateway готов):
  2.7 Frontend auth ─┐
  2.8 Graph viz ─────┤ (параллельно)
  2.9 Streaming ─────┤
  2.11 Telegram ─────┘

Независимые:
  2.10 Web tools (в любой момент)
  2.12 State расширение (в любой момент)
```

### Рекомендуемый порядок реализации Волны 2

```
3.1 Git-based ─────────→ 3.5 DevOps Agent ──→ 3.8 CI/CD интеграция
                    ├──→ 3.6 CLI Agents ───→ 3.10c QA-CLI граф
3.3 Sandbox ──┬────────→ 3.4 Security Agent
              └────────→ 3.7 Sandbox инфра (PG, Redis, инструменты)
3.2 Switch-Agent (независимо, когда второй граф готов)
3.9 QA промпты (независимо, 0 кода) → 3.10a TDD, 3.10b Multi-pass
```
