# 🚀 Развёртывание на VPS (Dockerfile / Dockploy)

Ниже — минимальная инструкция для деплоя backend через `Dockerfile` в Dockploy
и запуск frontend отдельным сервисом.

---

## 1) Backend (Aegra API)

**Dockerfile:** `./Dockerfile`

### Обязательные переменные окружения

- `LLM_API_KEY` — ключ LLM (обязателен).

Остальные переменные имеют дефолты в образе и опциональны.

### Рекомендуемые переменные

- `SERVER_URL` — публичный URL API (например `https://api.example.com`)
- `LOG_LEVEL` — `INFO`/`DEBUG` и т.д.
- `ENV_MODE` — `LOCAL`/`PROD`
- `LLM_API_URL` — endpoint LLM (по умолчанию берётся из кода)
- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY` — опционально
- `AEGRA_CONFIG` — путь к конфигу внутри контейнера  
  По умолчанию: `/app/aegra.prod.json`.
- `LANGFUSE_ENABLED`, `LANGFUSE_LOGGING` — если используете Langfuse

### CORS для фронтенда

По умолчанию `aegra.json` разрешает только localhost.  
Для VPS используйте `aegra.prod.json` (уже в репозитории) или
замените `allow_origins` на ваш домен:

```json
"allow_origins": ["https://app.example.com"]
```

Если используете `allow_origins: ["*"]`, то `allow_credentials` должен быть `false`.

### База данных

При старте контейнер:

- создаёт `uuid-ossp` (нужно право на `CREATE EXTENSION`)
- создаёт таблицы через ORM (идемпотентно)

Если у пользователя БД нет прав на extension — добавьте его вручную.

По умолчанию Postgres запускается внутри контейнера
(`POSTGRES_HOST=127.0.0.1`). Если хотите внешний Postgres —
переопределите `POSTGRES_HOST` и `POSTGRES_PORT`.

---

## 2) Frontend

**Вариант 1 (быстрый):** `frontend/Dockerfile.dev`  
Подходит для тестового деплоя.  
Переменная окружения: `VITE_API_URL=https://api.example.com`

**Вариант 2 (production):** собрать `vite build` и отдавать статику через nginx.

---

## 3) Проверка

- API health: `GET /health`
- API docs: `GET /docs`
- Web UI: `http(s)://<your-domain>`

---

## 4) Пример переменных для Dockploy (backend)

```bash
AEGRA_CONFIG=/app/aegra.prod.json
LLM_API_KEY=your-key
POSTGRES_HOST=your-db-host
POSTGRES_PORT=5432
POSTGRES_DB=aicrew
POSTGRES_USER=aicrew
POSTGRES_PASSWORD=strong-password
LANGFUSE_LOGGING=false
SERVER_URL=https://api.example.com
LOG_LEVEL=INFO
LLM_API_URL=https://your-llm-proxy/v1
```

## 5) Volumes для Dockploy (если Postgres внутри контейнера)

Чтобы сохранять данные, добавьте volume на `PGDATA`:

- Путь в контейнере: `/var/lib/postgresql/data`
- Пример: `aicrew_pgdata:/var/lib/postgresql/data`

Если используете внешний Postgres, volume не нужен.

## 6) Источник установки Aegra (если GitHub недоступен)

В PyPI пакета `aegra` нет. Есть два рабочих варианта:

1) Положить исходники в репозиторий:
   - путь: `vendor/aegra`
   - можно оформить как git submodule или просто скопировать код

2) Передать альтернативный источник через build-arg:

```bash
AEGRA_PIP_SOURCE=git+https://github.com/ibbybuilds/aegra.git
```

Можно указать URL на wheel/архив из приватного репозитория.
