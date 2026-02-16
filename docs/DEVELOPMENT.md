# Руководство разработчика

Как кастомизировать и расширять AI-crew.

---

## Содержание

1. [Структура проекта](#структура-проекта)
2. [Создание нового агента](#создание-нового-агента)
3. [Изменение промптов](#изменение-промптов)
4. [Изменение флоу агентов](#изменение-флоу-агентов)
5. [Добавление инструментов](#добавление-инструментов)
6. [Настройка LLM моделей](#настройка-llm-моделей)
7. [Работа с State](#работа-с-state)
8. [Отладка](#отладка)

---

## Структура проекта

```
AI-crew/
├── graphs/                    # LangGraph агенты
│   └── dev_team/
│       ├── graph.py          # Основной граф ⭐
│       ├── state.py          # Определение State ⭐
│       ├── agents/           # Агенты
│       │   ├── base.py       # Базовый класс
│       │   ├── pm.py
│       │   ├── analyst.py
│       │   ├── architect.py
│       │   ├── developer.py
│       │   └── qa.py
│       ├── prompts/          # Промпты агентов ⭐
│       │   ├── pm.yaml
│       │   ├── analyst.yaml
│       │   ├── architect.yaml
│       │   ├── developer.yaml
│       │   └── qa.yaml
│       └── tools/            # Инструменты
│           ├── github.py
│           └── filesystem.py
├── frontend/                  # React UI
│   └── src/
│       ├── api/              # Aegra API клиент
│       ├── components/       # UI компоненты
│       └── hooks/            # React hooks
├── tests/                    # Тесты
└── docs/                     # Документация
```

---

## Создание нового агента

### Шаг 1: Создать класс агента

Создайте файл `graphs/dev_team/agents/security.py`:

```python
"""
Security Engineer Agent

Responsible for security analysis and vulnerability detection.
"""

from langchain_core.messages import AIMessage

from .base import BaseAgent, get_llm, load_prompts, create_prompt_template
from ..state import DevTeamState


class SecurityAgent(BaseAgent):
    """Security Engineer agent for security analysis."""
    
    def __init__(self):
        prompts = load_prompts("security")
        llm = get_llm(role="security", temperature=0.3)
        super().__init__(name="security", llm=llm, prompts=prompts)
    
    def analyze_security(self, state: DevTeamState) -> dict:
        """
        Analyze code for security vulnerabilities.
        """
        prompt = create_prompt_template(
            self.system_prompt,
            self.prompts["security_analysis"]
        )
        
        chain = prompt | self.llm
        
        code_files = state.get("code_files", [])
        
        response = chain.invoke({
            "code_files": "\n\n".join([
                f"### {f['path']}\n```{f['language']}\n{f['content']}\n```"
                for f in code_files
            ]),
        })
        
        return {
            "messages": [AIMessage(content=response.content, name="security")],
            "security_issues": self._parse_issues(response.content),
            "current_agent": "security",
        }
    
    def _parse_issues(self, content: str) -> list[str]:
        """Parse security issues from response."""
        issues = []
        for line in content.split("\n"):
            if "vulnerability" in line.lower() or "security" in line.lower():
                issues.append(line.strip())
        return issues


# Singleton instance
_security_agent = None

def get_security_agent() -> SecurityAgent:
    """Get or create the Security agent instance."""
    global _security_agent
    if _security_agent is None:
        _security_agent = SecurityAgent()
    return _security_agent


def security_agent(state: DevTeamState) -> dict:
    """
    Security agent node function for LangGraph.
    """
    agent = get_security_agent()
    return agent.analyze_security(state)
```

### Шаг 2: Создать промпт

Создайте файл `graphs/dev_team/prompts/security.yaml`:

```yaml
# Security Engineer Agent Prompts

system: |
  You are a Security Engineer AI agent, part of a software development team.
  
  Your responsibilities:
  1. Analyze code for security vulnerabilities
  2. Check for common security issues (SQL injection, XSS, etc.)
  3. Verify secure coding practices
  4. Check dependencies for known vulnerabilities
  5. Recommend security improvements
  
  Guidelines:
  - Use OWASP Top 10 as reference
  - Check for authentication and authorization issues
  - Verify input validation and sanitization
  - Check for sensitive data exposure
  - Recommend security best practices

security_analysis: |
  Analyze the following code for security vulnerabilities:
  
  Code Files:
  {code_files}
  
  Please provide:
  1. List of security vulnerabilities (with severity: Critical, High, Medium, Low)
  2. Explanation of each vulnerability
  3. Recommendations for fixing
  4. Security best practices to follow
  
  Format:
  
  ## Vulnerabilities Found
  ### Critical
  - [Issue]: [Description]
  
  ### High
  - [Issue]: [Description]
  
  ## Recommendations
  - [Recommendation 1]
  - [Recommendation 2]
```

### Шаг 3: Добавить в граф

Отредактируйте `graphs/dev_team/graph.py`:

```python
from .agents.security import security_agent

def create_graph() -> StateGraph:
    builder = StateGraph(DevTeamState)
    
    # Добавить ноду
    builder.add_node("security", security_agent)
    
    # Добавить в флоу (после QA, перед git_commit)
    # QA -> Security -> git_commit
    builder.add_conditional_edges(
        "qa",
        route_after_qa,
        {
            "developer": "developer",
            "security": "security",  # Новый путь
            "git_commit": "git_commit",
            "pm_final": "pm_final",
        }
    )
    
    builder.add_edge("security", "git_commit")
    
    return builder
```

### Шаг 4: Обновить State (если нужно)

Добавьте в `graphs/dev_team/state.py`:

```python
class DevTeamState(TypedDict):
    # ... существующие поля ...
    
    # === Security Output ===
    security_issues: list[str]  # Security vulnerabilities found
```

---

## Изменение промптов

Промпты хранятся в YAML файлах в `graphs/dev_team/prompts/`.

### Структура промпта

```yaml
# System prompt (общая инструкция)
system: |
  You are a [Role] AI agent...
  
  Your responsibilities:
  1. [Task 1]
  2. [Task 2]

# Промпт для конкретной задачи
task_name: |
  [Instructions]
  
  Input: {input_variable}
  
  Please provide:
  1. [Expected output 1]
  2. [Expected output 2]
```

### Пример: Изменить стиль кода Developer

Отредактируйте `graphs/dev_team/prompts/developer.yaml`:

```yaml
system: |
  You are a Software Developer AI agent.
  
  Code Style:
  - Use TypeScript instead of JavaScript
  - Follow functional programming paradigm
  - Use const/let, never var
  - Prefer async/await over promises
  - Use Zod for validation
  - Write comprehensive tests (minimum 80% coverage)

implementation: |
  Implement the following using TypeScript and functional programming:
  
  Task: {task}
  Architecture: {architecture}
  
  Requirements:
  1. Use TypeScript with strict mode
  2. Functional components only (no classes)
  3. Immutable data structures
  4. Pure functions where possible
  5. Comprehensive error handling
  6. Full test coverage
```

### Тестирование промптов

```bash
# Запустить тесты агента
pytest tests/test_agents.py::TestDeveloperAgent -v

# Создать тестовую задачу через UI
# Наблюдать за изменениями в output
```

---

## Изменение флоу агентов

Флоу определяется в `graphs/dev_team/graph.py`.

### Текущий флоу:

```
START → PM → Analyst → Architect → Developer → Lint → Security → QA Gate → Reviewer → Git Commit → END
                ↓          ↓                                  ↓              ↓
         Clarification  Clarification                    back to Developer  back to Developer
```

`QA Gate` — это рантайм-проверка (sandbox/browser) перед code review:
- PASS (green gate) → `Reviewer`
- FAIL → `Developer`

`Lint` поддерживает non-blocking режим:
- `issues` (blocking) → назад в `Developer`
- `warnings` (non-blocking) → не блокирует флоу, но передаётся в контекст `Reviewer`

### Пример: Добавить параллельную проверку

```python
def create_graph() -> StateGraph:
    builder = StateGraph(DevTeamState)
    
    # Добавить агентов
    builder.add_node("developer", developer_agent)
    builder.add_node("qa", qa_agent)
    builder.add_node("security", security_agent)
    
    # Параллельное выполнение QA и Security
    builder.add_edge("developer", "qa")
    builder.add_edge("developer", "security")
    
    # Объединение результатов
    builder.add_node("merge_reviews", merge_reviews_node)
    builder.add_edge("qa", "merge_reviews")
    builder.add_edge("security", "merge_reviews")
    
    # Дальнейший флоу
    builder.add_conditional_edges(
        "merge_reviews",
        route_after_reviews,
        {
            "developer": "developer",  # Если нашли проблемы
            "git_commit": "git_commit",  # Если всё ок
        }
    )
    
    return builder
```

### Условные переходы

```python
def route_after_developer(state: DevTeamState) -> Literal["qa", "security", "both"]:
    """
    Определить, какие проверки нужны.
    """
    code_files = state.get("code_files", [])
    
    # Если есть backend код, нужна security проверка
    has_backend = any("api" in f["path"] or "server" in f["path"] for f in code_files)
    
    if has_backend:
        return "both"  # QA и Security параллельно
    else:
        return "qa"  # Только QA
```

---

## Добавление инструментов

Инструменты - это функции, которые агенты могут вызывать.

### Пример: Добавить инструмент для запуска тестов

Создайте `graphs/dev_team/tools/test_runner.py`:

```python
"""
Test Runner Tool

Allows agents to run tests on generated code.
"""

import subprocess
from langchain_core.tools import tool


@tool
def run_tests(
    test_command: str,
    working_directory: str = "."
) -> str:
    """
    Run tests using the specified command.
    
    Args:
        test_command: Command to run tests (e.g., "pytest", "npm test")
        working_directory: Directory to run tests in
        
    Returns:
        Test results (stdout and stderr)
    """
    try:
        result = subprocess.run(
            test_command,
            shell=True,
            cwd=working_directory,
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        output = f"Exit code: {result.returncode}\n\n"
        output += f"STDOUT:\n{result.stdout}\n\n"
        output += f"STDERR:\n{result.stderr}"
        
        return output
    except subprocess.TimeoutExpired:
        return "Error: Test execution timed out (60s limit)"
    except Exception as e:
        return f"Error running tests: {str(e)}"


# Export
test_tools = [run_tests]
```

### Использовать инструмент в агенте

```python
from ..tools.test_runner import test_tools

class QAAgent(BaseAgent):
    def __init__(self):
        prompts = load_prompts("qa")
        llm = get_llm(role="qa", temperature=0.3)
        
        # Привязать инструменты к LLM
        llm_with_tools = llm.bind_tools(test_tools)
        
        super().__init__(name="qa", llm=llm_with_tools, prompts=prompts)
```

---

## Настройка LLM моделей

### Вариант 1: Через переменные окружения (рекомендуется)

```bash
# .env — переопределить модель для конкретного агента
LLM_MODEL_DEVELOPER=gemini-3-pro-high
LLM_MODEL_ARCHITECT=claude-opus-4-5-thinking

# Или глобальный fallback
LLM_DEFAULT_MODEL=claude-sonnet-4-5-thinking
```

### Вариант 2: В коде агента

```python
# graphs/dev_team/agents/developer.py
def __init__(self):
    prompts = load_prompts("developer")
    llm = get_llm(
        model="gemini-3-pro-high",  # Явная модель
        temperature=0.1,
    )
    super().__init__(name="developer", llm=llm, prompts=prompts)
```

### Несколько API endpoints

```bash
# Основной endpoint
LLM_API_URL=https://main-proxy.example.com/v1
LLM_API_KEY=main-key

# Именованный endpoint "BACKUP"
LLM_BACKUP_URL=https://backup-proxy.example.com/v1
LLM_BACKUP_KEY=backup-key
```

```python
# В коде агента — использовать backup endpoint
llm = get_llm(role="developer", endpoint="backup")
```

---

## Работа с State

State - это общее состояние, передаваемое между агентами.

### Добавить новое поле

```python
# graphs/dev_team/state.py

class DevTeamState(TypedDict):
    # ... существующие поля ...
    
    # Новое поле
    estimated_time: NotRequired[str]  # Estimated completion time
    complexity_score: NotRequired[int]  # 1-10 complexity rating
```

### Использовать в агенте

```python
def pm_agent(state: DevTeamState) -> dict:
    agent = get_pm_agent()
    
    # Добавить новые данные в state
    return {
        **agent.decompose_task(state),
        "estimated_time": "2-3 hours",
        "complexity_score": 7,
    }
```

### Аккумулятор для списков

```python
from langgraph.graph.message import add_messages
from typing import Annotated

class DevTeamState(TypedDict):
    # Автоматически добавляет новые сообщения к существующим
    messages: Annotated[list[BaseMessage], add_messages]
```

---

## Отладка

### Использовать LangGraph Studio

```bash
# LangGraph Studio подключается к Aegra
# URL: http://localhost:8000
```

Возможности:
- Визуализация графа
- Пошаговое выполнение
- Time Travel (откат к любому состоянию)
- Редактирование State на лету

### Логирование

Добавьте логи в агентов:

```python
import logging

logger = logging.getLogger(__name__)

def developer_agent(state: DevTeamState) -> dict:
    logger.info(f"Developer agent invoked, task: {state['task']}")
    
    agent = get_developer_agent()
    result = agent.implement(state)
    
    logger.info(f"Generated {len(result['code_files'])} files")
    return result
```

### Langfuse Tracing

Все LLM вызовы автоматически логируются в Langfuse:
- Откройте http://localhost:3001
- Найдите trace по задаче
- Посмотрите промпты, ответы, токены

### Тестирование

```bash
# Запустить тесты с verbose
pytest tests/ -vv -s

# Запустить конкретный тест
pytest tests/test_agents.py::TestDeveloperAgent::test_implement_code -vv

# Запустить с отладчиком
pytest tests/ --pdb
```

---

## Полезные команды

```bash
# Перезапустить Aegra после изменений
docker-compose restart aegra

# Посмотреть логи
docker-compose logs -f aegra

# Проверить граф
python -c "from graphs.dev_team.graph import graph; print(graph)"

# Запустить линтер
ruff check graphs/
black graphs/

# Проверить типы
mypy graphs/
```

---

## Следующие шаги

- [Тестирование](TESTING.md) — как писать и запускать тесты
- [Архитектура](architecture_old.md) — детальное описание системы
- [Развёртывание](deployment.md) — Docker, production
