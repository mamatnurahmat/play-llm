"""
Config — Singleton konfigurasi untuk seluruh agent.
=====================================================
Membaca environment variables dari .env dan menyediakan
semua parameter yang dibutuhkan oleh agent-agent lain.
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv(override=True)

# Defaults per SCM provider
_PROVIDER_DEFAULTS = {
    "github":           "https://api.github.com",
    "gitlab":           "https://gitlab.com",
    "bitbucket_cloud":  "https://api.bitbucket.org/2.0",
    "bitbucket_server": "https://bitbucket.example.com",
}


@dataclass
class Config:
    """Immutable configuration container.

    Usage:
        cfg = Config.from_env()          # reads .env + os.environ
        cfg = Config.from_env(dotenv_path="/path/to/.env")
    """

    # SCM
    scm_provider: str = "github"
    scm_base_url: str = ""
    scm_org:      str = "MyOrg"
    scm_username: str = ""
    scm_token:    str = ""

    # LLM Gateway
    litellm_base_url:   str = "http://localhost:4000/v1"
    litellm_master_key: str = "sk-master-key-rahasia"
    model_name:         str = "gemini-1.5-pro"

    def __post_init__(self):
        self.scm_provider = self.scm_provider.lower()
        if not self.scm_base_url:
            self.scm_base_url = _PROVIDER_DEFAULTS.get(self.scm_provider, "https://api.github.com")

    # ----------------------------------------------------------------
    # Factory
    # ----------------------------------------------------------------
    @classmethod
    def from_env(cls, dotenv_path: str = None) -> "Config":
        """Create Config from environment variables (optionally loading a .env first)."""
        if dotenv_path:
            load_dotenv(dotenv_path, override=True)

        return cls(
            scm_provider      = os.environ.get("SCM_PROVIDER", "github"),
            scm_base_url      = os.environ.get("SCM_BASE_URL", "").strip(),
            scm_org            = os.environ.get("SCM_ORG", os.environ.get("GIT_ORG", "MyOrg")),
            scm_username       = os.environ.get("SCM_USERNAME", ""),
            scm_token          = os.environ.get("SCM_TOKEN", ""),
            litellm_base_url   = os.environ.get("LITELLM_BASE_URL", "http://localhost:4000/v1"),
            litellm_master_key = os.environ.get("LITELLM_MASTER_KEY", "sk-master-key-rahasia"),
            model_name         = os.environ.get("MODEL_NAME", "gemini-1.5-pro"),
        )

    @property
    def default_org(self) -> str:
        return self.scm_org
