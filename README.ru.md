# AI-crew

**🌐 Язык: [English](README.md) | [Русский](README.ru.md) | [中文](README.zh-CN.md)**

**Мультиагентная платформа разработки ПО на базе LangGraph**

AI-crew оркестрирует команды ИИ-агентов, которые автономно создают программное
обеспечение — от обсуждения деталей реализации с пользователем до деплоя готового
проекта и доставки рабочей ссылки. Платформа включает растущую коллекцию графов
агентных команд для разных сценариев: полноценные команды разработки, быстрые
кодинг-ассистенты и исследовательские бригады.

## Как это работает

1. **Вы описываете задачу** — через Web UI или Telegram-бот
2. **ИИ-менеджер обсуждает план** — уточняет требования, предлагает архитектуру, согласовывает детали
3. **Команда агентов выполняет** — аналитики, архитекторы, разработчики, ревьюеры, QA работают автономно
4. **Вы наблюдаете в реальном времени** — интерактивная визуализация графа показывает каждый шаг каждого агента
5. **Получаете результат** — задеплоенный проект с рабочей ссылкой приходит вам

## Команды агентов

| Граф | Назначение |
|------|-----------|
| **dev_team** | Полный цикл разработки — 7 агентов (PM, Analyst, Architect, Developer, Security, Reviewer, QA). От требований до Pull Request |
| **standard_dev** | Автономная разработка задач средней сложности. PM + Developer + Reviewer с ограниченным циклом ревью |
| **simple_dev** | Быстрая генерация кода — один Developer-агент, без ревью. Скрипты, сниппеты, небольшие фичи за секунды |
| **research** | Универсальное исследование по любой теме — поиск в интернете, анализ источников, структурированные отчёты со ссылками |

## Ключевые возможности

- **Несколько конфигураций команд** — выбирайте нужную команду под задачу: от одиночного разработчика до полной бригады из 7 агентов
- **Доставка от идеи до продакшена** — цикл не останавливается на PR; проект деплоится, и вы получаете рабочий URL
- **Human-in-the-Loop** — ИИ-менеджер обсуждает с вами детали реализации до начала работы команды
- **Интерактивная визуализация графа** — наблюдайте за выполнением каждого узла агента в реальном времени на живом графе
- **Telegram-интеграция** — создавайте и отслеживайте задачи прямо из Telegram
- **Escalation ladder** — автоматическая эскалация при зацикливании Dev↔QA
- **Observability** — полный трейсинг и отладка через Langfuse
- **Docker ready** — dev (docker-compose) и prod (all-in-one image)

## Архитектура

```
  Telegram ─────┐
                ▼
  Web UI ──► Gateway API ──► LangGraph Engine
                                    │
          ┌─────────────────────────┤
          ▼                         ▼
   ┌─ dev_team ──────┐     ┌─ research ──────┐
   │ PM → Analyst →  │     │ Researcher →    │
   │ Architect →     │     │ Web Search →    │
   │ Developer →     │     │ Report          │
   │ Security →      │     └─────────────────┘
   │ Reviewer → QA   │
   └──────┬──────────┘     ┌─ simple_dev ────┐
          │                │ Developer →     │
          ▼                │ Commit          │
   CI/CD → Deploy          └─────────────────┘
          │
          ▼
   Live URL → User

   PostgreSQL  │  Langfuse  │  GitHub
```

## Быстрый старт

```bash
# 1. Настроить окружение
cp env.example .env
# Заполнить LLM_API_KEY в .env

# 2. Запустить все сервисы
docker-compose up -d

# 3. Запустить frontend
cd frontend && npm install && npm run dev
```

Откройте http://localhost:5173, введите задачу и наблюдайте за работой агентов на интерактивном графе.

**Подробнее:** [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)

## Документация

| Документ | Описание |
|----------|----------|
| [Быстрый старт](docs/GETTING_STARTED.md) | Установка и запуск за 10 минут |
| [Архитектура](docs/architecture_old.md) | Детальное описание системы, граф агентов, state-модель |
| [Разработка](docs/DEVELOPMENT.md) | Как добавить агента, изменить промпты, настроить LLM |
| [Тестирование](docs/TESTING.md) | Запуск тестов, фикстуры, CI/CD |
| [Развёртывание](docs/deployment.md) | Docker Compose (dev) и Dockerfile (prod) |
| [Bootstrap deploy VPS (Ansible)](docs/DEPLOY_VPS_ANSIBLE.md) | Подготовка серверов для автодеплоя приложений |
| [Roadmap](docs/IDEAS.md) | Идеи для развития проекта |

## Стек

| Компонент | Технология |
|-----------|-----------|
| Оркестрация | LangGraph |
| API | Aegra (FastAPI) |
| БД | PostgreSQL + pgvector |
| Observability | Langfuse |
| Web UI | React + Vite + Tailwind |
| Telegram-бот | Python (aiogram) |
| LLM | OpenAI-совместимый прокси (Claude, Gemini, GLM, etc.) |
| Деплой | Docker Compose / Dockerfile |

## Структура проекта

```
AI-crew/
├── graphs/                   # Графы агентных команд
│   ├── dev_team/             #   Полная команда из 7 агентов
│   ├── standard_dev/         #   Разработка средней сложности
│   ├── simple_dev/           #   Быстрый кодинг одним агентом
│   ├── research/             #   Исследования и аналитика
│   └── common/               #   Общие утилиты, типы, git, logging
├── frontend/                 # React Web UI с визуализацией графа
├── gateway/                  # API-шлюз (FastAPI)
├── telegram/                 # Telegram-бот
├── tests/                    # Тесты (pytest)
├── vendor/aegra/             # Aegra server (vendored)
├── scripts/                  # Docker entrypoint, setup, nginx
├── docs/                     # Документация
├── docker-compose.yml        # Development
├── Dockerfile                # Production (all-in-one)
├── aegra.json                # Конфиг Aegra
└── env.example               # Шаблон .env
```

## Тестирование

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## Кастомизация

- **Промпты** — `graphs/*/prompts/*.yaml`
- **Модели** — env `LLM_MODEL_PM`, `LLM_MODEL_DEVELOPER`, etc.
- **Новый агент** — см. [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)
- **Новый граф** — добавьте директорию в `graphs/` с `graph.py` и `manifest.yaml`

## Лицензия

MIT
