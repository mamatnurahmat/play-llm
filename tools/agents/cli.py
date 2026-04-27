"""
CLI entry point for the `mantools` PyPI package.
==================================================
Usage after `pip install mantools`:
    mantools check                         # pre-flight check
    mantools server                        # REST API mode
    mantools config                        # show current config
    mantools config set KEY VALUE          # set env var globally (~/.mantools/.env)
    mantools config set KEY VALUE --local  # set env var locally (./.env)
    mantools config init                   # interactive setup wizard
    mantools <repo_name> [branch]          # quick clone
"""

import os
import sys
import asyncio

os.environ["NETRC"] = "/dev/null"

from agents.config import Config
from agents.clone_agent import CloneAgent
from agents.branch_agent import BranchAgent
from agents.pr_agent import PRAgent
from agents.update_image_agent import UpdateImageAgent
from agents.quick_pr_agent import QuickPRAgent
from agents.health_check import HealthChecker
from agents.server import run_server

# Agent registry: action → class
AGENT_REGISTRY = {
    "clone":         CloneAgent,
    "create-branch": BranchAgent,
    "pull-request":  PRAgent,
    "update-image":  UpdateImageAgent,
    "quick-pr":      QuickPRAgent,
}

# Reserved CLI subcommands (not treated as repo names)
_SUBCOMMANDS = {"server", "check", "config", "init"}


def _run_config(argv: list):
    """Handle `mantools config` subcommands."""
    if len(argv) <= 2 or argv[2] == "show":
        Config.show_config()
        return

    if argv[2] == "set":
        if len(argv) < 5:
            print("Usage: mantools config set KEY VALUE [--local]")
            print()
            print("Contoh:")
            print("  mantools config set GEMINI_API_KEY AIza...")
            print("  mantools config set SCM_TOKEN ghp_xxx --local")
            print()
            print("Keys yang tersedia:")
            print("  SCM_PROVIDER, SCM_ORG, SCM_USERNAME, SCM_TOKEN")
            print("  LLM_PROVIDER, GEMINI_API_KEY, OPENAI_API_KEY, LLM_API_KEY")
            print("  MODEL_NAME, LLM_BASE_URL")
            sys.exit(1)
        key   = argv[3].upper()
        value = argv[4]
        scope = "local" if "--local" in argv[5:] else "global"
        Config.set_env_var(key, value, scope)
        target = Config.env_file_path(scope)
        print(f"✅ {key} disimpan di {target}")
        return

    if argv[2] == "init":
        _run_config_init()
        return

    print(f"❌ Unknown config command: {argv[2]}")
    print("   Available: show, set, init")
    sys.exit(1)


def _run_config_init():
    """Interactive config initialization wizard."""
    print("🔧 ManTools — Config Wizard")
    print("   Menyimpan ke ~/.mantools/.env\n")

    scope = "global"

    try:
        # SCM
        provider = input("SCM Provider (github/gitlab/bitbucket_cloud) [github]: ").strip() or "github"
        Config.set_env_var("SCM_PROVIDER", provider, scope)

        org = input("SCM Organization/Namespace: ").strip()
        if org:
            Config.set_env_var("SCM_ORG", org, scope)

        username = input("SCM Username: ").strip()
        if username:
            Config.set_env_var("SCM_USERNAME", username, scope)

        token = input("SCM Token (PAT): ").strip()
        if token:
            Config.set_env_var("SCM_TOKEN", token, scope)

        # LLM
        print()
        print("LLM Provider:")
        print("  1. Gemini (default)")
        print("  2. OpenAI")
        print("  3. Anthropic")
        print("  4. Ollama (lokal)")
        llm_choice = input("Pilih (1/2/3/4) [1]: ").strip() or "1"

        llm_map = {"1": "gemini", "2": "openai", "3": "anthropic", "4": "ollama"}
        llm_provider = llm_map.get(llm_choice, "gemini")
        Config.set_env_var("LLM_PROVIDER", llm_provider, scope)

        if llm_provider == "gemini":
            api_key = input("Gemini API Key (AIza...): ").strip()
            if api_key:
                Config.set_env_var("GEMINI_API_KEY", api_key, scope)
            model = input("Model [gemini-2.5-flash]: ").strip() or "gemini-2.5-flash"
        elif llm_provider == "openai":
            api_key = input("OpenAI API Key (sk-...): ").strip()
            if api_key:
                Config.set_env_var("OPENAI_API_KEY", api_key, scope)
            model = input("Model [gpt-4o]: ").strip() or "gpt-4o"
        elif llm_provider == "anthropic":
            api_key = input("Anthropic API Key: ").strip()
            if api_key:
                Config.set_env_var("ANTHROPIC_API_KEY", api_key, scope)
            model = input("Model [claude-sonnet-4-20250514]: ").strip() or "claude-sonnet-4-20250514"
        elif llm_provider == "ollama":
            base_url = input("Ollama URL [http://localhost:11434/v1]: ").strip()
            if base_url:
                Config.set_env_var("LLM_BASE_URL", base_url, scope)
            model = input("Model [qwen2.5-coder:14b]: ").strip() or "qwen2.5-coder:14b"
        else:
            model = "gemini-2.5-flash"

        Config.set_env_var("MODEL_NAME", model, scope)

        print()
        print(f"✅ Config tersimpan di {Config.env_file_path(scope)}")
        print("   Jalankan `mantools check` untuk verifikasi.")

    except (EOFError, KeyboardInterrupt):
        print("\n❌ Dibatalkan.")
        sys.exit(1)


def main():
    cfg = Config.from_env()

    # ---- Sub-commands ----
    if len(sys.argv) > 1 and sys.argv[1].lower() == "server":
        run_server(cfg)
        return

    if len(sys.argv) > 1 and sys.argv[1].lower() == "check":
        checker = HealthChecker(cfg)
        checker.run()
        return

    if len(sys.argv) > 1 and sys.argv[1].lower() == "config":
        _run_config(sys.argv)
        return

    # ---- Determine action & kwargs ----
    org    = cfg.default_org
    action = "clone"
    action_kwargs = {}

    # Non-interactive mode: mantools <repo> [branch]
    if len(sys.argv) >= 2 and sys.argv[1].lower() not in _SUBCOMMANDS:
        repo_name     = sys.argv[1]
        action_kwargs = {"ref": sys.argv[2] if len(sys.argv) > 2 else "main"}
    else:
        # Interactive mode
        print("🚀 ManTools — GitOps AI Agent")
        print(f"   SCM Provider : {cfg.scm_provider.upper()}")
        print(f"   LLM Mode     : {cfg.llm_mode_display}")
        print(f"   SCM Base URL : {cfg.scm_base_url}\n")
        try:
            print("Pilih Aksi:")
            print("  1. Clone / Analyze Repository")
            print("  2. Create Branch (via API)")
            print("  3. Create Pull/Merge Request (via API)")
            print("  4. Update Image in YAML")
            print("  5. Quick PR (Update Image -> PR)")
            choice = input("Pilihan (1/2/3/4/5) [1]: ").strip() or "1"

            if choice == "5":
                repo_name = input("Nama repository [gitops]: ").strip() or "gitops"
            else:
                repo_name = input("Nama repository: ").strip()
                if not repo_name:
                    print("❌ Nama repository wajib diisi."); sys.exit(1)

            org_in = input(f"Organisasi [{cfg.default_org}]: ").strip()
            if org_in:
                org = org_in

            if choice == "2":
                action  = "create-branch"
                exist_b = input("Existing branch [main]: ").strip() or "main"
                new_b   = input("Nama branch baru: ").strip()
                if not new_b: print("❌ Nama branch baru wajib."); sys.exit(1)
                action_kwargs = {"existing_branch": exist_b, "new_branch": new_b}

            elif choice == "3":
                action = "pull-request"
                src_b  = input("Source branch: ").strip()
                if not src_b: print("❌ Source branch wajib."); sys.exit(1)
                dst_b  = input("Destination branch [main]: ").strip() or "main"
                action_kwargs = {"source_branch": src_b, "dest_branch": dst_b}

            elif choice == "4":
                action = "update-image"
                ref_b  = input("Branch [main]: ").strip() or "main"
                yaml_f = input("Path file YAML (misal: deployment.yaml): ").strip()
                if not yaml_f: print("❌ Path YAML wajib."); sys.exit(1)
                img    = input("Image baru (misal: app:v2.0.0): ").strip()
                if not img: print("❌ Image wajib."); sys.exit(1)
                action_kwargs = {"ref": ref_b, "yaml_file": yaml_f, "new_image": img}

            elif choice == "5":
                action = "quick-pr"
                ns     = input("Namespace [default]: ").strip() or "default"
                dep    = input("Nama Deployment: ").strip()
                if not dep: print("❌ Nama deployment wajib."); sys.exit(1)
                img    = input("Image baru (misal: app:v1.2.3): ").strip()
                if not img: print("❌ Image wajib."); sys.exit(1)
                action_kwargs = {"namespace": ns, "deployment": dep, "image": img}

            else:
                action = "clone"
                ref    = input("Branch/Tag [main]: ").strip() or "main"
                action_kwargs = {"ref": ref}

        except EOFError:
            print("\n❌ Input dibatalkan."); sys.exit(1)

    # ---- Instantiate & Run Agent ----
    agent_cls = AGENT_REGISTRY.get(action)
    if not agent_cls:
        print(f"❌ Unknown action: {action}")
        print(f"   Available: {', '.join(AGENT_REGISTRY.keys())}")
        sys.exit(1)

    agent = agent_cls(config=cfg, repo_name=repo_name, org=org, action_kwargs=action_kwargs)

    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        print("\n⚠️ Dihentikan oleh pengguna.")
    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {e}")
        print(f"\n💡 Pastikan:")
        print(f"   → LLM tersedia di {cfg.effective_base_url}")
        print(f"   → SCM_TOKEN sudah di-set di .env")
        print(f"   → git sudah terinstall")


if __name__ == "__main__":
    main()
