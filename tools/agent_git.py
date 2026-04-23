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
import re
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


def git_create_branch(work_dir: str, existing_branch: str, new_branch: str) -> dict:
    """Creates a new branch from an existing branch and pushes it to remote.
    
    Args:
        work_dir: Path to the git repository directory.
        existing_branch: Name of the existing branch to base on.
        new_branch: Name of the new branch to create.
        
    Returns:
        dict: Dictionary with 'status' and 'message'.
    """
    try:
        subprocess.run(["git", "fetch", "origin", existing_branch], cwd=work_dir, capture_output=True)
        subprocess.run(["git", "checkout", existing_branch], cwd=work_dir, capture_output=True)
        subprocess.run(["git", "pull", "origin", existing_branch], cwd=work_dir, capture_output=True)
        res = subprocess.run(["git", "checkout", "-b", new_branch], cwd=work_dir, capture_output=True, text=True)
        if res.returncode != 0:
            return {"status": "error", "message": f"Failed to create new branch {new_branch}: {res.stderr}"}
            
        res_push = subprocess.run(["git", "push", "-u", "origin", new_branch], cwd=work_dir, capture_output=True, text=True)
        if res_push.returncode != 0:
            return {"status": "error", "message": f"Failed to push new branch {new_branch}: {res_push.stderr}"}
            
        return {"status": "success", "message": f"Successfully created and pushed branch {new_branch} based on {existing_branch}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def git_create_pull_request(work_dir: str, source_branch: str, dest_branch: str, title: str, body: str) -> dict:
    """Creates a pull request using GitHub CLI.
    
    Args:
        work_dir: Path to the git repository directory.
        source_branch: Name of the branch containing the changes.
        dest_branch: Name of the branch to merge into.
        title: Title of the pull request.
        body: Description/body of the pull request.
        
    Returns:
        dict: Dictionary with 'status' and 'message' (with PR URL).
    """
    try:
        cmd = [
            "gh", "pr", "create", 
            "--base", dest_branch, 
            "--head", source_branch, 
            "--title", title, 
            "--body", body
        ]
        res = subprocess.run(cmd, cwd=work_dir, capture_output=True, text=True)
        if res.returncode != 0:
            return {"status": "error", "message": f"Failed to create PR: {res.stderr}"}
            
        pr_url = res.stdout.strip()
        return {"status": "success", "message": f"Successfully created Pull Request: {pr_url}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def update_yaml_image(file_path: str, new_image: str) -> dict:
    """Updates the 'image: ...' line in a YAML file with the new image.
    
    Args:
        file_path: Path to the YAML file.
        new_image: The new image value.
    """
    try:
        with open(file_path, 'r') as f:
            lines = f.readlines()
            
        updated = False
        for i, line in enumerate(lines):
            if re.search(r'^\s*-?\s*image:\s*.*$', line):
                prefix = line[:line.find('image:')]
                lines[i] = f"{prefix}image: {new_image}\n"
                updated = True
                
        if not updated:
            return {"status": "error", "message": "No 'image:' key found in the file."}
            
        with open(file_path, 'w') as f:
            f.writelines(lines)
            
        return {"status": "success", "message": f"Successfully updated image in {file_path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def git_commit_and_push(work_dir: str, commit_message: str) -> dict:
    """Commits all changes and pushes to the remote repository.
    
    Args:
        work_dir: Path to the git repository directory.
        commit_message: The commit message to use.
    """
    try:
        subprocess.run(["git", "add", "."], cwd=work_dir, capture_output=True)
        res_commit = subprocess.run(["git", "commit", "-m", commit_message], cwd=work_dir, capture_output=True, text=True)
        if "nothing to commit" in res_commit.stdout:
            return {"status": "success", "message": "No changes to commit."}
            
        res_push = subprocess.run(["git", "push"], cwd=work_dir, capture_output=True, text=True)
        if res_push.returncode != 0:
            return {"status": "error", "message": f"Failed to push: {res_push.stderr}"}
            
        return {"status": "success", "message": "Successfully committed and pushed changes."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


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

async def run_git_agent(action: str, repo_name: str, org: str, action_kwargs: dict):
    """Menjalankan Git Manager AI Agent menggunakan LiteLLM / OpenAI."""

    full_repo = f"{org}/{repo_name}"
    dest_dir = repo_name

    instruction = dedent(f"""\
        Kamu adalah seorang Git Repository Manager yang ahli dalam mengelola repository GitHub.

        Repository target: {full_repo} (Local directory: '{dest_dir}')
    """)
    
    if action == "clone":
        ref = action_kwargs.get("ref", "main")
        instruction += dedent(f"""\
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
        6. Berikan laporan lengkap.
        """)
        user_message = f"Clone repository '{full_repo}' dengan branch/tag '{ref}' ke folder '{dest_dir}', lalu berikan laporan lengkap tentang repository tersebut."
        
    elif action == "create-branch":
        existing_branch = action_kwargs.get("existing_branch")
        new_branch = action_kwargs.get("new_branch")
        instruction += dedent(f"""\
        TUGAS UTAMA: Membuat branch baru bernama '{new_branch}' dari branch '{existing_branch}'.

        Langkah-langkah WAJIB:
        1. Cek apakah folder '{dest_dir}' sudah ada. Jika belum, lakukan git_clone terlebih dahulu dari branch '{existing_branch}'.
        2. Gunakan tool git_create_branch dengan work_dir='{dest_dir}', existing_branch='{existing_branch}', new_branch='{new_branch}'.
        3. Berikan laporan lengkap bahwa branch berhasil dibuat.
        """)
        user_message = f"Buat branch baru '{new_branch}' dari '{existing_branch}' pada repository '{full_repo}'."
        
    elif action == "pull-request":
        source_branch = action_kwargs.get("source_branch")
        dest_branch = action_kwargs.get("dest_branch")
        delete_after_merge = action_kwargs.get("delete_after_merge", True)
        
        instruction += dedent(f"""\
        TUGAS UTAMA: Membuat Pull Request dari branch '{source_branch}' menuju '{dest_branch}'.
        
        Langkah-langkah WAJIB:
        1. Cek apakah folder '{dest_dir}' sudah ada. Jika belum, lakukan git_clone.
        2. Gunakan tool git_create_pull_request dengan work_dir='{dest_dir}', source_branch='{source_branch}', dest_branch='{dest_branch}'.
           Buat judul (title) dan deskripsi (body) yang rapi secara otomatis.
        3. Jika Delete After Merge diaktifkan ({delete_after_merge}), jalankan tool run_shell_command dengan perintah `gh repo edit --delete-branch-on-merge` pada work_dir='{dest_dir}'.
        4. Berikan laporan lengkap berisi URL Pull Request tersebut.
        """)
        user_message = f"Buat Pull Request dari '{source_branch}' ke '{dest_branch}' pada repository '{full_repo}'."
        
    elif action == "update-image":
        ref = action_kwargs.get("ref", "main")
        yaml_file = action_kwargs.get("yaml_file")
        new_image = action_kwargs.get("new_image")
        
        instruction += dedent(f"""\
        TUGAS UTAMA: Memperbarui versi image pada file YAML dan melakukan push.
        
        Langkah-langkah WAJIB:
        1. Cek apakah folder '{dest_dir}' sudah ada. Jika belum, lakukan git_clone branch '{ref}'.
        2. Gunakan tool update_yaml_image dengan file_path='{dest_dir}/{yaml_file}' dan new_image='{new_image}'.
        3. Gunakan tool git_commit_and_push dengan work_dir='{dest_dir}' dan pesan commit 'Update image to {new_image}'.
        4. Berikan laporan bahwa image berhasil diupdate.
        """)
        user_message = f"Update file '{yaml_file}' dengan image '{new_image}' di branch '{ref}' pada repository '{full_repo}'."
    else:
        instruction += "\nTUGAS UTAMA: Bantu user sesuai instruksi."
        user_message = "Mulai tugas."

    available_functions = {
        "git_clone": git_clone,
        "git_clone_gh": git_clone_gh,
        "git_status": git_status,
        "git_log": git_log,
        "git_branch_list": git_branch_list,
        "git_tag_list": git_tag_list,
        "list_directory": list_directory,
        "read_file": read_file,
        "run_shell_command": run_shell_command,
        "git_create_branch": git_create_branch,
        "git_create_pull_request": git_create_pull_request,
        "update_yaml_image": update_yaml_image,
        "git_commit_and_push": git_commit_and_push
    }
    
    tools = get_openai_tools(list(available_functions.values()))

    client = AsyncOpenAI(
        api_key=LITELLM_MASTER_KEY,
        base_url=LITELLM_BASE_URL
    )

    messages = [
        {"role": "system", "content": instruction},
        {"role": "user", "content": user_message}
    ]

    print(f"📦 Repository : {full_repo}")
    print(f"📂 Dest Dir   : {dest_dir}")
    print(f"⚡ Action     : {action}")
    if action == "clone":
        print(f"🌿 Branch/Tag : {action_kwargs.get('ref', 'main')}")
    elif action == "create-branch":
        print(f"🌿 Source     : {action_kwargs.get('existing_branch')}")
        print(f"✨ New Branch : {action_kwargs.get('new_branch')}")
    elif action == "pull-request":
        print(f"🌿 Source     : {action_kwargs.get('source_branch')}")
        print(f"🎯 Target     : {action_kwargs.get('dest_branch')}")
    elif action == "update-image":
        print(f"🌿 Branch     : {action_kwargs.get('ref')}")
        print(f"📄 YAML File  : {action_kwargs.get('yaml_file')}")
        print(f"📦 New Image  : {action_kwargs.get('new_image')}")

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
    org = DEFAULT_ORG
    action = "clone"
    action_kwargs = {}

    if len(sys.argv) < 2 or sys.argv[1].lower() == "init":
        print("🚀 Memulai mode interaktif...")
        try:
            print("\nPilih Aksi:")
            print("1. Clone / Analyze Repository")
            print("2. Create Branch")
            print("3. Create Pull Request")
            print("4. Update Image in YAML")
            action_choice = input("Masukkan pilihan (1/2/3/4) [1]: ").strip()
            
            repo_input = input("Masukkan nama repository: ").strip()
            if not repo_input:
                print("❌ Error: Nama repository wajib diisi.")
                sys.exit(1)
            repo_name = repo_input
                
            org_input = input(f"Masukkan nama organisasi git [{DEFAULT_ORG}]: ").strip()
            if org_input:
                org = org_input
                
            if action_choice == "2":
                action = "create-branch"
                exist_b = input("Masukkan nama existing branch [main]: ").strip() or "main"
                new_b = input("Masukkan nama branch baru yg akan dibuat: ").strip()
                if not new_b:
                    print("❌ Error: Nama branch baru wajib diisi.")
                    sys.exit(1)
                action_kwargs = {"existing_branch": exist_b, "new_branch": new_b}
                
            elif action_choice == "3":
                action = "pull-request"
                src_b = input("Masukkan nama source branch: ").strip()
                if not src_b:
                    print("❌ Error: Source branch wajib diisi.")
                    sys.exit(1)
                dst_b = input("Masukkan nama destination branch [main]: ").strip() or "main"
                del_merge = input("Delete source branch after merge? (y/n) [y]: ").strip().lower()
                action_kwargs = {
                    "source_branch": src_b, 
                    "dest_branch": dst_b,
                    "delete_after_merge": del_merge != 'n'
                }
                
            elif action_choice == "4":
                action = "update-image"
                ref_b = input("Masukkan nama branch [main]: ").strip() or "main"
                yaml_f = input("Masukkan lokasi file YAML (misal: deployment.yaml): ").strip()
                if not yaml_f:
                    print("❌ Error: Lokasi file YAML wajib diisi.")
                    sys.exit(1)
                img = input("Masukkan nama image baru (misal: repo/app:v1.2.3): ").strip()
                if not img:
                    print("❌ Error: Nama image wajib diisi.")
                    sys.exit(1)
                action_kwargs = {
                    "ref": ref_b,
                    "yaml_file": yaml_f,
                    "new_image": img
                }
                
            else:
                action = "clone"
                ref_input = input("Masukkan nama branch/tag [main]: ").strip()
                action_kwargs = {"ref": ref_input if ref_input else "main"}
                
        except EOFError:
            print("\n❌ Error: Input dibatalkan.")
            sys.exit(1)
    else:
        action = "clone"
        repo_name = sys.argv[1]
        action_kwargs = {"ref": sys.argv[2] if len(sys.argv) > 2 else "main"}

    try:
        asyncio.run(run_git_agent(action, repo_name, org, action_kwargs))
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
