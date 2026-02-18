# Ansible bootstrap for deploy VPS

This folder contains an idempotent bootstrap playbook for deploy servers used by AI-crew.

After bootstrap, deployment of new apps should go through the graph (DevOps -> git_commit -> deploy_trigger), without re-running Ansible on every deploy.

## Structure

- `playbooks/bootstrap_deploy_vps.yml` - main playbook
- `templates/traefik-docker-compose.yml.j2` - Traefik compose template
- `inventory/hosts.ini.example` - inventory example
- `group_vars/deploy_vps.yml.example` - shared vars example

## Prerequisites

1. Control machine has Ansible installed (`ansible-core` 2.14+).
2. SSH access to target hosts (root or sudo user).
3. Ubuntu/Debian target hosts.

## Quick start

1. Copy examples:

```bash
cp scripts/ansible/inventory/hosts.ini.example scripts/ansible/inventory/hosts.ini
cp scripts/ansible/group_vars/deploy_vps.yml.example scripts/ansible/group_vars/deploy_vps.yml
```

2. Edit:

- `scripts/ansible/inventory/hosts.ini` - hosts/IPs
- `scripts/ansible/group_vars/deploy_vps.yml` - deploy user/email/options

3. Run:

```bash
ansible-playbook -i scripts/ansible/inventory/hosts.ini scripts/ansible/playbooks/bootstrap_deploy_vps.yml
```

4. Verify on host:

```bash
docker ps
docker network ls | grep traefik-public
```

## What this playbook does

- installs Docker engine + docker compose plugin
- creates deploy user and adds it to docker group
- creates `/home/<deploy_user>/apps`
- creates Traefik files at `/home/<deploy_user>/traefik`
- creates shared docker network `traefik-public`
- starts Traefik with `docker compose up -d`

## Per new server: what to change

For each host in inventory, usually only:

- `ansible_host`
- `ansible_user`
- `deploy_user` (optional, default `deploy`)
- `traefik_email`
- `domain_ip` (optional, used in helper output only)

## Multi-server usage

Bootstrap all:

```bash
ansible-playbook -i scripts/ansible/inventory/hosts.ini scripts/ansible/playbooks/bootstrap_deploy_vps.yml
```

Bootstrap one host:

```bash
ansible-playbook -i scripts/ansible/inventory/hosts.ini scripts/ansible/playbooks/bootstrap_deploy_vps.yml --limit deploy-eu-1
```

## Notes

- Playbook is safe to re-run.
- This playbook does not deploy application code. It prepares server infrastructure only.
- Application deployments stay automated from graph/GitHub Actions after bootstrap.
