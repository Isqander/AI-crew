# E2E Test Prompts for Sandbox & CI/CD Verification

## Как запускать

Через Gateway API, Frontend или напрямую через Aegra.
Перед запуском убедись, что нужные env vars выставлены:

```bash
# Для CI/CD интеграции (Module 3.8):
export USE_CI_INTEGRATION=true
export GITHUB_TOKEN=ghp_...

# Для sandbox (Module 3.7) — работает по умолчанию:
export USE_QA_SANDBOX=true
```

---

## Prompt 1: Базовый E2E (Sandbox + CI)

**Цель:** Проверить что Developer генерирует CI workflow, QA тестирует в sandbox, CI check работает.

**Для репозитория:** создать пустой GitHub-репо или использовать существующий тестовый.

```
Task: Create a simple Python calculator library with full CI/CD pipeline.

Requirements:
- A Python module `calculator.py` with functions: add, subtract, multiply, divide
- Division by zero should raise ValueError with a clear message
- A comprehensive test file `test_calculator.py` using pytest
- A `requirements.txt` with pytest
- A `.github/workflows/ci.yml` GitHub Actions workflow that:
  - Triggers on push and pull_request
  - Uses Python 3.11
  - Installs dependencies from requirements.txt
  - Runs ruff linter
  - Runs pytest with verbose output

Keep it minimal — no web framework, no database, just a library with tests and CI.
```

**Что проверяет:**
- [x] Developer генерирует `calculator.py`, `test_calculator.py`, `requirements.txt`, `.github/workflows/ci.yml`
- [x] QA запускает pytest в sandbox → тесты должны пройти
- [x] CI check node мониторит GitHub Actions (если USE_CI_INTEGRATION=true)
- [x] Весь граф: PM → Analyst → Architect → Developer → Reviewer → QA → git_commit → CI → pm_final

---

## Prompt 2: PostgreSQL E2E (Sandbox Postgres)

**Цель:** Проверить что sandbox проект может работать с PostgreSQL.

> **Внимание:** QA-агент пока НЕ передаёт `enable_postgres=True` автоматически.
> Этот промпт тестирует генерацию кода, но sandbox-тест PostgreSQL пока проходит
> только через скрипт `verify_sandbox_ci.py`.

```
Task: Create a Python FastAPI microservice for managing a to-do list with PostgreSQL.

Requirements:
- FastAPI app with CRUD endpoints: POST /todos, GET /todos, GET /todos/{id}, DELETE /todos/{id}
- SQLAlchemy ORM with a Todo model (id, title, completed, created_at)
- Database connection via DATABASE_URL environment variable
- Alembic migration for initial schema
- Tests using pytest + httpx (TestClient) with a test database
- requirements.txt with all dependencies
- .github/workflows/ci.yml with:
  - PostgreSQL service container (postgres:16-alpine)
  - Python 3.11
  - Run migrations, then pytest

Use minimal code — no authentication, no pagination.
The DATABASE_URL format: postgresql://user:password@host:port/dbname
```

**Что проверяет:**
- [x] Developer генерирует FastAPI + SQLAlchemy код
- [x] Developer создаёт CI workflow с PostgreSQL service container
- [x] QA тестирует синтаксис/импорты в sandbox (без реального PG)
- [ ] Sandbox PostgreSQL connectivity (через `verify_sandbox_ci.py`)

---

## Prompt 3: Frontend + Backend (Browser Testing)

**Цель:** Проверить Browser E2E тесты в sandbox.

```
Task: Create a minimal React + Vite counter app with E2E tests.

Requirements:
- React counter with +/- buttons and current count display
- Playwright E2E test that verifies:
  - Counter starts at 0
  - Click + increments
  - Click - decrements
- package.json with all dependencies
- .github/workflows/ci.yml

Keep it to 3-4 files maximum.
```

**Что проверяет:**
- [x] Browser sandbox image (Playwright + Chromium)
- [x] QA runs Playwright E2E tests
- [x] Screenshot collection

---

## Prompt 4: Быстрый smoke-test (минимальный)

**Цель:** Самый быстрый прогон для проверки что граф в целом работает.

```
Task: Create a Python script that prints "Hello, World!" and a test that verifies it.

Files needed:
- hello.py: print("Hello, World!")
- test_hello.py: test that captures stdout and asserts "Hello, World!"
- requirements.txt: pytest
- .github/workflows/ci.yml: basic Python CI
```

**Что проверяет:**
- [x] Минимальный прогон через весь граф
- [x] Sandbox execution (pytest)
- [x] CI workflow generation

---

## Как читать результаты

### Sandbox
В логах aegra ищи:
```
qa.test_code.execute      language=python files=4 commands=[...]
qa.test_code.sandbox_done exit_code=0 tests_passed=True
qa.test_code.verdict      approved=True
```

### CI/CD
```
ci_check.start  repo=owner/repo branch=ai/task-...
ci.wait_start   run_id=12345
ci.completed    conclusion=success elapsed_s=45.2
router.after_ci decision=pm_final ci_status=success
```

### Ошибки
```
# Sandbox не доступен:
sandbox.client.http_error error=ConnectError...

# GitHub token не задан:
ci_check.error error=...GITHUB_TOKEN...

# CI timeout:
ci.timeout run_id=12345 elapsed_s=600.0
router.after_ci decision=developer ci_status=timeout
```
