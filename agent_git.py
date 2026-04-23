#!/usr/bin/env python3
"""
Git Manager AI Agent - OpenAI Compatible (LiteLLM Gateway)
=========================================================
Agent untuk melakukan git clone repository dari organisasi GitHub
dengan single-branch mode, lalu menganalisa struktur project.

Menggunakan LiteLLM Gateway yang berjalan di localhost:4000

Usage:
    python agent_git.py <repo_name> [branch/tag]
    python agent_git.py gitops-k8s develop
    python agent_git.py crypner-be-digitoken-module v1.2.3

Default org: Qoin-Digital-Indonesia
Default ref: main (single-branch)
"""
import os
import sys
import json
import asyncio
import subprocess
import warnings
import inspect
from textwrap import dedent

# Bypass .netrc parsing error
os.environ["NETRC"] = "/dev/null"

from dotenv import load_dotenv

try:
    from openai import AsyncOpenAI
except ImportError:
    print("❌ Error: Package 'openai' tidak ditemukan.")
    print("   Silakan install dengan: pip install openai")
    sys.exit(1)

# Load environment variables
load_dotenv()

# Konfigurasi default
DEFAULT_ORG = os.environ.get("GIT_ORG", "Qoin-Digital-Indonesia")
LITELLM_MASTER_KEY = os.environ.get("LITELLM_MASTER_KEY", "sk-master-key-rahasia")
LITELLM_BASE_URL = os.environ.get("LITELLM_BASE_URL", "http://localhost:4000/v1")
MODEL_NAME = os.environ.get("MODEL_NAME", "gemini-1.5-pro")

if not os.environ.get("LITELLM_MASTER_KEY"):
    print("⚠️ Peringatan: LITELLM_MASTER_KEY tidak ditemukan di .env. Menggunakan default.")

# ============================================================
# Definisi Custom Tools (Python Functions)
# ============================================================

def git_clone(repo_url: str, dest_dir: str, branch: str, single_branch: bool) -> dict:
    """Clones a git repository to a local directory.

    Args:
        repo_url: Full repository URL (e.g. 'https://github.com/Qoin-Digital-Indonesia/gitops-k8s.git')
        dest_dir: Local destination directory name for the cloned repo.
        branch: Branch or tag name to checkout (e.g. 'main', 'develop', 'v1.2.3').
        single_branch: If true, clone only the specified branch (faster, less disk usage).

    Returns:
        dict: Dictionary with 'status' and 'message' keys.
    """
    try:
        cmd = ["git", "clone", "--branch", branch]
        if single_branch:
            cmd.append("--single-branch")
        cmd.extend([repo_url, dest_dir])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            return {"status": "success", "message": f"Successfully cloned {repo_url} (branch: {branch}) to {dest_dir}"}
        else:
            return {"status": "error", "message": f"Git clone failed: {result.stderr.strip()}"}
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "Git clone timed out after 120 seconds."}
    except Exception as e:
        return {"status": "error", "message": f"Error: {e}"}


def git_clone_gh(repo_name: str, dest_dir: str, branch: str) -> dict:
    """Clones a git repository using GitHub CLI (gh). Supports SSH/HTTPS based on gh config.

    Args:
        repo_name: Short repository name with org (e.g. 'Qoin-Digital-Indonesia/gitops-k8s').
        dest_dir: Local destination directory name for the cloned repo.
        branch: Branch or tag name to checkout.

    Returns:
        dict: Dictionary with 'status' and 'message' keys.
    """
    try:
        cmd = ["gh", "repo", "clone", repo_name, dest_dir, "--", "-b", branch, "--single-branch"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            return {"status": "success", "message": f"Successfully cloned {repo_name} (branch: {branch}) to {dest_dir}"}
        else:
            return {"status": "error", "message": f"gh clone failed: {result.stderr.strip()}"}
    except FileNotFoundError:
        return {"status": "error", "message": "GitHub CLI (gh) is not installed. Please install it or use git_clone tool instead."}
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "gh clone timed out after 120 seconds."}
    except Exception as e:
        return {"status": "error", "message": f"Error: {e}"}


def git_status(work_dir: str) -> dict:
    """Shows the git status of a repository.

    Args:
        work_dir: Path to the git repository directory.

    Returns:
        dict: Dictionary with 'status', 'branch', and 'output' keys.
    """
    try:
        # Get current branch
        branch_result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=work_dir, capture_output=True, text=True
        )
        # Get status
        status_result = subprocess.run(
            ["git", "status", "--short"],
            cwd=work_dir, capture_output=True, text=True
        )
        # Get last commit
        log_result = subprocess.run(
            ["git", "log", "-1", "--oneline"],
            cwd=work_dir, capture_output=True, text=True
        )
        return {
            "status": "success",
            "branch": branch_result.stdout.strip(),
            "changes": status_result.stdout.strip() or "(clean - no changes)",
            "last_commit": log_result.stdout.strip()
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def git_log(work_dir: str, count: int) -> dict:
    """Shows the recent git log entries.

    Args:
        work_dir: Path to the git repository directory.
        count: Number of log entries to show (max 20).

    Returns:
        dict: Dictionary with 'status' and 'log' keys.
    """
    try:
        n = min(int(count), 20)
        result = subprocess.run(
            ["git", "log", f"-{n}", "--oneline", "--decorate"],
            cwd=work_dir, capture_output=True, text=True
        )
        if result.returncode == 0:
            return {"status": "success", "log": result.stdout.strip()}
        else:
            return {"status": "error", "log": result.stderr.strip()}
    except Exception as e:
        return {"status": "error", "log": str(e)}


def git_branch_list(work_dir: str) -> dict:
    """Lists all branches (local and remote) in a repository.

    Args:
        work_dir: Path to the git repository directory.

    Returns:
        dict: Dictionary with 'status' and 'branches' keys.
    """
    try:
        result = subprocess.run(
            ["git", "branch", "-a"],
            cwd=work_dir, capture_output=True, text=True
        )
        if result.returncode == 0:
            branches = [b.strip() for b in result.stdout.strip().split("\n") if b.strip()]
            return {"status": "success", "branches": branches}
        else:
            return {"status": "error", "branches": [], "message": result.stderr.strip()}
    except Exception as e:
        return {"status": "error", "branches": [], "message": str(e)}


def git_tag_list(work_dir: str) -> dict:
    """Lists all tags in a repository.

    Args:
        work_dir: Path to the git repository directory.

    Returns:
        dict: Dictionary with 'status' and 'tags' keys.
    """
    try:
        result = subprocess.run(
            ["git", "tag", "-l", "--sort=-v:refname"],
            cwd=work_dir, capture_output=True, text=True
        )
        if result.returncode == 0:
            tags = [t.strip() for t in result.stdout.strip().split("\n") if t.strip()]
            return {"status": "success", "tags": tags}
        else:
            return {"status": "error", "tags": [], "message": result.stderr.strip()}
    except Exception as e:
        return {"status": "error", "tags": [], "message": str(e)}


def list_directory(dir_path: str) -> dict:
    """Lists all files and subdirectories in a given directory path.

    Args:
        dir_path: Path to the directory to list.

    Returns:
        dict: Dictionary with 'status' and 'entries' keys.
    """
    try:
        entries = os.listdir(dir_path)
        return {"status": "success", "entries": entries}
    except Exception as e:
        return {"status": "error", "entries": [], "message": str(e)}


def read_file(file_path: str) -> dict:
    """Reads the content of a file from the local filesystem.

    Args:
        file_path: Path to the file to read.

    Returns:
        dict: Dictionary with 'status' and 'content' keys.
    """
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        return {"status": "success", "content": content}
    except Exception as e:
        return {"status": "error", "content": f"Error reading file: {e}"}


def run_shell_command(command: str, work_dir: str) -> dict:
    """Runs a shell command in a specified working directory. Only allows safe read-only commands.

    Args:
        command: The shell command to execute (e.g. 'ls -la', 'cat README.md', 'git diff').
        work_dir: Directory to run the command in.

    Returns:
        dict: Dictionary with 'status', 'stdout', and 'stderr' keys.
    """
    # Daftar command yang diizinkan (read-only / safe)
    allowed_prefixes = ["ls", "cat", "head", "tail", "wc", "find", "tree", "git log", "git diff", "git show", "git branch", "git tag", "git remote"]
    is_allowed = any(command.strip().startswith(prefix) for prefix in allowed_prefixes)

    if not is_allowed:
        return {"status": "error", "stdout": "", "stderr": f"Command '{command}' is not allowed. Only read-only commands are permitted."}

    try:
        result = subprocess.run(
            command, shell=True, cwd=work_dir,
            capture_output=True, text=True, timeout=30
        )
        return {
            "status": "success" if result.returncode == 0 else "error",
            "stdout": result.stdout.strip()[:2000],  # Limit output
            "stderr": result.stderr.strip()[:500]
        }
    except subprocess.TimeoutExpired:
        return {"status": "error", "stdout": "", "stderr": "Command timed out after 30 seconds."}
    except Exception as e:
        return {"status": "error", "stdout": "", "stderr": str(e)}


# ============================================================
# OpenAI Tools Converter
# ============================================================

def get_openai_tools(functions):
    """Converts standard Python functions into OpenAI function calling schemas."""
    tools = []
    for func in functions:
        sig = inspect.signature(func)
        properties = {}
        required = []
        for name, param in sig.parameters.items():
            param_type = "string"
            if param.annotation == int:
                param_type = "integer"
            elif param.annotation == bool:
                param_type = "boolean"
            
            properties[name] = {
                "type": param_type,
                "description": f"Parameter {name}"
            }
            if param.default == inspect.Parameter.empty:
                required.append(name)
                
        tools.append({
            "type": "function",
            "function": {
                "name": func.__name__,
                "description": func.__doc__.split("\n")[0] if func.__doc__ else f"Call {func.__name__}",
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        })
    return tools

# ============================================================
# Fungsi utama untuk menjalankan Agent
# ============================================================

async def run_git_agent(repo_name: str, ref: str, org: str):
    """Menjalankan Git Manager AI Agent menggunakan LiteLLM / OpenAI."""

    full_repo = f"{org}/{repo_name}"
    dest_dir = repo_name

    instruction = dedent(f"""\
        Kamu adalah seorang Git Repository Manager yang ahli dalam mengelola repository GitHub.

        TUGAS UTAMA: Clone repository {full_repo} dengan branch/tag '{ref}' (single-branch mode), lalu analisa strukturnya.

        Langkah-langkah WAJIB:
        1. Cek apakah folder '{dest_dir}' sudah ada menggunakan tool list_directory pada direktori '.'.
           - Jika sudah ada, JANGAN clone ulang. Langsung lanjut ke langkah 3.
           - Jika belum ada, lanjut ke langkah 2.
        2. Clone repository menggunakan tool git_clone_gh dengan repo_name='{full_repo}', dest_dir='{dest_dir}', branch='{ref}'.
           Jika git_clone_gh gagal (misalnya gh tidak tersedia), coba menggunakan tool git_clone dengan repo_url='https://github.com/{full_repo}.git', dest_dir='{dest_dir}', branch='{ref}', single_branch=true.
        3. Setelah clone berhasil atau folder sudah ada, gunakan tool git_status untuk melihat status repository di folder '{dest_dir}'.
        4. Gunakan tool list_directory untuk melihat isi folder '{dest_dir}'.
        5. Gunakan tool git_log dengan work_dir='{dest_dir}' dan count=5 untuk melihat 5 commit terakhir.
        6. Berikan laporan lengkap berisi:
           - Status clone (berhasil/sudah ada)
           - Branch/tag aktif
           - Struktur folder (daftar file/folder)
           - 5 commit terakhir
           - Ringkasan singkat tentang project berdasarkan file yang ada

        PENTING: Kamu HARUS menyelesaikan SEMUA langkah dan memberikan laporan lengkap di akhir.
    """)

    available_functions = {
        "git_clone": git_clone,
        "git_clone_gh": git_clone_gh,
        "git_status": git_status,
        "git_log": git_log,
        "git_branch_list": git_branch_list,
        "git_tag_list": git_tag_list,
        "list_directory": list_directory,
        "read_file": read_file,
        "run_shell_command": run_shell_command
    }
    
    tools = get_openai_tools(list(available_functions.values()))

    client = AsyncOpenAI(
        api_key=LITELLM_MASTER_KEY,
        base_url=LITELLM_BASE_URL
    )

    messages = [
        {"role": "system", "content": instruction},
        {"role": "user", "content": f"Clone repository '{full_repo}' dengan branch/tag '{ref}' ke folder '{dest_dir}', lalu berikan laporan lengkap tentang repository tersebut."}
    ]

    print(f"📦 Repository : {full_repo}")
    print(f"🌿 Branch/Tag : {ref}")
    print(f"📂 Dest Dir   : {dest_dir}")
    print(f"🤖 Memulai Git Manager AI Agent (LiteLLM Gateway + {MODEL_NAME})...\n")

    max_turns = 15
    for turn in range(max_turns):
        response = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            tools=tools,
            tool_choice="auto"
        )
        
        response_message = response.choices[0].message
        
        # Simpan message dari assistant ke history
        messages.append(response_message)
        
        if response_message.content:
            print(f"\n{response_message.content}")
            
        if response_message.tool_calls:
            for tool_call in response_message.tool_calls:
                func_name = tool_call.function.name
                try:
                    func_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    func_args = {}
                    
                print(f"  🔧 Memanggil tool: {func_name}({func_args})")
                
                func = available_functions.get(func_name)
                if func:
                    result = func(**func_args)
                else:
                    result = {"status": "error", "message": f"Tool {func_name} not found"}
                    
                print(f"  ✅ Tool response diterima: {func_name}")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": func_name,
                    "content": json.dumps(result)
                })
        else:
            # Tidak ada tool call lagi, berarti agent sudah memberikan final answer
            break

    # Status akhir
    print("\n######################")
    print(f"📋 Status Akhir:")
    if os.path.isdir(dest_dir):
        print(f"   ✅ Repository tersedia di: {os.path.abspath(dest_dir)}")
    else:
        print(f"   ❌ Repository tidak ditemukan (Clone gagal).")


# ============================================================
# Entry Point
# ============================================================
def main():
    repo_name = None
    ref = "main"

    if len(sys.argv) < 2:
        print("❌ Error: Nama repository wajib diisi.")
        print(f"\nUsage: python agent_git.py <repo_name> [branch/tag]")
        print(f"\nContoh:")
        print(f"  python agent_git.py gitops-k8s")
        print(f"  python agent_git.py gitops-k8s develop")
        print(f"  python agent_git.py crypner-be-digitoken-module v1.2.3")
        print(f"\nDefault org: {DEFAULT_ORG}")
        print(f"Default ref: main (single-branch)")
        sys.exit(1)

    repo_name = sys.argv[1]
    if len(sys.argv) > 2:
        ref = sys.argv[2]

    try:
        asyncio.run(run_git_agent(repo_name, ref, DEFAULT_ORG))
    except KeyboardInterrupt:
        print("\n\n⚠️ Agent dihentikan oleh pengguna (Ctrl+C).")
    except Exception as e:
        print(f"\n❌ Error saat menjalankan agent:")
        print(f"   Tipe  : {type(e).__name__}")
        print(f"   Pesan : {e}")
        print(f"\n💡 Tips Troubleshooting:")
        print(f"   → Pastikan LiteLLM Gateway sedang berjalan di {LITELLM_BASE_URL}")
        print(f"   → Cek apakah package 'openai' terinstall: pip install openai")
        print(f"   → Pastikan git dan/atau gh (GitHub CLI) terinstall.")

if __name__ == "__main__":
    main()
