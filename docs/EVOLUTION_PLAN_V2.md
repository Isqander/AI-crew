# AI-crew: План эволюции v2

> Архитектурный анализ с учётом принятых решений.
> Дата: 8 февраля 2026

---

## Содержание

1. [Принятые решения (сводка)](#1-принятые-решения-сводка)
2. [Ключевой архитектурный вопрос: граф-как-код vs граф-как-YAML/JSON](#2-ключевой-архитектурный-вопрос)
3. [Два режима работы: исполнение и редактирование](#3-два-режима-работы)
4. [Мысли по Memory/RAG](#4-мысли-по-memoryrag)
5. [Visual Graph Editor — насколько это сложно?](#5-visual-graph-editor)
6. [Архитектурные решения, влияющие на всё остальное](#6-архитектурные-решения)
7. [План: Лёгкое](#7-лёгкое)
8. [План: Среднее](#8-среднее)
9. [План: Сложное](#9-сложное)
10. [Не-изменения системы (новые агенты и применения)](#10-не-изменения-системы)
11. [Switch-Agent и мульти-граф архитектура](#11-switch-agent)
12. [Целевая архитектура](#12-целевая-архитектура)
13. [Общий таймлайн и зависимости](#13-таймлайн)

---

## 1. Принятые решения (сводка)

На основе обсуждения EVOLUTION_PLAN v1. Зафиксированные выборы:

### Лёгкое (Волна 1)
| Пункт | Решение |
|-------|---------|
| 3.1 Retry логика | Вариант A (tenacity) + C (fallback chain). Exponential backoff + fallback на доступную модель |
| 3.2 Логирование | structlog |
| 3.3 Streaming | Доделать существующий SSE (`streamRun()` уже есть в `aegra.ts`) |
| 3.4 LLM конфиг | YAML-файл `config/agents.yaml` + env overrides |
| 4.4 Интернет | A+B+C. Web search (пока бесплатное/заглушка, потом свой API), скачивание изображений, fetch |
| 4.5 Визуализация графа | React Flow, read-only |
| 4.10 Telegram | Отдельный сервис-бот через Aegra API |

### Среднее (Волна 2)
| Пункт | Решение |
|-------|---------|
| 3.5 Sandbox | Docker-in-Docker (вариант A) |
| 4.1 VPS Deploy | DevOps Agent + GitHub Actions (не прямой SSH из агента) |
| 4.2 CLI-агенты | VPS + API-обёртка, как узел в графе |
| 4.3 Git-based код | Вариант A (GitHub branches) + Вариант B (локальные файлы для CLI) |

### Сложное (Волна 3)
| Пункт | Решение |
|-------|---------|
| 3.7 + 4.6 Visual Graph Editor | React Flow Editor + YAML/JSON хранение. Две архитектурные задачи: (1) перестройка под задачу, (2) эволюция библиотеки графов |
| 3.8 Self-Improvement | Prompt Optimization (DSPy), анализ прошлых flow (Meta-Agent) |
| 4.7 Meta-Agent | Анализ flow history |
| 4.8 Перестройка графа | Подход B (multiple graphs) + Switch-Agent. Подход C (динамическая генерация) — отдельная задача на будущее |

### Не-изменения системы (отдельные от архитектуры)
| Пункт | Решение |
|-------|---------|
| 3.6 Security Agent | Часть графа. Может анализировать и задеплоенное. Рассмотреть DevSecOps |
| 4.11 Не-софтверные задачи | Research flow и др. — применение системы, учесть в архитектуре |

### Архитектура
| Пункт | Решение |
|-------|---------|
| 5.1 Микросервисы | Docker Compose по мере необходимости, цель — Фаза 2 |
| 5.2 Aegra | Остаёмся, но снимаем мораторий на изменения кода Aegra при необходимости |

---

## 2. Ключевой архитектурный вопрос: граф-как-код vs граф-как-YAML/JSON {#2-ключевой-архитектурный-вопрос}

Это решение влияет на: Visual Graph Editor, AI-driven graph evolution,
dynamic graph building, Switch-Agent, библиотеку графов — по сути на всё.

### Что именно мы описываем?

Граф в LangGraph состоит из трёх слоёв:

```
┌──────────────────────────────────────────────┐
│ Слой 1: Node Functions (логика агентов)      │  ← Всегда Python
│   pm_agent(), analyst_agent(), qa_agent()    │
│   Это классы, промпты, LLM-вызовы           │
├──────────────────────────────────────────────┤
│ Слой 2: Router Functions (условная логика)   │  ← Python или декларативное
│   route_after_qa(), should_clarify()         │
│   Условия, пороги, маппинг состояний        │
├──────────────────────────────────────────────┤
│ Слой 3: Topology (граф = кто → куда)         │  ← Вопрос про этот слой
│   add_node("pm", pm_agent)                   │
│   add_edge("pm", "analyst")                  │
│   add_conditional_edges("qa", route_after_qa)│
└──────────────────────────────────────────────┘
```

**Слой 1** (node functions) — всегда Python. Тут нет вопросов.

**Слой 2** (routers) — вот тут развилка:
- Простые роутеры (`if state["approved"]: return "commit"`) — можно описать декларативно
- Сложные (`route_after_qa` с эскалационной лестницей) — нужен Python

**Слой 3** (topology) — именно про него вопрос «код или YAML».

### Подход A: Граф-как-код (Python — source of truth)

**За:**
- Полная мощность LangGraph API без абстракций
- Сложные роутеры с произвольной Python-логикой
- Нативная поддержка IDE: автодополнение, линтинг, дебаг
- CLI-агенты (Claude Code, Codex) **отлично** модифицируют Python
- Тесты работают нативно через pytest
- Git diff читаем и осмысленен
- Нет слоя компиляции = нет нового класса багов
- Существующая кодовая база уже в этом формате

**Против:**
- Нельзя редактировать с фронтенда (нужен код → PR)
- Динамическая перестройка на лету требует `importlib` + `exec` (опасно)
- Для «библиотеки графов» нужна файловая структура с конвенциями
- Нетехническому пользователю недоступно (но у нас и нет такого юзкейса)

### Подход B: Граф-как-YAML/JSON (декларативный формат)

Пример:
```yaml
# graphs_library/dev_full.yaml
name: dev_full
description: "Full development flow with all agents"
state: DevTeamState

nodes:
  - id: pm
    function: dev_team.agents.pm.pm_agent
  - id: analyst
    function: dev_team.agents.analyst.analyst_agent
  - id: architect
    function: dev_team.agents.architect.architect_agent
  - id: developer
    function: dev_team.agents.developer.developer_agent
  - id: qa
    function: dev_team.agents.qa.qa_agent
  - id: clarification
    function: dev_team.graph.clarification_node
    interrupt_before: true
  - id: git_commit
    function: dev_team.graph.git_commit_node

edges:
  - from: START
    to: pm
  - from: pm
    to: analyst

conditional_edges:
  - from: analyst
    router: dev_team.graph.route_after_analyst
    mapping:
      clarification: clarification
      architect: architect
  - from: qa
    router: dev_team.graph.route_after_qa
    mapping:
      developer: developer
      architect_escalation: architect_escalation
      human_escalation: human_escalation
      git_commit: git_commit
      pm_final: pm_final
```

Компилятор:
```python
def compile_graph_from_yaml(yaml_path: str) -> CompiledGraph:
    config = yaml.safe_load(open(yaml_path))
    builder = StateGraph(resolve_state_class(config["state"]))

    for node in config["nodes"]:
        func = import_function(node["function"])
        builder.add_node(node["id"], func)

    for edge in config["edges"]:
        builder.add_edge(
            START if edge["from"] == "START" else edge["from"],
            END if edge["to"] == "END" else edge["to"],
        )

    for ce in config.get("conditional_edges", []):
        router = import_function(ce["router"])
        builder.add_conditional_edges(ce["from"], router, ce["mapping"])

    interrupt_nodes = [n["id"] for n in config["nodes"] if n.get("interrupt_before")]
    return builder.compile(interrupt_before=interrupt_nodes)
```

**За:**
- Visual editor на фронте читает и пишет YAML — реализуем
- AI (наши LLM-агенты) легко парсят и модифицируют структурированный YAML
- Валидация через JSON Schema — проверяемо до компиляции
- Хранение в БД для версионирования — естественно
- Динамическая компиляция в runtime — безопасно (нет `exec`)
- «Библиотека графов» = просто папка с YAML-файлами
- EvoAgentX-style эволюция — удобно мутировать структуру

**Против:**
- Нужен компилятор YAML → StateGraph (+ его тесты, + его баги)
- **Все функции (nodes, routers) всё равно в Python** — YAML ссылается на них по имени
- Это слой абстракции — усложнение для разработчика
- Сложные роутеры неудобно описывать декларативно
- Расхождение: YAML показывает «что», а Python — «как». Нужно держать в синхронизации
- Дебаг: ошибка может быть в YAML, в компиляторе или в Python — больше мест для поиска

### Подход C: Гибрид (мой вывод)

**Рекомендация: Python как source of truth + JSON-экспорт для визуализации + YAML-конфиг для библиотеки графов.**

Логика:

1. **Для существующих графов** (dev_team, research, etc.) — Python.
   Это проверено, гибко, CLI-агенты умеют с ним работать.

2. **Для визуализации на фронте** — используем то, что уже есть:
   `graph.get_graph().to_json()` (LangGraph нативно экспортирует структуру).
   Aegra уже имеет endpoint для этого (`assistant_service.py` → `aget_graph`).
   Т.е. визуализация **не требует** YAML вообще.

3. **Для «библиотеки графов»** — YAML-метаданные + Python-код:
   ```
   graphs_library/
   ├── dev_full/
   │   ├── manifest.yaml      # Имя, описание, parameters, для UI
   │   └── graph.py           # Собственно граф (Python)
   ├── dev_quick/
   │   ├── manifest.yaml
   │   └── graph.py
   └── research/
       ├── manifest.yaml
       └── graph.py
   ```
   `manifest.yaml` содержит метаданные для UI (название, описание, параметры,
   какие агенты задействованы), но **не** определяет топологию.

4. **Для AI-driven модификации** — AI меняет Python-код и создаёт PR.
   Для LLM-агентов: формируем текстовый запрос → получаем diff.
   Для CLI-агентов: просто `claude "Измени граф X так-то. Создай PR."`.

5. **Для Visual Graph Editor** (если дойдём) — отдельный вопрос (см. секцию 5).

6. **Для динамической генерации на лету (4.8 C)** — если когда-то понадобится:
   YAML-подмножество (только топология, ссылки на зарегистрированные функции).
   Это **дополнение** к основному Python-подходу, а не замена.

### Для ИИ: что проще менять — код или YAML?

Зависит от **типа ИИ**:

| ИИ-агент | Лучше с кодом | Лучше с YAML |
|----------|:---:|:---:|
| Claude Code CLI | **Да** — работает с кодовой базой нативно | Да, но избыточно |
| Codex CLI | **Да** | Да |
| Наш LLM-агент (через API) | Сложнее (надо генерить валидный Python) | **Да** — структурированный формат, меньше ошибок |
| Visual Editor (фронт) | Нет | **Да** |

**Вывод:** Для CLI-агентов код удобнее. Для наших LLM-агентов и для UI — YAML удобнее. Но поскольку мы планируем использовать CLI-агентов для сложных задач (а модификация графа — это сложная задача), **Python-first подход + YAML-метаданные** — оптимальный выбор.

### Решающий аргумент

Нужно задать вопрос: **кто чаще будет менять графы?**

- Человек в IDE (с ИИ-ассистентом) — Python отлично
- CLI-агент (Claude Code) — Python отлично
- Visual Editor на фронте — нужен YAML или JSON
- Наш внутренний Meta-Agent — YAML проще, но он может и PR с кодом создать

Учитывая, что Visual Editor — это самая сложная и самая поздняя фича,
а все остальные сценарии прекрасно работают с Python,
**Python-first — правильный выбор**.

Если потом понадобится Visual Editor, мы добавим YAML-слой **поверх**,
а не **вместо** Python. Это может выглядеть так:
- Editor читает JSON из `graph.get_graph().to_json()` (уже готово)
- Editor сохраняет изменения как YAML
- Backend компилирует YAML в StateGraph (используя реестр функций)
- Или: Editor генерирует Python-код и создаёт PR

---

## 3. Два режима работы: исполнение и редактирование {#3-два-режима-работы}

Отличная архитектурная мысль. Разделяем чётко:

### Режим 1: Исполнение задач

```
Пользователь загружает задачу
    │
    ▼
Switch-Agent классифицирует
    │
    ├── Выбирает готовый flow из библиотеки
    │   (dev_full, dev_quick, research, devops...)
    │
    └── [Будущее] Генерирует flow на лету (4.8 C)
    │
    ▼
Выбранный граф исполняется
    │
    ▼
Результат (PR, ссылка на сайт, отчёт)
```

Здесь всё просто: библиотека графов = набор скомпилированных графов,
Switch-Agent выбирает нужный. LangGraph subgraphs для этого идеально
подходят (и Aegra это уже поддерживает через `vendor/aegra/graphs/subgraph_agent/`).

### Режим 2: Редактирование библиотеки графов

Три подрежима — **все жизнеспособны, не взаимоисключающие:**

**2а. Человек в IDE (+ ИИ-ассистент)**
- Ничего менять не надо в системе
- Человек правит Python-код, запускает тесты, коммитит
- Это основной режим работы сейчас и в ближайшем будущем
- **Сложность: 0 (уже работает)**

**2б. ИИ через наши интерфейсы**
- AI-crew получает задачу: «Создай граф для CI/CD pipeline»
- Developer-агент (или CLI-агент) генерирует код графа
- Результат → PR в репозиторий AI-crew
- Человек ревьюит и мерджит

```
Задача: "Создай новый flow для data engineering задач"
    │
    ▼
AI-crew (используя dev_full flow):
    │
    ├── PM: понимает задачу (создать новый граф)
    ├── Architect: проектирует новый flow
    ├── Developer: пишет Python-код нового графа
    ├── QA: проверяет код
    └── git_commit: PR в репозиторий AI-crew
    │
    ▼
Человек ревьюит PR → merge → новый граф доступен в библиотеке
```

**Куда AI может пушить?**
- В ветку `ai/new-graph-*` → создаёт PR. Это безопасно.
- **Нельзя** пушить напрямую в main — риск сломать AI-crew.
- Даже если сломается — это git, можно откатить. Но PR-workflow лучше.

**Сложность: 2/10** (по сути уже работает, надо только:
добавить шаблон/пример нового графа + зарегистрировать в aegra.json)

**2в. Visual Editor на фронтенде**
- Самый сложный вариант (подробно в секции 5)
- Нужен если цель — «non-developer может создавать workflows»
- Для нашего текущего кейса (мы — разработчики) — **избыточен**

**Моя рекомендация: 2а + 2б**. Visual Editor отложить. Если понадобится —
реализовать как YAML-based editor поверх реестра компонентов.

---

## 4. Мысли по Memory/RAG {#4-мысли-по-memoryrag}

Ты верно подметил ключевой момент. Разберём подробнее:

### Почему «классический» RAG для кодовых задач не нужен

LLM-модели (Claude, GPT-4, etc.) уже содержат в весах:
- Паттерны проектирования
- Best practices для всех популярных фреймворков
- Типичные решения типичных задач
- Документацию к библиотекам (до даты обучения)

CLI-агенты (Claude Code, Codex) **не используют RAG** — и при этом
генерируют код лучше, чем большинство RAG-решений. Почему?
Потому что для кодирования нужен **контекст конкретного проекта**,
а не «типовые решения из базы знаний».

### Где контекст полезен (и без RAG)

| Источник контекста | Как агент его получает |
|---|---|
| Существующий код проекта | Через Git: `read_file_from_branch()`, `get_diff()` |
| Архитектурные решения | State: `architecture_decisions`, `tech_stack` |
| Предыдущие решения этого flow | State: всё накопленное PM → Analyst → Architect |
| Стиль кода проекта | Через Git: агент видит существующий код |

Git-based workflow (п. 4.3) **заменяет** RAG для большинства сценариев.
Агент просто читает файлы из ветки — и у него весь контекст.

### Где Memory/RAG может быть полезен

1. **Анализ прошлых flow** (Meta-Agent, п. 4.7):
   «Прошлый раз на похожей задаче мы застряли на Dev↔QA 5 итераций
   потому что забыли про CORS. Предупредить архитектора.»
   Это не RAG для кодирования — это RAG для **процесса**.

2. **Пользовательские предпочтения**:
   «Этот пользователь предпочитает FastAPI, а не Flask.
   Всегда хочет Docker. Не любит длинные промежуточные отчёты.»

3. **Project-specific conventions** (для мульти-проектного режима):
   «В проекте X мы используем Pydantic v2, а не v1.
   Тесты пишем через pytest-asyncio.»

### Рекомендация

- **Сейчас:** не делать RAG. Фокус на Git-based code sharing.
- **Потом (с Meta-Agent):** добавить запись и поиск по истории flow.
  Использовать pgvector (уже есть). Но это часть Meta-Agent,
  а не отдельная система.
- **Никогда:** не делать RAG «типовых решений». LLM уже это знает.

---

## 5. Visual Graph Editor — насколько это сложно? {#5-visual-graph-editor}

### Определяем scope

«Visual Graph Editor» — это на самом деле три разных фичи:

| Фича | Что делает | Кому нужна |
|-------|-----------|-----------|
| A. Визуализация | Показать граф read-only с текущим состоянием | Всем пользователям |
| B. Простое редактирование | Включить/выключить агентов, изменить параметры | Продвинутым пользователям |
| C. Полноценный редактор | Drag-and-drop, новые узлы, произвольные связи | Low-code платформа |

### Фича A: Визуализация (уже решено — делаем)

**Сложность: 2-3 дня**

Что есть:
- `graph.get_graph().to_json()` — LangGraph нативно экспортирует структуру
- Aegra уже имеет `aget_graph()` в `assistant_service.py`
- Frontend на React + Tailwind, готов к React Flow

Что нужно:
1. `npm install @xyflow/react` в frontend
2. Компонент `GraphVisualization.tsx` (~200 строк)
3. API-вызов для получения topology (или хардкод)
4. Подсветка `currentAgent` из state (уже есть в `ProgressTracker`)
5. Auto-layout (dagre или elk.js для автоматического расположения узлов)

**Это реально 2-3 дня. Не блокирует ничего.**

### Фича B: Простое редактирование

**Сложность: 5-7 дней** (при YAML/JSON подходе), **8-10 дней** (при Python подходе)

Что нужно для YAML:
1. YAML-компилятор (описан выше): ~2 дня
2. API для чтения/записи YAML: ~1 день
3. UI: формы для параметров (max_qa_iterations, enabled_agents): ~2 дня
4. Валидация + hot-reload: ~2 дня

Что нужно для Python:
1. UI: формы для параметров → генерация diff → PR: ~3 дня
2. Webhook для hot-reload после merge: ~2 дня
3. Сложнее: пользователь не видит результат мгновенно (PR-цикл)

### Фича C: Полноценный drag-and-drop редактор

**Сложность: 14-21 день**

Это фактически low-code платформа. Нужно:
1. React Flow с кастомными узлами и связями: ~5 дней
2. YAML-компилятор с полной валидацией: ~3 дня
3. Реестр компонентов (какие узлы доступны, их параметры): ~2 дня
4. Preview (запустить граф в sandbox и показать что получится): ~3 дня
5. Сохранение, версионирование, откат: ~3 дня
6. UX: undo/redo, группировка, поиск: ~3 дня
7. Тесты, edge cases, документация: ~2 дня

### Альтернатива: «Скажи ИИ — он сделает»

Ты поднял правильный вопрос:

> «Может обойтись без Visual Graph Editor и просто говорить ИИ:
> Сделай такой-то граф?»

Это **рабочий подход** и для многих сценариев **лучший**:

```
Пользователь: "Создай flow: PM → Analyst → два параллельных 
              Developer (frontend + backend) → QA → Deploy"

AI-crew (используя flow для изменения AI-crew):
    │
    ├── Architect: проектирует новый flow
    ├── Developer/CLI: создаёт Python-код графа
    ├── QA: проверяет (lint + пробный запуск)
    └── git_commit: PR
```

**Преимущества:**
- Не нужен Visual Editor (сложность = 0 от этой фичи)
- ИИ понимает контекст и может учесть тонкости
- Результат — Python-код, который можно ревьюить и тестировать
- Git-история изменений

**Недостатки:**
- Нет мгновенной обратной связи (PR-цикл)
- Нужно словами описать то, что визуально показать проще
- Ошибки ИИ менее очевидны, чем в визуальном редакторе

### Мой вывод по Visual Graph Editor

**Делаем фичу A (визуализация) — точно, в Волне 1.**

**Фичу B (простое редактирование) — можно отложить.**
Вместо неё: AI-driven graph creation (режим 2б).
Если понадобится — реализуем B как «формы параметров»
(max_qa_iterations, enabled_agents) без полного drag-and-drop.

**Фичу C (полный редактор) — не делаем, пока нет конкретного юзкейса.**
Вернёмся, если появятся non-developer пользователи.

**Архитектурное решение для будущего:**
При реализации A (визуализация) сразу закладываем возможность
перехода к B/C: храним описание графа в `manifest.yaml`,
используем React Flow с кастомными узлами.
Так что если потом понадобится редактирование — не придётся
переделывать визуализацию с нуля.

---

## 6. Архитектурные решения, влияющие на всё остальное {#6-архитектурные-решения}

### 6.1 Что нужно решить/сделать ДО начала реализации фич

Некоторые решения влияют на всё остальное и дешевле сделать их рано:

#### a) Мульти-граф архитектура (→ блокирует Switch-Agent, Research flow, библиотеку)

**Что сделать:** Настроить LangGraph subgraphs + зарегистрировать в Aegra.

LangGraph нативно поддерживает subgraphs. В Aegra уже есть пример:
`vendor/aegra/graphs/subgraph_agent/graph.py`:
```python
from react_agent import graph as react_graph
builder.add_node("subgraph_agent", react_graph)
```

Для нас это означает:
```python
# graphs/router/graph.py — мета-граф
from dev_team.graph import graph as dev_graph
from research_team.graph import graph as research_graph

builder = StateGraph(RouterState)
builder.add_node("router", router_agent)
builder.add_node("dev_team", dev_graph)        # subgraph
builder.add_node("research_team", research_graph)  # subgraph
builder.add_conditional_edges("router", route_by_type, {
    "dev": "dev_team",
    "research": "research_team",
})
```

**Или проще:** Несколько графов в `aegra.json`:
```json
{
  "graphs": {
    "dev_team": "./graphs/dev_team/graph.py:graph",
    "research_team": "./graphs/research_team/graph.py:graph",
    "router": "./graphs/router/graph.py:graph"
  }
}
```

Router выбирает `assistant_id` при создании run.

**Сложность: 2/10.** Но влияет на всё. Лучше заложить рано.

#### b) Формат библиотеки графов (→ блокирует графовый каталог, Switch-Agent)

**Что сделать:** Определить структуру `graphs/` и `manifest.yaml`.

```
graphs/
├── dev_team/
│   ├── manifest.yaml       # Метаданные для UI и Switch-Agent
│   ├── graph.py             # LangGraph граф
│   ├── state.py             # State definition
│   ├── agents/              # Агенты
│   ├── prompts/             # Промпты
│   └── tools/               # Инструменты
├── research_team/
│   ├── manifest.yaml
│   ├── graph.py
│   └── ...
└── router/
    ├── manifest.yaml
    └── graph.py
```

```yaml
# graphs/dev_team/manifest.yaml
name: "dev_team"
display_name: "Development Team"
description: "Full software development flow: from requirements to PR"
version: "1.0"
task_types: ["new_project", "feature", "bugfix", "refactor"]
agents:
  - pm
  - analyst
  - architect
  - developer
  - qa
features:
  - hitl_clarification
  - qa_escalation
  - git_commit
parameters:
  max_qa_iterations: 3
  use_security_agent: false
  deploy_after_commit: false
```

Switch-Agent читает все `manifest.yaml` и выбирает подходящий граф.

**Сложность: 1/10.** Но определяет конвенции.

#### c) structlog + retry (→ блокирует всё остальное из-за consistency)

Если мы меняем логирование и добавляем retry — лучше сделать это **до**
написания новых агентов (DevOps, Security, Router), чтобы они
сразу использовали правильные паттерны.

#### d) Aegra: policy на модификацию

**Решение принято:** мораторий снят, можем модифицировать при необходимости.

**Ценность нетронутого кода Aegra:**
- Возможность обновиться до upstream версии через `git merge`
- Гарантия, что наши проблемы — в нашем коде, а не в Aegra

**Практический подход:**
1. Создать ветку `aegra-upstream` — чистый код Aegra
2. Наша `main` содержит наши изменения
3. Обновления: merge `aegra-upstream` → `main`
4. При конфликтах: решаем в пользу наших изменений

Что может понадобиться менять в Aegra:
- Добавить auth middleware (сейчас его нет)
- Добавить custom endpoints (graph topology, analytics)
- Изменить streaming behaviour
- Добавить multi-graph routing на уровне API

**Альтернатива модификации Aegra:** FastAPI-прокси перед Aegra:
```python
# gateway/main.py
from fastapi import FastAPI
import httpx

gateway = FastAPI()

# Проксируем стандартные Aegra endpoints
@gateway.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(path: str, request: Request):
    async with httpx.AsyncClient() as client:
        resp = await client.request(...)
    return Response(content=resp.content, ...)

# Свои endpoints
@gateway.get("/api/graph/topology")
async def graph_topology(): ...

@gateway.get("/api/analytics/flows")
async def analytics(): ...
```

Это чище, чем модификация Aegra. Решает 90% потребностей.
Модифицировать Aegra — только если прокси недостаточно.

### 6.2 Что можно делать параллельно без блокировок

Эти задачи ни на что не влияют архитектурно:
- Retry логика (base.py)
- structlog (замена логгера)
- LLM config YAML (config/agents.yaml)
- Streaming на фронте (доделать существующее)
- Telegram бот (отдельный сервис)
- Web tools (tools/web.py)
- Визуализация графа (React Flow, read-only)

### 6.3 Что нужно делать последовательно

```
1. structlog + retry + LLM config  ← фундамент, сразу
2. Мульти-граф (subgraphs + manifest)  ← архитектура для Switch-Agent
3. Git-based code sharing  ← меняет всех агентов
4. Switch-Agent + Router  ← использует мульти-граф
5. Sandbox  ← новый сервис в docker-compose
6. CLI-агенты  ← зависит от sandbox инфраструктуры
7. DevOps Agent  ← зависит от git-based + sandbox
```

---

## 7. Лёгкое (Волна 1) {#7-лёгкое}

Общая оценка: **5-8 дней** при параллелизации.

### 7.1 Retry логика для LLM вызовов

**Решение:** Tenacity + fallback chain.

**Реализация:**

```python
# base.py — дополнения
from tenacity import (
    retry, stop_after_attempt, wait_exponential,
    retry_if_exception_type, before_sleep_log,
)

class RetryableError(Exception):
    """LLM errors that should be retried."""
    pass

def invoke_with_retry(chain, **kwargs):
    """Invoke LLM chain with exponential backoff retry."""
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        retry=retry_if_exception_type((
            RetryableError,
            # OpenAI-compatible errors
            # ConnectionError, TimeoutError, etc.
        )),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _invoke():
        return chain.invoke(kwargs)
    return _invoke()

def get_llm_with_fallback(role: str, **kwargs) -> BaseChatModel:
    """Get LLM with fallback chain."""
    primary = get_llm(role=role, **kwargs)
    fallback_model = config.get_fallback_model(role)
    if fallback_model:
        fallback = get_llm(model=fallback_model, **kwargs)
        return primary.with_fallbacks([fallback])
    return primary
```

**Файлы:**
- `base.py`: `invoke_with_retry()`, `get_llm_with_fallback()`
- Каждый агент: заменить `chain.invoke()` → `invoke_with_retry(chain, ...)`

**Сложность: 1/10 | 0.5 дня**

---

### 7.2 Структурированное логирование

**Решение:** structlog.

**Реализация:**

```python
# logging_config.py (новый файл)
import structlog
import os

def configure_logging():
    env_mode = os.getenv("ENV_MODE", "LOCAL").upper()

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if env_mode == "LOCAL":
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.DEBUG if env_mode == "LOCAL" else logging.INFO
        ),
    )

# Использование в агентах:
import structlog
logger = structlog.get_logger()

# В начале каждого flow:
structlog.contextvars.bind_contextvars(
    thread_id=config["configurable"]["thread_id"],
    run_id=config["configurable"]["run_id"],
)

# Далее все логи автоматически содержат thread_id и run_id:
logger.info("agent.invoke", agent="developer", files_count=5)
# → 2026-02-08T12:00:00 [info] agent.invoke agent=developer files_count=5 thread_id=abc123
```

**Файлы:**
- Новый: `graphs/dev_team/logging_config.py`
- `graph.py`: заменить `configure_logging()` → новый
- `base.py`: `structlog.get_logger()` вместо `logging.getLogger()`
- Все агенты: замена logger (механическая, одинаковая)
- `requirements.txt`: добавить `structlog`

**Сложность: 2/10 | 0.5-1 день**

---

### 7.3 Streaming в Frontend

**Решение:** Доделать существующий SSE.

**Что есть:** `aegraClient.streamRun()` в `frontend/src/api/aegra.ts` —
полностью рабочий SSE-клиент. `useTask` хук использует polling 2сек.

**Что сделать:**

1. Новый хук `useStreamingTask.ts`:
```typescript
export function useStreamingTask(threadId: string) {
  const [state, setState] = useState<TaskState | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const startStreaming = useCallback(async (input: any) => {
    setIsStreaming(true);
    setError(null);
    try {
      const client = getAegraClient();
      for await (const event of client.streamRun(threadId, input)) {
        setState(event);
      }
    } catch (err) {
      setError(err);
      // Fallback: switch to polling
    } finally {
      setIsStreaming(false);
    }
  }, [threadId]);

  return { state, isStreaming, error, startStreaming };
}
```

2. `TaskDetail.tsx`: при создании run → streaming, при reconnect → polling fallback
3. `Chat.tsx`: обновлять сообщения real-time
4. `ProgressTracker.tsx`: подсветка текущего агента без задержки

**Нюанс по Aegra:** Проверить, поддерживает ли Aegra `stream_mode: 'messages'`
для посимвольного стриминга LLM-ответов. Если нет — только `'values'`
(полный state snapshot после каждого node).

**Файлы:**
- Новый: `frontend/src/hooks/useStreamingTask.ts`
- `TaskDetail.tsx`: переключить на streaming
- `Chat.tsx`: обработка потоковых обновлений

**Сложность: 3/10 | 1-2 дня**

---

### 7.4 Конфигурация LLM в файл

**Решение:** `config/agents.yaml` + env overrides.

```yaml
# config/agents.yaml
defaults:
  endpoint: default
  temperature: 0.7
  max_tokens: 4096

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
    fallback_model: gemini-3-flash-preview
  analyst:
    model: gemini-claude-sonnet-4-5-thinking
    temperature: 0.7
  architect:
    model: gemini-claude-opus-4-5-thinking
    temperature: 0.7
    fallback_model: gemini-claude-sonnet-4-5-thinking
  developer:
    model: glm-4.7
    temperature: 0.2
    endpoint: default
  qa:
    model: glm-4.7
    temperature: 0.3
```

Приоритет: env vars > yaml > defaults.

**Файлы:**
- Новый: `config/agents.yaml`
- `base.py`: `load_agent_config()`, обновить `get_llm()`, `get_model_for_role()`
- `requirements.txt`: pyyaml уже есть

**Сложность: 2/10 | 0.5-1 день**

---

### 7.5 Доступ агентов в интернет

**Решение:** Сразу A+B+C (web search, download, fetch).

**Web Search — поэтапно:**
1. Сначала: DuckDuckGo (бесплатный, через `duckduckgo-search`).
   Или заглушка с конфигурируемым URL.
2. Потом: подключить свой поисковый API через env `SEARCH_API_URL`.

```python
# tools/web.py
import httpx
from langchain_core.tools import tool

SEARCH_API_URL = os.getenv("SEARCH_API_URL", "")

@tool
async def web_search(query: str, num_results: int = 5) -> str:
    """Search the web for information."""
    if SEARCH_API_URL:
        # Custom search API
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                SEARCH_API_URL,
                params={"q": query, "limit": num_results},
            )
            return resp.text
    else:
        # Fallback: DuckDuckGo
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=num_results))
        return "\n\n".join(
            f"**{r['title']}**\n{r['body']}\nURL: {r['href']}"
            for r in results
        )

@tool
async def download_image(url: str, save_path: str) -> str:
    """Download an image from URL and save to workspace."""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(url, timeout=30)
    if "image" not in resp.headers.get("content-type", ""):
        return f"Error: URL is not an image ({resp.headers.get('content-type')})"
    path = Path(WORKSPACE_DIR) / save_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(resp.content)
    return f"Image saved: {save_path} ({len(resp.content)} bytes)"

@tool
async def fetch_webpage(url: str) -> str:
    """Fetch and extract text content from a webpage."""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(url, timeout=30)
    import trafilatura
    text = trafilatura.extract(resp.text) or resp.text[:5000]
    return text[:4000]  # Limit for LLM context
```

**Файлы:**
- Новый: `tools/web.py`
- `requirements.txt`: `httpx`, `trafilatura`, `duckduckgo-search`
- Агенты: подключить tools через `bind_tools()` по необходимости

**Сложность: 3/10 | 1-2 дня**

---

### 7.6 Визуализация графа на фронте

**Решение:** React Flow, read-only, с подсветкой текущего агента.

**Backend:** Aegra уже имеет `aget_graph()` → `to_json()`.
Можно использовать напрямую или добавить endpoint в gateway.

**Frontend:**

```typescript
// components/GraphVisualization.tsx
import { ReactFlow, Background, Controls, MarkerType } from '@xyflow/react';
import dagre from 'dagre';

// Auto-layout через dagre
function getLayoutedElements(nodes, edges) {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: 'TB', nodesep: 80, ranksep: 100 });
  // ... calculate positions
  return { nodes: layoutedNodes, edges: layoutedEdges };
}

// Node styles based on state
function getNodeStyle(nodeId: string, currentAgent: string, completedAgents: string[]) {
  if (nodeId === currentAgent) return { background: '#22d3ee', animation: 'pulse' }; // cyan
  if (completedAgents.includes(nodeId)) return { background: '#a3e635' }; // lime
  return { background: '#334155' }; // slate
}
```

**Файлы:**
- `frontend/package.json`: добавить `@xyflow/react`, `dagre`
- Новый: `frontend/src/components/GraphVisualization.tsx`
- `TaskDetail.tsx`: добавить вкладку/панель с графом

**Сложность: 3/10 | 2-3 дня**

---

### 7.7 Telegram-интерфейс

**Решение:** Отдельный сервис через Aegra API.

```python
# telegram/bot.py
from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message
from aiogram.filters import Command

bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))
dp = Dispatcher()
router = Router()

@router.message(Command("task"))
async def create_task(message: Message):
    task_text = message.text.removeprefix("/task").strip()
    if not task_text:
        await message.reply("Использование: /task <описание задачи>")
        return

    thread = await aegra_client.create_thread()
    run = await aegra_client.create_run(
        thread["thread_id"],
        {"task": task_text},
    )
    await message.reply(
        f"Задача создана!\n"
        f"Thread: `{thread['thread_id']}`\n"
        f"Web: {WEB_URL}/task/{thread['thread_id']}",
        parse_mode="Markdown",
    )
    asyncio.create_task(
        monitor_run(message.chat.id, thread["thread_id"])
    )

@router.message(Command("status"))
async def check_status(message: Message):
    # Показать активные задачи пользователя
    ...

@router.message(Command("help"))
async def help_cmd(message: Message):
    await message.reply(
        "/task <описание> — создать задачу\n"
        "/status — статус задач\n"
        "/cancel <thread_id> — отменить задачу\n"
        "Ответ на сообщение бота — ответ на HITL-вопрос"
    )
```

**HITL через Telegram:**
Когда агент запрашивает clarification:
1. Бот отправляет вопрос пользователю
2. Пользователь отвечает (reply на сообщение бота)
3. Бот вызывает `aegra_client.continue_thread(thread_id, response)`

**Деплой:** Отдельный Docker-контейнер.

**Файлы:**
- Новая директория: `telegram/`
- `telegram/bot.py`, `telegram/handlers.py`, `telegram/aegra_client.py`
- `docker-compose.yml`: новый сервис `telegram`
- `requirements.txt` (или отдельный для telegram): `aiogram>=3.0`

**Сложность: 4/10 | 3-5 дней**

---

## 8. Среднее (Волна 2) {#8-среднее}

Общая оценка: **15-20 дней** при частичной параллелизации.

### 8.1 Code Execution Sandbox (Docker-in-Docker)

**Решение:** Вариант A — Docker sandbox.

**Архитектура:**

```
Aegra (Developer node)
    │
    │ POST /api/sandbox/run
    ▼
Sandbox Service (отдельный контейнер)
    │
    ├── Создать tmpdir с файлами
    ├── docker run <image> <command>
    │     ├── mem_limit: 256m
    │     ├── timeout: 60s
    │     ├── network: disabled (или allowlist)
    │     ├── read_only: true (кроме /workspace)
    │     └── remove: true (ephemeral)
    │
    └── Вернуть: stdout, stderr, exit_code, artifacts
```

**Как node в графе:**
```
Developer → sandbox_check → QA
               │
               ├── tests pass → QA
               └── tests fail → Developer (с ошибками)
```

**docker-compose дополнение:**
```yaml
sandbox:
  image: docker:27-dind
  privileged: true
  environment:
    DOCKER_TLS_CERTDIR: ""
  volumes:
    - sandbox_workspace:/workspace
  # API для запуска через HTTP:
  # Или: sandbox_api (наш Python-сервис) + docker socket mount
```

**Для безопасности:**
- Песочница без сети (или allowlist для pip install)
- Лимит RAM/CPU через cgroups
- Жёсткий timeout
- Контейнер удаляется после выполнения
- Никаких секретов внутри

**Файлы:**
- Новый: `tools/sandbox.py` (API клиент)
- Новый: `sandbox/` директория (сервис)
- `graph.py`: новый node `sandbox_check`
- `state.py`: `sandbox_results: NotRequired[dict]`
- `docker-compose.yml`: сервис `sandbox`

**Сложность: 6/10 | 3-5 дней**

---

### 8.2 VPS Deploy + CI/CD

**Решение:** DevOps Agent + GitHub Actions.

#### Секреты: подход к безопасности

Вопрос: что хранить в GitHub Secrets автоматически, а что нет?

**Рекомендуемое разделение:**

| Тип секрета | Пример | Кто вносит | Где хранится |
|-------------|--------|-----------|--------------|
| Инфра (не критично) | `VPS_HOST`, `APP_NAME`, `DOMAIN` | Агент автоматически | GitHub Secrets (через API) |
| Инфра (критично) | `VPS_SSH_KEY`, `VPS_USER` | Человек однократно | GitHub Secrets (вручную) |
| Приложение | `DATABASE_URL`, `API_KEY` | Зависит от проекта | GitHub Secrets или `.env` на VPS |
| Платформа AI-crew | `LLM_API_KEY`, `GITHUB_TOKEN` | Человек | env vars AI-crew |

**Workflow:**

1. DevOps Agent анализирует код → определяет нужные секреты
2. Генерирует список:
   ```
   Необходимые секреты для деплоя:
   [AUTO] VPS_HOST=31.59.58.143
   [AUTO] APP_NAME=my-todo-app
   [MANUAL] VPS_SSH_KEY — приватный SSH-ключ для доступа к VPS
   [MANUAL] DATABASE_URL — строка подключения к БД (если есть)
   ```
3. Автоматические → агент прописывает через GitHub API
4. Ручные → HITL: уведомляет пользователя через UI/Telegram:
   «Пожалуйста, добавьте следующие секреты в GitHub Secrets: ...
   Инструкция: Settings → Secrets → Actions → New repository secret»
5. Агент ждёт подтверждения, проверяет наличие секретов, продолжает

**Можно ускорить:** Для повторных деплоев (тот же VPS, те же ключи)
секреты уже настроены — агент проверяет и пропускает HITL.

**DevOps Agent в графе:**
```
... → QA (approved) → [Security] → DevOps → git_commit → END
                                      │
                                      ├── Генерирует Dockerfile
                                      ├── Генерирует docker-compose.yml
                                      ├── Генерирует .github/workflows/deploy.yml
                                      ├── Настраивает Traefik labels
                                      ├── [HITL если нужны ручные секреты]
                                      └── Результат: deploy_url в state
```

**Файлы:**
- Новый: `agents/devops.py` + `prompts/devops.yaml`
- Новый: `tools/github_actions.py` (управление secrets, workflows)
- `graph.py`: новый node
- `state.py`: `deploy_url`, `infra_files`

**Сложность: 7/10 | 5-10 дней**

---

### 8.3 CLI-агенты (Claude Code CLI, Codex CLI)

**Решение:** VPS + API-обёртка + узел в графе.

Ты правильно подметил: CLI-агент как узел в графе — это чище,
чем как отдельный сервис. Он просто ещё один «исполнитель»,
альтернатива Developer-агенту.

**Архитектура:**

```
Граф:
  ... → Architect → route_to_executor
                         │
                    ┌────┴─────┐
                    ▼          ▼
              developer    cli_agent
              (наш LLM)   (Claude Code CLI)
                    │          │
                    └────┬─────┘
                         ▼
                        QA → ...
```

**CLI-Agent node:**

```python
# agents/cli_agent.py
async def cli_agent_node(state: DevTeamState) -> dict:
    """Delegate code generation to Claude Code CLI on remote VPS."""
    runner = CLIAgentRunner(
        host=os.getenv("CLI_VPS_HOST"),
        ssh_key=os.getenv("CLI_VPS_SSH_KEY"),
    )

    result = await runner.run_claude_code(
        repo=state["working_repo"],
        branch=state["working_branch"],
        instructions=format_instructions(state),
        # Claude Code сам клонирует репо, делает изменения, коммитит
    )

    return {
        "cli_agent_output": result.output,
        "current_agent": "cli_agent",
        # Код уже в ветке (CLI-агент коммитит напрямую)
        # Файлы обновлять в state не надо — они в git
    }
```

**API-обёртка на VPS CLI-агента:**

```python
# cli_runner/server.py (на VPS с CLI-агентами)
from fastapi import FastAPI

app = FastAPI()

@app.post("/jobs")
async def create_job(request: CLIJobRequest):
    """
    1. git clone {repo} /workspace/{job_id}
    2. git checkout {branch}
    3. claude --print --dangerously-skip-permissions "{instructions}"
    4. git add . && git commit && git push
    5. Вернуть результат
    """
    workspace = f"/workspace/{request.job_id}"
    # Clone
    await run(f"git clone {request.repo} {workspace}")
    await run(f"git checkout {request.branch}", cwd=workspace)
    # Run CLI agent
    result = await run(
        f'claude --print --dangerously-skip-permissions "{request.instructions}"',
        cwd=workspace,
        timeout=600,  # 10 минут максимум
    )
    # Push results
    await run("git add . && git commit -m 'Changes by CLI agent' && git push", cwd=workspace)
    # Cleanup
    shutil.rmtree(workspace)
    return {"output": result.stdout, "exit_code": result.returncode}
```

**Роутинг Developer vs CLI-Agent:**

```python
def route_to_executor(state: DevTeamState) -> Literal["developer", "cli_agent"]:
    """Choose between our Developer agent and CLI agent."""
    # CLI-агент лучше для:
    # - Сложных задач (много файлов, рефакторинг)
    # - Существующих проектов (нужно разобраться в кодовой базе)
    # - Задач, требующих итеративного подхода

    complexity = state.get("task_complexity", 5)
    has_repo = bool(state.get("working_repo"))
    execution_mode = state.get("execution_mode", "auto")

    if execution_mode == "cli":
        return "cli_agent"
    if execution_mode == "internal":
        return "developer"

    # Auto: CLI для сложных задач с существующим репо
    if complexity >= 7 and has_repo:
        return "cli_agent"
    return "developer"
```

**Важно:** CLI-агентов надо зарегистрировать вручную (подписки Anthropic/OpenAI).
VPS тоже настраивается вручную. Агент использует уже готовую инфраструктуру.

**Файлы:**
- Новый: `agents/cli_agent.py`
- Новый: `tools/cli_runner.py` (SSH/HTTP клиент к VPS)
- Новый: `cli_runner/` (сервис для VPS с CLI-агентами)
- `graph.py`: node + conditional edge
- `state.py`: `execution_mode`, `cli_agent_output`

**Сложность: 6/10 | 3-7 дней** (без учёта настройки VPS)

---

### 8.4 Git-based передача кода между агентами

**Решение:** GitHub branches (Вариант A) + локальные файлы для CLI (Вариант B).

**Ключевое изменение:** Вместо `code_files: list[CodeFile]` в state
храним ссылку на ветку. Каждый агент читает/пишет через Git.

**State (дополнения):**
```python
# state.py — новые поля
working_branch: NotRequired[str]      # "ai/task-20260208-123456"
working_repo: NotRequired[str]        # "owner/repo"
file_manifest: NotRequired[list[str]] # ["src/app.py", "tests/test_app.py"]
```

**Новые tools:**
```python
# tools/git_workspace.py
@tool
def read_file_from_branch(repo: str, branch: str, path: str) -> str:
    """Read a file from a specific branch."""
    ...

@tool
def commit_files_to_branch(
    repo: str, branch: str,
    files: list[dict],  # [{"path": "...", "content": "..."}]
    message: str,
) -> str:
    """Commit multiple files to a branch in a single commit."""
    ...

@tool
def list_branch_files(repo: str, branch: str, path: str = "") -> list[str]:
    """List files in a branch."""
    ...

@tool
def get_branch_diff(repo: str, branch: str, base: str = "main") -> str:
    """Get diff between branch and base."""
    ...
```

**Обратная совместимость:** Для маленьких задач (без репо) —
`code_files` в state работает как раньше. Для задач с репо — Git.

**Агент PM создаёт ветку:**
```python
# В pm_agent, если задача с репо:
if repository:
    branch = f"ai/task-{timestamp}"
    create_branch(repository, branch)
    return {
        "working_branch": branch,
        "working_repo": repository,
        ...
    }
```

**git_commit_node упрощается:** Ветка уже есть, файлы уже закоммичены.
Остаётся только создать PR.

**Файлы:**
- Новый: `tools/git_workspace.py`
- `state.py`: новые поля
- Все агенты: адаптировать к чтению из git (если `working_branch` в state)
- `git_commit_node`: упростить (PR из готовой ветки)

**Сложность: 5/10 | 3-5 дней**

---

## 9. Сложное (Волна 3) {#9-сложное}

### 9.1 Visual Graph Editor (3.7 + 4.6)

**Решение:** React Flow Editor + возможность YAML/JSON хранения.
Две отдельные архитектурные задачи.

Подробный анализ — в секции 5 выше.

**Задача 1: Адаптация графа под задачу (на лету)**

Подход B из v1: multiple pre-defined graphs + Switch-Agent.
Это уже покрыто в секции 11 (Switch-Agent).

**Задача 2: Эволюция библиотеки графов**

Это **не** постоянный автоматический процесс (пока дорого).
Запускается человеком: «Meta-Agent, проанализируй последние 50 flow
и предложи улучшения графа».

**Workflow эволюции:**
```
Человек: "Проанализируй и улучши"
    │
    ▼
Meta-Agent анализирует flow history:
    ├── Средние итерации Dev↔QA: 2.3
    ├── 40% задач проходят без Analyst (simple bugfixes)
    ├── QA находит одни и те же проблемы (CORS, types)
    │
    ▼
Meta-Agent предлагает:
    ├── Создать quick_fix flow (без Analyst, без Architect)
    ├── Добавить auto-fix node перед QA (lint + типы)
    ├── Изменить промпт Developer: всегда добавлять CORS
    │
    ▼
Человек одобряет / корректирует
    │
    ▼
AI-crew реализует изменения (через dev_full flow):
    ├── Developer/CLI: создаёт новый граф / модифицирует промпты
    └── git_commit: PR
```

**Сложность: 6/10** (Meta-Agent) + **3/10** (реализация через AI-crew) = **9/10 total**

---

### 9.2 Self-Improvement Loop (3.8)

**Решение:** Prompt Optimization (DSPy) + Meta-Agent анализ.

**Уровень 1: Prompt Optimization (DSPy)**

```python
# optimization/prompt_optimizer.py
import dspy

class AgentEvaluator(dspy.Module):
    """Evaluate agent output quality."""

    def __init__(self):
        self.evaluate = dspy.Predict("task, agent_output, ground_truth -> score, feedback")

    def forward(self, task, agent_output, ground_truth=""):
        return self.evaluate(
            task=task,
            agent_output=agent_output,
            ground_truth=ground_truth,
        )

# Метрики:
# - qa_iteration_count (чем меньше — тем лучше Developer промпт)
# - test_pass_rate (sandbox results)
# - pr_merged (человек принял результат)
# - hitl_count (чем меньше clarifications — тем лучше)
```

**Когда запускать:** Вручную, после накопления 20-50 flow.
Результат: обновлённые YAML-промпты → PR.

**Уровень 2: Flow Analysis (Meta-Agent)**

Описан выше в задаче 2 секции 9.1.

**Сложность: 7/10 | 7-14 дней**

---

### 9.3 Анализ прошлых flow (4.7 Meta-Agent)

**Реализация:**

```python
# agents/meta.py
class MetaAgent(BaseAgent):
    """Offline agent for flow analysis and improvement suggestions."""

    def analyze(self, flow_records: list[FlowRecord]) -> MetaAnalysis:
        """
        Analyze:
        1. Success rate (PR merged / total)
        2. Average Dev↔QA iterations
        3. HITL frequency
        4. Common QA issues (categories)
        5. Time per agent
        6. Cost per flow (from Langfuse)
        7. Patterns: which task types succeed/fail
        """
        ...

    def suggest(self, analysis: MetaAnalysis) -> list[Suggestion]:
        """
        Suggest:
        - Prompt improvements (specific agent, specific issue)
        - Graph modifications (add/remove nodes, change routing)
        - New tools needed
        - Model changes (cheaper model where quality is sufficient)
        """
        ...
```

**Данные для анализа:**
- PostgreSQL checkpoints (state history per run)
- Langfuse traces (cost, latency, token counts)
- GitHub (PR merged/closed)
- HITL responses (patterns in clarifications)

**UI:** Отдельная страница `/analytics` с dashboard:
- График: success rate over time
- Таблица: top issues by category
- Рекомендации Meta-Agent

**Сложность: 6/10 | 5-7 дней**

---

## 10. Не-изменения системы {#10-не-изменения-системы}

### 10.1 Security Agent

Это **не архитектурное изменение**, а новый агент в существующем графе.

**Два режима работы:**

**A) Static Security Review (в основном графе):**
```
Developer → QA → Security → git_commit
                    │
                    └── critical issues → Developer
```
LLM-анализ + инструменты (bandit, semgrep, gitleaks).

**B) Runtime Security Check (с DevOps):**
```
DevOps → deploy → Security (runtime)
                       │
                       ├── Проверить задеплоенное: HTTPS, headers, ports
                       ├── Trivy scan Docker image
                       └── Результат в report
```

**DevSecOps или отдельные агенты?**

Рекомендация: **один Security Agent с разными режимами**.
Вызывается из разных точек графа с разным промптом:
- `security_static_review` — после Developer, статический анализ кода
- `security_runtime_check` — после Deploy, проверка окружения

Можно реализовать как один агент с разными промптами:
```python
class SecurityAgent(BaseAgent):
    def static_review(self, state): ...  # SAST, secrets, deps
    def runtime_check(self, state): ...  # deployed app, docker image
```

**Сложность: 4/10 | 2-3 дня**

---

### 10.2 Не-софтверные задачи (research и др.)

Это **применение системы**, а не изменение архитектуры.
Нужно:

1. Создать `graphs/research_team/` с агентами: Researcher, Writer, Editor
2. Зарегистрировать в `aegra.json`
3. Switch-Agent / Router направляет research-задачи туда
4. Обновить документацию и описание проекта

**Какие ещё задачи может решать система:**
- **Research**: анализ рынка, сравнение технологий, literature review
- **Content**: написание статей, документации, спецификаций
- **Data Analysis**: анализ данных, построение гипотез, визуализации
- **DevOps**: настройка инфраструктуры, CI/CD (отдельный flow)
- **Consulting**: архитектурный аудит, code review существующего проекта

Каждый тип задачи = отдельный граф в библиотеке.

**Сложность: 3-5/10 за каждый новый flow**

---

## 11. Switch-Agent и мульти-граф архитектура {#11-switch-agent}

### Архитектурный вопрос

Ты спрашиваешь: один огромный граф со всеми вариантами
или до входа в граф свитчим отдельной LLM?

**Три варианта:**

#### A: Один мега-граф

```python
builder = StateGraph(UniversalState)
builder.add_node("router", router_node)
builder.add_node("pm", pm_agent)
builder.add_node("analyst", analyst_agent)
builder.add_node("researcher", researcher_agent)
builder.add_node("devops", devops_agent)
# ... все агенты всех flow в одном графе
builder.add_conditional_edges("router", route_by_type, {
    "dev_full": "pm",
    "quick_fix": "developer",
    "research": "researcher",
})
```

**Проблемы:**
- State раздувается (все поля всех flow)
- Граф становится нечитаемым
- Сложно тестировать отдельные flow
- Сложно управлять (включить/выключить flow)

#### B: Subgraphs (LangGraph нативно поддерживает)

```python
# graphs/router/graph.py
from dev_team.graph import graph as dev_graph
from research_team.graph import graph as research_graph

builder = StateGraph(RouterState)
builder.add_node("router", router_agent)
builder.add_node("dev_team", dev_graph)       # Вставляем как subgraph
builder.add_node("research", research_graph)  # Другой subgraph
builder.add_conditional_edges("router", route_by_type, {
    "dev": "dev_team",
    "research": "research",
})
```

**Преимущества:**
- Каждый flow = отдельный граф (отдельный файл, тесты, state)
- Router — тонкая прослойка
- Checkpointer пробрасывается автоматически
- Streaming работает с `subgraphs=True`
- Можно добавлять новые flow без изменения существующих

**Нюанс:** State mapping — если state разных subgraphs отличается,
нужен трансформер. Но можно использовать общий базовый state +
дополнительные поля в каждом subgraph.

#### C: Роутинг на уровне API (до графа)

```python
# Router — не LangGraph node, а обычный Python
async def create_run(task: str, ...):
    # Классификация задачи LLM-кой
    task_type = await classify_task(task)

    # Выбор assistant_id
    graph_name = GRAPH_MAPPING[task_type]  # "dev_team" | "research" | etc.

    # Создание run в Aegra с нужным assistant
    thread = await aegra.create_thread()
    run = await aegra.create_run(
        thread_id=thread["thread_id"],
        assistant_id=graph_name,
        input={"task": task},
    )
```

**Преимущества:**
- Максимально просто
- Каждый граф полностью независим
- Aegra уже поддерживает несколько assistants

**Недостатки:**
- Роутинг вне LangGraph = нет checkpointing для решения роутера
- Если нужно перенаправить задачу mid-flow — сложнее

### Моя рекомендация: C + B

**Для начала: Вариант C** (роутинг на уровне API).
- Самый простой в реализации
- Каждый граф — отдельный assistant в Aegra
- Router — Python-функция или мини-LLM-вызов при создании run
- Фронтенд/Telegram вызывают router при создании задачи

**Потом: Вариант B** (subgraphs), если понадобится:
- Динамическая перемаршрутизация внутри flow
- Сложная логика выбора (зависит от промежуточных результатов)
- Единый state + единый checkpoint

**Реализация для C:**

```python
# api/router.py
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

class TaskClassification(BaseModel):
    task_type: str       # "dev_full", "dev_quick", "research", "devops"
    complexity: int      # 1-10
    reasoning: str

async def classify_task(task: str, context: str = "") -> TaskClassification:
    """Classify task and determine which graph to use."""
    llm = get_llm(role="router", temperature=0.1)
    structured_llm = llm.with_structured_output(TaskClassification)

    # Получить список доступных графов из manifest.yaml файлов
    available_graphs = load_graph_manifests()
    graphs_description = format_graphs_for_prompt(available_graphs)

    result = structured_llm.invoke(
        f"Classify this task and choose the appropriate workflow.\n\n"
        f"Task: {task}\n"
        f"Context: {context}\n\n"
        f"Available workflows:\n{graphs_description}"
    )
    return result
```

**Файлы:**
- Новый: `api/router.py`
- Обновить: `aegra.json` (несколько графов)
- Фронтенд: при создании задачи → вызвать router → создать run с нужным assistant
- Telegram: аналогично

**Сложность: 4/10 | 2-3 дня**

---

## 12. Целевая архитектура {#12-целевая-архитектура}

### Диаграмма (после всех волн)

```
┌──────────────────────────────────────────────────────────────┐
│                      Пользователи                             │
│    Web UI        Telegram Bot       API (REST/SSE)            │
│    (:5173)       (aiogram)          (для интеграций)          │
└──────┬──────────────┬────────────────────┬───────────────────┘
       │              │                    │
       └──────────────┼────────────────────┘
                      │
        ┌─────────────▼──────────────┐
        │   [Gateway / Proxy]        │  ← Можно оставить Aegra напрямую
        │   Auth, Rate Limiting      │     или FastAPI-прокси перед Aegra
        └─────────────┬──────────────┘
                      │
        ┌─────────────▼──────────────┐
        │   Task Router              │  ← Python-функция + LLM classification
        │   classify_task()          │     На уровне API, до графа
        └─────────────┬──────────────┘
                      │
       ┌──────────────┼──────────────────────┐
       ▼              ▼                      ▼
┌────────────┐ ┌─────────────┐ ┌──────────────────┐
│ dev_team   │ │ research    │ │ Новые flow       │
│ graph      │ │ graph       │ │ (по мере роста)  │
│            │ │             │ │                  │
│ PM→Analyst │ │ Coordinator │ │ data_engineering │
│ →Architect │ │ →Researcher │ │ devops_only      │
│ →Dev/CLI   │ │ →Analyst    │ │ content          │
│ →QA→Sec    │ │ →Writer     │ │ ...              │
│ →DevOps    │ │ →Editor     │ │                  │
└─────┬──────┘ └──────┬──────┘ └────────┬─────────┘
      │               │                 │
      └───────────────┼─────────────────┘
                      │
   ┌──────────┬───────┼──────────┬──────────────┐
   ▼          ▼       ▼          ▼              ▼
┌───────┐ ┌───────┐ ┌──────┐ ┌────────┐ ┌──────────┐
│ LLM   │ │GitHub │ │ Web  │ │Sandbox │ │CLI Agents│
│ API   │ │ API   │ │Search│ │(Docker)│ │(Claude/  │
│(proxy)│ │       │ │      │ │        │ │ Codex)   │
└───────┘ └───┬───┘ └──────┘ └───┬────┘ └────┬─────┘
              │                   │           │
              ▼                   ▼           ▼
        ┌──────────┐       ┌──────────┐ ┌──────────┐
        │ GitHub   │       │   VPS    │ │   VPS    │
        │ Actions  │──────►│ (deploy) │ │  (CLI    │
        │ CI/CD    │  SSH  │ Traefik  │ │ sandbox) │
        └──────────┘       └────┬─────┘ └──────────┘
                                │
                          app.IP.nip.io

┌─────────────────────────────────────────────────┐
│                 Data Layer                        │
│  PostgreSQL + pgvector                            │
│  Langfuse (traces, costs)                         │
│  structlog → JSON → [Loki/ELK если нужно]        │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│           Meta Layer (запускается вручную)        │
│  Meta-Agent: анализ flow history                  │
│  DSPy Optimizer: prompt optimization              │
│  [Будущее] Graph Evolution                        │
└─────────────────────────────────────────────────┘
```

### Docker Compose (целевой, Фаза 2)

```yaml
services:
  # === Core ===
  postgres:
    image: pgvector/pgvector:pg16
    volumes: [postgres_data:/var/lib/postgresql/data]
    ports: ["5432:5432"]

  aegra:
    build: .
    ports: ["8000:8000"]
    depends_on: [postgres]
    environment:
      DATABASE_URI: postgresql://...
      LLM_API_URL: ${LLM_API_URL}
      LLM_API_KEY: ${LLM_API_KEY}

  frontend:
    build: ./frontend
    ports: ["5173:5173"]
    depends_on: [aegra]

  # === Observability ===
  langfuse:
    image: langfuse/langfuse:2
    ports: ["3000:3000"]
    depends_on: [postgres]

  # === Execution Plane ===
  sandbox:
    build: ./sandbox
    privileged: true  # для Docker-in-Docker
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - sandbox_workspace:/workspace

  # === Interfaces ===
  telegram:
    build: ./telegram
    environment:
      TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN}
      AEGRA_API_URL: http://aegra:8000
    depends_on: [aegra]

  # === CLI Agents (опционально, может быть на отдельном VPS) ===
  # cli-runner:
  #   build: ./cli_runner
  #   environment:
  #     ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}

volumes:
  postgres_data:
  sandbox_workspace:
```

### Изменения в State (суммарно)

```python
class DevTeamState(TypedDict):
    # ========= Существующие поля (без изменений) =========
    task: str
    repository: NotRequired[str]
    context: NotRequired[str]
    requirements: list[str]
    user_stories: list[UserStory]
    architecture: dict
    tech_stack: list[str]
    architecture_decisions: list[ArchitectureDecision]
    code_files: list[CodeFile]               # Сохраняем для маленьких задач
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

    # ========= Волна 1 =========
    task_type: NotRequired[str]              # "new_project", "bugfix", "research"
    task_complexity: NotRequired[int]        # 1-10

    # ========= Волна 2 =========
    # Git-based code sharing
    working_branch: NotRequired[str]         # "ai/task-20260208-123456"
    working_repo: NotRequired[str]           # "owner/repo"
    file_manifest: NotRequired[list[str]]    # Файлы в ветке

    # Sandbox
    sandbox_results: NotRequired[dict]       # {stdout, stderr, exit_code, tests_passed}

    # Security
    security_review: NotRequired[dict]       # {critical, warnings, info}

    # Deploy
    deploy_url: NotRequired[str]             # "http://app.31.59.58.143.nip.io"
    infra_files: NotRequired[list[CodeFile]] # Dockerfile, CI/CD, docker-compose

    # CLI-agents
    cli_agent_output: NotRequired[str]
    execution_mode: NotRequired[str]         # "auto" | "internal" | "cli"
```

---

## 13. Общий таймлайн и зависимости {#13-таймлайн}

### Порядок реализации

```
Неделя 1-2: Фундамент
├── [P] Retry логика (0.5 дня)                    ← Параллельно
├── [P] structlog (0.5-1 день)                     ← Параллельно
├── [P] LLM config YAML (0.5-1 день)              ← Параллельно
├── [P] Web tools (1-2 дня)                        ← Параллельно
├── [P] Визуализация графа / React Flow (2-3 дня) ← Параллельно
├── [S] Streaming на фронте (1-2 дня)             ← После знакомства с UI
└── [S] Мульти-граф + manifest.yaml (1-2 дня)     ← Архитектурная основа

Неделя 3-4: Инфраструктура
├── [P] Telegram бот (3-5 дней)                    ← Параллельно
├── [S] Git-based code sharing (3-5 дней)          ← Меняет всех агентов
├── [S] Switch-Agent / Router (2-3 дня)            ← После мульти-граф

Неделя 5-7: Execution Plane
├── [S] Code Sandbox (3-5 дней)                    ← После git-based
├── [S] CLI-агенты (3-7 дней)                      ← После git-based + sandbox infra
├── [S] DevOps Agent + CI/CD (5-10 дней)           ← После git-based
├── [P] Security Agent (2-3 дня)                   ← Параллельно с DevOps

Неделя 8+: Evolution (по мере необходимости)
├── [ ] Research flow (3-5 дней)
├── [ ] Meta-Agent (5-7 дней)
├── [ ] Prompt Optimization (7-14 дней)
├── [ ] [Опционально] Visual Graph Editor (7-14 дней)
└── [ ] [Опционально] Graph Evolution (14-21 день)

[P] = можно параллельно с другими [P]
[S] = последовательно (зависит от предыдущего)
```

### Матрица зависимостей

```
                    Зависит от:
Задача              │ structlog │ LLM cfg │ Git-based │ Multi-graph │ Sandbox │
────────────────────┼───────────┼─────────┼───────────┼─────────────┼─────────┤
Retry               │           │         │           │             │         │
structlog           │           │         │           │             │         │
LLM config          │           │         │           │             │         │
Streaming           │           │         │           │             │         │
Web tools           │           │         │           │             │         │
Graph viz           │           │         │           │             │         │
Telegram            │           │         │           │             │         │
────────────────────┼───────────┼─────────┼───────────┼─────────────┼─────────┤
Git-based code      │     ~     │         │           │             │         │
Switch-Agent        │           │         │           │      ✓      │         │
Sandbox             │     ~     │         │     ~     │             │         │
CLI-агенты          │     ~     │         │     ✓     │             │    ~    │
DevOps Agent        │     ~     │    ~    │     ✓     │             │    ~    │
Security Agent      │     ~     │         │     ~     │             │    ~    │
────────────────────┼───────────┼─────────┼───────────┼─────────────┼─────────┤
Research flow       │     ~     │    ~    │           │      ✓      │         │
Meta-Agent          │     ~     │         │           │             │         │
Prompt Optimization │     ~     │         │           │             │         │
Visual Editor       │           │         │           │      ~      │         │

✓ = жёсткая зависимость
~ = желательно сделать раньше, но не блокирует
```

### Общая оценка

| Уровень | Задачи | Дни (AI) | Дни (человек) |
|---------|--------|:--------:|:-------------:|
| Лёгкое | 7 задач | 8-12 | 15-25 |
| Среднее | 4 задачи | 15-25 | 30-50 |
| Сложное | 4+ задачи | 20-40 | 40-80 |
| **Итого** | **15+ задач** | **~45-75** | **~90-150** |

При параллелизации (AI делает несколько задач одновременно) — **30-50 дней**.

### Что делать в первый день

1. `structlog` + `retry` + `config/agents.yaml` — всё в `base.py` и окружении
2. Создать `graphs/dev_team/manifest.yaml` — конвенция для библиотеки
3. Обновить `aegra.json` — подготовить к мульти-графу
4. `npm install @xyflow/react` — готовность к визуализации

Это займёт 2-3 часа и создаст фундамент для всего остального.

---

## Приложение: Открытые вопросы

1. **VPS для CLI-агентов:** Отдельный от VPS для деплоя? Или тот же?
   Рекомендация: отдельный (безопасность), но для начала можно один.

2. **Aegra и мульти-граф:** Aegra поддерживает несколько assistant_id.
   Нужно проверить, как работает routing на уровне API.

3. **State sharing между subgraphs:** Если dev_team и research_team
   имеют разные state — нужен маппинг. Можно использовать общий BaseState.

4. **CLI-агент лицензии:** Anthropic/OpenAI subscriptions для CLI tools.
   Нужно уточнить стоимость и лимиты.

5. **nip.io и HTTPS:** nip.io не поддерживает HTTPS напрямую.
   Traefik + Let's Encrypt может не работать с wildcard nip.io.
   Альтернатива: sslip.io или собственный домен с wildcard DNS.

6. **Aegra gateway vs модификация:** Для первых фич (graph topology endpoint)
   проще добавить gateway. Модифицировать Aegra — когда gateway не достаточно.
