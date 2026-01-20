# Руководство по тестированию AI-crew

## Установка зависимостей для тестирования

```bash
# Установить основные зависимости
pip install -r requirements.txt

# Тесты уже включены в requirements.txt:
# - pytest>=8.0.0
# - pytest-asyncio>=0.23.0
```

## Запуск тестов

### Запустить все тесты
```bash
pytest tests/ -v
```

### Запустить конкретный файл тестов
```bash
pytest tests/test_state.py -v
pytest tests/test_agents.py -v
pytest tests/test_graph.py -v
pytest tests/test_tools.py -v
pytest tests/test_integration.py -v
```

### Запустить конкретный тест
```bash
pytest tests/test_state.py::TestDevTeamState::test_create_initial_state_minimal -v
```

### Запустить с coverage
```bash
# Установить coverage
pip install pytest-cov

# Запустить с отчетом
pytest tests/ --cov=graphs --cov-report=html --cov-report=term

# Посмотреть HTML отчет
# Откройте htmlcov/index.html в браузере
```

### Запустить только быстрые тесты (пропустить медленные)
```bash
pytest tests/ -v -m "not slow"
```

### Запустить в параллельном режиме (быстрее)
```bash
# Установить pytest-xdist
pip install pytest-xdist

# Запустить на 4 ядрах
pytest tests/ -n 4
```

## Структура тестов

```
tests/
├── __init__.py                 # Пакет тестов
├── conftest.py                 # Фикстуры и конфигурация pytest
├── test_state.py              # Тесты DevTeamState
├── test_agents.py             # Тесты всех агентов
├── test_graph.py              # Тесты LangGraph workflow
├── test_tools.py              # Тесты GitHub и filesystem инструментов
└── test_integration.py        # Интеграционные тесты
```

## Описание тестов

### test_state.py
Тестирует структуру состояния (DevTeamState):
- Создание начального состояния
- Проверка всех обязательных полей
- Типы CodeFile и UserStory

### test_agents.py
Тестирует каждого агента:
- **PM Agent**: декомпозиция задач, прогресс, финальный ревью
- **Analyst Agent**: сбор требований, запрос уточнений
- **Architect Agent**: проектирование архитектуры
- **Developer Agent**: генерация кода, парсинг code blocks
- **QA Agent**: ревью кода, поиск проблем

### test_graph.py
Тестирует LangGraph workflow:
- Роутинг между агентами
- Условные переходы (clarification, QA feedback loop)
- Узлы (clarification_node, git_commit_node)
- Компиляция графа

### test_tools.py
Тестирует инструменты агентов:
- **GitHub Tools**: создание PR, веток, коммитов
- **Filesystem Tools**: чтение/запись файлов, создание директорий

### test_integration.py
Интеграционные тесты:
- Human-in-the-Loop (HITL) workflow
- Обработка ошибок
- Мультиагентная коллаборация (Developer ↔ QA)

## Моки и фикстуры

### Доступные фикстуры (из conftest.py)

```python
# Моки LLM
mock_llm              # Синхронный mock LLM
mock_async_llm        # Асинхронный mock LLM

# Тестовые данные
sample_task           # Пример задачи
sample_state          # Пример DevTeamState

# Моки сервисов
mock_github_client    # Mock GitHub API
```

### Пример использования фикстуры
```python
def test_my_function(sample_state, mock_llm):
    # sample_state уже инициализирован
    result = my_function(sample_state, mock_llm)
    assert result["task"] == "Create a simple calculator API"
```

## Переменные окружения для тестов

Тесты используют тестовые API ключи (см. `conftest.py`):
```python
os.environ["OPENAI_API_KEY"] = "test-key"
os.environ["ANTHROPIC_API_KEY"] = "test-key"
```

Для настоящих интеграционных тестов (если нужны):
```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
```

## CI/CD интеграция

### GitHub Actions пример

Создайте `.github/workflows/tests.yml`:
```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
    
    - name: Run tests
      run: |
        pytest tests/ -v --cov=graphs --cov-report=xml
    
    - name: Upload coverage
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
```

## Отладка тестов

### Печать вывода во время тестов
```bash
pytest tests/ -v -s
```

### Остановиться на первой ошибке
```bash
pytest tests/ -x
```

### Запустить отладчик при ошибке
```bash
pytest tests/ --pdb
```

### Показать локальные переменные при ошибке
```bash
pytest tests/ -v --showlocals
```

## Проверка типов

```bash
# Установить mypy
pip install mypy

# Проверить типы
mypy graphs/
```

## Линтинг

```bash
# Установить инструменты
pip install ruff black

# Проверить код стиль
ruff check graphs/
black --check graphs/

# Автоматически исправить
ruff check graphs/ --fix
black graphs/
```

## Полезные команды

### Создать отчет о покрытии в терминале
```bash
pytest tests/ --cov=graphs --cov-report=term-missing
```

### Запустить только failed тесты из прошлого запуска
```bash
pytest --lf
```

### Показать самые медленные тесты
```bash
pytest tests/ --durations=10
```

### Запустить тесты с подробным выводом
```bash
pytest tests/ -vv
```

## Написание новых тестов

### Шаблон теста агента
```python
import pytest
from unittest.mock import Mock, patch

@patch('path.to.agent.get_llm')
@patch('path.to.agent.load_prompts')
def test_new_agent_feature(mock_load_prompts, mock_get_llm, sample_state):
    """Test description."""
    # Arrange
    mock_load_prompts.return_value = {"system": "Test"}
    mock_llm = Mock()
    mock_llm.invoke = Mock(return_value=Mock(content="Response"))
    mock_get_llm.return_value = mock_llm
    
    # Act
    result = my_agent_function(sample_state)
    
    # Assert
    assert "expected_key" in result
    assert result["expected_key"] == "expected_value"
```

### Шаблон интеграционного теста
```python
def test_workflow_integration(sample_state):
    """Test complete workflow."""
    # Setup initial state
    state = sample_state
    
    # Execute workflow steps
    state = step1(state)
    state = step2(state)
    state = step3(state)
    
    # Verify final state
    assert state["current_agent"] == "complete"
    assert len(state["code_files"]) > 0
```

## Частые проблемы

### Проблема: `ModuleNotFoundError`
**Решение:** Убедитесь, что находитесь в корне проекта:
```bash
cd AI-crew
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
pytest tests/
```

### Проблема: Тесты падают с timeout
**Решение:** Увеличьте timeout или пропустите медленные тесты:
```bash
pytest tests/ -v --timeout=300
# или
pytest tests/ -v -m "not slow"
```

### Проблема: Import errors в тестах
**Решение:** Проверьте, что все `__init__.py` файлы существуют:
```bash
touch graphs/__init__.py
touch graphs/dev_team/__init__.py
touch graphs/dev_team/agents/__init__.py
touch graphs/dev_team/tools/__init__.py
```

## Дополнительные ресурсы

- [Pytest Documentation](https://docs.pytest.org/)
- [unittest.mock Guide](https://docs.python.org/3/library/unittest.mock.html)
- [LangGraph Testing Best Practices](https://langchain-ai.github.io/langgraph/tutorials/testing/)

---

**Вопросы?** Создайте issue в репозитории или обратитесь к документации.
