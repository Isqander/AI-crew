# История изменений

## [0.2.0] - 2026-01-20

### 🔧 Исправлено
1. **Dockerfile** - Исправлена команда запуска Aegra сервера
   - Было: `CMD ["python", "-m", "agent_server.main"]`
   - Стало: `CMD ["aegra", "start", "--config", "/app/aegra.json"]`

2. **PostgreSQL Checkpointer** - Заменён MemorySaver на PostgresSaver
   - Файл: `graphs/dev_team/graph.py`
   - Теперь состояния сохраняются в PostgreSQL и не теряются при перезапуске
   - Автоматический fallback на MemorySaver если DATABASE_URL не указан

3. **TypedDict с Optional полями** - Исправлена типизация
   - Файл: `graphs/dev_team/state.py`
   - Использован `NotRequired` вместо `Optional` для TypedDict
   - Добавлена поддержка Python 3.9-3.10 через typing_extensions

### ✅ Добавлено
- **Полное покрытие тестами** (49 тестов)
  - `tests/test_state.py` - тесты структуры состояния
  - `tests/test_agents.py` - тесты всех агентов
  - `tests/test_graph.py` - тесты графа и роутинга
  - `tests/test_tools.py` - тесты инструментов
  - `tests/test_integration.py` - интеграционные тесты

- **Документация**
  - `docs/GETTING_STARTED.md` - быстрый старт
  - `docs/TESTING.md` - руководство по тестированию
  - `docs/DEVELOPMENT.md` - руководство разработчика
  - `docs/IDEAS.md` - идеи для развития
  - `docs/CHANGELOG.md` - история изменений

- **Зависимости**
  - Добавлен `typing-extensions>=4.7.0` для поддержки NotRequired

### 📝 Документация
- Создана полная документация по проекту
- Добавлены инструкции по запуску и тестированию
- Описаны возможности кастомизации агентов и промптов
- Задокументированы идеи для развития

---

## [0.1.0] - Начальная версия

### ✨ Возможности
- Мультиагентная система разработки на базе LangGraph
- 5 агентов: PM, Analyst, Architect, Developer, QA
- Human-in-the-Loop для уточняющих вопросов
- Интеграция с GitHub (создание PR, коммиты)
- Web UI на React + TypeScript
- Aegra сервер для API
- PostgreSQL для хранения состояний
- Langfuse для observability
- Docker Compose для развёртывания
