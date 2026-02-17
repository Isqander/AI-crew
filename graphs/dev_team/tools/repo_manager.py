"""
Deploy Repository Manager
==========================

Manages target repositories for deployed applications (single-repo strategy).

The ``RepoManager`` selects the target repo and branch for a given app.
The ``DeploySecretsManager`` writes VPS secrets to GitHub Secrets via API
so that GitHub Actions can SSH into the deploy VPS.

**Important:** This is *platform-level* code — the AI agents never see
the secret values.  They are read from the AI-crew server environment
and encrypted before being sent to GitHub.

Environment variables:
  - ``DEPLOY_SINGLE_REPO``    — e.g. ``user/ai-crew-deploy``
  - ``DEPLOY_VPS_SSH_KEY``    — path to file OR raw key content
  - ``DEPLOY_VPS_HOST``       — deploy VPS IP address
  - ``DEPLOY_VPS_USER``       — deploy user (default: ``deploy``)
  - ``GITHUB_TOKEN``          — with ``repo`` scope
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass

import httpx
import structlog

logger = structlog.get_logger()

GITHUB_API = "https://api.github.com"


@dataclass
class RepoTarget:
    """Target repository + branch for deployment."""
    repo: str           # "owner/repo-name"
    branch: str         # "project/todo-app"


class DeploySecretsManager:
    """Write deploy VPS secrets to a GitHub repo via the Actions Secrets API.

    Uses libsodium (PyNaCl) for encryption when available, otherwise falls
    back to a pure-Python tweetnacl implementation.

    The secrets written:
      - ``VPS_SSH_KEY`` — SSH private key for the deploy user
      - ``VPS_HOST``    — IP address of the deploy VPS
      - ``VPS_USER``    — username on the deploy VPS
    """

    def __init__(self, github_token: str | None = None):
        self.github_token = github_token or os.getenv("GITHUB_TOKEN", "")
        self._headers = {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _read_vps_ssh_key(self) -> str:
        """Read the VPS SSH key from env (path or inline content)."""
        raw = os.getenv("DEPLOY_VPS_SSH_KEY", "").strip()
        if not raw:
            return ""
        # If it looks like a file path, read the file
        if os.path.isfile(raw):
            with open(raw, "r", encoding="utf-8") as f:
                return f.read().strip()
        return raw

    def get_deploy_secrets(self) -> dict[str, str]:
        """Collect deploy secrets from the environment."""
        ssh_key = self._read_vps_ssh_key()
        host = os.getenv("DEPLOY_VPS_HOST", "").strip()
        user = os.getenv("DEPLOY_VPS_USER", "deploy").strip()

        secrets = {}
        if ssh_key:
            secrets["VPS_SSH_KEY"] = ssh_key
        if host:
            secrets["VPS_HOST"] = host
        if user:
            secrets["VPS_USER"] = user
        return secrets

    def _encrypt_secret(self, public_key_b64: str, secret_value: str) -> str:
        """Encrypt a secret value using the repo's public key (libsodium)."""
        try:
            from nacl import encoding, public as nacl_public
            public_key = nacl_public.PublicKey(
                public_key_b64.encode("utf-8"), encoding.Base64Encoder
            )
            sealed_box = nacl_public.SealedBox(public_key)
            encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
            return base64.b64encode(encrypted).decode("utf-8")
        except ImportError:
            logger.error("deploy_secrets.nacl_not_installed",
                         hint="Install PyNaCl: pip install pynacl")
            raise RuntimeError(
                "PyNaCl is required for GitHub Secrets encryption. "
                "Install it with: pip install pynacl"
            )

    def ensure_secrets(self, repo: str) -> dict[str, bool]:
        """Set deploy VPS secrets on the target GitHub repo (synchronous).

        Returns dict of {secret_name: success_bool}.
        """
        secrets = self.get_deploy_secrets()
        if not secrets:
            logger.warning("deploy_secrets.no_secrets",
                           hint="Set DEPLOY_VPS_SSH_KEY, DEPLOY_VPS_HOST in env")
            return {}

        # Get the repo's public key for encryption
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                f"{GITHUB_API}/repos/{repo}/actions/secrets/public-key",
                headers=self._headers,
            )
            if resp.status_code != 200:
                logger.error("deploy_secrets.get_public_key_failed",
                             repo=repo, status=resp.status_code,
                             body=resp.text[:200])
                return {name: False for name in secrets}

            key_data = resp.json()
            key_id = key_data["key_id"]
            public_key_b64 = key_data["key"]

        results: dict[str, bool] = {}
        for name, value in secrets.items():
            try:
                encrypted = self._encrypt_secret(public_key_b64, value)
                with httpx.Client(timeout=30) as client:
                    resp = client.put(
                        f"{GITHUB_API}/repos/{repo}/actions/secrets/{name}",
                        headers=self._headers,
                        json={
                            "encrypted_value": encrypted,
                            "key_id": key_id,
                        },
                    )
                success = resp.status_code in (201, 204)
                results[name] = success
                if success:
                    logger.info("deploy_secrets.set", repo=repo, secret=name)
                else:
                    logger.error("deploy_secrets.set_failed",
                                 repo=repo, secret=name,
                                 status=resp.status_code)
            except Exception as exc:
                logger.error("deploy_secrets.error",
                             repo=repo, secret=name, error=str(exc)[:200])
                results[name] = False

        return results


class RepoManager:
    """Manages the target repository for deploying generated applications.

    Strategy: single-repo.  All projects go into one shared repo
    (``DEPLOY_SINGLE_REPO``) on separate branches (``project/{app_name}``).
    """

    def __init__(self):
        self.single_repo = os.getenv("DEPLOY_SINGLE_REPO", "").strip()
        self.secrets_manager = DeploySecretsManager()

    def get_target(self, app_name: str) -> RepoTarget | None:
        """Return the target repo + branch for a given app.

        Returns ``None`` if deploy repo is not configured.
        """
        if not self.single_repo:
            logger.warning("repo_manager.no_deploy_repo",
                           hint="Set DEPLOY_SINGLE_REPO env var")
            return None
        return RepoTarget(
            repo=self.single_repo,
            branch=f"project/{app_name}",
        )

    def ensure_secrets(self, repo: str) -> dict[str, bool]:
        """Ensure deploy secrets are set on the repo (idempotent)."""
        return self.secrets_manager.ensure_secrets(repo)


# Module-level singleton
_repo_manager: RepoManager | None = None


def get_repo_manager() -> RepoManager:
    """Get or create the global RepoManager instance."""
    global _repo_manager
    if _repo_manager is None:
        _repo_manager = RepoManager()
    return _repo_manager
