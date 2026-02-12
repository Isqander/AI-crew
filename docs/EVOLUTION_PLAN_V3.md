# AI-crew: План эволюции v3

> Финальный архитектурный план, готовый к реализации.
> Дата: 8 февраля 2026

---

## Содержание

1. [Зафиксированные решения](#1-зафиксированные-решения)
2. [Безопасность и аутентификация](#2-безопасность)
3. [Качество AI-генерированного кода (framing)](#3-качество-кода)
4. [Визуализация графа: что показываем](#4-визуализация)
5. [Switch-Agent и мульти-граф: финальная архитектура](#5-switch-agent)
6. [Gateway: FastAPI-прокси перед Aegra](#6-gateway)
7. [Секреты при деплое: разделение ответственности](#7-секреты)
8. [Линтеры и автопроверки в pipeline](#8-линтеры)
9. [CLI-агенты: универсальные исполнители](#9-cli-агенты)
10. [Git-based передача кода: итоговый подход](#10-git-based)
11. [Сохранение flow-истории: Langfuse + доработки](#11-flow-history)
12. [Волна 1: Лёгкое (реализация)](#12-волна-1)
13. [Волна 2: Среднее (реализация)](#13-волна-2)
14. [Волна 3: Сложное (отложено, архитектура заложена)](#14-волна-3)
15. [Целевая архитектура](#15-целевая-архитектура)
16. [Файлы для создания/изменения (чеклист)](#16-чеклист)
17. [Порядок реализации (day-by-day)](#17-порядок)

---

## 1. Зафиксированные решения {#1-зафиксированные-решения}

### Итоговые выборы

| # | Пункт | Решение | Статус |
|---|-------|---------|--------|
| 1 | Retry логика | Tenacity + exponential backoff + fallback chain | Волна 1 |
| 2 | Логирование | structlog (JSON в проде, консоль локально) | Волна 1 |
| 3 | Streaming | Доделать SSE (streamRun уже есть) | Волна 1 |
| 4 | LLM конфиг | `config/agents.yaml` + env overrides | Волна 1 |
| 5 | Web tools | DuckDuckGo (потом свой API) + fetch + download | Волна 1 |
| 6 | Визуализация графа | React Flow read-only, **всё**: узлы, связи, модели, промпты | Волна 1 |
| 7 | Telegram | Отдельный сервис через Aegra API | Волна 1 |
| 8 | **Аутентификация** | Gateway auth + регистрация пользователей | **Волна 1** |
| 9 | Sandbox | Docker-in-Docker | Волна 2 |
| 10 | VPS Deploy + CI/CD | DevOps Agent + GitHub Actions | Волна 2 |
| 11 | CLI-агенты | VPS + API-обёртка, узел в графе, любая роль | Волна 2 |
| 12 | Git-based код | GitHub branches (Вариант A). Без локальных файлов | Волна 2 |
| 13 | Switch-Agent | **Внешний роутер** (API-level, Вариант C). На фронте — выбор графа или авто | Волна 2 |
| 14 | Visual Graph Editor | **Отложен**. Визуализация — да, редактирование — нет | Долгий ящик |
| 15 | Self-Improvement | **Отложен**. Но сохранение всех flow — обязательно | Долгий ящик |
| 16 | Динамическая генерация | **Отложена** (4.8 C) | Долгий ящик |

### Архитектурные решения

| Пункт | Решение |
|-------|---------|
| Граф-представление | **Python-first** + JSON-экспорт (`to_json()`) + YAML-метаданные (`manifest.yaml`) |
| Будущий Editor | Обратный путь: Frontend → JSON → Python (с помощью LLM или компилятора). Не сейчас |
| Subgraphs | Используем как кирпичики внутри графов (нативно LangGraph). Не для Switch-Agent |
| Aegra | Остаёмся. Мораторий на изменения **снят**. Основная стратегия — **FastAPI gateway** перед Aegra |
| Микросервисы | Фаза 2 по мере подключения CLI-агентов. Пока docker-compose |
| State sharing | Разные команды = разные проекты. Не мешаем. Общий BaseState не нужен |
| nip.io + HTTPS | Traefik + Let's Encrypt (работает, проверено) |
| VPS для CLI | **Отдельный** от VPS для деплоя |

---

## 2. Безопасность и аутентификация {#2-безопасность}

### 2.1 Текущее состояние

**Критическая проблема:** Сейчас наружу открыто всё без аутентификации.

| Сервис | Порт | Текущий доступ | Что нужно |
|--------|------|---------------|-----------|
| Frontend | 5173 | Открыт, без auth | Аутентификация + регистрация |
| Aegra API | 8000 | Открыт, `AUTH_TYPE=noop` | Закрыть за gateway |
| Langfuse | 3001 | Открыт (свой auth есть) | Оставить, он сам умеет auth |
| PostgreSQL | 5433 | Открыт | Оставить (для прямого доступа), но ограничить по IP если на VPS |

### 2.2 Архитектура аутентификации

**Подход:** Gateway отвечает за auth. Aegra работает в внутренней сети без auth (`AUTH_TYPE=noop`).

```
Интернет
    │
    ▼
┌────────────────────────────────────────┐
│  Gateway (FastAPI)  :8081              │  ← Единственная точка входа
│  ├── /auth/register  POST             │
│  ├── /auth/login     POST             │
│  ├── /auth/me        GET              │
│  ├── /api/*          → proxy Aegra    │  ← Проверка JWT
│  ├── /ws/*           → proxy Aegra    │  ← Проверка JWT
│  └── /graph/*        (свои endpoints) │
└────────────────┬───────────────────────┘
                 │ внутренняя сеть (docker)
    ┌────────────┼────────────────┐
    ▼            ▼                ▼
  Aegra:8000  Langfuse:3001   Postgres:5433
  (нет auth)  (свой auth)    (ограничить доступ)
```

**Порты наружу:**

| Сервис | Наружу | Комментарий |
|--------|--------|-------------|
| Gateway | **:8081** | Единственная точка входа для API |
| Frontend | **:5173** | Статика (в проде через nginx) |
| Langfuse | **:3001** | Свой auth (NextAuth), оставить |
| PostgreSQL | **:5433** | Оставить для прямого доступа. На VPS — ограничить firewall по IP |
| Aegra | — | **Закрыть**. Доступен только из docker-сети |
| Sandbox | — | Только внутренняя сеть |
| Telegram | — | Только внутренняя сеть (webhook или polling) |

### 2.3 Реализация аутентификации

**Простая, но полноценная схема:**

```python
# gateway/auth.py
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer
import jwt
import bcrypt

# Пользователи в PostgreSQL (отдельная таблица)
# Минимальная модель: id, email, password_hash, display_name, created_at, is_active

security = HTTPBearer()

async def get_current_user(token = Depends(security)) -> User:
    """Validate JWT token and return user."""
    try:
        payload = jwt.decode(token.credentials, SECRET_KEY, algorithms=["HS256"])
        user = await get_user_by_id(payload["sub"])
        if not user or not user.is_active:
            raise HTTPException(status_code=401)
        return user
    except jwt.PyJWTError:
        raise HTTPException(status_code=401)

# Endpoints:
# POST /auth/register  — email + password → создать пользователя, вернуть JWT
# POST /auth/login     — email + password → вернуть JWT
# GET  /auth/me        — текущий пользователь
# POST /auth/refresh   — обновить JWT
```

**Фронтенд:**
- Добавить страницу Login/Register
- Хранить JWT в localStorage или httpOnly cookie
- `AegraClient` → добавить `Authorization: Bearer <token>` в заголовки
- Protected routes: если нет токена → редирект на /login

**Зависимости:** `pyjwt`, `bcrypt`, `python-multipart`

**Сложность: 3/10 | 1-2 дня**

### 2.4 Безопасность docker-compose (обновлённый)

```yaml
services:
  # Gateway — единственный сервис с внешним портом для API
  gateway:
    build: ./gateway
    ports:
      - "8081:8081"
    environment:
      AEGRA_URL: http://aegra:8000
      JWT_SECRET: ${JWT_SECRET}
      DATABASE_URL: postgresql://...@postgres:5433/aicrew
    depends_on: [aegra, postgres]

  # Aegra — ЗАКРЫТ снаружи
  aegra:
    build: .
    # ports: НЕТ — доступен только из docker-сети
    expose:
      - "8000"
    environment:
      AUTH_TYPE: noop  # auth на уровне gateway
      # ... остальное без изменений

  # Frontend — открыт
  frontend:
    build: ./frontend
    ports:
      - "5173:5173"
    environment:
      VITE_API_URL: http://localhost:8081  # Через gateway!

  # Langfuse — открыт (свой auth)
  langfuse:
    ports:
      - "3001:3001"

  # PostgreSQL — оставляем для прямого доступа
  postgres:
    ports:
      - "${POSTGRES_PORT:-5433}:5433"
```

---

## 3. Качество AI-генерированного кода (framing) {#3-качество-кода}

Приложение, сгенерированное ИИ-агентами, нужно держать в правильных рамках.

### 3.1 Тип A: Внутри графа (промпты, агенты, loops)

Это то, что мы **уже делаем и будем расширять**:

| Механизм | Где | Что делает |
|----------|-----|-----------|
| Промпты с best practices | `prompts/*.yaml` | Задают стандарты кода, тестов, архитектуры |
| QA Agent | Узел графа | Код-ревью, проверка требований |
| Dev↔QA loop (≤3 итерации) | Граф | Итеративное исправление |
| Architect escalation | Граф | Арбитраж при зацикливании |
| Security Agent | Узел графа | SAST, secrets, deps |
| Human escalation (HITL) | Граф | Человек решает сложные случаи |
| Sandbox (тесты) | Узел графа | Запуск тестов до PR |

### 3.2 Тип B: Вне графа — архитектурный уровень

Это нужно **заложить в инфраструктуру**, чтобы ИИ не мог обойти:

| Механизм | Реализация | Зачем |
|----------|-----------|-------|
| **Линтеры в CI/CD** | GitHub Actions: pre-commit hooks, CI pipeline | Код не мерджится без прохождения линтеров |
| **Тесты в CI/CD** | GitHub Actions: pytest, jest, etc. | Обязательное покрытие перед мерджем |
| **Branch protection** | GitHub: require PR reviews, status checks | ИИ не может пушить напрямую в main |
| **PR как единица работы** | Всегда PR, никогда прямой push | Человек или CI ревьюит каждое изменение |
| **Template repos** | Шаблоны проектов с pre-configured tooling | Новые проекты сразу с правильной структурой |
| **CODEOWNERS** | GitHub CODEOWNERS file | Критичные файлы требуют ревью конкретных людей |
| **Dependency scanning** | Dependabot / Renovate в CI | Автоматическая проверка зависимостей |
| **Container scanning** | Trivy в CI | Сканирование Docker-образов |
| **Secrets detection** | gitleaks в pre-commit | Блокировка коммитов с секретами |

**Ключевой принцип:** ИИ-агенты работают через Git (ветки → PR). Все проверки — в CI/CD pipeline, который **невозможно обойти** (branch protection rules).

**DevOps Agent при создании проекта автоматически:**
1. Настраивает branch protection rules
2. Добавляет CI pipeline с линтерами/тестами
3. Настраивает pre-commit hooks
4. Добавляет CODEOWNERS если нужно

---

## 4. Визуализация графа: что показываем {#4-визуализация}

### Решение

Python-first + JSON-экспорт + YAML-метаданные. Показываем **всё**:

- Узлы и связи (из `graph.get_graph().to_json()`)
- Модели для каждого агента (из `config/agents.yaml`)
- Промпты (из `prompts/*.yaml`)
- Текущий статус узла (active/completed/pending из state)

### Что возвращает `graph.get_graph().to_json()`

LangGraph нативно экспортирует структуру графа в JSON-формат:
```json
{
  "nodes": [
    {"id": "__start__", "type": "schema", "data": "..."},
    {"id": "pm", "type": "runnable", "data": {"id": ["langchain", "..."], "name": "pm_agent"}},
    {"id": "analyst", "type": "runnable", "data": "..."},
    ...
  ],
  "edges": [
    {"source": "__start__", "target": "pm"},
    {"source": "pm", "target": "analyst"},
    {"source": "analyst", "target": "architect", "conditional": true, "data": "route_after_analyst"},
    ...
  ]
}
```

### Что **нужно дополнить** (endpoint в Gateway)

`to_json()` не содержит информацию о моделях и промптах — это наши данные.
Gateway собирает полную картину:

```python
# gateway/endpoints/graph.py
@router.get("/graph/topology/{graph_id}")
async def graph_topology(graph_id: str):
    """
    Полная информация о графе для визуализации:
    - topology: nodes + edges (из LangGraph to_json())
    - agents: модели, температуры (из config/agents.yaml)
    - prompts: system prompt для каждого агента (из prompts/*.yaml)
    - manifest: метаданные графа (из manifest.yaml)
    """
    # 1. Topology из Aegra
    topology = await get_graph_topology(graph_id)  # proxy к Aegra или import

    # 2. Agent config
    agent_config = load_agent_config()  # config/agents.yaml

    # 3. Prompts (только system — для отображения, не полные шаблоны)
    prompts = {}
    for agent_name in ["pm", "analyst", "architect", "developer", "qa"]:
        try:
            p = load_prompts(agent_name)
            prompts[agent_name] = {
                "system": p.get("system", "")[:500],  # Обрезка для UI
                "templates": list(p.keys()),
            }
        except FileNotFoundError:
            pass

    # 4. Manifest
    manifest = load_manifest(graph_id)

    return {
        "topology": topology,
        "agents": {
            name: {
                "model": agent_config.get("agents", {}).get(name, {}).get("model", "default"),
                "temperature": agent_config.get("agents", {}).get(name, {}).get("temperature", 0.7),
                "fallback_model": agent_config.get("agents", {}).get(name, {}).get("fallback_model"),
            }
            for name in ["pm", "analyst", "architect", "developer", "qa"]
        },
        "prompts": prompts,
        "manifest": manifest,
    }
```

### Frontend компонент

```typescript
// components/GraphVisualization.tsx
// React Flow с кастомными узлами, показывающими:
// - Название агента
// - Модель (badge)
// - Статус (цвет: active=cyan, completed=green, pending=slate)
// - По клику: system prompt, параметры
// Edges: обычные и conditional (пунктир + label)
```

### Будущее (Editor)

Если решим делать Editor — добавим **обратный путь**:
1. Фронт редактирует JSON-представление
2. Backend конвертирует JSON → Python (через LLM или компилятор)
3. Результат → PR

Но **не сейчас**. Архитектура не мешает добавить это позже.

---

## 5. Switch-Agent и мульти-граф: финальная архитектура {#5-switch-agent}

### Решение: внешний роутер (Вариант C)

**Не subgraphs** для маршрутизации между flow. Subgraphs — кирпичики **внутри** графов.

```
Пользователь
    │
    ├── Выбирает граф вручную на фронте  ─┐
    │                                       │
    └── Выбирает "Авто" (Switch-Agent)  ──┤
                                           │
                                           ▼
                                    ┌──────────────┐
                                    │ Gateway       │
                                    │ POST /api/run │
                                    │               │
                                    │ if auto:      │
                                    │   classify()  │  ← LLM-вызов (с retry+fallback!)
                                    │   → graph_id  │
                                    │               │
                                    │ Aegra.create_ │
                                    │ run(graph_id) │
                                    └──────┬───────┘
                                           │
                              ┌────────────┼────────────┐
                              ▼            ▼            ▼
                         dev_team    research_team   ...другие
```

### Как это работает с Aegra

Aegra поддерживает несколько графов в `aegra.json`:
```json
{
  "graphs": {
    "dev_team": "./graphs/dev_team/graph.py:graph",
    "research_team": "./graphs/research_team/graph.py:graph"
  }
}
```

При создании run передаётся `assistant_id` — это и есть выбор графа.
Router в Gateway просто выбирает `assistant_id` перед вызовом Aegra.

### Роутер (classify_task)

```python
# gateway/router.py
from pydantic import BaseModel

class TaskClassification(BaseModel):
    graph_id: str        # "dev_team", "research_team", etc.
    complexity: int      # 1-10
    reasoning: str

async def classify_task(task: str, available_graphs: list[dict]) -> TaskClassification:
    """
    Classify task and choose graph.
    Uses LLM with retry+fallback (same as agents).
    """
    llm = get_llm_with_fallback(role="router", temperature=0.1)
    structured_llm = llm.with_structured_output(TaskClassification)

    graphs_desc = "\n".join(
        f"- {g['name']}: {g['description']} (task_types: {g['task_types']})"
        for g in available_graphs
    )

    return await structured_llm.ainvoke(
        f"Choose the best workflow for this task.\n\n"
        f"Task: {task}\n\n"
        f"Available workflows:\n{graphs_desc}\n\n"
        f"Respond with graph_id, complexity (1-10), and reasoning."
    )
```

### Фронтенд

```
┌──────────────────────────────────────┐
│ Новая задача                          │
│                                       │
│ Описание: [________________________] │
│                                       │
│ Флоу:  ○ Авто (Switch-Agent)         │
│        ○ Development Team             │
│        ○ Research Team                │
│        ○ ... (из manifest.yaml)       │
│                                       │
│           [Запустить]                  │
└──────────────────────────────────────┘
```

Список графов на фронте — из `GET /graph/list` (Gateway читает все `manifest.yaml`).

### Сложность

- Router в Gateway: **2/10 | 1 день**
- Мульти-граф в aegra.json: **1/10 | 0.5 дня**
- Фронтенд (выбор графа): **2/10 | 0.5 дня**
- Второй граф (research_team): **3-5/10 | 2-3 дня** (когда дойдём)

---

## 6. Gateway: FastAPI-прокси перед Aegra {#6-gateway}

### Зачем

1. Аутентификация (JWT) — Aegra не трогаем
2. Switch-Agent / Router
3. Расширенные endpoints (graph topology, analytics, graph list)
4. Rate limiting
5. CORS (единая точка)
6. Будущее: webhook для Telegram, CLI-agent API

### Структура

```
gateway/
├── main.py              # FastAPI app
├── auth.py              # JWT auth, register/login
├── proxy.py             # Прокси к Aegra
├── router.py            # Switch-Agent (classify_task)
├── endpoints/
│   ├── graph.py         # /graph/topology, /graph/list
│   └── analytics.py     # /analytics/* (будущее)
├── models.py            # Pydantic models
├── config.py            # Settings
├── Dockerfile
└── requirements.txt
```

### Прокси к Aegra

```python
# gateway/proxy.py
from fastapi import Request, Response, Depends
import httpx

AEGRA_URL = os.getenv("AEGRA_URL", "http://aegra:8000")

async def proxy_to_aegra(request: Request, user = Depends(get_current_user)):
    """Proxy authenticated requests to Aegra."""
    async with httpx.AsyncClient() as client:
        # Пробросить метод, путь, тело, query params
        url = f"{AEGRA_URL}{request.url.path}"
        response = await client.request(
            method=request.method,
            url=url,
            content=await request.body(),
            params=dict(request.query_params),
            headers={"Content-Type": request.headers.get("Content-Type", "application/json")},
            timeout=300.0,  # Длинные LLM-вызовы
        )
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=dict(response.headers),
        )
```

Для SSE streaming — нужен streaming proxy:
```python
# gateway/proxy.py
async def proxy_stream_to_aegra(request: Request, user = Depends(get_current_user)):
    """Proxy SSE streaming from Aegra."""
    async def stream():
        async with httpx.AsyncClient() as client:
            async with client.stream(
                method="POST",
                url=f"{AEGRA_URL}{request.url.path}",
                content=await request.body(),
                timeout=600.0,
            ) as response:
                async for chunk in response.aiter_bytes():
                    yield chunk

    return StreamingResponse(stream(), media_type="text/event-stream")
```

### Маршрутизация в Gateway

```python
# gateway/main.py
from fastapi import FastAPI

app = FastAPI(title="AI-crew Gateway")

# Auth (без JWT)
app.include_router(auth_router, prefix="/auth", tags=["auth"])

# Свои endpoints (с JWT)
app.include_router(graph_router, prefix="/graph", tags=["graph"], dependencies=[Depends(get_current_user)])

# Всё остальное → proxy к Aegra (с JWT)
@app.api_route("/threads/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
@app.api_route("/assistants/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
@app.api_route("/runs/{path:path}", methods=["GET", "POST"])
@app.api_route("/store/{path:path}", methods=["GET", "POST", "PUT"])
async def proxy(request: Request, user = Depends(get_current_user)):
    return await proxy_to_aegra(request)

# SSE streaming — отдельный обработчик
@app.post("/threads/{thread_id}/runs/stream")
async def stream_proxy(thread_id: str, request: Request, user = Depends(get_current_user)):
    return await proxy_stream_to_aegra(request)

# Health (без auth)
@app.get("/health")
async def health():
    return {"status": "ok"}
```

**Сложность: 4/10 | 2-3 дня** (включая auth)

---

## 7. Секреты при деплое: разделение ответственности {#7-секреты}

### Проблема

Если человек вносит секреты, а ИИ имеет к ним доступ — это плохо.

### Решение: трёхуровневое разделение

```
┌─────────────────────────────────────────────────────────────┐
│  Уровень 1: ИИ-агент настраивает (некритичные)              │
│  ─────────────────────────────────────────────               │
│  APP_NAME, DOMAIN, NODE_ENV, LOG_LEVEL                      │
│  Где: GitHub Secrets (через API) или .env на VPS            │
│  ИИ имеет доступ: ДА                                        │
│  Риск: НИЗКИЙ                                               │
├─────────────────────────────────────────────────────────────┤
│  Уровень 2: Человек настраивает, ИИ НЕ имеет доступа       │
│  ─────────────────────────────────────────────               │
│  VPS_SSH_KEY, DATABASE_URL, API_KEYS клиента               │
│  Где: GitHub Secrets (вручную) — WRITE-ONLY для ИИ          │
│  ИИ имеет доступ: НЕТ (GitHub Secrets write-only по дизайну)│
│  Риск: СРЕДНИЙ (человек вносит, CI использует)              │
├─────────────────────────────────────────────────────────────┤
│  Уровень 3: Платформенные секреты AI-crew                   │
│  ─────────────────────────────────────────────               │
│  LLM_API_KEY, GITHUB_TOKEN (AI-crew), JWT_SECRET            │
│  Где: env-переменные на хосте AI-crew, НЕ в GitHub Secrets  │
│  ИИ имеет доступ: ИСПОЛЬЗУЕТ, но НЕ ВИДИТ (env в runtime)   │
│  Риск: НИЗКИЙ (стандартная практика)                         │
└─────────────────────────────────────────────────────────────┘
```

### Ключевой момент: GitHub Secrets = write-only

GitHub Secrets по дизайну: после записи — нельзя прочитать через API.
Даже если ИИ-агент имеет `GITHUB_TOKEN` с правом записи secrets,
он не может **прочитать** уже записанные секреты.

CI/CD (GitHub Actions) видит секреты **только в runtime** workflow,
и даже там они маскируются в логах.

**Вывод:** Человек вносит критичные секреты в GitHub Secrets вручную.
ИИ-агент **не имеет к ним доступа** после записи. Это безопасно.

### Workflow DevOps-агента

```
DevOps Agent:
    1. Анализирует проект → определяет нужные секреты
    2. Генерирует список:
       [AUTO] APP_NAME=my-todo-app         → прописывает сам
       [AUTO] DOMAIN=myapp.31.59.58.143.nip.io → прописывает сам
       [MANUAL] VPS_SSH_KEY              → HITL: просит человека
       [MANUAL] DATABASE_URL             → HITL: просит человека
    3. Автоматические → записывает через GitHub API
    4. Ручные → уведомляет через UI/Telegram:
       "Пожалуйста, добавьте VPS_SSH_KEY в GitHub Secrets
        Settings → Secrets → Actions → New repository secret"
    5. Ждёт подтверждения (HITL)
    6. Проверяет наличие секретов (через API можно проверить,
       что секрет СУЩЕСТВУЕТ, не читая значение)
    7. Продолжает деплой
```

---

## 8. Линтеры и автопроверки в pipeline {#8-линтеры}

### Линтеры между Dev и QA (в графе)

Да, это часть конкретного графа. Можно добавить **lint node**:

```
Developer → lint_check → QA
               │
               ├── lint pass → QA
               └── lint fail → Developer (с ошибками)
```

```python
# В graph.py
def lint_check_node(state: DevTeamState) -> dict:
    """Run linters on generated code before QA review."""
    results = run_linters(state["code_files"], state.get("tech_stack", []))
    if results["errors"]:
        return {
            "issues_found": results["errors"],
            "current_agent": "developer",
        }
    return {
        "current_agent": "qa",
    }
```

### Линтеры в CI/CD (при деплое)

DevOps Agent генерирует CI pipeline с линтерами **на основе стека**:

```python
# agents/devops.py
LINTER_CONFIGS = {
    "python": {
        "linters": ["ruff check .", "mypy --strict ."],
        "ci_step": "pip install ruff mypy && ruff check . && mypy .",
    },
    "javascript": {
        "linters": ["eslint . --ext .js,.jsx,.ts,.tsx"],
        "ci_step": "npm run lint",
    },
    "typescript": {
        "linters": ["eslint .", "tsc --noEmit"],
        "ci_step": "npm run lint && npx tsc --noEmit",
    },
    "go": {
        "linters": ["golangci-lint run"],
        "ci_step": "golangci-lint run",
    },
    # ... расширяемо
}

def get_linters_for_stack(tech_stack: list[str]) -> list[str]:
    """Determine linters based on project tech stack."""
    linters = []
    for tech in tech_stack:
        lang = detect_language(tech)  # "react" → "javascript", "fastapi" → "python"
        if lang in LINTER_CONFIGS:
            linters.extend(LINTER_CONFIGS[lang]["linters"])
    return list(set(linters))
```

### Библиотека конфигов линтеров

```
config/linters/
├── python.yaml      # ruff + mypy config
├── javascript.yaml  # eslint + prettier config
├── typescript.yaml  # eslint + tsc config
├── go.yaml          # golangci-lint config
└── docker.yaml      # hadolint config
```

DevOps Agent при генерации CI pipeline:
1. Определяет стек проекта (из `tech_stack` в state)
2. Подбирает подходящие линтеры
3. Генерирует `lint` step в `.github/workflows/ci.yml`
4. Опционально добавляет `.pre-commit-config.yaml`

---

## 9. CLI-агенты: универсальные исполнители {#9-cli-агенты}

### Ключевое уточнение

CLI-агенты — **не только кодеры**. Они могут быть:
- Архитекторами (проектирование)
- Менеджерами (анализ задач)
- Ресёрчерами (исследования)
- Кодерами (реализация)
- Любой другой ролью

Специфика: дороже, мощнее, работают с файловой системой напрямую.

### Узел в графе

```python
# agents/cli_agent.py
async def cli_agent_node(state: DevTeamState) -> dict:
    """
    Universal CLI agent node.
    Role determined by state context.
    """
    role = state.get("cli_agent_role", "developer")  # Роль определяется роутером
    instructions = format_instructions_for_role(state, role)

    runner = CLIAgentRunner(api_url=os.getenv("CLI_RUNNER_URL"))

    result = await runner.execute(
        repo=state.get("working_repo"),
        branch=state.get("working_branch"),
        instructions=instructions,
        cli_tool=state.get("cli_tool", "claude"),  # "claude" | "codex"
        timeout=state.get("cli_timeout", 600),
    )

    return {
        "cli_agent_output": result.output,
        "current_agent": f"cli_{role}",
        # Если CLI-агент коммитит — файлы уже в git
    }
```

### Роутинг: внутренний агент vs CLI

```python
def route_to_executor(state: DevTeamState) -> str:
    """Choose executor based on complexity and mode."""
    mode = state.get("execution_mode", "auto")

    if mode == "cli":
        return "cli_agent"
    if mode == "internal":
        return "developer"

    # Auto: CLI для сложных задач с существующим репо
    complexity = state.get("task_complexity", 5)
    has_repo = bool(state.get("working_repo"))

    if complexity >= 7 and has_repo:
        return "cli_agent"
    return "developer"
```

### API-обёртка на VPS CLI-агента

```python
# cli_runner/server.py (на отдельной VPS)
from fastapi import FastAPI
from pydantic import BaseModel
import asyncio, shutil, uuid

app = FastAPI(title="CLI Agent Runner")

class CLIJobRequest(BaseModel):
    repo: str | None = None
    branch: str | None = None
    instructions: str
    cli_tool: str = "claude"  # "claude" | "codex"
    timeout: int = 600
    github_token: str | None = None

class CLIJobResult(BaseModel):
    job_id: str
    output: str
    exit_code: int
    files_changed: list[str] = []

@app.post("/jobs", response_model=CLIJobResult)
async def create_job(req: CLIJobRequest):
    job_id = str(uuid.uuid4())[:8]
    workspace = f"/workspace/{job_id}"

    try:
        # 1. Clone repo (если есть)
        if req.repo:
            token_prefix = f"https://x-access-token:{req.github_token}@" if req.github_token else "https://"
            repo_url = req.repo.replace("https://", token_prefix)
            await run_cmd(f"git clone {repo_url} {workspace}")
            if req.branch:
                await run_cmd(f"git checkout {req.branch}", cwd=workspace)
        else:
            os.makedirs(workspace)

        # 2. Run CLI agent
        if req.cli_tool == "claude":
            cmd = f'claude --print --dangerously-skip-permissions "{req.instructions}"'
        elif req.cli_tool == "codex":
            cmd = f'codex --approval-mode full-auto "{req.instructions}"'

        result = await run_cmd(cmd, cwd=workspace, timeout=req.timeout)

        # 3. Commit + push (если есть repo)
        if req.repo:
            await run_cmd("git add -A && git diff --cached --quiet || git commit -m 'Changes by CLI agent'", cwd=workspace)
            await run_cmd("git push", cwd=workspace)
            files = (await run_cmd("git diff --name-only HEAD~1", cwd=workspace)).stdout.strip().split("\n")
        else:
            files = []

        return CLIJobResult(
            job_id=job_id,
            output=result.stdout[-5000:],  # Обрезка
            exit_code=result.returncode,
            files_changed=files,
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
```

---

## 10. Git-based передача кода: итоговый подход {#10-git-based}

### Решение: только GitHub branches (Вариант A)

Локальные файлы для CLI (Вариант B) — **не нужны**.
CLI-агенты подключаются к Git напрямую (токен есть).

Для маленьких задач (без репо) — CLI-агенты и не нужны.
`code_files` в state работает как раньше.

### Логика

```
Задача с репо?
    │
    ├── НЕТ → code_files в state (как сейчас)
    │         → git_commit_node создаёт ветку и PR
    │
    └── ДА → PM создаёт рабочую ветку
              → working_branch + working_repo в state
              → Все агенты работают через git tools
              → CLI-агент коммитит напрямую в ветку
              → git_commit_node только создаёт PR
```

### Новые поля в State

```python
# state.py — дополнения для Волны 2
class DevTeamState(TypedDict):
    # ... всё существующее ...

    # === Волна 1 ===
    task_type: NotRequired[str]           # "new_project", "bugfix", "research"
    task_complexity: NotRequired[int]     # 1-10

    # === Волна 2: Git-based ===
    working_branch: NotRequired[str]      # "ai/task-20260208-123456"
    working_repo: NotRequired[str]        # "owner/repo"
    file_manifest: NotRequired[list[str]] # Файлы в ветке

    # === Волна 2: Sandbox ===
    sandbox_results: NotRequired[dict]    # {stdout, stderr, exit_code}

    # === Волна 2: Security ===
    security_review: NotRequired[dict]    # {critical, warnings, info}

    # === Волна 2: Deploy ===
    deploy_url: NotRequired[str]          # "https://app.31.59.58.143.nip.io"
    infra_files: NotRequired[list[dict]]  # Dockerfile, CI/CD files

    # === Волна 2: CLI ===
    cli_agent_output: NotRequired[str]
    cli_agent_role: NotRequired[str]      # "developer", "architect", etc.
    execution_mode: NotRequired[str]      # "auto" | "internal" | "cli"
    cli_tool: NotRequired[str]            # "claude" | "codex"
```

---

## 11. Сохранение flow-истории: Langfuse + доработки {#11-flow-history}

### Текущее состояние Langfuse

| Компонент | Статус | Что нужно |
|-----------|--------|-----------|
| Langfuse server | Работает в docker-compose | Ничего |
| `langfuse>=2.0.0` в requirements | Установлен | Ничего |
| Aegra интеграция | Есть: `langfuse_integration.py` в Aegra | Включить: `LANGFUSE_ENABLED=true` |
| Graph-level tracing | Работает: node starts/ends, state | Ничего |
| **LLM-level tracing** | **НЕ работает**: агенты не передают callbacks | **Нужна доработка** |

### Проблема

Aegra передаёт Langfuse callbacks в `config["callbacks"]`, но наши агенты
вызывают `chain.invoke()` **без передачи этих callbacks**.

В результате: Langfuse видит, что node "developer" запустился и завершился,
но **не видит** промпт, ответ LLM, токены и стоимость.

### Решение: передавать callbacks в LLM вызовы

```python
# base.py — обновление BaseAgent
class BaseAgent:
    def invoke(self, state: dict, config: RunnableConfig = None) -> dict:
        raise NotImplementedError

    def _get_callbacks(self, config: dict | None) -> list:
        """Extract callbacks from LangGraph config for Langfuse tracing."""
        if config and "callbacks" in config:
            return config["callbacks"]
        return []

    def _invoke_chain(self, chain, inputs: dict, config: dict | None = None):
        """Invoke chain with callbacks from config."""
        callbacks = self._get_callbacks(config)
        if callbacks:
            return chain.invoke(inputs, config={"callbacks": callbacks})
        return chain.invoke(inputs)
```

Каждый агент: заменить `chain.invoke(inputs)` → `self._invoke_chain(chain, inputs, config)`.

**Важно:** Для этого node functions должны принимать `config`:

```python
# Текущее:
def pm_agent(state: DevTeamState) -> dict:

# Новое:
def pm_agent(state: DevTeamState, config: RunnableConfig = None) -> dict:
```

LangGraph автоматически передаёт `config` если функция его принимает.

### Что будет видно после доработки

В Langfuse (http://localhost:3001):
- **Trace** на каждый run (thread_id + run_id)
- **Span** на каждый node (pm, analyst, architect, developer, qa)
- **Generation** на каждый LLM-вызов: промпт, ответ, модель, токены, стоимость, latency
- **State** на каждом шаге (из checkpoints)
- **Метрики**: cost per run, tokens per agent, latency distribution

### Ручной экспорт

Langfuse UI позволяет:
- Фильтровать traces по дате, тегам, пользователю
- Экспортировать данные через API (`GET /api/public/traces`)
- Просматривать полный промпт↔ответ для каждого LLM-вызова

Для анализа «дать ИИ посмотреть» — можно экспортировать JSON через API:
```bash
curl "http://localhost:3001/api/public/traces?limit=50" \
  -H "Authorization: Bearer $LANGFUSE_PUBLIC_KEY"
```

### Сложность доработки

**2/10 | 0.5-1 день** — механическая замена в каждом агенте.

---

## 12. Волна 1: Лёгкое {#12-волна-1}

**Общая оценка: 8-12 дней** при параллелизации.

### 12.1 Retry логика для LLM вызовов

**Файлы:**
- `graphs/dev_team/agents/base.py` — добавить `invoke_with_retry()`, `get_llm_with_fallback()`
- Все агенты — заменить `chain.invoke()` → `invoke_with_retry(chain, ...)`
- `requirements.txt` — добавить `tenacity`

```python
# base.py
from tenacity import (
    retry, stop_after_attempt, wait_exponential,
    retry_if_exception_type, before_sleep_log,
)
import structlog

logger = structlog.get_logger()

def invoke_with_retry(chain, inputs: dict, config: dict | None = None, **kwargs):
    """Invoke LLM chain with exponential backoff retry."""
    callbacks = config.get("callbacks", []) if config else []

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _invoke():
        invoke_config = {"callbacks": callbacks} if callbacks else {}
        return chain.invoke(inputs, config=invoke_config)

    return _invoke()

def get_llm_with_fallback(role: str, **kwargs) -> BaseChatModel:
    """Get LLM with fallback chain."""
    agent_config = load_agent_config()
    primary = get_llm(role=role, **kwargs)
    fallback_model = agent_config.get("agents", {}).get(role, {}).get("fallback_model")
    if fallback_model:
        fallback = get_llm(model=fallback_model, **kwargs)
        return primary.with_fallbacks([fallback])
    return primary
```

**Сложность: 1/10 | 0.5 дня**

---

### 12.2 Структурированное логирование

**Файлы:**
- Новый: `graphs/dev_team/logging_config.py`
- `graphs/dev_team/graph.py` — заменить `configure_logging()`
- `graphs/dev_team/agents/base.py` — `structlog.get_logger()`
- Все агенты — замена logger (механическая)
- `requirements.txt` — добавить `structlog`

```python
# logging_config.py
import logging
import os
import structlog

def configure_logging():
    env_mode = os.getenv("ENV_MODE", "LOCAL").upper()
    log_level = os.getenv("LOG_LEVEL", "DEBUG" if env_mode == "LOCAL" else "INFO")

    # Стандартный logging (для библиотек)
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(message)s",
    )

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
            getattr(logging, log_level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
```

**Сложность: 2/10 | 0.5-1 день**

---

### 12.3 Streaming в Frontend

**Файлы:**
- Новый: `frontend/src/hooks/useStreamingTask.ts`
- `frontend/src/pages/TaskDetail.tsx` — переключить на streaming
- `frontend/src/components/Chat.tsx` — real-time обновления
- `frontend/src/components/ProgressTracker.tsx` — подсветка без задержки

**Сложность: 3/10 | 1-2 дня**

---

### 12.4 Конфигурация LLM в файл

**Файлы:**
- Новый: `config/agents.yaml`
- `graphs/dev_team/agents/base.py` — `load_agent_config()`, обновить `get_llm()`, `get_model_for_role()`

```yaml
# config/agents.yaml
defaults:
  endpoint: default
  temperature: 0.7
  max_tokens: 4096

endpoints:
  default:
    url: ${LLM_API_URL}
    api_key: ${LLM_API_KEY}
  backup:
    url: ${LLM_BACKUP_URL}
    api_key: ${LLM_BACKUP_KEY}

agents:
  pm:
    model: gemini-claude-sonnet-4-5-thinking
    temperature: 0.7
    fallback_model: gemini-3-flash-preview
  analyst:
    model: gemini-claude-sonnet-4-5-thinking
    temperature: 0.7
    fallback_model: gemini-3-flash-preview
  architect:
    model: gemini-claude-opus-4-5-thinking
    temperature: 0.7
    fallback_model: gemini-claude-sonnet-4-5-thinking
  developer:
    model: glm-4.7
    temperature: 0.2
    fallback_model: gemini-3-flash-preview
  qa:
    model: glm-4.7
    temperature: 0.3
    fallback_model: gemini-3-flash-preview
  router:
    model: gemini-3-flash-preview
    temperature: 0.1
    fallback_model: glm-4.7
```

**Сложность: 2/10 | 0.5-1 день**

---

### 12.5 Доступ агентов в интернет

**Файлы:**
- Новый: `graphs/dev_team/tools/web.py`
- `requirements.txt` — `httpx`, `trafilatura`, `duckduckgo-search`
- Агенты — подключить tools по необходимости

**Сложность: 3/10 | 1-2 дня**

---

### 12.6 Визуализация графа на фронте

**Файлы:**
- `frontend/package.json` — `@xyflow/react`, `dagre`
- Новый: `frontend/src/components/GraphVisualization.tsx`
- `frontend/src/pages/TaskDetail.tsx` — вкладка/панель с графом
- Gateway: `GET /graph/topology/{graph_id}` — topology + models + prompts

**Показываем всё:**
- Узлы с названием агента и моделью (badge)
- Связи (обычные и conditional с label)
- По клику на узел: system prompt, параметры, fallback model
- Текущий статус (цвет)

**Сложность: 3/10 | 2-3 дня**

---

### 12.7 Telegram-интерфейс

**Файлы:**
- Новая директория: `telegram/`
- `telegram/bot.py`, `telegram/handlers.py`, `telegram/aegra_client.py`
- `telegram/Dockerfile`
- `docker-compose.yml` — новый сервис

**Сложность: 4/10 | 3-5 дней**

---

### 12.8 Аутентификация (Gateway)

**Файлы:**
- Новая директория: `gateway/`
- `gateway/main.py`, `gateway/auth.py`, `gateway/proxy.py`, `gateway/config.py`
- `gateway/endpoints/graph.py`
- `gateway/Dockerfile`
- `docker-compose.yml` — новый сервис gateway, убрать порт у aegra
- `frontend/src/api/aegra.ts` — JWT headers, VITE_API_URL → gateway
- Новые: `frontend/src/pages/Login.tsx`, `frontend/src/pages/Register.tsx`
- `frontend/src/App.tsx` — protected routes

**Сложность: 4/10 | 2-3 дня**

---

### 12.9 Langfuse integration fix

**Файлы:**
- `graphs/dev_team/agents/base.py` — `_invoke_chain()` method
- Все агенты — добавить `config: RunnableConfig` параметр, передавать callbacks
- `docker-compose.yml` / `.env` — `LANGFUSE_ENABLED=true`

**Сложность: 2/10 | 0.5-1 день**

---

### 12.10 Мульти-граф основа (manifest.yaml)

**Файлы:**
- Новый: `graphs/dev_team/manifest.yaml`
- `aegra.json` — подготовить к нескольким графам
- Gateway: `GET /graph/list` — список графов из manifest-ов

```yaml
# graphs/dev_team/manifest.yaml
name: "dev_team"
display_name: "Development Team"
description: "Full software development flow: from requirements to PR"
version: "1.0"
task_types: ["new_project", "feature", "bugfix", "refactor"]
agents:
  - id: pm
    display_name: "Project Manager"
  - id: analyst
    display_name: "Business Analyst"
  - id: architect
    display_name: "Software Architect"
  - id: developer
    display_name: "Developer"
  - id: qa
    display_name: "QA Engineer"
features:
  - hitl_clarification
  - qa_escalation
  - git_commit
parameters:
  max_qa_iterations: 3
  use_security_agent: false
  deploy_after_commit: false
```

**Сложность: 1/10 | 0.5 дня**

---

## 13. Волна 2: Среднее {#13-волна-2}

**Общая оценка: 15-25 дней** при частичной параллелизации.

### 13.1 Code Execution Sandbox

Описан в EVOLUTION_PLAN_V2 (секция 8.1). Без изменений.

**Файлы:**
- Новая директория: `sandbox/`
- `sandbox/server.py`, `sandbox/Dockerfile`
- Новый: `graphs/dev_team/tools/sandbox.py`
- `graphs/dev_team/graph.py` — node `sandbox_check`
- `docker-compose.yml` — сервис sandbox

**Сложность: 6/10 | 3-5 дней**

---

### 13.2 VPS Deploy + CI/CD (DevOps Agent)

**Файлы:**
- Новый: `graphs/dev_team/agents/devops.py`
- Новый: `graphs/dev_team/prompts/devops.yaml`
- Новый: `graphs/dev_team/tools/github_actions.py`
- `graphs/dev_team/graph.py` — node devops_agent
- `graphs/dev_team/state.py` — `deploy_url`, `infra_files`

**DevOps Agent генерирует для проекта:**
1. `Dockerfile`
2. `docker-compose.yml` (для деплоя)
3. `.github/workflows/deploy.yml` (CI/CD)
4. Traefik labels для nip.io домена
5. `.pre-commit-config.yaml` с линтерами
6. Branch protection rules (через GitHub API)

**Сложность: 7/10 | 5-10 дней**

---

### 13.3 CLI-агенты

Описан в секции 9 выше.

**Файлы:**
- Новый: `graphs/dev_team/agents/cli_agent.py`
- Новый: `graphs/dev_team/tools/cli_runner.py`
- Новая директория: `cli_runner/` (для VPS)
- `graphs/dev_team/graph.py` — node + conditional edge

**Сложность: 6/10 | 3-7 дней** (без настройки VPS)

---

### 13.4 Git-based передача кода

Описан в секции 10 выше.

**Файлы:**
- Новый: `graphs/dev_team/tools/git_workspace.py`
- `graphs/dev_team/state.py` — новые поля
- Все агенты — адаптация к git-based workflow
- `graphs/dev_team/graph.py` — git_commit_node упрощение

**Сложность: 5/10 | 3-5 дней**

---

### 13.5 Switch-Agent (API-level Router)

Описан в секции 5 выше.

**Файлы:**
- `gateway/router.py` — `classify_task()`
- `gateway/endpoints/graph.py` — `GET /graph/list`
- `frontend/src/components/TaskForm.tsx` — выбор графа
- `aegra.json` — несколько графов (когда появятся)

**Сложность: 4/10 | 2-3 дня**

---

### 13.6 Security Agent

**Два режима:**
- `security_static_review` — после Developer (SAST, secrets, deps)
- `security_runtime_check` — после Deploy (HTTPS, headers, image scan)

**Файлы:**
- Новый: `graphs/dev_team/agents/security.py`
- Новый: `graphs/dev_team/prompts/security.yaml`
- `graphs/dev_team/graph.py` — node(s) в соответствующих местах

**Сложность: 4/10 | 2-3 дня**

---

## 14. Волна 3: Сложное (отложено) {#14-волна-3}

### Отложенные задачи

| Задача | Почему отложена | Когда вернуться |
|--------|----------------|-----------------|
| Visual Graph Editor | Сложно (14-21 день), нет юзкейса | Когда появятся non-dev пользователи |
| Self-Improvement Loop | Дорого, нужен eval harness | После 50+ flow в Langfuse |
| Анализ прошлых flow (Meta-Agent) | Нужны данные | После 50+ flow |
| Prompt Optimization (DSPy) | Зависит от Meta-Agent | После Meta-Agent |
| Динамическая генерация графов | Сложно, не ясен ROI | Если понадобится |
| Graph Evolution (EvoAgentX) | R&D, далёкое будущее | Может никогда |

### Что заложено в архитектуре для будущего

- **Langfuse** сохраняет все flow → данные для Meta-Agent
- **manifest.yaml** → метаданные для UI и будущего Editor
- **`to_json()`** → структура графа доступна в JSON
- **Python-first** → CLI-агенты и LLM могут модифицировать графы
- **Gateway** → можно добавить любые endpoints
- **pgvector** в PostgreSQL → готов для vector memory

---

## 15. Целевая архитектура {#15-целевая-архитектура}

### После Волны 1

```
┌─────────────────────────────────────────────────────┐
│                    Пользователи                       │
│  Web UI (:5173)          Telegram Bot                 │
│  ├── Login/Register      ├── /task, /status           │
│  ├── Создать задачу      └── HITL ответы              │
│  ├── Выбор графа                                      │
│  ├── Chat + Streaming                                 │
│  ├── Визуализация графа (React Flow)                  │
│  └── Langfuse link                                    │
└────────────────┬──────────────────────────────────────┘
                 │
        ┌────────▼────────┐
        │   Gateway :8081 │  ← JWT auth, router, graph endpoints
        └────────┬────────┘
                 │
        ┌────────▼────────┐
        │  Aegra :8000    │  ← Внутренняя сеть, no auth
        │  (LangGraph)    │
        └────────┬────────┘
                 │
        ┌────────▼────────┐
        │    dev_team      │  ← Единственный граф (пока)
        │  PM→Analyst→...  │
        │  + retry/fallback│
        │  + structlog     │
        │  + web tools     │
        └────────┬────────┘
                 │
    ┌────────────┼────────────┐
    ▼            ▼            ▼
  LLM API    GitHub API   Langfuse (:3001)
  (proxy)                  (traces + costs)
                 │
        ┌────────▼────────┐
        │   PostgreSQL     │  ← Checkpoints, users, pgvector
        │   :5433          │
        └─────────────────┘
```

### После Волны 2

```
┌──────────────────────────────────────────────────────────────────┐
│                      Пользователи                                  │
│    Web UI (:5173)       Telegram (:polling)      API (:8081)       │
└──────┬──────────────────────┬──────────────────────┬──────────────┘
       │                      │                      │
       └──────────────────────┼──────────────────────┘
                              │
               ┌──────────────▼──────────────┐
               │   Gateway :8081             │
               │   ├── JWT auth              │
               │   ├── Switch-Agent/Router   │
               │   ├── /graph/* endpoints    │
               │   └── proxy → Aegra         │
               └──────────────┬──────────────┘
                              │
               ┌──────────────▼──────────────┐
               │   Aegra :8000 (внутренний)  │
               └──────────────┬──────────────┘
                              │
              ┌───────────────┼───────────────────┐
              ▼               ▼                   ▼
       ┌────────────┐  ┌────────────┐  ┌──────────────────┐
       │ dev_team   │  │ research   │  │ Новые flow       │
       │            │  │ _team      │  │                  │
       │ PM→Analyst │  │ Coord→     │  │ devops_only      │
       │ →Architect │  │ Researcher │  │ content          │
       │ →Dev/CLI   │  │ →Writer    │  │ ...              │
       │ →Security  │  │ →Editor    │  │                  │
       │ →QA        │  │            │  │                  │
       │ →DevOps    │  │            │  │                  │
       └─────┬──────┘  └──────┬────┘  └────────┬─────────┘
             │                │                 │
             └────────────────┼─────────────────┘
                              │
      ┌───────┬───────────────┼───────────┬──────────────┐
      ▼       ▼               ▼           ▼              ▼
  ┌───────┐ ┌──────┐ ┌──────────┐ ┌────────┐ ┌──────────────┐
  │ LLM   │ │GitHub│ │  Web     │ │Sandbox │ │CLI Runner    │
  │ API   │ │ API  │ │  Search  │ │(DinD)  │ │(отдельн. VPS)│
  └───────┘ └──┬───┘ └──────────┘ └────────┘ └──────────────┘
               │
      ┌────────▼────────┐
      │  GitHub Actions  │───────► VPS (deploy)
      │  CI/CD           │         Traefik + nip.io
      └─────────────────┘

  ┌─────────────────────────────────────────────────┐
  │                 Data Layer                        │
  │  PostgreSQL + pgvector (:5433)                   │
  │  Langfuse (:3001) — traces, costs, flow history  │
  │  structlog → JSON (→ Loki если нужно)            │
  └─────────────────────────────────────────────────┘
```

### Docker Compose (целевой после Волны 2)

```yaml
version: "3.8"

services:
  # === Core ===
  postgres:
    image: pgvector/pgvector:pg16
    ports: ["${POSTGRES_PORT:-5433}:5433"]
    volumes: [postgres_data:/var/lib/postgresql/data]
    healthcheck: ...

  aegra:
    build: .
    expose: ["8000"]  # Только внутренняя сеть!
    depends_on: [postgres]
    environment:
      AUTH_TYPE: noop
      DATABASE_URL: postgresql+asyncpg://...@postgres:5433/aicrew
      LANGFUSE_ENABLED: "true"
      LANGFUSE_HOST: http://langfuse:3001
      # LLM, GitHub, etc.

  gateway:
    build: ./gateway
    ports: ["8081:8081"]  # Единственный API-порт наружу
    depends_on: [aegra, postgres]
    environment:
      AEGRA_URL: http://aegra:8000
      DATABASE_URL: postgresql://...@postgres:5433/aicrew
      JWT_SECRET: ${JWT_SECRET}

  frontend:
    build: ./frontend
    ports: ["5173:5173"]
    environment:
      VITE_API_URL: ${GATEWAY_URL:-http://localhost:8081}

  # === Observability ===
  langfuse:
    image: langfuse/langfuse:latest
    ports: ["3001:3001"]
    depends_on: [postgres]
    environment:
      DATABASE_URL: postgresql://...@postgres:5433/aicrew
      NEXTAUTH_SECRET: ${LANGFUSE_NEXTAUTH_SECRET}

  # === Execution ===
  sandbox:
    build: ./sandbox
    privileged: true
    volumes: [sandbox_workspace:/workspace]
    # Нет портов наружу

  # === Interfaces ===
  telegram:
    build: ./telegram
    environment:
      TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN}
      GATEWAY_URL: http://gateway:8081
    depends_on: [gateway]
    # Нет портов наружу (polling)

volumes:
  postgres_data:
  sandbox_workspace:

networks:
  default:
    name: aicrew-network
```

---

## 16. Файлы для создания/изменения (чеклист) {#16-чеклист}

### Волна 1 — Новые файлы

```
config/
└── agents.yaml                        # LLM конфигурация

gateway/
├── main.py                            # FastAPI gateway
├── auth.py                            # JWT auth
├── proxy.py                           # Прокси к Aegra
├── router.py                          # Switch-Agent
├── config.py                          # Settings
├── models.py                          # Pydantic models
├── endpoints/
│   └── graph.py                       # /graph/topology, /graph/list
├── Dockerfile
└── requirements.txt

graphs/dev_team/
├── manifest.yaml                      # Метаданные графа
├── logging_config.py                  # structlog config
└── tools/
    └── web.py                         # Web search, fetch, download

telegram/
├── bot.py                             # aiogram bot
├── handlers.py                        # Обработчики команд
├── aegra_client.py                    # HTTP клиент к Gateway
├── Dockerfile
└── requirements.txt

frontend/src/
├── components/
│   └── GraphVisualization.tsx         # React Flow визуализация
├── hooks/
│   └── useStreamingTask.ts            # SSE streaming hook
└── pages/
    ├── Login.tsx                       # Страница входа
    └── Register.tsx                    # Страница регистрации
```

### Волна 1 — Изменяемые файлы

```
graphs/dev_team/agents/base.py         # retry, fallback, structlog, LLM config, callbacks
graphs/dev_team/agents/pm.py           # structlog + config param + callbacks
graphs/dev_team/agents/analyst.py      # structlog + config param + callbacks
graphs/dev_team/agents/architect.py    # structlog + config param + callbacks
graphs/dev_team/agents/developer.py    # structlog + config param + callbacks
graphs/dev_team/agents/qa.py           # structlog + config param + callbacks
graphs/dev_team/graph.py               # structlog, configure_logging → новый
graphs/dev_team/state.py               # task_type, task_complexity

docker-compose.yml                     # + gateway, telegram; aegra: expose only
aegra.json                             # CORS → gateway port
requirements.txt                       # + structlog, tenacity, httpx, trafilatura, duckduckgo-search

frontend/package.json                  # + @xyflow/react, dagre
frontend/src/api/aegra.ts              # JWT headers, VITE_API_URL → gateway
frontend/src/App.tsx                   # Protected routes
frontend/src/components/TaskForm.tsx   # Выбор графа
frontend/src/pages/TaskDetail.tsx      # + GraphVisualization
frontend/src/pages/Home.tsx            # Redirect if not logged in
```

### Волна 2 — Новые файлы

```
sandbox/
├── server.py
└── Dockerfile

graphs/dev_team/agents/
├── devops.py                          # DevOps Agent
├── security.py                        # Security Agent
└── cli_agent.py                       # CLI Agent node

graphs/dev_team/prompts/
├── devops.yaml                        # DevOps промпты
└── security.yaml                      # Security промпты

graphs/dev_team/tools/
├── git_workspace.py                   # Git-based code operations
├── github_actions.py                  # CI/CD management
├── sandbox.py                         # Sandbox client
└── cli_runner.py                      # CLI runner client

cli_runner/                            # Для отдельной VPS
├── server.py
├── Dockerfile
└── requirements.txt

config/linters/                        # Конфигурации линтеров
├── python.yaml
├── javascript.yaml
└── typescript.yaml
```

---

## 17. Порядок реализации (day-by-day) {#17-порядок}

### Волна 1: План на 8-12 дней

```
День 1-2: Фундамент (параллельно)
├── [P] structlog + configure_logging()        (0.5-1 день)
├── [P] config/agents.yaml + load_agent_config  (0.5-1 день)
├── [P] retry + fallback в base.py              (0.5 дня)
├── [P] Langfuse fix (callbacks в агентах)       (0.5 дня)
└── [P] manifest.yaml для dev_team              (0.5 дня)

День 3-4: Gateway + Auth (последовательно)
├── [S] Gateway: FastAPI + proxy к Aegra         (1 день)
├── [S] Gateway: JWT auth (register/login)       (1 день)
└── [S] docker-compose: gateway, порты           (0.5 дня)

День 5-6: Frontend (параллельно)
├── [P] Login/Register страницы                  (1 день)
├── [P] JWT в AegraClient                        (0.5 дня)
├── [P] GraphVisualization (React Flow)          (1-2 дня)
└── [P] Streaming hook                           (1 день)

День 7-8: Web tools + Gateway endpoints
├── [P] tools/web.py (search, fetch, download)   (1 день)
├── [P] Gateway: /graph/topology endpoint        (0.5 дня)
├── [P] Gateway: /graph/list endpoint            (0.5 дня)
└── [P] Фронт: выбор графа в TaskForm            (0.5 дня)

День 9-12: Telegram
├── [S] Telegram bot: базовая структура          (1 день)
├── [S] Handlers: /task, /status, /help          (1 день)
├── [S] HITL через Telegram                       (1 день)
└── [S] Docker + тестирование                     (1 день)
```

### Волна 2: План на 15-25 дней

```
День 1-5: Git-based + Switch-Agent
├── [S] tools/git_workspace.py                   (2 дня)
├── [S] Адаптация агентов к git-based            (2 дня)
├── [P] Gateway: router.py (classify_task)        (1 день)
└── [P] Фронт: выбор авто/ручной                 (0.5 дня)

День 6-10: Sandbox + Security
├── [S] Sandbox service                           (3 дня)
├── [S] tools/sandbox.py + sandbox_check node     (1 день)
├── [P] Security Agent                            (2 дня)

День 11-20: DevOps + CLI
├── [S] DevOps Agent + prompts                    (3-5 дней)
├── [S] tools/github_actions.py                   (2 дня)
├── [S] CLI Runner (API wrapper)                  (2-3 дня)
├── [S] CLI Agent node в графе                    (1-2 дня)
└── [S] Линтеры в CI pipeline                     (1 день)

День 21-25: Интеграция + тестирование
├── [ ] Интеграция всех компонентов               (2 дня)
├── [ ] Тестирование e2e                          (2 дня)
└── [ ] Документация                               (1 день)
```

### Матрица зависимостей (обновлённая)

```
                   Зависит от:
Задача             │ structlog │ LLM cfg │ Gateway │ Git-based │ Sandbox │
───────────────────┼───────────┼─────────┼─────────┼───────────┼─────────┤
Retry              │           │    ~    │         │           │         │
structlog          │           │         │         │           │         │
LLM config         │           │         │         │           │         │
Langfuse fix       │     ~     │         │         │           │         │
Streaming          │           │         │    ~    │           │         │
Web tools          │     ~     │         │         │           │         │
Graph viz          │           │         │    ✓    │           │         │
Auth               │           │         │  (=)    │           │         │
Telegram           │           │         │    ✓    │           │         │
manifest.yaml      │           │         │         │           │         │
───────────────────┼───────────┼─────────┼─────────┼───────────┼─────────┤
Git-based code     │     ~     │         │         │           │         │
Switch-Agent       │           │    ~    │    ✓    │           │         │
Sandbox            │     ~     │         │         │     ~     │         │
CLI-агенты         │     ~     │         │         │     ✓     │    ~    │
DevOps Agent       │     ~     │    ~    │         │     ✓     │    ~    │
Security Agent     │     ~     │         │         │     ~     │    ~    │

✓ = жёсткая зависимость
~ = желательно сделать раньше
(=) = это одна задача (Gateway = Auth)
```

---

## Приложение A: Закрытые вопросы (из V2)

| Вопрос | Ответ |
|--------|-------|
| VPS для CLI-агентов | Отдельный от VPS для деплоя |
| Aegra и мульти-граф | Работает. `assistant_id` = graph name или UUID |
| State sharing subgraphs | Не нужен. Разные команды для разных проектов |
| CLI-агент лицензии | Считаем дорогим. Не парюсь |
| nip.io + HTTPS | Работает с Traefik + Let's Encrypt |
| Aegra gateway vs модификация | Gateway. Модифицировать — если gateway недостаточно |
| Локальные файлы для CLI | Не нужны. CLI подключается к Git напрямую |
| Visual Graph Editor | Отложен в долгий ящик |
| Self-Improvement | Отложен. Но flow сохраняем через Langfuse |

## Приложение B: Env-переменные (итоговый список)

```bash
# === LLM ===
LLM_API_URL=https://clipapi4me.31.59.58.143.nip.io/v1
LLM_API_KEY=your-key
LLM_BACKUP_URL=                     # Резервный endpoint
LLM_BACKUP_KEY=

# === Database ===
POSTGRES_USER=aicrew
POSTGRES_PASSWORD=strong-password
POSTGRES_DB=aicrew
POSTGRES_PORT=5433

# === Gateway ===
JWT_SECRET=your-jwt-secret-32chars
GATEWAY_URL=http://localhost:8081    # Для фронтенда

# === GitHub ===
GITHUB_TOKEN=ghp_xxx
GITHUB_DEFAULT_REPO=

# === Langfuse ===
LANGFUSE_ENABLED=true
LANGFUSE_SECRET_KEY=sk-xxx
LANGFUSE_PUBLIC_KEY=pk-xxx
LANGFUSE_NEXTAUTH_SECRET=secret
LANGFUSE_SALT=salt

# === Telegram ===
TELEGRAM_BOT_TOKEN=123456:ABC-DEF

# === Web Search ===
SEARCH_API_URL=                      # Пусто = DuckDuckGo

# === CLI Runner (на отдельной VPS) ===
CLI_RUNNER_URL=http://cli-vps:8001

# === Logging ===
LOG_LEVEL=DEBUG
ENV_MODE=LOCAL                       # LOCAL | PRODUCTION
```
