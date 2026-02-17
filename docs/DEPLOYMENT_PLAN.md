# AI-crew: План деплоя целевых приложений

> Полный план реализации автоматизированного деплоя приложений, создаваемых AI-crew.
> Включает: анализ текущего состояния, выбор стратегий, детальный план реализации.
>
> Дата: 17 февраля 2026
> Связанные документы:
> - [ARCHITECTURE_V2.md](ARCHITECTURE_V2.md) — целевая архитектура (§3.2, §8.5)
> - [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) — общий план реализации (§3.5 DevOps Agent)

---

## Содержание

1. [Целевой сценарий](#1-целевой-сценарий)
2. [Текущее состояние](#2-текущее-состояние)
3. [Решение 1: Домены — nip.io vs свой субдомен](#3-домены)
4. [Решение 2: Стратегия управления репозиториями](#4-стратегия-репо)
5. [Решение 3: Управление секретами](#5-секреты)
6. [Целевая архитектура деплоя](#6-целевая-архитектура)
7. [План реализации](#7-план-реализации)
8. [Что автоматизировано vs ручное](#8-автоматизация)

---

## 1. Целевой сценарий {#1-целевой-сценарий}

```
Пользователь                      AI-crew                              VPS Deploy
    │                                │                                      │
    │  "Создай TODO-приложение       │                                      │
    │   на FastAPI + React"          │                                      │
    │──────────────────────────────>│                                      │
    │                                │                                      │
    │  [PM уточняет]                 │                                      │
    │  "Какой UI фреймворк?"        │                                      │
    │<──────────────────────────────│                                      │
    │  "React, Material UI"          │                                      │
    │──────────────────────────────>│                                      │
    │                                │                                      │
    │  [Analyst → Architect →        │                                      │
    │   Developer → Security →       │                                      │
    │   Reviewer → QA → DevOps]      │                                      │
    │                                │                                      │
    │                                │  1. Создаёт/выбирает GitHub repo    │
    │                                │  2. Пушит код + infra файлы          │
    │                                │  3. Записывает секреты (VPS_*)       │
    │                                │  4. GitHub Actions запускается       │
    │                                │───────────────────────────────────>│
    │                                │                                      │ Lint → Test
    │                                │                                      │ Build → Deploy
    │                                │                                      │ Traefik + SSL
    │                                │  5. Проверяет деплой (health check) │
    │                                │<───────────────────────────────────│
    │                                │                                      │
    │  "Готово! Ваше приложение:     │                                      │
    │   https://todo-app.deploy.     │                                      │
    │   myplatform.com"              │                                      │
    │<──────────────────────────────│                                      │
```

**Ключевое требование:** максимальная автоматизация. DevOps-агент не должен тратить токены на рутину — только на адаптацию шаблонов под конкретный стек.

---

## 2. Текущее состояние {#2-текущее-состояние}

### Что реализовано (DONE)

| Компонент | Файл | Статус | Описание |
|-----------|------|--------|----------|
| **DevOps Agent** | `agents/devops.py` | Done | Генерирует Dockerfile, docker-compose, deploy.yml, Traefik labels |
| **DevOps промпты** | `prompts/devops.yaml` | Done | system + generate_infra промпты |
| **Deploy шаблон** | `config/deploy/deploy_template.yml` | Done | GitHub Actions workflow template |
| **VPS setup скрипт** | `scripts/setup_deploy_vps.sh` | Done | Docker, Traefik, deploy user |
| **GitHub Actions tools** | `tools/github_actions.py` | Done | trigger_ci, wait_for_ci, get_ci_logs |
| **Git workspace tools** | `tools/git_workspace.py` | Done | Ветки, файлы, PR, batch commit |
| **State поля** | `state.py` | Done | deploy_url, infra_files, working_branch |
| **CI/CD в графе** | `graph.py` | Done | ci_check_node, route_after_ci |
| **DevOps node** | `graph.py` | Done | devops_agent → git_commit pipeline |
| **Schemas** | `agents/schemas.py` | Done | DevOpsResponse, InfraFileOutput |
| **36 тестов** | `test_devops*.py` | Done | Unit + parsing + routing + schema |

### Что НЕ реализовано (TODO)

| # | Компонент | Критичность | Описание |
|---|-----------|-------------|----------|
| 1 | **Управление репозиториями** | CRITICAL | Нет механизма создания/выбора repo для целевого проекта |
| 2 | **Запись GitHub Secrets** | CRITICAL | Нет кода для автоматической записи VPS_SSH_KEY, VPS_HOST, VPS_USER через API |
| 3 | **Деплой-триггер** | HIGH | После пуша нет отслеживания, что GitHub Actions запустился и завершился |
| 4 | **Health check после деплоя** | HIGH | Нет проверки, что приложение реально доступно по deploy_url |
| 5 | **End-to-end pipeline** | HIGH | Отдельные компоненты есть, но не связаны в единый flow |
| 6 | **DNS/домен настройка** | MEDIUM | Только nip.io hardcoded, нет выбора стратегии |
| 7 | **Cleanup** | LOW | Нет удаления/cleanup старых деплоев |
| 8 | **Prefect мониторинг** | LOW | Упомянут в архитектуре, не реализован |
| 9 | **VPS setup улучшения** | MEDIUM | Нет self-hosted runner, нет firewall, нет authorized_keys автоматики |

---

## 3. Решение 1: Домены — nip.io vs свой субдомен {#3-домены}

### Вариант A: nip.io

`https://todo-app.31.59.58.143.nip.io`

Wildcard DNS-сервис: `*.IP.nip.io` резолвится в `IP`. Бесплатно, без настройки.

| Плюсы | Минусы |
|-------|--------|
| **Zero-config** — работает сразу, никакой настройки DNS | **Непрофессиональный URL** — выглядит как dev/staging |
| **Бесплатно** — никаких доменов покупать не надо | **Зависимость от сервиса** — если nip.io ляжет, все домены недоступны |
| **Бесконечные субдомены** — столько, сколько нужно | **Let's Encrypt rate limits** — nip.io это ONE registered domain для ВСЕХ пользователей nip.io. Лимит: 50 сертов/неделю на registered domain, могут закончиться из-за чужих пользователей |
| **Нет API-интеграции** — DevOps агенту не нужен DNS API | **Блокировки** — некоторые корп. файрволы блокируют nip.io |
| **Идеально для прототипов** | **TLS challenge только** — httpChallenge нестабилен через nip.io |

**Техническая реализация:** DevOps агент просто формирует URL `{app_name}.{ip}.nip.io` — 0 API-вызовов.

### Вариант B: Свой субдомен (wildcard)

`https://todo-app.deploy.myplatform.com`

Одноразовая настройка wildcard DNS: `*.deploy.myplatform.com → VPS_IP`.

| Плюсы | Минусы |
|-------|--------|
| **Профессиональный URL** — пригоден для демо клиентам | **Нужен домен** — покупка + поддержка |
| **Полный контроль** — DNS в твоих руках | **Одноразовая настройка** — wildcard A-запись в DNS |
| **Свои rate limits** — 50 certs/week для ТВОЕГО домена | **DNS propagation** — при первой настройке 5-30 мин |
| **Надёжность** — не зависишь от nip.io | Wildcard Let's Encrypt требует DNS-01 challenge (API к DNS-провайдеру) |
| **Wildcard cert** — один `*.deploy.myplatform.com` сертификат для всех приложений | |
| **Zero-config для каждого приложения** — после начальной настройки wildcard DNS, каждое новое приложение работает автоматически, как nip.io | |

**Техническая реализация:**

```
Разовая настройка (5 минут):
  1. DNS: *.deploy.myplatform.com → A → 31.59.58.143
  2. Traefik: DNS-01 challenge для wildcard cert

Далее автоматически:
  DevOps агент формирует URL: {app_name}.deploy.myplatform.com
  — 0 API-вызовов, как nip.io!
```

### Вариант C: Гибрид — nip.io по умолчанию + опциональный свой домен

Рекомендуемый вариант.

```python
# devops.py
deploy_ip = os.getenv("DEPLOY_VPS_IP", "31.59.58.143")
custom_domain = os.getenv("DEPLOY_DOMAIN")  # Например: "deploy.myplatform.com"

if custom_domain:
    deploy_url = f"https://{app_name}.{custom_domain}"
else:
    deploy_url = f"https://{app_name}.{deploy_ip}.nip.io"
```

| Настройка | Результат |
|-----------|-----------|
| `DEPLOY_DOMAIN` не задан | `https://todo-app.31.59.58.143.nip.io` |
| `DEPLOY_DOMAIN=deploy.mysite.ru` | `https://todo-app.deploy.mysite.ru` |

**Преимущество:** работает из коробки (nip.io), но при желании одна env-переменная переключает на профессиональные URL.

### Рекомендация

**Вариант C (гибрид):**
- Стартуем с nip.io (0 настройки)
- Когда готов домен — одна env-переменная `DEPLOY_DOMAIN`
- Для wildcard cert добавляем DNS-01 challenge в Traefik (Cloudflare/Route53 API)
- Сложность: минимальная — 2 часа на добавление гибрида

---

## 4. Решение 2: Стратегия управления репозиториями {#4-стратегия-репо}

### Вариант A: Пул заранее созданных репозиториев

```
GitHub: project-01, project-02, ..., project-50 (пустые)
AI-crew: берёт следующий свободный → push → set secrets → deploy
```

| Плюсы | Минусы |
|-------|--------|
| Чистое разделение проектов | Нужно заранее создать и управлять пулом |
| Каждый проект — свой git history | **GitHub Secrets нужно записывать в каждый repo** |
| Стандартная модель GitHub | Расход пустых repo |
| Простой cleanup (удалить repo) | Нужен tracking занятых/свободных |
| | Пул может закончиться |

**Секреты:** AI-crew записывает VPS_SSH_KEY, VPS_HOST, VPS_USER через GitHub API (есть API для этого). Секреты хранятся как env-переменные на сервере AI-crew, ИИ их не видит.

### Вариант B: Один репо, ветки на проект

```
GitHub: ai-crew-projects (один repo)
Ветки: project/todo-app, project/calculator, project/blog
Secrets: установлены один раз на уровне repo
```

| Плюсы | Минусы |
|-------|--------|
| **Секреты настроены один раз** | Грязный git history (все проекты в одном repo) |
| Простое управление | Workflow файл должен быть в каждой ветке |
| Нет пула | Конфликты при concurrent push |
| | Сложнее cleanup (удалить ветку ≠ удалить deploy) |

**GitHub Actions на разных ветках — можно ли?**

Да, это работает. Два подхода:

**Подход B1: Workflow файл в каждой ветке**
```yaml
# .github/workflows/deploy.yml (в ветке project/todo-app)
on:
  push:
    branches: [project/todo-app]
```
Каждая ветка содержит свой workflow. GitHub Actions запускает workflow из push-ветки.
**Проблема:** workflow файл нужно создавать в каждой ветке.

**Подход B2: Единый workflow в main с динамической логикой**
```yaml
on:
  push:
    branches: [project/*]

jobs:
  deploy:
    runs-on: ubuntu-latest
    env:
      APP_NAME: ${{ github.ref_name }} # "project/todo-app"
    steps:
      - uses: actions/checkout@v4
      # ... APP_NAME определяет что и куда деплоить
```
**Проблема:** workflow в main не запустится при push в другую ветку, если этот push не меняет `.github/workflows/` в main. На самом деле GitHub Actions ВСЕГДА использует workflow file из PUSH-ветки (для `on: push`), поэтому этот подход не работает без workflow в ветке.

**Вердикт по B:** Работает, но каждая ветка должна содержать `.github/workflows/deploy.yml`. DevOps-агент это и так генерирует — значит, подход жизнеспособен.

### Вариант C: Динамическое создание репозиториев через GitHub API

```
AI-crew: POST /user/repos → "ai-todo-app-2026-02-17" → push → set secrets → deploy
```

| Плюсы | Минусы |
|-------|--------|
| **Полная автоматизация** — никакого пула | Нужен GitHub token с `repo` + `admin:repo_hook` scope |
| Чистое разделение проектов | Создание repo = 1-2 сек (API) |
| Имя repo = имя проекта (читабельно) | На Free: до 500 repos (достаточно) |
| Простой cleanup (delete repo via API) | Чуть больше кода на создание |
| Секреты записываются автоматически | |
| Нет заранее заготовленных ресурсов | |

**API для создания repo:**
```python
# github.com/rest/repos/repos#create-a-repository-for-the-authenticated-user
POST /user/repos
{
  "name": "ai-todo-app-2026-02-17",
  "private": true,
  "auto_init": false,
  "description": "Generated by AI-crew"
}
```

**API для записи секретов:**
```python
# 1. Получить public key репозитория
GET /repos/{owner}/{repo}/actions/secrets/public-key
# → { key_id, key }

# 2. Зашифровать секрет через libsodium (PyNaCl)
from nacl import encoding, public
public_key = public.PublicKey(key_bytes, encoding.Base64Encoder)
sealed_box = public.SealedBox(public_key)
encrypted = sealed_box.encrypt(secret_value.encode())

# 3. Записать секрет
PUT /repos/{owner}/{repo}/actions/secrets/{secret_name}
{
  "encrypted_value": base64(encrypted),
  "key_id": key_id
}
```

### Сравнительная таблица

| Критерий | A: Пул repos | B: Один repo | C: Динамические repos |
|----------|-------------|-------------|----------------------|
| Настройка секретов | Per-repo (авто через API) | **Один раз** | Per-repo (авто через API) |
| Сложность реализации | Средняя | Средняя | Средняя |
| Изоляция проектов | Высокая | **Низкая** | Высокая |
| Ручная работа | Создать пул | Создать repo + secrets | **Ничего** |
| Cleanup | Просто (delete repo) | Сложно (ветки + deploy) | Просто (delete repo) |
| Масштабирование | Пул ≤ N | Неограничено | До 500 repos (Free) |
| Читабельность | Repo01, repo02... | project/todo-app | **ai-todo-app** |
| CI/CD конфликты | Нет | Возможны | Нет |

### Рекомендация

**Основной: Вариант C (динамические repos)** — полная автоматизация, чистая изоляция.

**Fallback: Вариант B (один repo)** — для простоты на начальном этапе, если не хочется усложнять.

**Предлагаемый путь:**
1. **Фаза 1:** Вариант B (один repo `ai-crew-deploy`) — быстро запускаемся, секреты один раз
2. **Фаза 2:** Миграция на Вариант C (динамические repos) — полная автоматизация

---

## 5. Решение 3: Управление секретами {#5-секреты}

### Проблема

DevOps-агент генерирует `.github/workflows/deploy.yml`, который использует:
- `secrets.VPS_SSH_KEY` — SSH-ключ для доступа к VPS
- `secrets.VPS_HOST` — IP-адрес VPS
- `secrets.VPS_USER` — пользователь на VPS

Эти секреты нужно каким-то образом прописать в GitHub, причём:
- ИИ-агенты **не должны видеть** сами значения секретов
- Процесс должен быть **автоматическим** (не вводить руками каждый раз)

### Решение: Platform-level Secret Injection

```
┌─────────────────────────────────────────────────────────────────┐
│  AI-crew Server Environment                                     │
│                                                                  │
│  ENV VARS (set once by human, never visible to AI):             │
│    DEPLOY_VPS_SSH_KEY=/path/to/key  (или содержимое ключа)      │
│    DEPLOY_VPS_HOST=31.59.58.143                                  │
│    DEPLOY_VPS_USER=deploy                                        │
│    GITHUB_TOKEN=ghp_xxx (с scope: repo, admin:repo_hook)        │
│                                                                  │
│  Когда DevOps Agent завершил и код запушен:                     │
│    Platform Code (не агент!) автоматически:                      │
│    1. Читает DEPLOY_VPS_* из ENV                                │
│    2. Шифрует через GitHub API (libsodium)                      │
│    3. Записывает в GitHub Secrets целевого repo                  │
│    4. ИИ об этом не знает, секреты не попадают в контекст       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Реализация: `tools/deploy_secrets.py`**
```python
class DeploySecretsManager:
    """Platform-level secret injection into GitHub repos.

    This is NOT an AI tool — it's called by platform code
    after DevOps agent commits infrastructure files.
    """

    def __init__(self):
        self.github_token = os.environ["GITHUB_TOKEN"]
        self.vps_ssh_key = os.environ["DEPLOY_VPS_SSH_KEY"]
        self.vps_host = os.environ["DEPLOY_VPS_HOST"]
        self.vps_user = os.environ.get("DEPLOY_VPS_USER", "deploy")

    async def ensure_secrets(self, repo: str) -> None:
        """Set VPS secrets on the target repo (idempotent)."""
        secrets = {
            "VPS_SSH_KEY": self.vps_ssh_key,
            "VPS_HOST": self.vps_host,
            "VPS_USER": self.vps_user,
        }
        for name, value in secrets.items():
            await self._set_secret(repo, name, value)

    async def _set_secret(self, repo, name, value):
        # 1. Get repo public key
        # 2. Encrypt with libsodium
        # 3. PUT /repos/{repo}/actions/secrets/{name}
        ...
```

### Для Варианта B (один repo)

Секреты записываются **один раз вручную** (или скриптом):
```bash
# Запустить один раз при настройке
python scripts/setup_repo_secrets.py \
  --repo user/ai-crew-deploy \
  --vps-key ~/.ssh/deploy_ed25519 \
  --vps-host 31.59.58.143 \
  --vps-user deploy
```

### Для Варианта C (динамические repos)

Секреты записываются **автоматически** при каждом создании repo — через `DeploySecretsManager`.

---

## 6. Целевая архитектура деплоя {#6-целевая-архитектура}

### End-to-end flow (Фаза 1 — один repo)

```
graph.py (после QA approved):
│
├── devops_agent()
│   ├── Генерирует: Dockerfile, docker-compose.prod.yml, deploy.yml
│   ├── Определяет: app_name, deploy_url
│   └── Возвращает: infra_files, deploy_url
│
├── git_commit_node()
│   ├── Мержит code_files + infra_files
│   ├── Создаёт ветку: project/{app_name}
│   ├── Batch commit через Git Tree API
│   └── Push в repo (ai-crew-deploy)
│
├── deploy_trigger_node()  ← НОВЫЙ
│   ├── Ждёт запуска GitHub Actions (polling)
│   ├── wait_for_ci() — ждёт завершения
│   ├── При CI FAIL: логи → developer (fix loop)
│   └── При CI PASS: → deploy_verify
│
└── deploy_verify_node()  ← НОВЫЙ
    ├── HTTP GET deploy_url (health check)
    ├── Retry 5 раз с интервалом 15 сек (приложение стартует)
    ├── При SUCCESS: → pm_final (ссылка пользователю)
    └── При FAIL: → уведомление (deploy failed, но код готов)
```

### VPS Deploy — структура

```
/home/deploy/
├── traefik/
│   ├── docker-compose.yml      # Traefik reverse proxy
│   ├── acme/acme.json          # Let's Encrypt certs
│   └── config/                 # Dynamic config (если нужно)
│
├── apps/
│   ├── todo-app/
│   │   ├── docker-compose.prod.yml
│   │   ├── .env                # App-specific env (если нужен)
│   │   └── (image загружен через docker load)
│   ├── calculator/
│   │   └── ...
│   └── blog/
│       └── ...
│
└── .ssh/
    ├── id_ed25519              # SSH key (используется GitHub Actions)
    └── authorized_keys
```

### GitHub Actions Deploy Workflow (что генерирует DevOps Agent)

```yaml
name: Deploy
on:
  push:
    branches: [project/todo-app]  # или [main] для Варианта C

env:
  APP_NAME: todo-app
  DEPLOY_DIR: /home/${{ secrets.VPS_USER }}/apps/todo-app

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup + Lint + Test
        run: ...

  build-and-deploy:
    needs: lint-and-test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Build Docker image
        run: docker build -t ${{ env.APP_NAME }}:latest .

      - name: Save & Transfer image
        run: docker save ${{ env.APP_NAME }}:latest | gzip > image.tar.gz

      - name: Deploy to VPS
        uses: appleboy/scp-action@v0.1.7
        with:
          host: ${{ secrets.VPS_HOST }}
          username: ${{ secrets.VPS_USER }}
          key: ${{ secrets.VPS_SSH_KEY }}
          source: "image.tar.gz,docker-compose.prod.yml"
          target: ${{ env.DEPLOY_DIR }}

      - name: Start application
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.VPS_HOST }}
          username: ${{ secrets.VPS_USER }}
          key: ${{ secrets.VPS_SSH_KEY }}
          script: |
            cd ${{ env.DEPLOY_DIR }}
            docker load < image.tar.gz
            docker compose -f docker-compose.prod.yml up -d --remove-orphans
            rm -f image.tar.gz

      - name: Health check
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.VPS_HOST }}
          username: ${{ secrets.VPS_USER }}
          key: ${{ secrets.VPS_SSH_KEY }}
          script: |
            sleep 10
            curl -sf http://localhost:$(docker port ${{ env.APP_NAME }} | head -1 | cut -d: -f2)/health || echo "Health check pending..."
```

---

## 7. План реализации {#7-план-реализации}

### Фаза 0: Подготовка инфраструктуры (ручная, 1-2 часа)

| # | Действие | Кто | Описание |
|---|----------|-----|----------|
| 0.1 | Настроить VPS | Человек | Запустить `scripts/setup_deploy_vps.sh` (уже есть) |
| 0.2 | Настроить authorized_keys | Человек | Скопировать pub key deploy-юзера |
| 0.3 | Создать deploy repo | Человек | `ai-crew-deploy` (для Фазы 1) ИЛИ настроить `GITHUB_TOKEN` с правами на создание repos (для Фазы 2) |
| 0.4 | Записать секреты на платформе | Человек | `DEPLOY_VPS_SSH_KEY`, `DEPLOY_VPS_HOST`, `DEPLOY_VPS_USER` в .env AI-crew |
| 0.5 | Опционально: настроить wildcard DNS | Человек | `*.deploy.mysite.ru → VPS_IP` |

### Фаза 1: Минимальный E2E деплой (5-7 дней)

#### Модуль D1: Гибридный домен (0.5 дня)

| Действие | Файл | Что делать |
|----------|------|-----------|
| Изменить | `agents/devops.py` | Добавить `DEPLOY_DOMAIN` env var, гибридная логика URL |
| Изменить | `prompts/devops.yaml` | Передать domain info в промпт |
| Добавить | `env.example` | `DEPLOY_DOMAIN=` (пустой = nip.io) |
| Тесты | | Проверить оба варианта URL |

**Реализация:**
```python
# devops.py — обновление _build_deploy_url
def _build_deploy_url(app_name: str) -> str:
    deploy_ip = os.getenv("DEPLOY_VPS_IP", DEFAULT_DEPLOY_IP)
    custom_domain = os.getenv("DEPLOY_DOMAIN")
    if custom_domain:
        return f"https://{app_name}.{custom_domain}"
    return f"https://{app_name}.{deploy_ip}.nip.io"
```

#### Модуль D2: Repo Manager (1-2 дня)

| Действие | Файл | Что делать |
|----------|------|-----------|
| Создать | `graphs/dev_team/tools/repo_manager.py` | Создание/выбор repo, запись секретов |
| Создать | `graphs/dev_team/tools/deploy_secrets.py` | Platform-level secret injection |
| Изменить | `requirements.txt` | `PyNaCl>=1.5.0` (для шифрования секретов) |
| Изменить | `env.example` | `DEPLOY_VPS_SSH_KEY`, `DEPLOY_VPS_HOST`, `DEPLOY_VPS_USER`, `DEPLOY_REPO_STRATEGY` |
| Тесты | `tests/test_repo_manager.py` | Unit тесты с mock GitHub API |

**Два режима:**
```python
class RepoManager:
    """Manages target repositories for deployed applications."""

    def __init__(self):
        self.strategy = os.getenv("DEPLOY_REPO_STRATEGY", "single")  # "single" | "dynamic"
        self.single_repo = os.getenv("DEPLOY_SINGLE_REPO", "")  # "user/ai-crew-deploy"
        self.github_token = os.environ["GITHUB_TOKEN"]

    async def get_target_repo(self, app_name: str) -> RepoTarget:
        if self.strategy == "single":
            return RepoTarget(
                repo=self.single_repo,
                branch=f"project/{app_name}",
                is_new=False,
            )
        else:  # dynamic
            repo_name = f"ai-{app_name}"
            await self._create_repo(repo_name)
            await self._set_deploy_secrets(f"{self.github_owner}/{repo_name}")
            return RepoTarget(
                repo=f"{self.github_owner}/{repo_name}",
                branch="main",
                is_new=True,
            )
```

#### Модуль D3: Deploy Pipeline Node (2-3 дня)

| Действие | Файл | Что делать |
|----------|------|-----------|
| Создать | `graphs/dev_team/tools/deploy_pipeline.py` | Оркестрация: push → secrets → CI → verify |
| Изменить | `graphs/dev_team/graph.py` | deploy_trigger_node + deploy_verify_node |
| Изменить | `graphs/dev_team/state.py` | deploy_status, deploy_repo, deploy_branch |
| Изменить | `graphs/dev_team/prompts/devops.yaml` | Обновить инструкции для шаблона |
| Тесты | `tests/test_deploy_pipeline.py` | Unit тесты pipeline |

**Новые state поля:**
```python
# state.py — дополнения
deploy_status: NotRequired[str]        # "pending" | "deploying" | "deployed" | "failed"
deploy_repo: NotRequired[str]          # "user/ai-todo-app"
deploy_branch: NotRequired[str]        # "main" или "project/todo-app"
deploy_health_check: NotRequired[dict] # {status, url, response_code, checked_at}
```

**Новые узлы графа:**
```python
# graph.py

def deploy_trigger_node(state: DevTeamState, config=None) -> dict:
    """Push code + infra to target repo, set secrets, wait for CI."""
    repo_mgr = get_repo_manager()
    target = repo_mgr.get_target_repo(app_name)

    # 1. Push code to target repo/branch
    # 2. Ensure secrets are set (platform-level, not visible to AI)
    # 3. Wait for GitHub Actions to start and complete
    # 4. Return CI status
    ...

def deploy_verify_node(state: DevTeamState, config=None) -> dict:
    """Verify deployment by checking health endpoint."""
    deploy_url = state.get("deploy_url", "")
    # HTTP GET with retries
    # Return deploy_status: "deployed" | "failed"
    ...

def route_after_deploy(state: DevTeamState) -> str:
    status = state.get("deploy_status", "")
    if status == "deployed":
        return "pm_final"         # Успех → финальное сообщение с URL
    if status == "ci_failed":
        return "developer"        # CI fail → developer фиксит
    return "pm_final"             # Deploy fail → сообщение с ошибкой
```

#### Модуль D4: Git Commit Node обновление (1 день)

| Действие | Файл | Что делать |
|----------|------|-----------|
| Изменить | `graphs/dev_team/graph.py` | git_commit_node → push в target repo (не просто AI-crew repo) |
| Изменить | `graphs/common/git.py` | Поддержка push в произвольный repo |
| Тесты | | Обновить существующие тесты |

Сейчас `git_commit_node` пушит в `working_repo` (repo из state). Нужно разделить:
- Исходный `working_repo` (если задан пользователем)
- `deploy_repo` (целевой для деплоя — создаётся автоматически)

#### Модуль D5: VPS Setup улучшения (0.5 дня)

| Действие | Файл | Что делать |
|----------|------|-----------|
| Изменить | `scripts/setup_deploy_vps.sh` | Автоматизация authorized_keys, firewall (ufw) |
| Создать | `scripts/setup_repo_secrets.py` | Скрипт для ручной записи секретов (helper) |
| Изменить | `scripts/setup_deploy_vps.sh` | Traefik: поддержка wildcard cert (DNS-01 опционально) |

### Фаза 2: Полная автоматизация (3-5 дней, после Фазы 1)

#### Модуль D6: Динамическое создание repos (1-2 дня)

Реализация `strategy="dynamic"` в `RepoManager`:
- Создание repo через GitHub API
- Автоматическая запись секретов
- Cleanup: удаление repo по запросу

#### Модуль D7: Deploy мониторинг и cleanup (1-2 дня)

| Действие | Файл | Что делать |
|----------|------|-----------|
| Создать | `tools/deploy_monitor.py` | Мониторинг запущенных приложений |
| Создать | `tools/deploy_cleanup.py` | Остановка и удаление деплоев |
| Опционально | Prefect integration | Регистрация в Prefect для визуализации |

#### Модуль D8: Traefik wildcard cert для своего домена (0.5 дня)

Обновление `scripts/setup_deploy_vps.sh`:
```yaml
# Traefik с DNS-01 challenge (для *.deploy.mysite.ru)
- "--certificatesresolvers.letsencrypt.acme.dnschallenge=true"
- "--certificatesresolvers.letsencrypt.acme.dnschallenge.provider=cloudflare"
environment:
  CF_DNS_API_TOKEN: ${CF_DNS_API_TOKEN}
```

### Порядок реализации

```
Фаза 0: VPS + repo setup (ручная, 1-2 часа)
    │
    ▼
Фаза 1 (параллельно):
    ├── D1: Гибридный домен (0.5 дня)
    ├── D2: Repo Manager + Secrets (1-2 дня)
    ├── D3: Deploy Pipeline Nodes (2-3 дня) — зависит от D2
    ├── D4: Git Commit обновление (1 день)
    └── D5: VPS setup улучшения (0.5 дня)
    │
    ▼
Интеграционный тест: E2E деплой (1 день)
    │
    ▼
Фаза 2 (после проверки Фазы 1):
    ├── D6: Динамические repos (1-2 дня)
    ├── D7: Мониторинг + Cleanup (1-2 дня)
    └── D8: Wildcard cert (0.5 дня)
```

---

## 8. Что автоматизировано vs ручное {#8-автоматизация}

### Автоматизировано (ИИ/платформа делает сама)

| Действие | Кто делает | Токены |
|----------|-----------|--------|
| Генерация Dockerfile, docker-compose, deploy.yml | DevOps Agent (LLM) | ~1 вызов |
| Определение app_name, deploy_url | DevOps Agent (код) | 0 |
| Push кода + инфра файлов | Platform (git_commit_node) | 0 |
| Запись GitHub Secrets | Platform (deploy_secrets.py) | 0 |
| Ожидание CI + проверка статуса | Platform (deploy_trigger_node) | 0 |
| Health check после деплоя | Platform (deploy_verify_node) | 0 |
| Возврат URL пользователю | PM Agent (финальное сообщение) | 0 |

**Итого токенов на DevOps:** ~1 LLM-вызов (генерация infra). Всё остальное — код.

### Ручное (человек делает один раз)

| Действие | Когда | Время |
|----------|-------|-------|
| Настроить VPS (`setup_deploy_vps.sh`) | 1 раз при установке | 30 мин |
| Записать `DEPLOY_VPS_*` в .env AI-crew | 1 раз при установке | 5 мин |
| Создать deploy repo (Фаза 1) | 1 раз | 5 мин |
| Настроить wildcard DNS (опционально) | 1 раз | 10 мин |
| Установить `DEPLOY_DOMAIN` (опционально) | 1 раз | 1 мин |

### Что DevOps Agent НЕ делает (принцип Scripts-over-manual)

- **Не записывает секреты** — это делает платформенный код автоматически
- **Не настраивает DNS** — wildcard DNS или nip.io, оба не требуют runtime настройки
- **Не ждёт CI** — это делает deploy_trigger_node (чистый код, без LLM)
- **Не проверяет здоровье** — это делает deploy_verify_node (HTTP GET)
- **Не создаёт repos** — это делает RepoManager (чистый код)

DevOps Agent фокусируется **только** на том, что требует LLM:
- Анализ tech_stack и architecture
- Генерация правильного Dockerfile для конкретного стека
- Адаптация docker-compose с нужными сервисами (PG, Redis, etc.)
- Генерация CI/CD workflow с правильными шагами

---

## Приложение: ENV-переменные для деплоя

```bash
# === В .env AI-crew (на сервере AI-crew) ===

# Стратегия деплоя
DEPLOY_REPO_STRATEGY=single          # "single" — один repo (Фаза 1)
                                      # "dynamic" — создание repos (Фаза 2)

# Целевой repo (для strategy=single)
DEPLOY_SINGLE_REPO=user/ai-crew-deploy

# VPS для деплоя (платформенные секреты, ИИ не видит)
DEPLOY_VPS_IP=31.59.58.143
DEPLOY_VPS_HOST=31.59.58.143
DEPLOY_VPS_USER=deploy
DEPLOY_VPS_SSH_KEY=/path/to/deploy_key  # путь к файлу ключа

# Домен (опционально)
DEPLOY_DOMAIN=                        # пусто = nip.io
# DEPLOY_DOMAIN=deploy.mysite.ru     # свой субдомен

# DevOps Agent
USE_DEVOPS_AGENT=true                 # включить/выключить DevOps agent
```
