# Быстрый старт

Руководство по запуску AI-crew за 10 минут.

---

## Требования

- **Docker** и **Docker Compose** (v2.0+)
- **Node.js** 18+ (для frontend)
- **Python** 3.9+ (для локальной разработки)
- API ключи:
  - LLM API key (для прокси сервера)
  - GitHub Token (опционально, для создания PR)

---

## Шаг 1: Клонирование и настройка

```bash
# Клонировать репозиторий
cd AI-crew

# Создать .env файл из примера
cp env.example .env
```

## Шаг 2: Настройка переменных окружения

Отредактируйте `.env` и добавьте настройки LLM:

```bash
# === LLM API (обязательно) ===
LLM_API_URL=https://clipapi4me.31.59.58.143.nip.io/v1
LLM_API_KEY=your-api-key

# === Опционально ===
GITHUB_TOKEN=ghp_...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_PUBLIC_KEY=pk-lf-...
```

### Модели по умолчанию для агентов

Система использует OpenAI-совместимый прокси API с разными моделями для разных агентов:

| Агент | Модель по умолчанию        | Назначение |
|-------|----------------------------|------------|
| PM | claude-sonnet-4-5-thinking | Декомпозиция задач |
| Analyst | claude-sonnet-4-5-thinking | Сбор требований |
| Architect | claude-opus-4-6-thinking   | Проектирование архитектуры |
| Developer | gemini-3-pro-high          | Генерация кода |
| QA | gemini-3-flash-preview     | Ревью кода |

### Переопределение моделей

Можно переопределить модель для любого агента через переменные окружения:

```bash
LLM_MODEL_ARCHITECT=claude-opus-4-6-thinking
LLM_MODEL_DEVELOPER=gemini-3-pro-high
```

### Несколько API endpoints

Поддерживается несколько API endpoints с разными ключами:

```bash
# Основной endpoint
LLM_API_URL=https://clipapi4me.31.59.58.143.nip.io/v1
LLM_API_KEY=main-key

# Дополнительный endpoint "backup"
LLM_BACKUP_URL=https://other-api.example.com/v1
LLM_BACKUP_KEY=backup-key
```

### Доступные модели

- `claude-opus-4-6-thinking` - самая мощная, для сложных задач
- `claude-sonnet-4-5-thinking` - сбалансированная
- `gemini-3-pro-high` - хороша для генерации кода
- `gemini-3-flash-preview` - быстрая, для простых задач
- `glm-4.7` - альтернативная модель

### Где взять API ключи?

- **GitHub**: https://github.com/settings/tokens (нужны права: repo, write:packages)
- **Langfuse**: https://cloud.langfuse.com/ (или будет создан локально)

---

## Шаг 3: Запуск системы

### Вариант A: Docker Compose (рекомендуется)

```bash
# Запустить все сервисы (PostgreSQL, Aegra, Langfuse)
docker-compose up -d

# Проверить статус
docker-compose ps

# Посмотреть логи
docker-compose logs -f aegra
```

### Вариант B: Локальная разработка

```bash
# Установить зависимости
pip install -r requirements.txt

# Запустить PostgreSQL и Langfuse
docker-compose up -d postgres langfuse

# Установить Aegra
pip install git+https://github.com/ibbybuilds/aegra.git

# Запустить Aegra
aegra start --config aegra.json
```

---

## Шаг 4: Запуск Frontend

```bash
# Перейти в директорию frontend
cd frontend

# Установить зависимости
npm install

# Запустить dev сервер
npm run dev
```

Откройте http://localhost:5173 в браузере.

---

## Шаг 5: Проверка работоспособности

### Проверить endpoints:

1. **Aegra API**: http://localhost:8000/docs
   - Должен открыться Swagger UI с документацией API

2. **Langfuse**: http://localhost:3001
   - Интерфейс для мониторинга LLM вызовов
   - При первом запуске создайте аккаунт

3. **Frontend**: http://localhost:5173
   - Web UI для создания задач

### Создать тестовую задачу:

1. Откройте http://localhost:5173
2. Введите задачу, например:
   ```
   Create a simple REST API for managing TODO items with the following endpoints:
   - GET /todos - list all todos
   - POST /todos - create new todo
   - PUT /todos/:id - update todo
   - DELETE /todos/:id - delete todo
   ```
3. Нажмите "Запустить"
4. Наблюдайте за работой агентов в реальном времени

---

## Архитектура системы

```
┌─────────────┐
│   Browser   │ ← http://localhost:5173
└──────┬──────┘
       │
┌──────▼──────┐
│  React UI   │ (Frontend)
└──────┬──────┘
       │ REST API
┌──────▼──────┐
│ Aegra Server│ ← http://localhost:8000
└──────┬──────┘
       │
┌──────▼──────────────────┐
│   LangGraph Agents      │
│ ┌────┐ ┌────┐ ┌────┐   │
│ │ PM │→│Ana.│→│Arc.│   │
│ └────┘ └────┘ └────┘   │
│ ┌────┐ ┌────┐          │
│ │Dev.│→│ QA │          │
│ └────┘ └────┘          │
└─────────────────────────┘
       │
┌──────▼──────┐   ┌─────────┐
│ PostgreSQL  │   │Langfuse │
│ (States)    │   │(Monitor)│
└─────────────┘   └─────────┘
```

---

## Остановка системы

```bash
# Остановить все сервисы
docker-compose down

# Остановить и удалить данные
docker-compose down -v
```

---

## Следующие шаги

- [Архитектура](architecture_old.md) — как устроена система
- [Разработка](DEVELOPMENT.md) — как добавить агента, изменить промпты
- [Тестирование](TESTING.md) — как запускать и писать тесты
- [Развёртывание](deployment.md) — Docker Compose и Production

---

## Частые проблемы

### Ошибка: "Docker daemon is not running"
```bash
# Запустите Docker Desktop или Docker Engine
```

### Ошибка: "Port 8000 is already in use"
```bash
# Измените порт в docker-compose.yml
PORT=8001:8000
```

### Ошибка: "Invalid API key"
```bash
# Проверьте .env файл
cat .env | grep API_KEY
```

### Aegra не запускается
```bash
# Проверьте логи
docker-compose logs aegra

# Перезапустите
docker-compose restart aegra
```

### Frontend не подключается к API
```bash
# Проверьте VITE_API_URL в .env
VITE_API_URL=http://localhost:8000
```

---

## Получить помощь

- [Полная документация](architecture_old.md)
- [Руководство разработчика](DEVELOPMENT.md)
