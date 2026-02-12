# Развёртывание AI-crew

Два режима развёртывания:

| Режим | Что запускается | Когда использовать |
|-------|----------------|--------------------|
| **Dockerfile** (production) | Один контейнер: Aegra API (8000) + Frontend/nginx (5173) + Langfuse (3001) + PostgreSQL | VPS / Dokploy / одноконтейнерный хостинг |
| **docker-compose** (development) | Отдельные контейнеры: postgres, aegra, frontend (Vite dev), langfuse | Локальная разработка |

---

## 1. Production — единый контейнер (Dockerfile)

### Архитектура

```
┌─────────────────────────────────────────────┐
│  Container                                  │
│                                             │
│  supervisord                                │
│  ├── aegra    (python)       → :8000        │
│  ├── nginx    (frontend)     → :5173        │
│  └── langfuse (node, опц.)   → :3001        │
│                                             │
│  postgresql (embedded)       → :5433 (lo)   │
└─────────────────────────────────────────────┘
```

### Сборка

```bash
docker build -t aicrew .
```

Build-аргументы (опционально):

| Аргумент | По умолчанию | Описание |
|----------|-------------|----------|
| `VITE_API_URL` | `/api` | API base для фронтенда. `/api` → nginx проксирует на Aegra |
| `AEGRA_PIP_SOURCE` | *(пусто)* | Альтернативный pip source для Aegra |

### Запуск

```bash
docker run -d \
  -p 8000:8000 \
  -p 5173:5173 \
  -p 3001:3001 \
  -v aicrew_pgdata:/var/lib/postgresql/data \
  --env-file .env \
  aicrew
```

### Обязательные переменные окружения

| Переменная | Описание |
|-----------|----------|
| `LLM_API_KEY` | Ключ LLM API (обязателен для Aegra) |

### Рекомендуемые переменные

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `SERVER_URL` | `http://localhost:8000` | Публичный URL API |
| `LLM_API_URL` | *(из кода)* | Endpoint LLM |
| `LOG_LEVEL` | `INFO` | Уровень логирования |
| `ENV_MODE` | `LOCAL` | `LOCAL` / `PROD` |
| `AEGRA_CONFIG` | `/app/aegra.prod.json` | Путь к конфигу Aegra |

### Langfuse v2 (опционально)

> **Важно**: В контейнере используется **Langfuse v2**, которая работает только
> с PostgreSQL. Langfuse v3+ требует ClickHouse, Redis и S3 — слишком тяжело
> для single-container деплоя. Python SDK v3.x обратно совместим с сервером v2.

Для включения встроенного Langfuse-сервера:

```bash
LANGFUSE_ENABLED=true
LANGFUSE_NEXTAUTH_SECRET=your-strong-secret          # openssl rand -base64 32
LANGFUSE_SALT=your-strong-salt                        # openssl rand -base64 32
LANGFUSE_ENCRYPTION_KEY=<64-hex-chars>                # openssl rand -hex 32
LANGFUSE_NEXTAUTH_URL=https://ai-crew-langfuse.example.com
```

Если `LANGFUSE_ENABLED=false` (по умолчанию), процесс Langfuse не запускается,
порт 3001 свободен.

Для *клиента* Langfuse (трассировка из Aegra):

```bash
LANGFUSE_LOGGING=true
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_HOST=http://localhost:3001   # или внешний URL
```

### База данных

По умолчанию PostgreSQL запускается **внутри контейнера**
(`POSTGRES_HOST=127.0.0.1`). Для сохранения данных подключите volume
на `/var/lib/postgresql/data`.

Для внешнего Postgres — установите `POSTGRES_HOST` и `POSTGRES_PORT`:

```bash
POSTGRES_HOST=your-db-host
POSTGRES_PORT=5433
```

### CORS

`aegra.prod.json` разрешает `allow_origins: ["*"]` с `allow_credentials: false`.
Для ограничения замените на конкретные домены.

### Health Check

Контейнер проверяет:
- `GET http://localhost:8000/health` (Aegra API)
- `GET http://localhost:5173/` (Frontend/nginx)

---

## 2. Development — docker-compose

```bash
# Все сервисы
docker-compose up -d

# Только backend + DB
docker-compose up -d aegra

# Логи
docker-compose logs -f aegra
docker-compose logs -f langfuse

# Остановка
docker-compose down
```

Сервисы:

| Сервис | Порт | Описание |
|--------|------|----------|
| `postgres` | 5433 | PostgreSQL 16 + pgvector |
| `aegra` | 8000 | Aegra API |
| `frontend` | 5173 | Vite dev server (hot reload) |
| `langfuse` | 3001 | Langfuse (official image) |

### Переменные окружения

Создайте `.env` из `env.example`:

```bash
cp env.example .env
# Заполните LLM_API_KEY и остальные значения
```

---

## 3. Пример переменных для Dokploy (production)

```bash
# --- Обязательные ---
LLM_API_KEY=your-key
LLM_API_URL=https://your-llm-proxy/v1

# --- Aegra ---
AEGRA_CONFIG=/app/aegra.prod.json
SERVER_URL=https://ai-crew-aegra.example.com
LOG_LEVEL=INFO
ENV_MODE=PROD

# --- Database ---
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5433
POSTGRES_DB=aicrew
POSTGRES_USER=aicrew
POSTGRES_PASSWORD=strong-password

# --- Langfuse v2 (сервер) ---
LANGFUSE_ENABLED=true
LANGFUSE_NEXTAUTH_SECRET=random-secret-32chars
LANGFUSE_SALT=random-salt-32chars
LANGFUSE_ENCRYPTION_KEY=<openssl rand -hex 32>
LANGFUSE_NEXTAUTH_URL=https://ai-crew-langfuse.example.com

# --- Langfuse (клиент/трассировка) ---
LANGFUSE_LOGGING=true
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_HOST=http://127.0.0.1:3001
```

### Volumes (если Postgres внутри контейнера)

| Путь в контейнере | Volume |
|-------------------|--------|
| `/var/lib/postgresql/data` | `aicrew_pgdata` |

---

## 4. Traefik / Dokploy маршрутизация

| Домен | Порт контейнера | Сервис |
|-------|----------------|--------|
| `ai-crew-aegra.*.nip.io` | 8000 | Aegra API |
| `ai-crew-front.*.nip.io` | 5173 | Frontend (nginx) |
| `ai-crew-langfuse.*.nip.io` | 3001 | Langfuse |

Все три порта обслуживаются **одним контейнером** через supervisord.

---

## 5. Источник установки Aegra

В PyPI пакета `aegra` нет. Два рабочих варианта:

1. **vendor/aegra** — исходники в репозитории (текущий вариант)
2. **Build-arg** — альтернативный pip source:

```bash
docker build --build-arg AEGRA_PIP_SOURCE=git+https://github.com/ibbybuilds/aegra.git -t aicrew .
```
