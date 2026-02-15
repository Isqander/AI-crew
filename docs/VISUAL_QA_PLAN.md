# Visual QA Testing — План реализации

> Подробный план расширения QA-агента для визуального тестирования UI.
> Включает: помодульную разбивку, оценку сложности, анализ целесообразности.
>
> Дата: 14 февраля 2026
> Связанные документы:
> - [ARCHITECTURE_V2.md — Приложение C](ARCHITECTURE_V2.md#appendix-c-visual-qa)
> - [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) — основной план

---

## Содержание

1. [Текущее состояние и мотивация](#1-текущее-состояние)
2. [Сравнение с предложенным планом](#2-сравнение)
3. [Фаза 1: Scripted E2E (MVP)](#3-фаза-1)
4. [Фаза 2: Guided Exploration](#4-фаза-2)
5. [Фаза 3: Autonomous Loop (Experimental)](#5-фаза-3)
6. [Оценка сложности и сроки](#6-оценка-сложности)
7. [Целесообразность Observe → Act → Evaluate](#7-целесообразность)
8. [Чеклист готовности Visual QA](#8-чеклист)

---

## 1. Текущее состояние и мотивация {#1-текущее-состояние}

### Что уже есть

QA-агент (`agents/qa.py`) реализован и работает в Sandbox:
- **Sandbox-сервис** — Docker-in-Docker, FastAPI, POST /execute
- **QAAgent.test_code()** — запуск кода в sandbox, анализ stdout/stderr через LLM
- **Авто-определение языка** — Python, JS/TS, Go, Rust
- **Авто-генерация команд** — pytest, jest, vitest, go test, cargo test
- **LLM-анализ** — вердикт PASS/FAIL + список issues
- **Роутинг в графе** — Developer → Security → Reviewer → QA → git_commit

### Чего не хватает

QA-агент проверяет **backend-логику** (тесты, компиляция, синтаксис), но **не проверяет UI**:
- Рендерится ли страница?
- Работают ли кнопки и формы?
- Есть ли console errors в браузере?
- Выглядит ли UI как задумано?
- Работают ли ключевые пользовательские сценарии (flow)?

Для полноценного QA нужен **браузерный тестировщик**.

---

## 2. Сравнение с предложенным планом {#2-сравнение}

### Предложенный план (из обсуждения)

Двухэтапный подход:
- **Этап 1:** BrowserExecutionProvider, контракты, scripted_regression + guided_exploratory, remote_runner контракт, хранилище артефактов, observability
- **Этап 2:** autonomous_exploration, Observe → Act → Evaluate цикл, planner/verifier policy, hybrid_auto режим

### Мой подход: что я изменил и почему

| Аспект | Предложенный план | Мой вариант | Почему |
|--------|-------------------|-------------|--------|
| **Абстракция** | BrowserExecutionProvider (local + remote) сразу | Прямая интеграция с Sandbox, абстрагировать при появлении второго провайдера | YAGNI — один провайдер, одна реализация. Абстракция добавляет сложность без текущей пользы |
| **Remote runner контракт** | Подготовить API + schema сразу | Отложить до реальной потребности | Сейчас Sandbox справляется. Remote runner — отдельный проект |
| **Guided exploratory** | Как второй режим в Этапе 1 | Отдельная Фаза 2 после стабилизации E2E | E2E-тесты покрывают 80% кейсов. Exploration — усложнение |
| **Autonomous loop** | Отдельный Этап 2 (обязательный) | Фаза 3, **experimental**, не обязательный | Дорого, нестабильно, 5% дополнительной ценности (см. §7) |
| **Batch vs Loop** | Пошаговый Observe→Act→Evaluate | Фаза 2: batch exploration (один план → один прогон → один анализ) | В 5-10× дешевле, стабильнее, детерминированнее |
| **Verifier policy** | Отдельная проверка дефекта | Встроена в LLM-анализ результатов (confidence score) | Отдельный verifier — оверинжиниринг для текущего масштаба |
| **Planner policy** | Цели, подцели, критерии остановки | Exploration plan как JSON (Фаза 2) | Проще, предсказуемее |

### Ключевые принципы моего подхода

1. **Инкрементальность** — каждая фаза даёт ценность и работает самостоятельно
2. **Без преждевременных абстракций** — абстрагируем, когда появляется второй consumer
3. **Максимальное переиспользование** — Sandbox уже есть, Playwright добавляется как Docker-образ
4. **Batch > Loop** — один LLM-вызов дешевле и стабильнее десяти
5. **Experimental флаги** — новые режимы выключены по умолчанию

---

## 3. Фаза 1: Scripted E2E (MVP) {#3-фаза-1}

> **Статус: РЕАЛИЗОВАНО (15 февраля 2026)**
> Фаза 1 полностью реализована и проверена: PASS с 15 скриншотами.
> Все компоненты (sandbox browser mode, browser_runner, QA Agent test_ui,
> промпты, интеграция в граф) работают в production.

**Цель:** QA-агент генерирует и запускает Playwright E2E тесты для UI-проектов.

### 3.1 Модуль: Sandbox Browser Mode

**Файлы:**

| Действие | Файл | Что делать |
|----------|------|-----------|
| Создать | `sandbox/Dockerfile.browser` | Docker-образ с Playwright + Chromium + Node.js |
| Изменить | `sandbox/models.py` | Добавить `browser`, `collect_screenshots`, `app_start_command`, `app_ready_timeout` |
| Изменить | `sandbox/executor.py` | Выбор образа (browser vs standard), сбор скриншотов из /screenshots/ |
| Изменить | `sandbox/server.py` | Обработка новых полей, возврат screenshots + browser_console |
| Изменить | `docker-compose.yml` | Build sandbox-browser образа |

**Реализация:**

```python
# sandbox/models.py — расширение

class SandboxExecuteRequest(BaseModel):
    # ... существующие поля ...
    browser: bool = False
    collect_screenshots: bool = False
    app_start_command: str | None = None
    app_ready_timeout: int = 30

class SandboxExecuteResponse(BaseModel):
    # ... существующие поля ...
    screenshots: list[dict] = []       # [{name, base64}]
    browser_console: str = ""
    network_errors: list[str] = []
```

```python
# sandbox/executor.py — выбор образа

BROWSER_IMAGE = os.getenv("SANDBOX_BROWSER_IMAGE", "aicrew-sandbox-browser:latest")

async def execute(self, request: SandboxExecuteRequest) -> SandboxExecuteResponse:
    image = BROWSER_IMAGE if request.browser else self._get_language_image(request.language)
    # ... остальная логика аналогична текущей ...
    
    if request.collect_screenshots:
        # Копируем /screenshots/ из контейнера, кодируем в base64
        screenshots = self._collect_screenshots(container)
```

```dockerfile
# sandbox/Dockerfile.browser
FROM mcr.microsoft.com/playwright/python:v1.50.0-noble

# Node.js для JS-приложений
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs

# Python тестовые зависимости
RUN pip install pytest pytest-playwright

# Go (опционально, для Go web apps)
# RUN ... 

# Директория для скриншотов
RUN mkdir -p /screenshots

WORKDIR /workspace
```

**Тесты:**
- Unit: выбор образа, сбор скриншотов, модели
- Integration: запуск простого HTML+JS в browser-sandbox

### 3.2 Модуль: Browser Test Runner

Вспомогательный скрипт, который запускается **внутри sandbox-контейнера**.
QA-агент включает его в `code_files` при browser-тестировании.

**Файлы:**

| Действие | Файл | Что делать |
|----------|------|-----------|
| Создать | `graphs/dev_team/tools/browser_runner.py` | Шаблон runner-скрипта (строка, подставляется в code_files) |

**Что делает runner внутри контейнера:**

1. Устанавливает зависимости проекта (`npm install` / `pip install`)
2. Запускает приложение в фоне (`npm run dev` / `python app.py`)
3. Ожидает готовности (проверка порта / HTTP healthcheck)
4. Запускает Playwright-тесты
5. Собирает скриншоты в `/screenshots/`
6. Выводит structured JSON-отчёт в stdout

```python
# graphs/dev_team/tools/browser_runner.py

BROWSER_RUNNER_TEMPLATE = '''
#!/usr/bin/env python3
"""Browser test runner — executes inside sandbox container."""
import subprocess, time, sys, json, os, socket

APP_COMMAND = {app_command!r}
APP_PORT = {app_port}
APP_READY_TIMEOUT = {app_ready_timeout}
BASE_URL = f"http://localhost:{{APP_PORT}}"

def wait_for_port(port, timeout=30):
    """Wait until app is listening on port."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("localhost", port), timeout=1):
                return True
        except (ConnectionRefusedError, OSError):
            time.sleep(0.5)
    return False

def main():
    # 1. Start app in background
    if APP_COMMAND:
        proc = subprocess.Popen(
            APP_COMMAND, shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        print(f"[runner] App started (PID {{proc.pid}})")
    
    # 2. Wait for ready
    if not wait_for_port(APP_PORT, APP_READY_TIMEOUT):
        print("[runner] ERROR: App did not start in time")
        sys.exit(1)
    print(f"[runner] App ready on port {{APP_PORT}}")
    
    # 3. Run playwright tests
    result = subprocess.run(
        ["python", "-m", "pytest", "playwright_test.py", "-v",
         "--screenshot=on", "--output=/screenshots"],
        capture_output=True, text=True, timeout=90
    )
    
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    
    sys.exit(result.returncode)

if __name__ == "__main__":
    main()
'''
```

### 3.3 Модуль: QA Agent — test_ui()

**Файлы:**

| Действие | Файл | Что делать |
|----------|------|-----------|
| Изменить | `graphs/dev_team/agents/qa.py` | Добавить `test_ui()`, `has_ui()`, `_generate_browser_test()`, `_analyse_browser_results()`, `merge_results()` |
| Изменить | `graphs/dev_team/prompts/qa.yaml` | Добавить `generate_browser_test`, `analyse_browser_results` |
| Изменить | `graphs/dev_team/state.py` | Добавить `browser_test_results: NotRequired[dict]` |

**Реализация QA Agent:**

```python
# agents/qa.py — расширение (концепт)

# Env vars
USE_BROWSER_TESTING = os.getenv("USE_BROWSER_TESTING", "true").lower() in ("true", "1", "yes")

# UI-фреймворки
UI_INDICATORS = {
    "react", "vue", "angular", "svelte", "next.js", "nuxt",
    "nextjs", "gatsby", "vite", "html", "css", "tailwind",
    "bootstrap", "frontend", "web", "ui",
}

class QAAgent(BaseAgent):
    
    def has_ui(self, state: DevTeamState) -> bool:
        """Determine if the project has a UI component."""
        tech_stack = state.get("tech_stack", [])
        for tech in tech_stack:
            if tech.lower() in UI_INDICATORS:
                return True
        # Check code_files for HTML/JSX/TSX
        for f in state.get("code_files", []):
            path = f.get("path", "").lower()
            if any(path.endswith(ext) for ext in (".html", ".jsx", ".tsx", ".vue", ".svelte")):
                return True
        return False
    
    def test_ui(self, state: DevTeamState, config=None) -> dict:
        """Generate and run Playwright E2E tests.
        
        Steps:
          1. LLM generates Playwright test script from user_stories
          2. Build runner script with app start command
          3. Execute in browser-sandbox
          4. LLM analyses screenshots + console + results
          5. Return browser_test_results + verdict
        """
        # 1. Generate test
        test_script = self._generate_browser_test(state, config)
        
        # 2. Build sandbox request
        runner_script = self._build_runner(state)
        all_files = self._prepare_files(state, test_script, runner_script)
        
        # 3. Execute
        sandbox_result = self.sandbox.execute(
            language="python",
            code_files=all_files,
            commands=["python browser_runner.py"],
            timeout=120,
            memory_limit="512m",
            network=False,   # localhost only
            browser=True,
            collect_screenshots=True,
        )
        
        # 4. Analyse
        verdict = self._analyse_browser_results(
            state, sandbox_result, config
        )
        
        return {
            "browser_test_results": {
                "mode": "scripted_e2e",
                "screenshots": sandbox_result.get("screenshots", []),
                "console_logs": sandbox_result.get("browser_console", ""),
                "network_errors": sandbox_result.get("network_errors", []),
                "test_status": "pass" if verdict["approved"] else "fail",
                "defects_found": verdict.get("defects", []),
                "duration_seconds": sandbox_result.get("duration_seconds", 0),
            },
            "issues_found": verdict.get("issues", []),
        }
    
    def _generate_browser_test(self, state, config) -> str:
        """Use LLM to generate a Playwright test script."""
        prompt = create_prompt_template(
            self.system_prompt,
            self.prompts["generate_browser_test"],
        )
        chain = prompt | self.llm
        
        user_stories = state.get("user_stories", [])
        stories_text = "\n".join(
            f"- {s.get('title', '')}: {s.get('description', '')}"
            for s in user_stories[:5]
        )
        
        tech_stack = ", ".join(state.get("tech_stack", []))
        
        response = self._invoke_chain(chain, {
            "task": state.get("task", ""),
            "user_stories": stories_text or "No user stories available",
            "tech_stack": tech_stack or "Unknown",
            "code_structure": self._summarize_files(state.get("code_files", [])),
        }, config=config)
        
        return self._extract_code_block(response.content)
    
    def merge_results(self, code_result: dict, browser_result: dict) -> dict:
        """Merge code test results with browser test results."""
        merged = {**code_result}
        
        # Add browser results
        merged["browser_test_results"] = browser_result.get("browser_test_results")
        
        # Merge issues
        all_issues = code_result.get("issues_found", []) + browser_result.get("issues_found", [])
        merged["issues_found"] = all_issues
        
        # Overall verdict: both must pass
        code_approved = code_result.get("test_results", {}).get("approved", True)
        browser_approved = browser_result.get("browser_test_results", {}).get("test_status") == "pass"
        
        if not browser_approved:
            merged["test_results"]["approved"] = False
            merged["next_agent"] = "developer"
        
        return merged
```

### 3.4 Модуль: QA Prompts — Browser Templates

```yaml
# prompts/qa.yaml — новые шаблоны

generate_browser_test: |
  You need to generate a Playwright E2E test script for a web application.
  
  Task: {task}
  
  User Stories:
  {user_stories}
  
  Tech Stack: {tech_stack}
  
  Code Structure:
  {code_structure}
  
  Generate a Python Playwright test file (pytest-playwright style) that:
  1. Tests the MOST CRITICAL user flows (navigation, forms, buttons)
  2. Takes screenshots at key steps (page.screenshot(path="/screenshots/<name>.png"))
  3. Checks for console errors (page.on("console", ...))
  4. Verifies that key elements are visible
  5. Tests responsive behaviour (if applicable)
  
  Rules:
  - Use pytest-playwright fixtures (page, browser)
  - Base URL: http://localhost:3000 (or 8000 for Python apps)
  - Maximum 5 test functions
  - Each test should be independent
  - Include meaningful assertions
  - Take a screenshot BEFORE and AFTER key actions
  
  Return ONLY the Python code, wrapped in ```python ... ```.

analyse_browser_results: |
  Analyse the results of browser E2E tests for a web application.
  
  Task: {task}
  
  Test exit code: {exit_code}
  
  Test output (stdout):
  ```
  {stdout}
  ```
  
  Errors (stderr):
  ```
  {stderr}
  ```
  
  Browser console output:
  ```
  {console_logs}
  ```
  
  Network errors: {network_errors}
  
  Screenshots were taken at various steps (provided as images if available).
  
  Provide your analysis in this format:
  
  ## Verdict: [PASS or FAIL]
  
  ## UI Summary
  [What was tested, what worked, what didn't]
  
  ## Visual Issues
  - [visual issue 1, with screenshot reference] (or "None")
  
  ## Functional Issues
  - [functional issue 1] (or "None")
  
  ## Console/Network Issues
  - [issue] (or "None")
  
  ## Recommendations
  - [what the developer should fix]
```

### 3.5 Модуль: Graph Integration

**Файлы:**

| Действие | Файл | Что делать |
|----------|------|-----------|
| Изменить | `graphs/dev_team/graph.py` | Обновить qa_agent node (вызывать test_ui если нужно) |
| Без изменений | route_after_qa | Логика не меняется (approved → git_commit, fail → developer) |

QA node function обновляется минимально — всё через `QAAgent.test_code()` + `QAAgent.test_ui()`.
Роутинг в графе **не меняется** — QA по-прежнему возвращает approved/fail.

### 3.6 Тесты для Фазы 1

| Файл | Тесты | Тип |
|------|-------|-----|
| `tests/test_browser_sandbox.py` | Модели, выбор образа, сбор скриншотов | Unit |
| `tests/test_qa_browser.py` | has_ui(), generate_browser_test(), analyse_browser_results(), merge_results() | Unit |
| `tests/test_qa_browser.py` | test_ui() с мок-sandbox | Unit |
| `tests/test_qa_browser_integration.py` | E2E: генерация + выполнение + анализ (с реальным sandbox) | Integration |

---

## 4. Фаза 2: Guided Exploration {#4-фаза-2}

**Цель:** LLM генерирует план обхода UI → Playwright выполняет весь план → LLM пакетно анализирует результаты.

**Предусловие:** Фаза 1 стабильна и в продакшне.

### 4.1 Ключевое отличие: Batch, не Loop

В отличие от пошагового Observe→Act→Evaluate, Guided Exploration работает **пакетно**:

```
Обычный loop (дорого):        Batch exploration (дёшево):
  
  LLM → action₁               LLM → plan [action₁..actionₙ]
  execute → screenshot₁            │
  LLM → action₂               execute all → [screenshot₁..screenshotₙ]
  execute → screenshot₂            │
  LLM → action₃               LLM → analyse all
  execute → screenshot₃
  ... × 20-50 шагов           = 2 LLM-вызова вместо 20-50
```

**Почему batch лучше:**
- **Стоимость:** 2 LLM-вызова vs 20-50 (в 10-25× дешевле)
- **Скорость:** 6-10 секунд vs 60-200 секунд
- **Стабильность:** нет зацикливания, план выполняется детерминированно
- **Воспроизводимость:** один и тот же план → один и тот же результат

### 4.2 Exploration Plan Format

```json
{
  "name": "Exploration: User Registration Flow",
  "base_url": "http://localhost:3000",
  "steps": [
    {
      "id": "step_1",
      "description": "Open home page",
      "action": "navigate",
      "url": "/",
      "screenshot": true,
      "assertions": ["title contains 'App'", "nav bar is visible"]
    },
    {
      "id": "step_2", 
      "description": "Click Register button",
      "action": "click",
      "selector": "text=Register",
      "screenshot": true,
      "assertions": ["registration form is visible"]
    },
    {
      "id": "step_3",
      "description": "Fill registration form",
      "action": "fill_form",
      "fields": [
        {"selector": "input[name=email]", "value": "test@example.com"},
        {"selector": "input[name=password]", "value": "Test123!@#"}
      ],
      "screenshot": false
    },
    {
      "id": "step_4",
      "description": "Submit form",
      "action": "click",
      "selector": "button[type=submit]",
      "screenshot": true,
      "wait_after": 2,
      "assertions": ["success message is visible OR dashboard is shown"]
    }
  ],
  "max_timeout": 60
}
```

### 4.3 Exploration Runner

Python-скрипт, выполняемый внутри sandbox. Читает `exploration_plan.json`,
выполняет шаги через Playwright, на каждом шаге собирает:
- Screenshot
- Console log (новые записи)
- Network errors (failed requests)
- DOM state (опционально)

Формирует `exploration_report.json` с результатами каждого шага.

### 4.4 LLM Prompts

Два промпта:
1. **generate_exploration_plan** — на основе user_stories, tech_stack, code_files генерирует JSON-план
2. **analyse_exploration** — на основе report.json + скриншотов генерирует вердикт + список дефектов

### 4.5 Файлы Фазы 2

| Действие | Файл | Что делать |
|----------|------|-----------|
| Создать | `graphs/dev_team/tools/exploration_runner.py` | Шаблон runner-скрипта для exploration |
| Изменить | `graphs/dev_team/agents/qa.py` | Добавить `test_explore()`, `_generate_exploration_plan()`, `_analyse_exploration()` |
| Изменить | `graphs/dev_team/prompts/qa.yaml` | Добавить `generate_exploration_plan`, `analyse_exploration` |
| Создать | `tests/test_qa_exploration.py` | Unit + integration тесты |

### 4.6 Тесты для Фазы 2

| Тест | Тип | Что проверяет |
|------|-----|---------------|
| test_generate_exploration_plan | Unit | LLM генерирует валидный JSON-план |
| test_exploration_runner | Unit | Runner правильно парсит план и выполняет шаги |
| test_analyse_exploration | Unit | LLM анализирует отчёт и скриншоты |
| test_explore_happy_path | Integration | Полный цикл: план → выполнение → анализ |
| test_explore_with_failures | Integration | Exploration с ошибками → defects detected |

---

## 5. Фаза 3: Autonomous Loop (Experimental) {#5-фаза-3}

> **Статус: DEFERRED — отложена на неопределённый срок.**
> Решение принято 14.02.2026: реализуем только Фазы 1 и 2.
> Фаза 3 остаётся в документации как справочный материал,
> но реализация откладывается до момента, когда Фазы 1-2 окажутся недостаточными.

**Цель:** QA-агент автономно исследует UI в цикле Observe → Act → Evaluate.

### 5.1 Архитектура Autonomous Loop

```
┌─────────────────────────────────────────────────────────────┐
│                   Autonomous Testing Loop                     │
│                                                               │
│  ┌──────────┐    ┌──────────┐    ┌───────────┐              │
│  │ OBSERVE  │───>│   PLAN   │───>│    ACT    │              │
│  │          │    │          │    │           │              │
│  │ DOM snap │    │ LLM:     │    │ Playwright│              │
│  │ Screen-  │    │ выбирает │    │ выполняет │              │
│  │ shot     │    │ следующее│    │ действие  │              │
│  │ Console  │    │ действие │    │           │              │
│  │ Network  │    │          │    │           │              │
│  └──────────┘    └──────────┘    └─────┬─────┘              │
│       ↑                                │                     │
│       │          ┌───────────┐         │                     │
│       │          │ EVALUATE  │<────────┘                     │
│       │          │           │                               │
│       │          │ Дефект?   │── да ──> запись дефекта       │
│       │          │ Цель?     │── да ──> завершение           │
│       │          │ Лимит?    │── да ──> завершение           │
│       │          │           │                               │
│       └──────────│ нет       │                               │
│                  └───────────┘                               │
│                                                               │
│  Guardrails: max_steps, timeout, domain_allowlist,           │
│              action_blocklist, max_consecutive_failures        │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 Sandbox Session API (новый)

Для autonomous loop нужен **stateful** sandbox — открытый браузер,
с которым можно взаимодействовать пошагово.

```
POST /sessions
  Body: { language, code_files, app_start_command, timeout }
  Response: { session_id }

POST /sessions/{id}/action
  Body: { type: "click"|"fill"|"navigate"|"screenshot"|"evaluate", params: {...} }
  Response: { screenshot_base64, console_new, network_new, dom_snapshot }

GET /sessions/{id}/state
  Response: { url, title, screenshot_base64, console_log, network_errors }

DELETE /sessions/{id}
  Response: { ok }
```

**Альтернатива (проще):** не добавлять session API, а выполнять loop **внутри одного sandbox-запуска**.
Runner-скрипт запускается с WebSocket-подключением к QA-агенту.
Но это сильно усложняет sandbox и нарушает его stateless-природу.

**Рекомендация:** session API — чище архитектурно, хотя и требует больше работы.

### 5.3 Safety Guardrails

| Параметр | Значение | Назначение |
|----------|----------|------------|
| `max_steps` | 30 | Максимум шагов в одном autonomous run |
| `step_timeout` | 15s | Таймаут на один шаг (action + evaluate) |
| `total_timeout` | 300s | Общий таймаут на весь autonomous run |
| `domain_allowlist` | `["localhost"]` | Разрешённые домены |
| `action_blocklist` | `["delete", "drop", "remove"]` | Запрещённые действия |
| `max_consecutive_failures` | 5 | Остановка при серии неудач |
| `max_llm_cost_per_run` | $1.00 | Бюджет на LLM-вызовы |

### 5.4 Explainability

Каждый шаг autonomous loop записывается в журнал:

```json
{
  "step": 7,
  "observation": "Login page with email/password form",
  "reasoning": "Need to test login with invalid credentials",
  "action": {"type": "fill", "selector": "#email", "value": "invalid@"},
  "result": "Field filled, no validation error shown yet",
  "defect": null,
  "confidence": 0.8
}
```

Журнал передаётся в финальный LLM-анализ для общего вердикта.

### 5.5 Файлы Фазы 3

| Действие | Файл | Что делать |
|----------|------|-----------|
| Создать | `sandbox/session_manager.py` | Session lifecycle (create, action, state, delete) |
| Изменить | `sandbox/server.py` | Добавить session endpoints |
| Создать | `graphs/dev_team/tools/autonomous_runner.py` | Autonomous loop orchestrator |
| Изменить | `graphs/dev_team/agents/qa.py` | Добавить autonomous_test(), guardrails |
| Изменить | `graphs/dev_team/prompts/qa.yaml` | Добавить autonomous_observe, autonomous_plan, autonomous_evaluate |
| Создать | `tests/test_qa_autonomous.py` | Unit + integration тесты |

---

## 6. Оценка сложности и сроки {#6-оценка-сложности}

### Сводная таблица

| Фаза | Сложность | Срок | Надёжность | Ценность | ROI |
|------|-----------|------|------------|----------|-----|
| **Фаза 1:** Scripted E2E | Средняя | 3-5 дней | Высокая | 80% | **Отличный** |
| **Фаза 2:** Guided Exploration | Высокая | 5-8 дней | Средняя | 15% | Хороший |
| **Фаза 3:** Autonomous Loop | Очень высокая | 8-15 дней | Низкая | 5% | Плохой |

### Детализация по Фазе 1

| Задача | Время | Сложность |
|--------|-------|-----------|
| Docker-образ с Playwright | 0.5 дня | Низкая — стандартный образ Microsoft |
| Sandbox API расширение | 0.5 дня | Низкая — добавление полей + выбор образа |
| Browser test runner | 1 день | Средняя — запуск приложения + тестов в контейнере |
| QA Agent: test_ui() | 1-1.5 дня | Средняя — генерация тестов + анализ результатов |
| QA Prompts | 0.5 дня | Средняя — качество промптов критично |
| State + Graph integration | 0.25 дня | Низкая — минимальные изменения |
| Тесты | 1 день | Средняя |
| **Итого** | **~4 дня** | |

### Детализация по Фазе 2

| Задача | Время | Сложность |
|--------|-------|-----------|
| Exploration plan format + validation | 0.5 дня | Низкая |
| Exploration runner script | 1.5 дня | Средняя — обработка ошибок, устойчивость |
| LLM plan generation | 1 день | Высокая — качество плана зависит от промпта |
| LLM batch analysis | 1 день | Высокая — multimodal, много скриншотов |
| QA Agent integration | 0.5 дня | Низкая |
| Тесты | 1.5 дня | Средняя |
| Стабилизация + тюнинг промптов | 1-2 дня | Высокая |
| **Итого** | **~7 дней** | |

### Детализация по Фазе 3

| Задача | Время | Сложность |
|--------|-------|-----------|
| Sandbox Session API | 2-3 дня | Высокая — stateful sessions, lifecycle |
| Observe → Plan → Act → Evaluate loop | 2-3 дня | Очень высокая — loop stability |
| Guardrails | 1 день | Средняя |
| Explainability журнал | 0.5 дня | Низкая |
| LLM промпты (observe/plan/evaluate) | 1 день | Очень высокая — каждый шаг = LLM call |
| Тесты | 1-2 дня | Высокая |
| Стабилизация + тюнинг | 2-5 дней | Очень высокая — flaky по природе |
| **Итого** | **~12 дней** | |

### Общий срок

- **Фазы 1 + 2:** ~11 дней (рекомендуемый scope)
- **Фазы 1 + 2 + 3:** ~23 дня (с autonomous loop)

---

## 7. Целесообразность Observe → Act → Evaluate {#7-целесообразность}

### 7.1 Что это на самом деле

Observe → Act → Evaluate — это паттерн **Browser Use / Computer Use Agent**.
По сути, LLM управляет браузером в реальном времени, принимая решения на каждом шаге.

Примеры реализаций в индустрии:
- [browser-use](https://github.com/browser-use/browser-use) — open-source
- Anthropic Computer Use — встроено в Claude
- OpenAI Operator — отдельный продукт

### 7.2 Плюсы

| # | Плюс | Комментарий |
|---|------|-------------|
| 1 | **Находит неожиданные баги** | Может кликнуть туда, куда сценарий не предусмотрел |
| 2 | **Адаптивен к изменениям UI** | Не ломается при изменении вёрстки (в отличие от E2E с selector'ами) |
| 3 | **Имитирует пользователя** | Реальное поведение, а не скриптовая проверка |
| 4 | **Не требует написания тестов** | Тесты "генерируются" на лету |

### 7.3 Минусы

| # | Минус | Насколько критично | Подробности |
|---|-------|--------------------|-------------|
| 1 | **Стоимость** | **Высокая** | Каждый шаг = LLM call с vision. ~$0.01-0.05/шаг. 30 шагов = $0.30-1.50 per test run. При 10 запусках/день = $3-15/день. Для comparison: scripted E2E = $0.01-0.05 per run (один LLM-вызов) |
| 2 | **Латентность** | **Высокая** | 3-10 секунд на шаг (screenshot → LLM → response). 30 шагов = 90-300 секунд. Scripted E2E: 10-30 секунд |
| 3 | **Нестабильность** | **Критическая** | LLM может: зацикливаться (кликает одно и то же), делать бессмысленные действия, не находить элементы, генерировать невалидные selector'ы. Flaky rate: 15-30% |
| 4 | **False Positives** | **Высокая** | LLM может "обнаружить" дефект, которого нет. Или не заметить реальный дефект. Без baseline-сравнения — субъективная оценка |
| 5 | **Невоспроизводимость** | **Средняя** | Каждый run может дать разные результаты. Тот же "тест" может пройти 7 из 10 раз |
| 6 | **Сложность отладки** | **Высокая** | Когда autonomous loop находит "баг" — нужно разбираться, реальный ли он |
| 7 | **Тюнинг промптов** | **Высокая** | Каждый тип проекта (SPA, SSR, dashboard) требует разных стратегий обхода |

### 7.4 Сравнение подходов

```
                    Scripted E2E    Batch Exploration    Autonomous Loop
                    ────────────    ─────────────────    ───────────────
Стоимость/run       $0.01-0.05     $0.05-0.20           $0.30-1.50
Время/run           10-30s         20-60s               90-300s
Надёжность          95%+           80-90%               70-85%
False positive      <5%            10-15%               15-30%
Воспроизводимость   99%            90%                  70%
Покрытие            Высокое*       Среднее-высокое      Потенциально выше
Сложность реализ.   Средняя        Высокая              Очень высокая
Сложность поддержки Низкая         Средняя              Высокая

* При хорошо написанных тестах
```

### 7.5 Мой вердикт

**Scripted E2E (Фаза 1) — обязательно.** Это фундамент. Даёт 80% ценности визуального QA.
Надёжно, дёшево, воспроизводимо. LLM генерирует тесты один раз — дальше они выполняются детерминированно.

**Guided Exploration (Фаза 2) — рекомендую.** Batch exploration добавляет "exploratory testing"
без кратного роста стоимости. 2 LLM-вызова вместо 30. Хороший баланс.

**Autonomous Loop (Фаза 3) — НЕ рекомендую как обязательный.**
- Реализовать можно, **но за 60% усилий получаем 5% дополнительной ценности**
- Текущие LLM (включая vision models) недостаточно надёжны для production autonomous testing
- Индустрия (browser-use, Operator) тоже ещё в alpha/beta
- Если Scripted E2E + Batch Exploration покрывают потребности — autonomous не нужен

**Когда autonomous loop может быть оправдан:**
- Тестирование очень сложных multi-step flows (checkout, wizard, onboarding)
- Когда UI часто меняется и selector-based тесты постоянно ломаются
- Когда есть бюджет на LLM и время на тюнинг

### 7.6 Рекомендация

```
Фаза 1 (Scripted E2E)          ◄─── Реализовать сейчас
    ↓
Фаза 2 (Guided Exploration)    ◄─── Реализовать после стабилизации Фазы 1
    ↓
Стабилизация + мониторинг       ◄─── Собрать метрики, оценить coverage
    ↓
Фаза 3 (Autonomous Loop)       ◄─── Только если Фазы 1-2 недостаточно
```

---

## 8. Чеклист готовности Visual QA {#8-чеклист}

### Фаза 1 — Definition of Done  ✅ Реализовано 15.02.2026

#### Sandbox Browser Mode
- [x] `sandbox/Dockerfile.browser`: образ с Playwright + Chromium + Node.js
- [x] `sandbox/models.py`: поля browser, collect_screenshots, app_start_command, app_ready_timeout
- [x] `sandbox/executor.py`: выбор образа (browser vs standard), сбор скриншотов
- [x] `sandbox/server.py`: новые поля в response (screenshots, browser_console, network_errors)
- [x] Docker-compose: build sandbox-browser образа
- [ ] Unit-тесты: модели, выбор образа, сбор скриншотов

#### Browser Test Runner
- [x] `graphs/dev_team/tools/browser_runner.py`: шаблон runner-скрипта
- [x] Runner: установка зависимостей, запуск приложения, ожидание готовности
- [x] Runner: запуск Playwright тестов, сбор скриншотов
- [x] Runner: structured JSON output
- [ ] Unit-тесты: парсинг, генерация runner-скрипта

#### QA Agent: test_ui()
- [x] `agents/qa.py`: `has_ui()` — определение UI-проекта по tech_stack / code_files
- [x] `agents/qa.py`: `test_ui()` — генерация + выполнение + анализ
- [x] `agents/qa.py`: `_generate_browser_test()` — LLM генерирует Playwright тест
- [x] `agents/qa.py`: `_analyse_browser_results()` — LLM анализирует скриншоты + результаты
- [x] `agents/qa.py`: `merge_results()` — объединение code + browser results
- [x] `agents/qa.py`: `_extract_code_block()` — извлечение кода из LLM-ответа
- [x] `prompts/qa.yaml`: `generate_browser_test` template
- [x] `prompts/qa.yaml`: `analyse_browser_results` template
- [x] `state.py`: `browser_test_results: NotRequired[dict]`
- [x] `graph.py`: qa_agent node вызывает test_ui() при наличии UI
- [x] `USE_BROWSER_TESTING` env var (default: true)
- [ ] Unit-тесты: has_ui(), generate, analyse, merge
- [ ] Integration-тесты: полный цикл с mock sandbox

### Фаза 2 — Definition of Done

#### Exploration
- [ ] `tools/exploration_runner.py`: runner-скрипт для batch exploration
- [ ] `agents/qa.py`: `test_explore()`, `_generate_exploration_plan()`, `_analyse_exploration()`
- [ ] `prompts/qa.yaml`: `generate_exploration_plan`, `analyse_exploration`
- [ ] `USE_BROWSER_EXPLORATION` env var (default: false)
- [ ] Exploration plan JSON schema + validation
- [ ] Unit-тесты: план, runner, анализ
- [ ] Integration-тесты: полный цикл

### Фаза 3 — Definition of Done (Experimental)

#### Autonomous Loop
- [ ] `sandbox/session_manager.py`: stateful browser sessions
- [ ] Sandbox session API: POST /sessions, POST /action, GET /state, DELETE
- [ ] `tools/autonomous_runner.py`: loop orchestrator
- [ ] `agents/qa.py`: `autonomous_test()`, guardrails
- [ ] `prompts/qa.yaml`: autonomous_observe, autonomous_plan, autonomous_evaluate
- [ ] Safety: max_steps, timeout, domain_allowlist, action_blocklist
- [ ] Explainability: журнал решений
- [ ] `USE_AUTONOMOUS_TESTING` env var (default: false)
- [ ] Unit + Integration тесты

---

## Приложение: Зависимости между фазами

```
Фаза 1 (Scripted E2E)
  ├── Sandbox Browser Mode      ◄── независимый, можно начать сразу
  ├── Browser Test Runner        ◄── зависит от Sandbox Browser Mode
  └── QA Agent: test_ui()       ◄── зависит от Runner + Sandbox
      └── State + Graph          ◄── зависит от test_ui()

Фаза 2 (Guided Exploration)
  ├── Exploration Runner         ◄── зависит от Sandbox Browser Mode (Фаза 1)
  └── QA Agent: test_explore()   ◄── зависит от Runner + стабильная Фаза 1

Фаза 3 (Autonomous Loop)
  ├── Sandbox Session API        ◄── новый компонент
  ├── Autonomous Runner          ◄── зависит от Session API
  └── QA Agent: autonomous       ◄── зависит от Runner + стабильная Фаза 2
```
