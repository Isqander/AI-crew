# Bootstrap deploy VPS через Ansible

Этот документ про одноразовую подготовку VPS для автоматических деплоев из графа AI-crew.

После выполнения этого bootstrap:
- каждый новый деплой приложения из новой ветки запускается из графа (через GitHub Actions),
- Ansible повторно запускать для каждого приложения не нужно.

## Что создаётся на сервере

Playbook `scripts/ansible/playbooks/bootstrap_deploy_vps.yml`:
- ставит Docker и docker compose plugin,
- создаёт пользователя деплоя (`deploy` по умолчанию),
- создаёт `/home/<deploy_user>/apps`,
- поднимает Traefik в `/home/<deploy_user>/traefik`,
- создаёт сеть `traefik-public`,
- опционально включает UFW (22/80/443).

## 1. Подготовка control-машины

```bash
pip install "ansible-core>=2.14"
ansible-galaxy collection install -r scripts/ansible/requirements.yml
```

## 2. Подготовка inventory и переменных

```bash
cp scripts/ansible/inventory/hosts.ini.example scripts/ansible/inventory/hosts.ini
cp scripts/ansible/group_vars/deploy_vps.yml.example scripts/ansible/group_vars/deploy_vps.yml
```

Заполни:
- `scripts/ansible/inventory/hosts.ini`:
  - `ansible_host` (IP сервера),
  - `ansible_user` (обычно `root`).
- `scripts/ansible/group_vars/deploy_vps.yml`:
  - `deploy_user`,
  - `traefik_email`,
  - `domain_ip` (если пусто, берётся IP хоста),
  - `setup_ufw` (`true/false`).

## 3. Запуск bootstrap

```bash
ansible-playbook -i scripts/ansible/inventory/hosts.ini scripts/ansible/playbooks/bootstrap_deploy_vps.yml
```

Только один сервер:

```bash
ansible-playbook -i scripts/ansible/inventory/hosts.ini scripts/ansible/playbooks/bootstrap_deploy_vps.yml --limit deploy-eu-1
```

## 4. Что сделать после bootstrap

1. Взять приватный ключ deploy-пользователя с VPS (или подготовить отдельный ключ для GitHub Actions).
2. Убедиться, что ключ соответствует доступу на этот VPS.
3. На стороне AI-crew задать переменные:
   - `DEPLOY_VPS_HOST`
   - `DEPLOY_VPS_USER`
   - `DEPLOY_VPS_SSH_KEY`
4. Проверить, что `USE_DEPLOY=true` и `USE_CI_INTEGRATION=true`.

## 5. Что менять для каждого нового сервера

Минимум:
- добавить новую запись в `scripts/ansible/inventory/hosts.ini`:
  - имя хоста,
  - `ansible_host`,
  - `ansible_user`.
- при необходимости переопределить host vars:
  - `deploy_user`,
  - `traefik_email`,
  - `domain_ip`.

Пример:

```ini
[deploy_vps]
deploy-eu-1 ansible_host=31.59.58.143 ansible_user=root
deploy-us-1 ansible_host=203.0.113.10 ansible_user=root deploy_user=deploy
```

## 6. Как это работает дальше (без Ansible)

После bootstrap дальнейший lifecycle такой:
1. Граф генерирует приложение и `deploy.yml` в ветке (`ai/**` или `project/**`).
2. Граф коммитит/создаёт PR.
3. `deploy_trigger` запускает GitHub Actions.
4. GitHub Actions по SSH деплоит в `/home/<deploy_user>/apps/<app-name>`.
5. Traefik публикует `https://<app-name>.<domain_or_ip>.nip.io`.

То есть Ansible нужен для подготовки инфраструктуры серверов, а не для регулярных деплоев приложений.
