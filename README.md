# 🤖 AI-crew

**Мультиагентная платформа разработки на базе LangGraph**

AI-crew — это self-hosted система, где команда ИИ-агентов (Менеджер, Аналитик, Архитектор, Разработчик, QA) совместно создают приложения от требований до готового кода с pull request.

---

## ✨ Возможности

- 🧠 **5 специализированных агентов** работают как настоящая команда
- 🔄 **Human-in-the-Loop** - агенты задают уточняющие вопросы
- 📝 **От идеи до кода** - полный цикл разработки
- 🔗 **GitHub интеграция** - автоматическое создание PR
- 🎨 **Modern Web UI** - React интерфейс для управления задачами
- 📊 **Observability** - трейсинг через Langfuse
- 🐳 **Docker ready** - простое развёртывание
- 🧪 **Полное покрытие тестами** - 49 автоматических тестов

---

## 🏗 Архитектура

```
┌─────────────┐
│   Browser   │ ← Web UI для создания задач
└──────┬──────┘
       │
┌──────▼──────┐
│  React UI   │
└──────┬──────┘
       │ REST API
┌──────▼──────┐
│ Aegra Server│ ← LangGraph Platform
└──────┬──────┘
       │
┌──────▼──────────────────────────┐
│   LangGraph Agent Workflow      │
│                                  │
│  ┌────┐  ┌────────┐  ┌────────┐│
│  │ PM │─→│Analyst │─→│Architect││
│  └────┘  └────────┘  └────────┘│
│                ↓                 │
│  ┌─────────┐  ┌────┐  ┌────┐  │
│  │Developer│→│ QA │→│Git │  │
│  └─────────┘  └────┘  └────┘  │
└─────────────────────────────────┘
       │
┌──────▼──────┐   ┌─────────┐
│ PostgreSQL  │   │Langfuse │
│ (States)    │   │(Monitor)│
└─────────────┘   └─────────┘
```

### Агенты:

| Агент | Роль | LLM |
|-------|------|-----|
| 👔 **PM** | Декомпозиция задач, координация | GPT-4o |
| 📊 **Analyst** | Сбор требований, user stories | Claude 3.5 Sonnet |
| 🏛 **Architect** | Проектирование архитектуры | Claude 3.5 Sonnet |
| 💻 **Developer** | Написание кода | GPT-4o |
| 🧪 **QA** | Code review, тестирование | GPT-4o-mini |

---

## 🚀 Быстрый старт

### Требования

- Docker & Docker Compose
- Node.js 18+ (для frontend)
- API ключи: OpenAI, Anthropic (опционально)

### Установка

```bash
# 1. Клонировать репозиторий
cd AI-crew

# 2. Создать .env из примера
cp env.example .env

# 3. Добавить API ключи в .env
# OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...

# 4. Запустить все сервисы
docker-compose up -d

# 5. Запустить frontend
cd frontend && npm install && npm run dev
```

### Проверка

- **Aegra API**: http://localhost:8000/docs
- **Langfuse**: http://localhost:3000
- **Frontend**: http://localhost:5173

### Первая задача

1. Откройте http://localhost:5173
2. Введите задачу:
   ```
   Create a REST API for managing TODO items with CRUD endpoints
   ```
3. Нажмите "Запустить"
4. Наблюдайте за работой агентов в реальном времени!

---

## 📚 Документация

### Для пользователей:
- **[Быстрый старт](docs/GETTING_STARTED.md)** ⭐ - Установка и запуск за 10 минут
- **[Архитектура](docs/architecture.md)** - Детальное описание системы
- **[История изменений](docs/CHANGELOG.md)** - Что нового в проекте

### Для разработчиков:
- **[Руководство разработчика](docs/DEVELOPMENT.md)** ⭐ - Как кастомизировать агентов
- **[Тестирование](docs/TESTING.md)** - Как запускать и писать тесты
- **[Идеи для развития](docs/IDEAS.md)** - Roadmap и возможности

---

## 🛠 Стек технологий

| Компонент | Технология |
|-----------|-----------|
| Оркестрация агентов | **LangGraph** |
| Backend/API | **Aegra** (FastAPI) |
| База данных | **PostgreSQL** |
| Observability | **Langfuse** |
| Web UI | **React** + TypeScript |
| LLM | OpenAI, Anthropic, Google |
| Деплой | **Docker Compose** |

---

## 🧪 Тестирование

Проект имеет полное покрытие тестами:

```bash
# Установить зависимости
pip install -r requirements.txt

# Запустить все тесты
pytest tests/ -v

# С отчётом о покрытии
pytest tests/ --cov=graphs --cov-report=html

# Открыть HTML отчёт
open htmlcov/index.html
```

**Статистика тестов:**
- ✅ 6 тестов структуры состояния
- ✅ 13 тестов агентов
- ✅ 12 тестов графа и роутинга
- ✅ 12 тестов инструментов
- ✅ 6 интеграционных тестов

**Всего: 49 тестов**

---

## 📖 Примеры использования

### Создать REST API

```
Task: Create a FastAPI REST API for managing blog posts with:
- GET /posts - list all posts
- POST /posts - create new post
- GET /posts/{id} - get post by ID
- PUT /posts/{id} - update post
- DELETE /posts/{id} - delete post

Use PostgreSQL for storage and add proper validation.
```

### Создать React компонент

```
Task: Create a reusable React component for a modal dialog with:
- Customizable title and content
- Close button and overlay
- Animations
- TypeScript types
- Full accessibility support
```

### Рефакторинг кода

```
Task: Refactor the authentication module to use JWT tokens instead of sessions.
Repository: owner/my-app

Context: Current implementation uses session-based auth.
Need to migrate to JWT for stateless authentication.
```

---

## 🎯 Human-in-the-Loop

Агенты могут задавать уточняющие вопросы:

```
Аналитик: "Какую базу данных использовать: PostgreSQL или MongoDB?"
Архитектор: "Нужна ли аутентификация пользователей?"
```

Вы отвечаете через UI, и агенты продолжают работу с учётом ваших ответов.

---

## 🔧 Кастомизация

### Изменить промпты агентов

Промпты находятся в `graphs/dev_team/prompts/`:

```yaml
# graphs/dev_team/prompts/developer.yaml
system: |
  You are a Software Developer AI agent.
  
  Code Style:
  - Use TypeScript
  - Follow functional programming
  - Write comprehensive tests
```

### Изменить флоу агентов

Граф определяется в `graphs/dev_team/graph.py`:

```python
# Добавить нового агента
builder.add_node("security", security_agent)
builder.add_edge("qa", "security")
builder.add_edge("security", "git_commit")
```

### Создать нового агента

```python
# graphs/dev_team/agents/security.py
class SecurityAgent(BaseAgent):
    def __init__(self):
        prompts = load_prompts("security")
        llm = get_llm(provider="openai", model="gpt-4o")
        super().__init__(name="security", llm=llm, prompts=prompts)
```

Подробнее: [Руководство разработчика](docs/DEVELOPMENT.md)

---

## 💡 Roadmap

### ✅ Реализовано (v0.2.0)
- Мультиагентная система с 5 агентами
- Human-in-the-Loop
- GitHub интеграция
- Web UI
- PostgreSQL checkpointing
- Langfuse observability
- Полное покрытие тестами

### 🔜 В планах

**Короткосрочно (1-2 недели):**
- Retry логика для LLM вызовов
- Валидация входных данных
- Структурированное логирование

**Среднесрочно (1-2 месяца):**
- Code Execution Sandbox
- Vector Database для long-term memory
- Security Agent
- Template Library

**Долгосрочно (3-6 месяцев):**
- Интеграция с Jira/Linear
- Multi-repository support
- Visual Graph Editor
- Fine-tuned модели

Подробнее: [Идеи для развития](docs/IDEAS.md)

---

## 🤝 Участие в разработке

Мы приветствуем ваш вклад!

1. Fork репозиторий
2. Создайте feature branch (`git checkout -b feature/amazing-feature`)
3. Commit изменения (`git commit -m 'Add amazing feature'`)
4. Push в branch (`git push origin feature/amazing-feature`)
5. Создайте Pull Request

### Как помочь:

- 🐛 Сообщить о баге
- 💡 Предложить идею
- 📖 Улучшить документацию
- ✨ Реализовать новую функцию
- 🧪 Добавить тесты

---

## 📝 Лицензия

MIT License - свободно используйте в своих проектах.

---

## 🙏 Благодарности

Проект построен на плечах гигантов:

- [LangGraph](https://github.com/langchain-ai/langgraph) - оркестрация агентов
- [Aegra](https://github.com/ibbybuilds/aegra) - self-hosted LangGraph Platform
- [Langfuse](https://github.com/langfuse/langfuse) - observability
- [OpenAI](https://openai.com) & [Anthropic](https://anthropic.com) - LLM модели

---

## 📬 Контакты

- 📚 [Документация](docs/)
- 🐛 [Issues](https://github.com/your-repo/issues)
- 💬 [Discussions](https://github.com/your-repo/discussions)

---

<p align="center">
  Сделано с ❤️ и 🤖 AI
</p>

<p align="center">
  <strong>AI-crew v0.2.0</strong>
</p>
