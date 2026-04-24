#!/usr/bin/env python3
"""
Git Manager AI Agent — CLI Entry Point (A2A Architecture)
==========================================================
Slim entry point yang backward-compatible dengan versi monolitik.

Usage:
    python agent_git.py <repo_name> [branch/tag]    # quick clone
    python agent_git.py server                       # REST API mode
    python agent_git.py check                        # pre-flight check

Environment Variables (.env):
    SCM_PROVIDER, SCM_BASE_URL, SCM_ORG, SCM_USERNAME, SCM_TOKEN
    LITELLM_BASE_URL, LITELLM_MASTER_KEY, MODEL_NAME
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

    # ---- Determine action & kwargs ----
    org    = cfg.default_org
    action = "clone"
    action_kwargs = {}

    # Non-interactive mode: python agent_git.py <repo> [branch]
    if len(sys.argv) >= 2 and sys.argv[1].lower() not in ("init",):
        repo_name     = sys.argv[1]
        action_kwargs = {"ref": sys.argv[2] if len(sys.argv) > 2 else "main"}
    else:
        # Interactive mode
        print("🚀 Git Manager AI Agent — Interactive Mode")
        print(f"   SCM Provider : {cfg.scm_provider.upper()}")
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
        print(f"   → LiteLLM Gateway berjalan di {cfg.litellm_base_url}")
        print(f"   → SCM_TOKEN sudah di-set di .env")
        print(f"   → git sudah terinstall")


if __name__ == "__main__":
    main()
