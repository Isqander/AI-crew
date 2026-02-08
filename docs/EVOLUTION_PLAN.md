# AI-crew: План эволюции платформы

> Детальный анализ всех улучшений, архитектурных решений и вариантов реализации.
> Дата: 8 февраля 2026

---

## Содержание

1. [Текущее состояние](#1-текущее-состояние)
2. [Архитектурный фундамент: куда двигаемся](#2-архитектурный-фундамент-куда-двигаемся)
3. [Улучшения из IDEAS.md](#3-улучшения-из-ideasmd)
   - 3.1 Retry логика для LLM
   - 3.2 Структурированное логирование
   - 3.3 Streaming в Frontend
   - 3.4 Конфигурация LLM в файле
   - 3.5 Code Execution Sandbox
   - 3.6 Security Agent
   - 3.7 Visual Graph Editor
   - 3.8 Self-Improvement Loop
4. [Новые возможности](#4-новые-возможности)
   - 4.1 VPS Deploy + CI/CD (DevOps Agent)
   - 4.2 CLI-агенты (Claude Code, Codex)
   - 4.3 Git-based код между агентами
   - 4.4 Доступ в интернет
   - 4.5 Визуализация графа на фронте
   - 4.6 Редактирование графа на фронте
   - 4.7 Анализ прошлых флоу (Meta-Agent)
   - 4.8 Перестройка графа под задачу
   - 4.9 Switch-Agent (маршрутизатор)
   - 4.10 Telegram-интерфейс
   - 4.11 Не-софтверные задачи (research и др.)
5. [Архитектурные решения](#5-архитектурные-решения)
   - 5.1 Mono-container vs Microservices
   - 5.2 Aegra vs Самописное
   - 5.3 Полезные фреймворки и идеи
6. [Приоритизация и зависимости](#6-приоритизация-и-зависимости)
7. [Целевая архитектура](#7-целевая-архитектура)

---

## 1. Текущее состояние

### Что есть сейчас

```
Один Docker-контейнер (prod) / docker-compose (dev):
  PostgreSQL + pgvector
  Aegra Server (FastAPI, LangGraph Runtime)
  React Frontend (Vite + Tailwind)
  Langfuse (Observability)

Граф: PM → Analyst → Architect → Developer → QA → git_commit → END
  + HITL interrupts (clarification, human_escalation)
  + Dev↔QA loop (≤3 iter) → Architect escalation → Human escalation

Агенты: каждый = class + singleton + node function
LLM: ChatOpenAI через единый прокси (OpenAI-совместимый)
Tools: GitHub API (PyGithub), filesystem (локальный workspace)
Frontend: polling каждые 2 сек (streaming API есть, но не подключён)
```

### Ключевые ограничения

| Ограничение | Влияние |
|-------------|---------|
| Код передаётся в state как `code_files: list[CodeFile]` | Не масштабируется для больших проектов |
| Один граф, один flow | Нет адаптации под тип задачи |
| Нет retry / обработки ошибок LLM | Падает при rate limit или timeout |
| Polling вместо streaming | Задержка отображения, лишние запросы |
| Нет sandbox для кода | Невозможно проверить, что код работает |
| Нет CI/CD / деплоя | Результат — только PR в GitHub |
| Нет доступа в интернет | Агенты не могут искать документацию |
| Один контейнер = один worker | Не масштабируется горизонтально |

---

## 2. Архитектурный фундамент: куда двигаемся

### Целевая картина (Vision)

```
Пользователь (Web / Telegram / API)
        │
        ▼
   ┌─────────────┐
   │  API Gateway │  ← FastAPI (или оставить Aegra)
   │  + Auth      │
   └──────┬──────┘
          │
   ┌──────▼──────┐
   │  Orchestrator│  ← Switch-Agent / Meta-Agent
   │  (LangGraph) │     выбирает flow под задачу
   └──────┬──────┘
          │
    ┌─────┼──────────┬──────────────┐
    ▼     ▼          ▼              ▼
  Dev   Research   DevOps       Custom
  Flow  Flow       Flow         Flow
    │
    ├── PM, Analyst, Architect, Dev, QA, Security
    ├── CLI-agents (Claude Code / Codex) через sandbox
    ├── Web search, Image download
    └── Deploy to VPS → ссылка на сайт
```

### Ключевой принцип: постепенная эволюция

Не надо переписывать всё сразу. Многие улучшения — аддитивные.
LangGraph остаётся ядром. Aegra можно расширять или заменять постепенно.
Переход к микросервисам — когда реально упрёмся в потолок.

---

## 3. Улучшения из IDEAS.md

### 3.1 Retry логика для LLM вызовов

**Сложность:** 1/10 | **Сроки:** 0.5 дня | **Приоритет:** Критический

**Проблема:** Любой timeout, rate limit, 500-ка от LLM API — и весь flow падает.

**Варианты реализации:**

**Вариант A: Tenacity декоратор (рекомендуется)**
```python
# В base.py — обёртка для invoke
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from openai import RateLimitError, APITimeoutError, APIConnectionError

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=4, max=60),
    retry=retry_if_exception_type((RateLimitError, APITimeoutError, APIConnectionError)),
    before_sleep=lambda retry_state: logger.warning(
        "LLM retry %s/%s after %s",
        retry_state.attempt_number,
        3,
        type(retry_state.outcome.exception()).__name__
    ),
)
def invoke_with_retry(chain, **kwargs):
    return chain.invoke(kwargs)
```

**Вариант B: LangChain built-in retry**
```python
llm = ChatOpenAI(...).with_retry(
    stop_after_attempt=3,
    wait_exponential_jitter=True,
)
```

**Вариант C: Fallback chain (основная модель → запасная)**
```python
from langchain_core.runnables import RunnableWithFallbacks

primary = get_llm(role="architect")
fallback = get_llm(model="gemini-3-flash-preview")  # Дешевле, но работает
chain = primary.with_fallbacks([fallback])
```

**Рекомендация:** Вариант A + C. Retry с exponential backoff, а при полном
отказе основной модели — fallback на более доступную.

**Изменения в коде:**
- `base.py`: добавить `invoke_with_retry()`, `with_fallbacks()`
- Каждый агент: заменить `chain.invoke()` на `invoke_with_retry(chain, ...)`

---

### 3.2 Структурированное логирование

**Сложность:** 2/10 | **Сроки:** 0.5-1 день | **Приоритет:** Высокий

**Проблема:** Текущий `logging.basicConfig` с format-строкой — сложно парсить,
фильтровать, искать проблемы.

**Варианты реализации:**

**Вариант A: structlog (рекомендуется)**
```python
import structlog

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer()  # dev
        # structlog.processors.JSONRenderer()  # prod
    ],
)

logger = structlog.get_logger()

# Использование
logger.info("agent.invoke", agent="developer", task_id="abc123",
            files_count=5, model="glm-4.7")
# → 2026-02-08T12:00:00Z [info] agent.invoke agent=developer task_id=abc123 ...
```

**Вариант B: python-json-logger**
Минимальный — просто JSON-формат для стандартного logging.

**Рекомендация:** Вариант A. structlog даёт контекстные переменные
(task_id автоматически во всех логах одного flow), рендерится красиво
в dev и как JSON в prod.

**Изменения:**
- `requirements.txt`: добавить `structlog`
- `graph.py`: `configure_logging()` → structlog конфиг
- `base.py`: `structlog.get_logger()` вместо `logging.getLogger()`
- Каждый агент: заменить logger (можно скриптом, формат вызовов похожий)

---

### 3.3 Streaming в Frontend

**Сложность:** 3/10 | **Сроки:** 1-2 дня | **Приоритет:** Высокий

**Проблема:** Frontend поллит каждые 2 секунды. При этом в `aegra.ts` уже
есть метод `streamRun()` с SSE-парсингом — просто не подключён к UI.

**Вариант реализации (один — доделать то что есть):**

```typescript
// hooks/useStreamingTask.ts
export function useStreamingTask(threadId: string) {
  const [state, setState] = useState<DevTeamState | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);

  const startStreaming = useCallback(async (input: any) => {
    setIsStreaming(true);
    const client = getAegraClient();

    for await (const event of client.streamRun(threadId, input)) {
      // event — это snapshot state после каждого node
      setState(event);
    }
    setIsStreaming(false);
  }, [threadId]);

  return { state, isStreaming, startStreaming };
}
```

**Изменения:**
- Новый хук `useStreamingTask.ts`
- `TaskDetail.tsx`: переключить с polling на streaming
- `Chat.tsx`: обновлять сообщения по мере поступления
- `ProgressTracker.tsx`: обновлять текущий агент в реальном времени
- Fallback на polling если SSE-соединение обрывается

**Нюанс:** Aegra поддерживает `stream_mode: 'values'` — отдаёт полный state
после каждого node. Для посимвольного стриминга LLM-ответов нужен
`stream_mode: 'messages'` — надо проверить, поддерживает ли это Aegra.

---

### 3.4 Вынести конфигурацию LLM в файл

**Сложность:** 2/10 | **Сроки:** 0.5-1 день | **Приоритет:** Средний

**Проблема:** Модели и эндпоинты захардкожены в `base.py` (dict `DEFAULT_MODELS`),
настраиваются только через env vars.

**Вариант реализации:**

```yaml
# config/agents.yaml
defaults:
  endpoint: default
  temperature: 0.7

endpoints:
  default:
    url: ${LLM_API_URL}
    api_key: ${LLM_API_KEY}
  backup:
    url: ${LLM_BACKUP_URL}
    api_key: ${LLM_BACKUP_KEY}

agents:
  pm:
    model: gemini-claude-sonnet-4-5-thinking
    temperature: 0.7
    endpoint: default
    fallback_model: gemini-3-flash-preview
  analyst:
    model: gemini-claude-sonnet-4-5-thinking
    temperature: 0.7
  architect:
    model: gemini-claude-opus-4-5-thinking
    temperature: 0.7
  developer:
    model: glm-4.7
    temperature: 0.2
    endpoint: default
  qa:
    model: glm-4.7
    temperature: 0.3
  security:           # Будущий агент
    model: gemini-claude-sonnet-4-5-thinking
    temperature: 0.3
```

**Загрузка:**
```python
# base.py
def load_agent_config() -> dict:
    config_path = Path(__file__).parent.parent.parent.parent / "config" / "agents.yaml"
    with open(config_path) as f:
        raw = f.read()
    # Подставить env vars: ${LLM_API_URL} → os.getenv("LLM_API_URL")
    expanded = re.sub(r'\$\{(\w+)\}', lambda m: os.getenv(m.group(1), ''), raw)
    return yaml.safe_load(expanded)
```

**Изменения:**
- Новый файл `config/agents.yaml`
- `base.py`: `load_agent_config()`, обновить `get_llm()` и `get_model_for_role()`
- Env vars сохраняются как override (приоритет: env > yaml > defaults)

---

### 3.5 Code Execution Sandbox

**Сложность:** 6/10 | **Сроки:** 3-5 дней | **Приоритет:** Высокий

**Проблема:** Сгенерированный код никто не запускает. QA делает только
статический code review по тексту. Нет гарантии, что код хотя бы запускается.

**Варианты реализации:**

**Вариант A: Docker-in-Docker sandbox (рекомендуется)**
```python
# tools/sandbox.py
import docker
import tempfile

class CodeSandbox:
    """Запуск кода в изолированном Docker-контейнере."""

    def __init__(self):
        self.client = docker.from_env()
        self.timeout = 60  # секунд
        self.memory_limit = "256m"
        self.network_disabled = True

    def run(self, code_files: list[CodeFile], command: str,
            image: str = "python:3.11-slim") -> SandboxResult:
        """
        1. Создать tmpdir с файлами
        2. Mount в контейнер
        3. Выполнить command
        4. Вернуть stdout/stderr/exit_code
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            for f in code_files:
                path = Path(tmpdir) / f["path"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f["content"])

            result = self.client.containers.run(
                image=image,
                command=command,
                volumes={tmpdir: {"bind": "/workspace", "mode": "rw"}},
                working_dir="/workspace",
                mem_limit=self.memory_limit,
                network_disabled=self.network_disabled,
                remove=True,
                timeout=self.timeout,
            )
            return SandboxResult(stdout=result, exit_code=0)
```

**Вариант B: Firecracker microVM**
Более безопасно, но сложнее в настройке. Для наших целей overkill.

**Вариант C: Удалённый sandbox на VPS**
Если VPS уже есть для деплоя — можно использовать её же.
SSH + docker run на удалённой машине. Плюс: не нужен Docker-in-Docker.

**Вариант D: Заменяется деплоем на VPS (см. 4.1)**
Если система и так деплоит на VPS, то sandbox в классическом смысле
может быть не нужен — QA-агент просто проверяет задеплоенное приложение.
Но для юнит-тестов и quick check sandbox всё равно полезен.

**Рекомендация:** Вариант A для быстрых проверок (запуск тестов, lint, import check).
Вариант C/D для полноценного тестирования через VPS.

**Как это вписывается в граф:**
```
Developer → sandbox_run → QA
              │
              ├─ tests pass → QA (code review)
              └─ tests fail → Developer (fix + retry)
```

Новый node `sandbox_run` между Developer и QA.

**Изменения:**
- Новый `tools/sandbox.py`
- Новый node `sandbox_run` в `graph.py`
- `state.py`: добавить `sandbox_results: NotRequired[dict]`
- `docker-compose.yml`: mount Docker socket или отдельный sandbox-сервис
- Для prod: нужен доступ к Docker API или отдельный sandbox-сервер

---

### 3.6 Security Agent

**Сложность:** 4/10 | **Сроки:** 2-3 дня | **Приоритет:** Высокий

**Проблема:** Никто не проверяет сгенерированный код на уязвимости.

**Реализация:**

```python
# agents/security.py
class SecurityAgent(BaseAgent):
    """
    Проверяет код на уязвимости:
    1. LLM-анализ (OWASP Top 10, secrets in code, SQL injection, XSS)
    2. Статический анализ инструментами (Bandit, Semgrep)
    3. Dependency check (Trivy, pip-audit)
    """

    def review(self, state: DevTeamState) -> dict:
        # 1. LLM-based security review
        llm_review = self._llm_review(state["code_files"])

        # 2. Tool-based checks (если sandbox доступен)
        tool_results = self._run_security_tools(state["code_files"])

        # 3. Объединить результаты
        security_issues = self._merge_findings(llm_review, tool_results)

        return {
            "security_review": security_issues,
            "issues_found": security_issues.get("critical", []),
            "current_agent": "security",
        }
```

**Место в графе:**

Два варианта:
- **A) Параллельно с QA** (после Developer): Security + QA одновременно,
  потом merge результатов → Developer если есть issues
- **B) После QA** (последовательно): QA → Security → git_commit
  Проще в реализации, но дольше по времени.

**Рекомендация:** Вариант B для начала (проще), потом мигрировать на A.

```
Developer → QA → Security → git_commit
                    │
                    └── issues → Developer
```

**Инструменты для sandbox:**
- `bandit` — Python security linter
- `semgrep` — multi-language static analysis
- `pip-audit` / `npm audit` — dependency vulnerabilities
- `gitleaks` — secrets detection

**Изменения:**
- Новый `agents/security.py`
- Новый `prompts/security.yaml`
- `graph.py`: новый node + edges
- `state.py`: `security_review: NotRequired[dict]`
- `config/agents.yaml`: настройки для security agent

---

### 3.7 Visual Graph Editor

**Сложность:** 8/10 | **Сроки:** 7-14 дней | **Приоритет:** Низкий (но крутой)

**Проблема:** Граф описан в Python-коде. Чтобы изменить flow — нужен разработчик.

**Варианты реализации:**

**Вариант A: React Flow — Read-Only визуализация (рекомендуется для начала)**

Сначала сделать просто визуализацию текущего графа (см. п. 4.5),
потом добавлять интерактивность.

**Вариант B: React Flow — Полноценный Editor**

```
Frontend (React Flow)
  │
  │ Drag-and-drop, соединения
  ▼
JSON Schema описание графа
  │
  │ POST /api/graphs/save
  ▼
Backend: JSON → LangGraph StateGraph
  │
  │ compile + validate
  ▼
Hot-reload графа
```

Это требует:
1. **JSON DSL для описания графа** — промежуточный формат между визуальным
   редактором и LangGraph Python API
2. **Graph compiler** — конвертер JSON → StateGraph Python object
3. **Hot-reload** — заменить граф без перезапуска
4. **Валидация** — проверить граф на циклы, недоступные узлы, типы state

```json
// Пример JSON DSL
{
  "nodes": [
    {"id": "pm", "type": "agent", "agent": "pm", "position": {"x": 100, "y": 0}},
    {"id": "analyst", "type": "agent", "agent": "analyst", "position": {"x": 300, "y": 0}},
    {"id": "security", "type": "agent", "agent": "security", "position": {"x": 500, "y": 100}}
  ],
  "edges": [
    {"source": "pm", "target": "analyst", "type": "direct"},
    {"source": "analyst", "target": "architect", "type": "conditional",
     "router": "should_clarify", "mapping": {"clarification": "clarification", "continue": "architect"}}
  ]
}
```

**Вариант C: Подход EvoAgentX — граф хранится в YAML/JSON, эволюционирует**

Более реалистично и полезно: граф описывается в конфигурационном файле,
Meta-Agent может его менять (см. п. 4.7-4.8), а визуальный редактор —
просто UI для редактирования этого файла.

**Рекомендация:** Поэтапно:
1. Фаза 1: Read-only визуализация (п. 4.5) — 2-3 дня
2. Фаза 2: JSON DSL + compiler — 5-7 дней
3. Фаза 3: Drag-and-drop редактор — 5-7 дней

---

### 3.8 Self-Improvement Loop

**Сложность:** 9/10 | **Сроки:** 14-21 день | **Приоритет:** Исследовательский

**Проблема:** Агенты не учатся на своих ошибках. Каждый flow начинается с нуля.

**Три уровня self-improvement:**

**Уровень 1: Memory + RAG (проще всего, уже есть pgvector)**
```
Flow завершён
    │
    ▼
Сохранить в Vector DB:
  - task description
  - решения (architecture, code)
  - ошибки и как исправили
  - feedback пользователя
    │
    ▼
Следующий flow:
  - Semantic search по похожим задачам
  - Инжектить в контекст агентов
```

**Сложность:** 4/10 | Время: 3-5 дней
Используем pgvector (уже в docker-compose). Добавляем embeddings
через OpenAI/Cohere. Каждый агент перед работой ищет релевантный опыт.

**Уровень 2: Prompt Optimization (подход DSPy)**
```
Собрать датасет:
  - input (task) → output (quality score)
    │
    ▼
DSPy Optimizer:
  - MIPROv2: предложить лучшие инструкции
  - Few-shot: выбрать лучшие примеры
  - Evaluate: автоматическая оценка
    │
    ▼
Обновить промпты в YAML
```

**Сложность:** 7/10 | Время: 7-10 дней
DSPy идеально подходит для автоматической оптимизации промптов.
Нужна метрика качества (human feedback, test pass rate, code quality score).

**Уровень 3: Graph Evolution (подход EvoAgentX)**
```
Meta-Agent анализирует:
  - Какие flows успешны, какие нет
  - Bottlenecks (где тратится больше всего итераций)
  - Unused paths
    │
    ▼
Предлагает изменения в граф:
  - Добавить/убрать агентов
  - Изменить порядок
  - Изменить условия роутинга
    │
    ▼
A/B тест:
  - Новый граф vs старый
  - На аналогичных задачах
  - Автоматический откат если хуже
```

**Сложность:** 9/10 | Время: 14-21 день

**Рекомендация:** Уровень 1 делать сейчас (низкий риск, большой impact).
Уровень 2 — после стабилизации. Уровень 3 — когда будет достаточно данных.

**Из EvoAgentX полезно взять:**
- TextGrad — оптимизация промптов через градиенты текстового фидбека
- AFlow — оптимизация топологии workflow
- Подход к evaluation: автоматические метрики + human-in-the-loop

---

## 4. Новые возможности

### 4.1 VPS Deploy + CI/CD (DevOps Agent)

**Сложность:** 7/10 | **Сроки:** 5-10 дней | **Приоритет:** Высокий

**Задача:** Система генерирует код → деплоит на VPS → выдаёт ссылку.
CI/CD через GitHub Actions. Домен через nip.io.

**Архитектура:**

```
                    AI-crew создаёт PR
                           │
                           ▼
                    GitHub Repository
                           │
                    ┌──────┴──────┐
                    │  GitHub     │
                    │  Actions    │
                    │  workflow   │
                    └──────┬──────┘
                           │ SSH / Ansible
                           ▼
                    ┌──────────────┐
                    │     VPS      │
                    │  Docker      │
                    │  Compose     │
                    │  + Traefik   │
                    └──────┬──────┘
                           │
                    http://app-name.IP.nip.io
```

**Компоненты:**

**A) DevOps Agent (новый агент в графе)**
```python
class DevOpsAgent(BaseAgent):
    """
    Генерирует:
    1. Dockerfile для проекта
    2. docker-compose.yml
    3. GitHub Actions workflow (.github/workflows/deploy.yml)
    4. Traefik labels для автоматического routing
    5. Ansible playbook для первоначальной настройки VPS
    """

    def generate_infra(self, state: DevTeamState) -> dict:
        # Анализирует tech_stack и code_files
        # Генерирует все инфраструктурные файлы
        ...

    def setup_vps(self, state: DevTeamState) -> dict:
        # SSH на VPS, установить Docker, Traefik
        # Или через Ansible playbook
        ...
```

**B) GitHub Actions Workflow (генерируется агентом)**
```yaml
# .github/workflows/deploy.yml (шаблон)
name: Deploy to VPS
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Deploy via SSH
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.VPS_HOST }}
          username: ${{ secrets.VPS_USER }}
          key: ${{ secrets.VPS_SSH_KEY }}
          script: |
            cd /opt/apps/${{ github.event.repository.name }}
            git pull
            docker compose up -d --build
```

**C) Traefik для автоматического routing**
```yaml
# В генерируемом docker-compose.yml
services:
  app:
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.${APP_NAME}.rule=Host(`${APP_NAME}.${VPS_IP}.nip.io`)"
```

**D) Инициализация VPS (один раз, скрипт или Ansible)**
```bash
# scripts/setup_vps.sh
#!/bin/bash
# Установка Docker, Traefik, настройка firewall
apt-get update && apt-get install -y docker.io docker-compose-v2
# Запуск Traefik как reverse proxy
docker compose -f /opt/traefik/docker-compose.yml up -d
```

**Место в графе:**
```
... → QA (approved) → Security → DevOps → git_commit → deploy_trigger → END
                                    │
                                    ├── Генерирует Dockerfile, CI/CD
                                    ├── Пушит всё в GitHub
                                    └── GitHub Actions деплоит на VPS
```

**Альтернатива GitHub Actions: прямой деплой через SSH из агента**
Проще, но менее надёжно и без истории деплоев.

**Необходимые секреты (в state или env):**
- `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY` — доступ к VPS
- `GITHUB_TOKEN` с правами на Actions и Secrets
- VPS IP для nip.io домена

**Изменения:**
- Новый `agents/devops.py` + `prompts/devops.yaml`
- `graph.py`: новый node `devops` в цепочке
- `state.py`: `deploy_url`, `infra_files`, `ci_cd_config`
- `tools/ssh.py`: SSH-тулзы для VPS (или использовать Ansible)
- `tools/github_actions.py`: управление GitHub Secrets и Workflows
- `scripts/setup_vps.sh`: одноразовая настройка VPS

---

### 4.2 CLI-агенты (Claude Code CLI, Codex CLI)

**Сложность:** 6/10 | **Сроки:** 3-7 дней | **Приоритет:** Высокий

**Задача:** Использовать Claude Code и Codex CLI как "мощных исполнителей"
для сложных задач разработки, вместо или в дополнение к нашему Developer-агенту.

**Почему это нужно:**
- CLI-агенты (Claude Code, Codex) значительно лучше генерируют код,
  чем наш prompt-based подход: они сами ищут по кодовой базе, сами тестируют,
  сами итерируют
- Наш Developer-агент хорош для простых задач, но для сложных рефакторингов
  или полноценных фич CLI-агенты кратно эффективнее

**Варианты интеграции:**

**Вариант A: CLI-агент на выделенной VPS (рекомендуется)**
```
AI-crew (Developer node)
    │
    │ SSH + команда запуска
    ▼
VPS с CLI-агентами
    │
    ├── git clone {repo} /workspace/{task_id}
    ├── claude --print --dangerously-skip-permissions \
    │     "В репо {repo} нужно сделать: {task}. \
    │      Требования: {requirements}. Архитектура: {architecture}. \
    │      Когда закончишь — создай PR."
    │
    └── Результат: PR URL
```

**Вариант B: Docker-контейнер с CLI-агентом**
```dockerfile
FROM ubuntu:22.04
RUN npm install -g @anthropic/claude-code
# или: pip install openai-codex-cli
ENV ANTHROPIC_API_KEY=...
ENTRYPOINT ["claude", "--print", "--dangerously-skip-permissions"]
```

**Вариант C: API-обёртка над CLI**
```python
# tools/cli_agents.py
class CLIAgentRunner:
    """Запуск CLI-агентов через subprocess или SSH."""

    async def run_claude_code(self, task: str, repo: str,
                               requirements: str) -> CLIAgentResult:
        cmd = [
            "claude", "--print", "--dangerously-skip-permissions",
            f"Клонируй {repo}, сделай: {task}. "
            f"Требования: {requirements}. Создай PR когда закончишь."
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=f"/workspace/{task_id}",
        )
        stdout, stderr = await proc.communicate()
        return CLIAgentResult(output=stdout, pr_url=extract_pr_url(stdout))
```

**Маршрутизация: когда использовать CLI-агент vs нашего Developer:**

```python
def route_to_developer(state: DevTeamState) -> Literal["developer", "cli_agent"]:
    """
    Выбор исполнителя:
    - Простые задачи (1-3 файла) → наш developer
    - Сложные задачи (рефакторинг, много файлов, существующий проект) → CLI-агент
    """
    complexity = estimate_complexity(state)
    has_existing_repo = bool(state.get("repository"))

    if complexity > 7 or has_existing_repo:
        return "cli_agent"
    return "developer"
```

**Изменения:**
- Новый `tools/cli_agents.py`
- Новый node `cli_agent` в `graph.py` (альтернативный путь вместо `developer`)
- `state.py`: `cli_agent_output`, `execution_mode: Literal["internal", "cli"]`
- Docker-образ для CLI-агентов или настройка VPS
- Секреты: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` для CLI-агентов

---

### 4.3 Git-based передача кода между агентами

**Сложность:** 5/10 | **Сроки:** 3-5 дней | **Приоритет:** Высокий

**Проблема:** Сейчас код передаётся через `code_files: list[CodeFile]` в state.
Для больших проектов (100+ файлов) это:
- Съедает контекстное окно LLM
- Замедляет сериализацию state
- Не сохраняет историю изменений

**Варианты:**

**Вариант A: Git-ветки как workspace (рекомендуется)**
```
PM создаёт ветку: ai/task-{id}
    │
Architect коммитит architecture.md в ветку
    │
Developer коммитит код в ветку
    │
QA читает код из ветки, коммитит review.md
    │
Developer читает review, фиксит, коммитит
    │
Security проверяет код из ветки
    │
git_commit: создаёт PR из этой ветки
```

В state хранится только:
```python
class DevTeamState(TypedDict):
    # Вместо code_files: list[CodeFile]
    working_branch: str          # "ai/task-20260208-123456"
    working_repo: str            # "owner/repo"
    file_manifest: list[str]     # ["src/app.py", "tests/test_app.py"]
    # ... остальное как раньше
```

Каждый агент работает с Git через тулзы:
```python
# tools/git_workspace.py
@tool
def read_file_from_branch(repo: str, branch: str, path: str) -> str: ...
@tool
def commit_to_branch(repo: str, branch: str, files: list[dict]) -> str: ...
@tool
def list_branch_files(repo: str, branch: str) -> list[str]: ...
@tool
def get_diff(repo: str, branch: str, base: str = "main") -> str: ...
```

**Вариант B: Локальная файловая система + git**
```
/workspace/{task_id}/
    ├── .git/
    ├── src/
    └── tests/
```

Каждый агент работает с локальными файлами, git автоматически
фиксирует изменения после каждого node. Удобно для CLI-агентов.

**Вариант C: Гибрид**
- Для маленьких задач (< 10 файлов): code_files в state (как сейчас)
- Для больших: git-based workspace

**Рекомендация:** Вариант A для GitHub-based workflow,
Вариант B для CLI-агентов. Они не конфликтуют.

**Изменения:**
- Новый `tools/git_workspace.py`
- `state.py`: добавить `working_branch`, `file_manifest`
- Обновить всех агентов: вместо `state["code_files"]` → читать из git
- `git_commit_node`: упростить (ветка уже готова, просто создать PR)

---

### 4.4 Доступ агентов в интернет

**Сложность:** 3/10 | **Сроки:** 2-3 дня | **Приоритет:** Высокий

**Задача:** Агенты должны уметь:
1. Искать в интернете (документацию, примеры, best practices)
2. Скачивать изображения (для фронтенд-проектов)
3. Проверять URL (ссылки в сгенерированном коде)

**Реализация:**

**A) Web Search Tool**
```python
# tools/web.py
import httpx

@tool
async def web_search(query: str, num_results: int = 5) -> str:
    """Поиск в интернете через API."""
    # Вариант 1: Tavily API (специализирован для AI-агентов)
    # Вариант 2: SerpAPI / Serper.dev
    # Вариант 3: Bing Search API
    # Вариант 4: Свой API (пользователь предоставляет)
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.tavily.com/search",
            params={"query": query, "max_results": num_results},
            headers={"Authorization": f"Bearer {SEARCH_API_KEY}"}
        )
    results = resp.json()["results"]
    return "\n\n".join(f"**{r['title']}**\n{r['content']}\nURL: {r['url']}" for r in results)
```

**B) Скачивание изображений**
```python
@tool
async def download_image(url: str, save_path: str) -> str:
    """Скачать изображение и сохранить в workspace."""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(url)
        if resp.status_code == 200:
            content_type = resp.headers.get("content-type", "")
            if "image" not in content_type:
                return f"URL не содержит изображение: {content_type}"
            path = Path(WORKSPACE_DIR) / save_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(resp.content)
            return f"Изображение сохранено: {save_path}"
    return f"Ошибка скачивания: HTTP {resp.status_code}"
```

**C) Web Fetch (чтение содержимого страниц)**
```python
@tool
async def fetch_webpage(url: str) -> str:
    """Загрузить и очистить HTML-страницу до текста."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
    # Используем html2text или trafilatura для clean text
    import trafilatura
    text = trafilatura.extract(resp.text)
    return text[:4000]  # Ограничить для контекста
```

**Подключение к агентам:**
```python
# В agents/developer.py
from dev_team.tools.web import web_search, download_image, fetch_webpage

class DeveloperAgent(BaseAgent):
    def __init__(self):
        ...
        self.tools = [web_search, download_image, fetch_webpage]
        self.llm_with_tools = self.llm.bind_tools(self.tools)
```

**Изменения:**
- Новый `tools/web.py`
- `requirements.txt`: `tavily-python`, `trafilatura`, `html2text`
- Обновить агентов: `bind_tools()` для LLM
- Env vars: `SEARCH_API_KEY` (Tavily / Serper / custom)

---

### 4.5 Визуализация графа на фронте

**Сложность:** 3/10 | **Сроки:** 2-3 дня | **Приоритет:** Средний

**Задача:** Показать текущий граф агентов в реальном времени:
какой node активен, через какие прошли, какой путь выбран.

**Реализация:**

```
Backend: /api/graph/topology → JSON описание графа
Frontend: React Flow → визуализация с анимацией
```

**Backend (API endpoint):**
```python
# В Aegra или отдельном route
@app.get("/api/graph/topology")
def get_graph_topology():
    """Вернуть структуру графа как JSON."""
    return {
        "nodes": [
            {"id": "pm", "label": "PM", "type": "agent"},
            {"id": "analyst", "label": "Analyst", "type": "agent"},
            {"id": "clarification", "label": "HITL", "type": "interrupt"},
            ...
        ],
        "edges": [
            {"source": "pm", "target": "analyst", "type": "direct"},
            {"source": "analyst", "target": "architect", "type": "conditional",
             "conditions": ["clarification", "architect"]},
            ...
        ]
    }
```

Можно генерировать автоматически из LangGraph:
```python
# LangGraph имеет встроенный метод
graph_json = graph.get_graph().to_json()
```

**Frontend (React Flow):**
```tsx
// components/GraphVisualization.tsx
import ReactFlow, { Background, Controls } from 'reactflow';
import 'reactflow/dist/style.css';

function GraphVisualization({ topology, currentAgent, completedAgents }) {
  const nodes = topology.nodes.map(n => ({
    id: n.id,
    data: { label: n.label },
    style: getNodeStyle(n, currentAgent, completedAgents),
    position: calculatePosition(n), // auto-layout
  }));

  return (
    <ReactFlow nodes={nodes} edges={edges}>
      <Background />
      <Controls />
    </ReactFlow>
  );
}
```

**Изменения:**
- `frontend/package.json`: добавить `reactflow`
- Новый компонент `GraphVisualization.tsx`
- Backend endpoint для топологии (или хардкод на фронте)
- Интеграция с `currentAgent` из state для подсветки

---

### 4.6 Редактирование графа на фронте

**Сложность:** 8/10 | **Сроки:** 10-14 дней | **Приоритет:** Низкий

**Задача:** Пользователь может менять граф через drag-and-drop.

**Почему это сложно:**
1. Нужен JSON DSL промежуточный формат (см. 3.7)
2. Нужен компилятор JSON → LangGraph StateGraph
3. Нужна валидация (циклы, типы, совместимость)
4. Hot-reload или перезапуск графа
5. UX: какие параметры можно менять, какие нет

**Поэтапный подход:**

| Фаза | Что можно | Сложность |
|------|-----------|-----------|
| 1 | Включить/выключить агентов | 3/10 |
| 2 | Менять порядок агентов | 5/10 |
| 3 | Менять параметры роутинга (N итераций QA и т.д.) | 4/10 |
| 4 | Добавлять новых агентов из библиотеки | 7/10 |
| 5 | Полный drag-and-drop с произвольными связями | 9/10 |

**Рекомендация:** Фаза 1-3 покрывают 80% потребностей.
Полный визуальный редактор — это по сути low-code платформа, и на это
нужно выделять команду.

---

### 4.7 Анализ прошлых flow (Meta-Agent)

**Сложность:** 6/10 | **Сроки:** 5-7 дней | **Приоритет:** Средний

**Задача:** Отдельный агент анализирует историю выполненных flow:
что работало хорошо, где bottlenecks, какие паттерны ошибок.

**Реализация:**

```python
# agents/meta.py
class MetaAgent(BaseAgent):
    """
    Анализирует историю flow и предлагает улучшения.
    Не участвует в основном графе — запускается отдельно.
    """

    def analyze_flows(self, flow_history: list[FlowRecord]) -> MetaAnalysis:
        """
        Анализирует:
        1. Среднее число итераций Dev↔QA (и для каких задач больше)
        2. Частоту HITL-эскалаций
        3. Типичные ошибки (по категориям)
        4. Время выполнения каждого node
        5. Качество: PR merged vs rejected
        6. Паттерны в задачах, которые решаются хорошо/плохо
        """
        ...

    def suggest_improvements(self, analysis: MetaAnalysis) -> list[Suggestion]:
        """
        Предлагает:
        - Изменения в промптах (на основе частых ошибок)
        - Изменения в графе (добавить/убрать агентов)
        - Настройки (температура, модели)
        - Новые тулзы которых не хватает
        """
        ...
```

**Данные для анализа:**
- PostgreSQL checkpoints (уже хранятся)
- Langfuse traces (стоимость, время, качество)
- Git history (PR merged/rejected)
- HITL-ответы пользователя

**UI:**
- Отдельная страница `/analytics`
- Dashboard: графики успешности, время, стоимость
- Список рекомендаций Meta-Agent

**Изменения:**
- Новый `agents/meta.py`
- Новый граф `graphs/meta/graph.py` (отдельный от dev_team)
- Frontend: страница аналитики
- API: endpoints для flow history и анализа

---

### 4.8 Перестройка графа под задачу

**Сложность:** 7/10 | **Сроки:** 5-10 дней | **Приоритет:** Средний

**Задача:** Граф адаптируется под конкретную задачу. Например:
- Для простого баг-фикса: PM → Developer → QA → commit
- Для нового проекта: PM → Analyst → Architect → Developer → QA → Security → DevOps → commit
- Для ресёрча: PM → Researcher → Analyst → PM_Summary

**Два подхода:**

**Подход A: Parametric Graph (рекомендуется)**

Один граф, но с skip-логикой:
```python
def route_after_pm(state: DevTeamState) -> str:
    task_type = state.get("task_type")  # PM определяет тип задачи
    if task_type == "bugfix":
        return "developer"   # Пропускаем analyst, architect
    elif task_type == "research":
        return "researcher"
    else:
        return "analyst"     # Полный flow
```

**Подход B: Multiple Graphs (подход crewAI Flows)**

Несколько предопределённых графов:
```python
graphs = {
    "full_dev": create_full_dev_graph(),      # PM→Analyst→...→Deploy
    "quick_fix": create_quick_fix_graph(),    # PM→Dev→QA→Commit
    "research": create_research_graph(),       # PM→Researcher→Summary
    "refactor": create_refactor_graph(),       # PM→Architect→Dev→QA
}
```

Switch-Agent выбирает граф (см. 4.9).

**Подход C: Dynamic Graph Compilation (подход EvoAgentX)**

Meta-Agent генерирует граф на лету:
```python
class GraphBuilder:
    def build_from_task(self, task_analysis: dict) -> StateGraph:
        builder = StateGraph(DevTeamState)
        for node in task_analysis["required_agents"]:
            builder.add_node(node.id, node.function)
        for edge in task_analysis["edges"]:
            builder.add_edge(edge.source, edge.target)
        return builder
```

**Рекомендация:** Подход A для начала (минимум изменений), потом B
(несколько готовых flow), а C — только если/когда реально понадобится.

---

### 4.9 Switch-Agent (маршрутизатор)

**Сложность:** 4/10 | **Сроки:** 2-3 дня | **Приоритет:** Высокий

**Задача:** Первый node графа анализирует задачу и выбирает подходящий flow.

**Реализация:**

```python
# agents/router.py (или обновить PM)
class RouterAgent(BaseAgent):
    """
    Анализирует задачу и определяет:
    1. Тип задачи (new_project, feature, bugfix, refactor, research, devops)
    2. Сложность (1-10)
    3. Нужные агенты
    4. Нужен ли CLI-агент
    5. Нужен ли deploy
    """

    def route(self, state: DevTeamState) -> dict:
        prompt = create_prompt_template(
            self.system_prompt,
            self.prompts["classify_task"]
        )
        response = (prompt | self.llm_with_structured_output).invoke(
            {"task": state["task"], "context": state.get("context", "")}
        )
        return {
            "task_type": response.task_type,
            "task_complexity": response.complexity,
            "required_agents": response.agents,
            "use_cli_agent": response.use_cli,
            "needs_deploy": response.needs_deploy,
        }
```

**В графе:**
```python
# START → router → conditional edges
builder.add_node("router", router_agent)
builder.add_edge(START, "router")
builder.add_conditional_edges("router", route_by_task_type, {
    "full_dev": "pm",
    "quick_fix": "developer",
    "research": "researcher",
    "devops_only": "devops",
})
```

**Вариант: Router как часть PM**

Можно не создавать отдельного агента, а расширить PM:
PM сначала классифицирует задачу, потом route_after_pm определяет путь.
Проще, но менее чисто архитектурно.

**Изменения:**
- Новый `agents/router.py` + `prompts/router.yaml` (или расширить PM)
- `state.py`: `task_type`, `task_complexity`, `required_agents`
- `graph.py`: новый первый node + conditional edges

---

### 4.10 Telegram-интерфейс

**Сложность:** 4/10 | **Сроки:** 3-5 дней | **Приоритет:** Средний

**Задача:** Управлять AI-crew через Telegram-бота.

**Реализация:**

```python
# telegram/bot.py
from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
router = Router()

@router.message(Command("task"))
async def create_task(message: Message):
    """Создать задачу: /task Сделать REST API для todo-app"""
    task_text = message.text.removeprefix("/task").strip()

    # Создать thread + run через Aegra API
    thread = await aegra_client.create_thread()
    run = await aegra_client.create_run(thread["thread_id"], {
        "task": task_text,
    })

    await message.reply(
        f"Задача создана!\n"
        f"Thread: {thread['thread_id']}\n"
        f"Статус: {run['status']}\n"
        f"Web: {WEB_URL}/task/{thread['thread_id']}"
    )

    # Запустить фоновый мониторинг
    asyncio.create_task(monitor_task(message.chat.id, thread["thread_id"]))

async def monitor_task(chat_id: int, thread_id: str):
    """Мониторить выполнение и отправлять обновления."""
    while True:
        state = await aegra_client.get_thread_state(thread_id)
        current = state["values"].get("current_agent")

        if current == "waiting_for_user":
            question = state["values"].get("clarification_question")
            await bot.send_message(chat_id,
                f"Нужно уточнение:\n\n{question}\n\nОтветьте на это сообщение.")
            # Ждать ответ пользователя
            response = await wait_for_reply(chat_id)
            await aegra_client.continue_thread(thread_id, {
                "clarification_response": response,
                "needs_clarification": False,
            })
        elif current == "complete":
            summary = state["values"].get("summary", "Готово!")
            pr_url = state["values"].get("pr_url")
            await bot.send_message(chat_id, f"Задача завершена!\n\n{summary}")
            if pr_url:
                await bot.send_message(chat_id, f"PR: {pr_url}")
            break

        await asyncio.sleep(5)
```

**Архитектура:**
```
Telegram Bot (отдельный сервис)
    │
    │ HTTP
    ▼
Aegra API (тот же, что для Web UI)
```

Telegram-бот — это просто ещё один клиент Aegra API.
Вся логика графа остаётся в Aegra. Бот только:
- Создаёт threads/runs
- Мониторит состояние
- Отправляет обновления
- Принимает HITL-ответы

**Деплой:** Отдельный Docker-контейнер (или process в supervisor).

**Изменения:**
- Новая директория `telegram/`
- `telegram/bot.py`, `telegram/handlers.py`
- `docker-compose.yml`: новый сервис `telegram`
- Env: `TELEGRAM_BOT_TOKEN`
- `requirements.txt`: `aiogram>=3.0`

---

### 4.11 Не-софтверные задачи (research и др.)

**Сложность:** 5/10 | **Сроки:** 3-5 дней | **Приоритет:** Средний

**Задача:** Система может не только писать код, но и делать исследования,
анализировать документы, писать статьи, сравнивать инструменты.

**Реализация: отдельный граф `research_team`**

```python
# graphs/research_team/graph.py
"""
Research flow:
  Coordinator → Researcher(s) → Analyst → Writer → Editor → END
"""

class ResearcherAgent(BaseAgent):
    """
    Исследователь: ищет информацию в интернете,
    читает документы, собирает факты.
    Tools: web_search, fetch_webpage, download_image
    """

class WriterAgent(BaseAgent):
    """
    Писатель: структурирует найденную информацию,
    пишет отчёт/статью.
    """

class EditorAgent(BaseAgent):
    """
    Редактор: проверяет факты, улучшает текст,
    добавляет ссылки.
    """
```

**Граф:**
```
Router (из 4.9) определяет тип задачи
    │
    ├── task_type == "research"
    │       │
    │       ▼
    │   Coordinator → Researcher × N → Analyst → Writer → Editor → END
    │
    ├── task_type == "dev"
    │       │
    │       ▼
    │   PM → Analyst → Architect → Developer → QA → ...
    │
    └── task_type == "devops"
            ...
```

**Регистрация в Aegra:**
```json
// aegra.json
{
  "graphs": {
    "dev_team": "./graphs/dev_team/graph.py:graph",
    "research_team": "./graphs/research_team/graph.py:graph",
    "meta_team": "./graphs/meta/graph.py:graph"
  }
}
```

**Или: один граф с meta-routing**

Если Switch-Agent (4.9) на уровне одного графа — можно иметь все агенты
в одном графе и просто не задействовать ненужных. Проще в управлении,
но граф становится большим.

**Рекомендация:** Отдельные графы для принципиально разных задач,
один Switch-Agent / Router на уровне API, который направляет в нужный граф.

**Изменения:**
- Новая директория `graphs/research_team/`
- Новые агенты: Researcher, Writer, Editor
- `aegra.json`: регистрация нового графа
- Router: поддержка нескольких графов

---

## 5. Архитектурные решения

### 5.1 Mono-container vs Microservices

**Текущее состояние:** Один Dockerfile собирает всё (Aegra + Frontend + Langfuse + PostgreSQL через supervisor).

**Когда нужны микросервисы:**
- Sandbox для исполнения кода (нужен Docker-in-Docker или отдельная VM)
- CLI-агенты (нужна изолированная среда с git, node, python)
- Telegram-бот (отдельный long-running process)
- Масштабирование (несколько workers для параллельных задач)

**Рекомендуемая эволюция:**

| Фаза | Архитектура | Когда |
|------|-------------|-------|
| **Сейчас** | Docker Compose (dev), all-in-one (prod) | Текущее |
| **Фаза 1** | Docker Compose: + sandbox container + telegram bot | После sandbox + telegram |
| **Фаза 2** | Docker Compose: + CLI-agent runner + VPS deployer | После CLI-агентов + deploy |
| **Фаза 3** | Docker Swarm / K8s (если нужно масштабирование) | Когда > 10 параллельных задач |

**Целевой docker-compose.yml (Фаза 2):**
```yaml
services:
  postgres:        # БД
  aegra:           # API + LangGraph Runtime
  frontend:        # React UI
  langfuse:        # Observability
  sandbox:         # Code execution (Docker-in-Docker)
  cli-runner:      # Claude Code / Codex CLI
  telegram:        # Telegram bot
  # redis:         # Если понадобится очередь задач
```

**Вывод:** Переходить на микросервисы постепенно. Docker Compose
покрывает потребности до 10+ параллельных задач. Kubernetes — overkill
для текущего масштаба.

---

### 5.2 Aegra vs Самописное

**Что даёт Aegra:**
- LangGraph Platform-совместимый API (threads, runs, streaming)
- PostgreSQL checkpointer (state persistence)
- SSE streaming
- Interrupt/Resume для HITL
- Совместимость с LangGraph Studio

**Чего не даёт:**
- Multi-graph routing (один assistant = один граф)
- Очереди задач (нет worker pool)
- Кастомные endpoints (только стандартный LangGraph Protocol)
- Authentication / Authorization
- WebSocket (только SSE)

**Варианты:**

**A) Остаться на Aegra + расширить (рекомендуется)**

Aegra используется как ядро для LangGraph Runtime.
Дополнительные endpoints (graph topology, analytics, Telegram webhook)
добавляются как FastAPI middleware или отдельный сервис.

```python
# Можно расширить Aegra через FastAPI mount
from agent_server.app import app as aegra_app

# Или: отдельный FastAPI на другом порту
custom_api = FastAPI()

@custom_api.get("/api/graph/topology")
def graph_topology(): ...

@custom_api.post("/api/telegram/webhook")
def telegram_webhook(): ...
```

**B) Заменить Aegra на своё**

Имеет смысл только если:
- Aegra станет bottleneck по производительности
- Нужен глубокий контроль над execution lifecycle
- Нужна кастомная авторизация

Пока этого нет — замена преждевременна. Aegra работает, обновляется,
и совместима со стандартом.

**C) Использовать LangGraph Platform (Cloud)**

Официальный LangGraph Cloud от LangChain. Полностью managed.
Минусы: стоимость, vendor lock-in, нет self-hosted.
Не подходит для нашего кейса (self-hosted, VPS deploy).

**Рекомендация:** A. Aegra как ядро, дополнения рядом.
Пересмотреть если упрёмся в ограничения.

---

### 5.3 Полезные фреймворки и идеи

#### EvoAgentX (наиболее релевантный)

**Что взять:**
- **AFlow** — алгоритм оптимизации топологии workflow.
  Идея: запускать один и тот же task на разных конфигурациях графа,
  измерять качество, эволюционировать. Применимо к нашему Meta-Agent (4.7).
- **TextGrad** — оптимизация промптов через текстовые "градиенты".
  LLM оценивает выход другого LLM и предлагает, как улучшить промпт.
  Применимо к Self-Improvement (3.8, уровень 2).
- **Evaluation layer** — автоматическая оценка качества.
  Нужно строить: code quality score, test pass rate, user satisfaction.

**Что НЕ брать:**
- Весь фреймворк целиком — он заменяет LangGraph, а нам нужен LangGraph
  для совместимости с Aegra и экосистемой.
- Их Agent layer — у нас свой, более простой и контролируемый.

#### DSPy

**Что взять:**
- **MIPROv2 optimizer** — для автоматической оптимизации промптов.
  Можно использовать как standalone библиотеку, не заменяя LangChain.
- **Metrics framework** — подход к определению метрик качества.
- **Few-shot selection** — автоматический подбор примеров для промптов.

**Интеграция:**
```python
# Можно использовать DSPy optimizer отдельно
import dspy

# Определить модуль
class AgentPrompt(dspy.Module):
    def __init__(self):
        self.generate = dspy.Predict("task, context -> requirements")

    def forward(self, task, context):
        return self.generate(task=task, context=context)

# Оптимизировать
optimizer = dspy.MIPROv2(metric=code_quality_metric)
optimized = optimizer.compile(AgentPrompt(), trainset=past_tasks)
# Экспортировать оптимизированный промпт → наш YAML
```

#### crewAI

**Что взять:**
- **Flows** — подход к организации нескольких crew в единый workflow.
  У нас аналог — Switch-Agent (4.9) + несколько графов.
- **Process types** (sequential, hierarchical) — у нас уже есть.
- **Knowledge** — интеграция RAG. Аналог нашей Vector DB + Self-Improvement.

**Что НЕ брать:**
- Фреймворк целиком — crewAI менее гибкий, чем LangGraph для кастомных графов.
- Их deployment — у нас свой через Aegra + Docker.

#### Agency Swarm

**Что взять:**
- **SendMessage tool** — идея: агенты общаются друг с другом через tool call,
  а не через жёсткие edges. Это даёт больше гибкости.
  Можно реализовать как дополнительный паттерн (для "дискуссий" между агентами).
- **State management через settings.json** — у нас более мощный подход (TypedDict + PostgreSQL).

**Что НЕ брать:**
- OpenAI Assistants API зависимость — мы используем свой прокси.
- Их оркестрацию — LangGraph более зрелый.

#### Общий вывод по фреймворкам

| Фреймворк | Брать идеи | Интегрировать как lib | Заменять наш стек |
|-----------|------------|----------------------|-------------------|
| EvoAgentX | AFlow, TextGrad, Evaluation | Выборочно | Нет |
| DSPy | MIPROv2, Metrics | Да, как optimizer | Нет |
| crewAI | Flows подход | Нет | Нет |
| Agency Swarm | SendMessage паттерн | Нет | Нет |

**LangGraph остаётся ядром.** Он наиболее гибкий, хорошо документирован,
совместим с Aegra и LangChain экосистемой.

---

## 6. Приоритизация и зависимости

### Шкала сложности (AI разрабатывает)

| Уровень | Описание | Время (AI) | Время (человек) |
|---------|----------|------------|-----------------|
| 1-2/10 | Простое изменение | 0.5-1 день | 1-2 дня |
| 3-4/10 | Средняя задача | 1-3 дня | 3-5 дней |
| 5-6/10 | Существенная доработка | 3-5 дней | 1-2 недели |
| 7-8/10 | Сложная фича | 5-10 дней | 2-4 недели |
| 9-10/10 | Исследовательская работа | 10-21 день | 1-2 месяца |

### Матрица приоритетов

```
                    IMPACT
              Low ──────── High
         ┌─────────────────────┐
    Low  │ 3.4 LLM config     │ 3.1 Retry ← ДЕЛАТЬ ПЕРВЫМ
         │ 4.6 Graph editor   │ 3.2 Logging
         │                    │ 3.3 Streaming
  EFFORT │                    │ 4.9 Switch-Agent
         │                    │
         ├─────────────────────┤
   High  │ 3.7 Visual editor  │ 4.1 VPS Deploy + CI/CD
         │ 3.8 Self-Improve   │ 4.2 CLI-агенты
         │ 4.7 Meta-Agent     │ 4.3 Git-based code
         │ 4.8 Dynamic graph  │ 3.5 Sandbox
         │                    │ 3.6 Security Agent
         └─────────────────────┘
```

### Рекомендуемый порядок реализации

**Волна 1: Фундамент (1-2 недели)**

| # | Задача | Сложность | Зависимости |
|---|--------|-----------|-------------|
| 1 | Retry логика (3.1) | 1/10 | — |
| 2 | Структурированное логирование (3.2) | 2/10 | — |
| 3 | Конфигурация LLM в файле (3.4) | 2/10 | — |
| 4 | Streaming в Frontend (3.3) | 3/10 | — |
| 5 | Switch-Agent / Router (4.9) | 4/10 | — |

**Волна 2: Инфраструктура (2-3 недели)**

| # | Задача | Сложность | Зависимости |
|---|--------|-----------|-------------|
| 6 | Git-based код (4.3) | 5/10 | — |
| 7 | Доступ в интернет (4.4) | 3/10 | — |
| 8 | Code Sandbox (3.5) | 6/10 | Docker infra |
| 9 | Security Agent (3.6) | 4/10 | 3.5 (опционально) |
| 10 | Визуализация графа (4.5) | 3/10 | — |

**Волна 3: Деплой и CLI (2-3 недели)**

| # | Задача | Сложность | Зависимости |
|---|--------|-----------|-------------|
| 11 | VPS Deploy + CI/CD (4.1) | 7/10 | 4.3 (git-based) |
| 12 | CLI-агенты (4.2) | 6/10 | 4.3, Docker infra |
| 13 | Telegram (4.10) | 4/10 | — |
| 14 | Research flow (4.11) | 5/10 | 4.9 (router) |

**Волна 4: Эволюция (3-4 недели)**

| # | Задача | Сложность | Зависимости |
|---|--------|-----------|-------------|
| 15 | Meta-Agent (4.7) | 6/10 | Данные из flow history |
| 16 | DSPy prompt optimization (3.8 L2) | 7/10 | Метрики, датасет |
| 17 | Dynamic graph (4.8) | 7/10 | 4.7, JSON DSL |
| 18 | Graph Editor (4.6) | 8/10 | 4.5, JSON DSL |
| 19 | Self-Improvement (3.8 L3) | 9/10 | 4.7, 3.8 L2 |

---

## 7. Целевая архитектура

### Диаграмма (Phase 2 — после всех волн)

```
┌─────────────────────────────────────────────────────────────────┐
│                        Пользователи                             │
│     Web UI (:5173)    │    Telegram Bot    │    API (REST/SSE)  │
└───────────┬───────────┴─────────┬─────────┴──────────┬─────────┘
            │                     │                    │
            └─────────────────────┼────────────────────┘
                                  │
                    ┌─────────────▼──────────────┐
                    │      API Gateway           │
                    │  (Aegra + Custom Routes)   │
                    │  Auth, Rate Limiting       │
                    └─────────────┬──────────────┘
                                  │
                    ┌─────────────▼──────────────┐
                    │     Router / Switch-Agent   │
                    │  Классификация задачи      │
                    └─────────────┬──────────────┘
                                  │
            ┌─────────────────────┼──────────────────────┐
            ▼                     ▼                      ▼
    ┌───────────────┐   ┌────────────────┐   ┌──────────────────┐
    │   Dev Team    │   │ Research Team  │   │   Custom Flows   │
    │   Graph       │   │ Graph          │   │   (future)       │
    │               │   │                │   │                  │
    │ PM→Analyst→   │   │ Coordinator→   │   │ User-defined     │
    │ Architect→    │   │ Researcher→    │   │ via Graph Editor │
    │ Developer→    │   │ Analyst→       │   │                  │
    │ QA→Security→  │   │ Writer→Editor  │   │                  │
    │ DevOps        │   │                │   │                  │
    └───────┬───────┘   └───────┬────────┘   └───────┬──────────┘
            │                   │                    │
            └───────────────────┼────────────────────┘
                                │
        ┌───────────┬───────────┼───────────┬──────────────┐
        ▼           ▼           ▼           ▼              ▼
  ┌──────────┐ ┌─────────┐ ┌────────┐ ┌──────────┐ ┌────────────┐
  │ LLM API  │ │ GitHub  │ │  Web   │ │ Sandbox  │ │ CLI Agents │
  │ (proxy)  │ │   API   │ │ Search │ │ (Docker) │ │ (Claude/   │
  │          │ │         │ │        │ │          │ │  Codex)    │
  └──────────┘ └─────────┘ └────────┘ └──────────┘ └────────────┘
                    │                       │              │
                    ▼                       ▼              ▼
              ┌──────────┐          ┌────────────┐   ┌──────────┐
              │ GitHub   │          │  VPS       │   │  VPS     │
              │ Actions  │──SSH────►│  (deploy)  │   │  (CLI    │
              │ CI/CD    │          │  + Traefik │   │  sandbox)│
              └──────────┘          └────────────┘   └──────────┘
                                          │
                                    http://app.IP.nip.io

        ┌───────────────────────────────────────────┐
        │              Data Layer                    │
        │  PostgreSQL + pgvector (state, memory)    │
        │  Langfuse (observability, traces)          │
        │  Redis (опционально, очередь задач)        │
        └───────────────────────────────────────────┘

        ┌───────────────────────────────────────────┐
        │            Meta Layer                      │
        │  Meta-Agent (анализ flow, рекомендации)   │
        │  DSPy Optimizer (prompt optimization)      │
        │  Graph Evolution (EvoAgentX-inspired)      │
        └───────────────────────────────────────────┘
```

### Изменения в State

```python
class DevTeamState(TypedDict):
    # === Существующие поля (без изменений) ===
    task: str
    repository: NotRequired[str]
    context: NotRequired[str]
    requirements: list[str]
    user_stories: list[UserStory]
    architecture: dict
    tech_stack: list[str]
    architecture_decisions: list[ArchitectureDecision]
    code_files: list[CodeFile]                       # Для маленьких задач
    implementation_notes: str
    review_comments: list[str]
    test_results: dict
    issues_found: list[str]
    pr_url: NotRequired[str]
    commit_sha: NotRequired[str]
    summary: str
    messages: Annotated[list[BaseMessage], add_messages]
    current_agent: str
    next_agent: NotRequired[str]
    needs_clarification: bool
    clarification_question: NotRequired[str]
    clarification_context: NotRequired[str]
    clarification_response: NotRequired[str]
    qa_iteration_count: int
    architect_escalated: bool
    error: NotRequired[str]
    retry_count: int

    # === Новые поля (Волна 1) ===
    task_type: NotRequired[str]                      # bugfix, feature, research, etc.
    task_complexity: NotRequired[int]                 # 1-10

    # === Новые поля (Волна 2) ===
    working_branch: NotRequired[str]                 # Git branch для большых задач
    working_repo: NotRequired[str]                   # Repo для git-based работы
    file_manifest: NotRequired[list[str]]            # Список файлов в ветке
    sandbox_results: NotRequired[dict]               # Результаты sandbox
    security_review: NotRequired[dict]               # Результаты security

    # === Новые поля (Волна 3) ===
    deploy_url: NotRequired[str]                     # URL задеплоенного приложения
    infra_files: NotRequired[list[CodeFile]]         # Dockerfile, CI/CD файлы
    cli_agent_output: NotRequired[str]               # Выход CLI-агента
    execution_mode: NotRequired[str]                 # "internal" | "cli"
```

### Docker Compose (целевой)

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    volumes: [postgres_data:/var/lib/postgresql/data]

  aegra:
    build: .
    ports: ["8000:8000"]
    depends_on: [postgres]

  frontend:
    build: ./frontend
    ports: ["5173:5173"]
    depends_on: [aegra]

  langfuse:
    image: langfuse/langfuse:2
    ports: ["3000:3000"]
    depends_on: [postgres]

  sandbox:
    image: docker:dind
    privileged: true
    volumes: [sandbox_workspace:/workspace]

  cli-runner:
    build: ./docker/cli-runner
    volumes: [cli_workspace:/workspace]
    environment:
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}

  telegram:
    build: ./telegram
    environment:
      TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN}
      AEGRA_API_URL: http://aegra:8000
    depends_on: [aegra]

  # redis:  # Если понадобится очередь
  #   image: redis:7-alpine

volumes:
  postgres_data:
  sandbox_workspace:
  cli_workspace:
```

---

## Итого: что делаем и зачем

| # | Фича | Зачем | Волна |
|---|-------|-------|-------|
| 1 | Retry логика | Стабильность, отказоустойчивость | 1 |
| 2 | Structured logging | Отладка, мониторинг | 1 |
| 3 | LLM config YAML | Удобство, гибкость | 1 |
| 4 | Streaming | UX, real-time | 1 |
| 5 | Switch-Agent | Адаптивность под задачу | 1 |
| 6 | Git-based code | Масштабируемость для больших проектов | 2 |
| 7 | Web access | Контекст, документация | 2 |
| 8 | Sandbox | Проверка работоспособности кода | 2 |
| 9 | Security Agent | Безопасность генерируемого кода | 2 |
| 10 | Graph visualization | UX, понимание flow | 2 |
| 11 | VPS Deploy + CI/CD | End-to-end: задача → ссылка на сайт | 3 |
| 12 | CLI-агенты | Качество кода для сложных задач | 3 |
| 13 | Telegram | Доступность, удобство | 3 |
| 14 | Research flow | Расширение возможностей | 3 |
| 15 | Meta-Agent | Аналитика, улучшение системы | 4 |
| 16 | DSPy prompts | Автоматическое улучшение промптов | 4 |
| 17 | Dynamic graph | Адаптация графа под задачу | 4 |
| 18 | Graph Editor | Low-code настройка | 4 |
| 19 | Self-Improvement | Система учится на своём опыте | 4 |

**Общая оценка:** ~60-90 дней работы с ИИ (при параллелизации),
~4-6 месяцев человеческой разработки.

**Ключевой архитектурный принцип:** Инкрементальная эволюция.
LangGraph + Aegra остаются ядром. Новые сервисы добавляются как контейнеры
в Docker Compose. Переход на K8s/Swarm — только если реально нужно масштабирование.
