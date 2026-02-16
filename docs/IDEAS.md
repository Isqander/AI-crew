# Roadmap и идеи для развития

---

## Короткосрочные улучшения (1-2 недели)

### 1. Retry логика для LLM вызовов
**Проблема:** Нет обработки ошибок API (rate limits, timeouts).

**Решение:**
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10)
)
def invoke_llm_with_retry(llm, prompt):
    return llm.invoke(prompt)
```

**Приоритет:** Высокий  
**Сложность:** Низкая

---

### 2. Валидация входных данных
**Проблема:** Нет проверки task description, repository URL.

**Решение:** Создать модуль `graphs/dev_team/validation.py`:
```python
def validate_task(task: str) -> None:
    if not task or len(task) < 10:
        raise ValidationError("Task too short")
    if len(task) > 5000:
        raise ValidationError("Task too long")

def validate_repository(repo: str) -> None:
    pattern = r'^[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+$'
    if not re.match(pattern, repo):
        raise ValidationError("Invalid repo format")
```

**Приоритет:** Высокий  
**Сложность:** Низкая

---

### 3. Структурированное логирование
**Проблема:** Сложно отлаживать без логов.

**Решение:**
```python
import structlog

logger = structlog.get_logger()

class BaseAgent:
    def invoke(self, state: dict) -> dict:
        logger.info("agent.invoke",
                   agent=self.name,
                   task_id=state.get("task_id"),
                   state_keys=list(state.keys()))
```

**Приоритет:** Средний  
**Сложность:** Низкая

---

### 4. Streaming в Frontend
**Проблема:** UI использует polling вместо streaming.

**Решение:** Использовать `aegraClient.streamRun()` в React:
```typescript
const { startTask, state, isStreaming } = useStreamingTask()

// Real-time updates
useEffect(() => {
  startTask(threadId, input)
}, [])
```

**Приоритет:** Средний  
**Сложность:** Средняя

---

### 5. Вынести конфигурацию LLM в файл
**Проблема:** Модели жестко закодированы в агентах.

**Решение:** Создать `config/agents.yaml`:
```yaml
agents:
  pm:
    provider: openai
    model: gpt-4o
    temperature: 0.7
```

**Приоритет:** Низкий  
**Сложность:** Низкая

---

## Среднесрочные функции (1-2 месяца)

### 6. Code Execution Sandbox
**Описание:** Безопасно запускать сгенерированный код для проверки.

**Возможности:**
- Запуск тестов в изолированной среде
- Проверка работоспособности кода
- Автоматическое исправление ошибок выполнения

**Технологии:**
- Docker containers для изоляции
- Timeout и resource limits
- Автоматический rollback при ошибках

**Приоритет:** Высокий  
**Сложность:** Высокая

---

### 7. Vector Database для Long-term Memory
**Описание:** Хранить историю задач и использовать для контекста.

**Возможности:**
- Поиск похожих задач из прошлого
- Переиспользование решений
- Обучение на собственном опыте

**Технологии:**
- pgvector (уже в docker-compose!)
- Embeddings через OpenAI/Cohere
- Semantic search

**Пример:**
```python
# Найти похожие задачи
similar_tasks = vector_db.search(
    query=current_task,
    limit=3,
)

# Добавить в контекст
context = f"Similar tasks solved before:\n{similar_tasks}"
```

**Приоритет:** Средний  
**Сложность:** Средняя

---

### 8. Multi-Repository Support
**Описание:** Работать с несколькими репозиториями одновременно.

**Возможности:**
- Создание микросервисов
- Обновление зависимостей в mono-repo
- Синхронизация изменений между репо

**Приоритет:** Средний  
**Сложность:** Средняя

---

### 9. Template Library
**Описание:** Библиотека шаблонов для типичных задач.

**Примеры шаблонов:**
- REST API (FastAPI, Express, Django)
- CRUD приложения
- Authentication системы
- GraphQL APIs
- Микросервисы

**Структура:**
```
templates/
├── rest-api-fastapi/
│   ├── template.yaml
│   ├── prompts/
│   └── examples/
├── crud-react/
└── auth-jwt/
```

**Приоритет:** Средний  
**Сложность:** Средняя

---

### 10. Security Agent
**Описание:** Отдельный агент для проверки безопасности.

**Проверки:**
- OWASP Top 10
- Dependency vulnerabilities
- SQL injection, XSS
- Authentication issues
- Secrets in code

**Инструменты:**
- Bandit (Python)
- ESLint security plugin (JS/TS)
- Trivy (dependencies)
- Semgrep

**Приоритет:** Высокий  
**Сложность:** Средняя

---

## Долгосрочные идеи (3-6 месяцев)

### 11. Интеграция с Jira/Linear
**Описание:** Автоматическое создание тикетов и синхронизация статусов.

**Возможности:**
- Создание задач из AI-crew
- Автоматическое обновление статусов
- Связывание PR с тикетами
- Комментарии в тикеты

**Приоритет:** Средний  
**Сложность:** Средняя

---

### 12. Multi-language Support
**Описание:** Поддержка разных языков программирования.

**Текущее состояние:** Работает с любыми языками, но промпты оптимизированы для Python/TypeScript.

**Улучшения:**
- Специализированные промпты для языков
- Language-specific агенты
- Правильные инструменты для каждого языка

**Языки для добавления:**
- Go
- Rust
- Java
- C#
- Ruby

**Приоритет:** Низкий  
**Сложность:** Средняя

---

### 13. Collaborative Editing
**Описание:** Редактирование кода в реальном времени с AI.

**Возможности:**
- Live code suggestions
- Пошаговое улучшение кода
- Совместное написание с AI

**Технологии:**
- Monaco Editor
- WebSockets
- Operational Transform

**Приоритет:** Низкий  
**Сложность:** Высокая

---

### 14. Visual Graph Editor
**Описание:** Визуальный редактор для создания custom workflows.

**Возможности:**
- Drag-and-drop агентов
- Создание условных переходов
- Кастомизация без кода

**Технологии:**
- React Flow
- JSON Schema для конфигурации

**Приоритет:** Низкий  
**Сложность:** Высокая

---

### 15. Fine-tuned Models
**Описание:** Дообучить модели на вашем стиле кода.

**Возможности:**
- Изучение coding style из ваших репо
- Соблюдение внутренних стандартов
- Более точные результаты

**Подходы:**
- Few-shot learning (быстро)
- Fine-tuning (дорого, качественно)
- RAG с примерами кода (средне)

**Приоритет:** Низкий  
**Сложность:** Высокая

---

### 16. Cost Optimization
**Описание:** Умное управление бюджетом на LLM.

**Функции:**
- Tracking стоимости задач
- Автоматический выбор дешевой модели
- Кэширование результатов
- Budget limits и alerts

**Пример:**
```python
# Использовать GPT-4o только для критичных задач
if task_complexity > 8:
    model = "gpt-4o"
else:
    model = "gpt-4o-mini"  # В 10 раз дешевле
```

**Приоритет:** Средний  
**Сложность:** Средняя

---

### 17. A/B Testing для Промптов
**Описание:** Автоматическое тестирование разных версий промптов.

**Возможности:**
- Сравнение качества результатов
- Метрики (скорость, токены, качество)
- Автоматический выбор лучшего промпта

**Приоритет:** Низкий  
**Сложность:** Средняя

---

### 17b. UI Test Contract (Developer → QA Hints) `[IMPLEMENTED]`
**Описание:** Developer-агент после создания UI генерирует `.qa-hints.yaml` — структурированный контракт с селекторами, доступными элементами и возможными тест-сценариями. QA-агент читает этот файл вместо того, чтобы угадывать селекторы из code structure.

**Реализация (февраль 2026):**
- `developer.yaml`: промпт instruction для генерации `.qa-hints.yaml`
- `qa_helpers.py`: `extract_qa_hints()` + `format_qa_hints_for_prompt()`
- `qa_exploration.py`: извлечение hints и передача в промпт
- `qa_browser.py`: аналогично для Phase 1 (scripted E2E)
- `qa.yaml`: `generate_exploration_plan` и `generate_browser_test` промпты принимают `{qa_hints}`
- 12 unit-тестов (658 всего)

**Проблема:** Сейчас QA-агент генерирует exploration plan на основе code structure — сжатой сводки файлов. При этом LLM вынужден **угадывать** placeholder-текст, текст кнопок, CSS-классы. Это ведёт к неверным селекторам (TimeoutError, strict mode violations).

**Решение — трёхуровневый контракт:**

```yaml
# .qa-hints.yaml — генерируется Developer-агентом
selectors:
  main_input:
    css: "#todoInput"
    type: text
    placeholder: "Add a new task..."
  add_button:
    css: "#addBtn"
    text: "Add Task"
    type: button
  task_list:
    css: "#todoList"
    type: list
    item_css: "#todoList li"
  task_checkbox:
    css: ".todo-checkbox"
    type: checkbox
    note: "один на задачу — используй :first-child для первого"
  delete_button:
    css: ".delete-btn"
    text: "Delete"
    note: "один на задачу — используй li:first-child .delete-btn"

test_flows:
  add_task:
    - { action: fill, target: main_input, value: "Buy milk" }
    - { action: click, target: add_button }
  complete_task:
    - { action: click, target: "li:first-child .todo-checkbox" }
  delete_task:
    - { action: click, target: "li:first-child .delete-btn" }
```

**Архитектурная цепочка:**
1. **Analyst/Architect** — при проектировании комплексных UI, могут описать ключевые user flows и ожидаемые элементы в user stories / architecture decisions
2. **Developer** — после создания HTML/frontend кода, генерирует `.qa-hints.yaml` с реальными селекторами из написанного кода
3. **QA (exploration)** — читает `.qa-hints.yaml` и использует точные селекторы для exploration plan

**Преимущества:**
- Устраняет угадывание — Developer ЗНАЕТ свои селекторы
- Создаёт контракт между Developer и QA (аналог OpenAPI для UI)
- Analyst/Architect могут добавить тестовые сценарии
- Масштабируется на сложные UI

**Реализация:**
- Уровень графа: добавить шаг `generate_qa_hints` после Developer, перед QA
- Промпт для Developer: "Сгенерируй .qa-hints.yaml для созданного UI"
- QA exploration: если `.qa-hints.yaml` существует — использует его селекторы
- Fallback: если файла нет — текущий подход (code structure → LLM guess)

**Приоритет:** Высокий
**Сложность:** Средняя (граф + промпты + QA exploration интеграция)

---

## Экспериментальные идеи

### 18. Self-Improvement Loop
**Описание:** Агенты улучшают сами себя.

**Как:**
- Анализ собственных ошибок
- Автоматическое обновление промптов
- Обучение на фидбеке

**Риски:**
- Может ухудшиться качество
- Сложно контролировать
- Требует много тестирования

---

### 19. Multi-Agent Debate
**Описание:** Несколько агентов обсуждают решение.

**Пример:**
```
Architect 1: Предлагаю монолит
Architect 2: Лучше микросервисы
PM: Оцените trade-offs
→ Итоговое решение: Модульный монолит
```

**Приоритет:** Низкий  
**Сложность:** Высокая

---

### 20. Voice Interface
**Описание:** Голосовое управление через AI ассистента.

**Возможности:**
- Создание задач голосом
- Диалоги с агентами
- Голосовые отчёты о прогрессе

**Технологии:**
- Whisper для STT
- ElevenLabs для TTS

**Приоритет:** Очень низкий  
**Сложность:** Средняя

---

## Приоритизация

### Высокий приоритет:
1. ✅ Retry логика для LLM
2. ✅ Валидация входных данных
3. Code Execution Sandbox
4. Security Agent

### Средний приоритет:
5. Структурированное логирование
6. Streaming в Frontend
7. Vector Database
8. Multi-Repository Support
9. Template Library
10. Cost Optimization

### Низкий приоритет:
11. Вынести конфигурацию LLM
12. Интеграция с Jira
13. Multi-language Support
14. Остальные экспериментальные идеи

---

## Как внести вклад

1. Выберите задачу из списка выше
2. Создайте feature branch
3. Реализуйте + добавьте тесты
4. Обновите документацию
5. Создайте Pull Request
