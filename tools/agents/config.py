"""
Config — Singleton konfigurasi untuk seluruh agent.
=====================================================
Urutan loading environment variables:
  1. ~/.mantools/.env   (global config)
  2. ./.env             (project-level override)
  3. os.environ         (shell / CI override)

Default mode: Direct ke Gemini (tanpa LiteLLM).
"""

import os
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv

# Global config path
GLOBAL_CONFIG_DIR = Path.home() / ".mantools"
GLOBAL_ENV_FILE   = GLOBAL_CONFIG_DIR / ".env"

# Load order: global first, then local override
if GLOBAL_ENV_FILE.is_file():
    load_dotenv(GLOBAL_ENV_FILE, override=False)
load_dotenv(override=True)  # local .env

# Defaults per SCM provider
_PROVIDER_DEFAULTS = {
    "github":           "https://api.github.com",
    "gitlab":           "https://gitlab.com",
    "bitbucket_cloud":  "https://api.bitbucket.org/2.0",
    "bitbucket_server": "https://bitbucket.example.com",
}

# Defaults per LLM provider
_LLM_PROVIDER_DEFAULTS = {
    "gemini":    {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
                  "env_key": "GEMINI_API_KEY"},
    "openai":    {"base_url": "https://api.openai.com/v1",
                  "env_key": "OPENAI_API_KEY"},
    "anthropic": {"base_url": "https://api.anthropic.com/v1",
                  "env_key": "ANTHROPIC_API_KEY"},
    "ollama":    {"base_url": "http://localhost:11434/v1",
                  "env_key": ""},
}


@dataclass
class Config:
    """Immutable configuration container.

    Default: Direct ke Gemini API (LiteLLM disabled).

    Untuk enable LiteLLM gateway, set:
        LLM_PROVIDER=          (kosongkan)
        LITELLM_BASE_URL=http://localhost:4000/v1
        LITELLM_MASTER_KEY=sk-xxx
    """

    # SCM
    scm_provider: str = "github"
    scm_base_url: str = ""
    scm_org:      str = "MyOrg"
    scm_username: str = ""
    scm_token:    str = ""

    # LLM — default: direct gemini
    llm_provider:       str = "gemini"
    llm_api_key:        str = ""
    llm_base_url:       str = ""

    # LLM Gateway (hanya jika llm_provider kosong)
    litellm_base_url:   str = "http://localhost:4000/v1"
    litellm_master_key: str = ""

    # Model
    model_name:         str = "gemini-2.5-flash"

    def __post_init__(self):
        self.scm_provider = self.scm_provider.lower()
        if not self.scm_base_url:
            self.scm_base_url = _PROVIDER_DEFAULTS.get(self.scm_provider, "https://api.github.com")

    # ----------------------------------------------------------------
    # Computed Properties
    # ----------------------------------------------------------------

    @property
    def is_direct_mode(self) -> bool:
        """True if using direct LLM provider (not LiteLLM gateway)."""
        return bool(self.llm_provider)

    @property
    def effective_base_url(self) -> str:
        """Resolved base_url for the OpenAI client."""
        if self.is_direct_mode:
            if self.llm_base_url:
                return self.llm_base_url
            defaults = _LLM_PROVIDER_DEFAULTS.get(self.llm_provider, {})
            return defaults.get("base_url", "")
        return self.litellm_base_url

    @property
    def effective_api_key(self) -> str:
        """Resolved API key for the OpenAI client."""
        if self.is_direct_mode:
            if self.llm_api_key:
                return self.llm_api_key
            if self.llm_provider == "ollama":
                return "ollama"
            return ""
        return self.litellm_master_key

    @property
    def llm_mode_display(self) -> str:
        """Human-readable LLM mode string for CLI output."""
        if self.is_direct_mode:
            return f"Direct ({self.llm_provider.upper()})"
        return "Gateway (LiteLLM)"

    @property
    def default_org(self) -> str:
        return self.scm_org

    # ----------------------------------------------------------------
    # Factory
    # ----------------------------------------------------------------
    @classmethod
    def from_env(cls, dotenv_path: str = None) -> "Config":
        """Create Config from environment variables."""
        if dotenv_path:
            load_dotenv(dotenv_path, override=True)

        llm_provider = os.environ.get("LLM_PROVIDER", "gemini").lower().strip()

        # Auto-resolve API key from provider-specific env var
        llm_api_key = os.environ.get("LLM_API_KEY", "")
        if not llm_api_key and llm_provider:
            defaults = _LLM_PROVIDER_DEFAULTS.get(llm_provider, {})
            env_key = defaults.get("env_key", "")
            if env_key:
                llm_api_key = os.environ.get(env_key, "")

        return cls(
            scm_provider       = os.environ.get("SCM_PROVIDER", "github"),
            scm_base_url       = os.environ.get("SCM_BASE_URL", "").strip(),
            scm_org            = os.environ.get("SCM_ORG", os.environ.get("GIT_ORG", "MyOrg")),
            scm_username       = os.environ.get("SCM_USERNAME", ""),
            scm_token          = os.environ.get("SCM_TOKEN", ""),
            llm_provider       = llm_provider,
            llm_api_key        = llm_api_key,
            llm_base_url       = os.environ.get("LLM_BASE_URL", "").strip(),
            litellm_base_url   = os.environ.get("LITELLM_BASE_URL", "http://localhost:4000/v1"),
            litellm_master_key = os.environ.get("LITELLM_MASTER_KEY", ""),
            model_name         = os.environ.get("MODEL_NAME", "gemini-2.5-flash"),
        )

    # ----------------------------------------------------------------
    # Config File Management
    # ----------------------------------------------------------------

    @staticmethod
    def env_file_path(scope: str = "global") -> Path:
        """Return path to env file by scope."""
        if scope == "local":
            return Path.cwd() / ".env"
        return GLOBAL_ENV_FILE

    @staticmethod
    def set_env_var(key: str, value: str, scope: str = "global"):
        """Write or update a key=value in the env file."""
        env_path = Config.env_file_path(scope)
        env_path.parent.mkdir(parents=True, exist_ok=True)

        lines = []
        replaced = False
        if env_path.is_file():
            with open(env_path, "r") as f:
                for line in f:
                    if line.strip().startswith(f"{key}="):
                        lines.append(f"{key}={value}\n")
                        replaced = True
                    else:
                        lines.append(line)
        if not replaced:
            lines.append(f"{key}={value}\n")

        with open(env_path, "w") as f:
            f.writelines(lines)

    @staticmethod
    def show_config():
        """Print all config sources and current values."""
        cfg = Config.from_env()
        print("📂 Config Files:")
        print(f"   Global : {GLOBAL_ENV_FILE}" + (" ✅" if GLOBAL_ENV_FILE.is_file() else " (tidak ada)"))
        local_env = Path.cwd() / ".env"
        print(f"   Local  : {local_env}" + (" ✅" if local_env.is_file() else " (tidak ada)"))
        print()
        print("⚙️  Current Configuration:")
        print(f"   SCM_PROVIDER  = {cfg.scm_provider}")
        print(f"   SCM_ORG       = {cfg.scm_org}")
        print(f"   SCM_USERNAME  = {cfg.scm_username}")
        print(f"   SCM_TOKEN     = {'***' + cfg.scm_token[-4:] if len(cfg.scm_token) > 4 else '(empty)'}")
        print(f"   LLM_PROVIDER  = {cfg.llm_provider or '(gateway mode)'}")
        print(f"   LLM_API_KEY   = {'***' + cfg.llm_api_key[-4:] if len(cfg.llm_api_key) > 4 else '(empty)'}")
        print(f"   MODEL_NAME    = {cfg.model_name}")
        print(f"   LLM Mode      = {cfg.llm_mode_display}")
        print(f"   Effective URL  = {cfg.effective_base_url}")
