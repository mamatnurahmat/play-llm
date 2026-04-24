#!/usr/bin/env python3
"""
Git Manager AI Agent - Multi-SCM (GitHub / GitLab / Bitbucket)
===============================================================
Agent untuk melakukan operasi git pada berbagai SCM provider
menggunakan native HTTPS API (tidak bergantung pada GitHub CLI).

Mendukung provider: GitHub, GitLab, Bitbucket Server/Cloud
Menggunakan LiteLLM Gateway yang berjalan di localhost:4000

Usage:
    python agent_git.py <repo_name> [branch/tag]
    python agent_git.py my-service develop
    python agent_git.py my-service v1.2.3

    python agent_git.py server   # jalankan sebagai REST API
    python agent_git.py check    # periksa env, koneksi SCM, dan LLM

Environment Variables (.env):
    SCM_PROVIDER        = github | gitlab | bitbucket_cloud | bitbucket_server
    SCM_BASE_URL        = https://api.github.com         # sesuaikan provider
    SCM_ORG             = MyOrg                          # username/org/project
    SCM_USERNAME        = myuser                         # untuk clone HTTPS & API auth
    SCM_TOKEN           = ghp_xxxx / glpat-xxxx / ...   # PAT / App Password

    LITELLM_BASE_URL    = http://localhost:4000/v1
    LITELLM_MASTER_KEY  = sk-master-key-rahasia
    MODEL_NAME          = gemini-1.5-pro
"""

import os
import sys
import json
import asyncio
import subprocess
import inspect
import re
import urllib.request
import urllib.error
import urllib.parse
import base64
from textwrap import dedent

os.environ["NETRC"] = "/dev/null"

from dotenv import load_dotenv

try:
    from openai import AsyncOpenAI
except ImportError:
    print("❌ Error: Package 'openai' tidak ditemukan.")
    print("   Silakan install dengan: pip install openai")
    sys.exit(1)

load_dotenv(override=True)

# ============================================================
# Konfigurasi SCM Provider
# ============================================================

SCM_PROVIDER    = os.environ.get("SCM_PROVIDER", "github").lower()
SCM_BASE_URL    = os.environ.get("SCM_BASE_URL", "").strip()
SCM_ORG         = os.environ.get("SCM_ORG", os.environ.get("GIT_ORG", "MyOrg"))
SCM_USERNAME    = os.environ.get("SCM_USERNAME", "")
SCM_TOKEN       = os.environ.get("SCM_TOKEN", "")

# Default SCM_BASE_URL per provider jika tidak di-set
_PROVIDER_DEFAULTS = {
    "github":           "https://api.github.com",
    "gitlab":           "https://gitlab.com",
    "bitbucket_cloud":  "https://api.bitbucket.org/2.0",
    "bitbucket_server": "https://bitbucket.example.com",   # ganti dengan host Anda
}
if not SCM_BASE_URL:
    SCM_BASE_URL = _PROVIDER_DEFAULTS.get(SCM_PROVIDER, "https://api.github.com")

# LiteLLM / OpenAI Gateway
LITELLM_MASTER_KEY = os.environ.get("LITELLM_MASTER_KEY", "sk-master-key-rahasia")
LITELLM_BASE_URL   = os.environ.get("LITELLM_BASE_URL", "http://localhost:4000/v1")
MODEL_NAME         = os.environ.get("MODEL_NAME", "gemini-1.5-pro")

DEFAULT_ORG = SCM_ORG


# ============================================================
# Helper: HTTPS API Request (tanpa dependency eksternal)
# ============================================================

def _api_request(method: str, url: str, data: dict = None) -> dict:
    """Generic HTTPS request ke SCM REST API.
    
    Returns dict: {"status_code": int, "body": dict|str}
    """
    headers = {"Content-Type": "application/json", "Accept": "application/json"}

    if SCM_TOKEN:
        if SCM_PROVIDER == "github":
            headers["Authorization"] = f"Bearer {SCM_TOKEN}"
            headers["X-GitHub-Api-Version"] = "2022-11-28"
        elif SCM_PROVIDER == "gitlab":
            headers["PRIVATE-TOKEN"] = SCM_TOKEN
        elif SCM_PROVIDER in ("bitbucket_cloud", "bitbucket_server"):
            creds = base64.b64encode(f"{SCM_USERNAME}:{SCM_TOKEN}".encode()).decode()
            headers["Authorization"] = f"Basic {creds}"

    body = json.dumps(data).encode() if data else None
    req  = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            try:
                return {"status_code": resp.status, "body": json.loads(raw)}
            except json.JSONDecodeError:
                return {"status_code": resp.status, "body": raw}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return {"status_code": e.code, "body": json.loads(raw)}
        except json.JSONDecodeError:
            return {"status_code": e.code, "body": raw}
    except urllib.error.URLError as e:
        return {"status_code": 0, "body": str(e.reason)}


def _clone_url(org: str, repo: str) -> str:
    """Membangun clone URL dengan kredensial agar tidak perlu interaksi password."""
    if SCM_USERNAME and SCM_TOKEN:
        creds = f"{urllib.parse.quote(SCM_USERNAME)}:{urllib.parse.quote(SCM_TOKEN)}"
    else:
        creds = None

    if SCM_PROVIDER == "github":
        host = "github.com"
        path = f"{org}/{repo}.git"
    elif SCM_PROVIDER == "gitlab":
        # gitlab.com atau self-hosted
        host_raw = SCM_BASE_URL.replace("https://", "").replace("http://", "").rstrip("/")
        host = host_raw
        path = f"{org}/{repo}.git"
    elif SCM_PROVIDER == "bitbucket_cloud":
        host = "bitbucket.org"
        path = f"{org}/{repo}.git"
    elif SCM_PROVIDER == "bitbucket_server":
        host_raw = SCM_BASE_URL.replace("https://", "").replace("http://", "").split("/")[0]
        host = host_raw
        # Bitbucket Server: /scm/<project>/<repo>.git
        path = f"scm/{org}/{repo}.git"
    else:
        host = "github.com"
        path = f"{org}/{repo}.git"

    scheme = "https"
    if creds:
        return f"{scheme}://{creds}@{host}/{path}"
    return f"{scheme}://{host}/{path}"


# ============================================================
# SCM API helpers per provider
# ============================================================

def _github_create_branch(org: str, repo: str, new_branch: str, sha: str) -> dict:
    url = f"{SCM_BASE_URL}/repos/{org}/{repo}/git/refs"
    return _api_request("POST", url, {"ref": f"refs/heads/{new_branch}", "sha": sha})


def _gitlab_create_branch(org: str, repo: str, new_branch: str, ref: str) -> dict:
    project = urllib.parse.quote(f"{org}/{repo}", safe="")
    url = f"{SCM_BASE_URL}/api/v4/projects/{project}/repository/branches"
    return _api_request("POST", url, {"branch": new_branch, "ref": ref})


def _bitbucket_cloud_create_branch(org: str, repo: str, new_branch: str, sha: str) -> dict:
    url = f"{SCM_BASE_URL}/repositories/{org}/{repo}/refs/branches"
    return _api_request("POST", url, {"name": new_branch, "target": {"hash": sha}})


def _bitbucket_server_create_branch(org: str, repo: str, new_branch: str, sha: str) -> dict:
    url = f"{SCM_BASE_URL}/rest/api/1.0/projects/{org}/repos/{repo}/branches"
    return _api_request("POST", url, {"name": new_branch, "startPoint": sha})


def _get_head_sha(org: str, repo: str, branch: str) -> str:
    """Mengambil SHA commit terbaru dari sebuah branch via API."""
    if SCM_PROVIDER == "github":
        url  = f"{SCM_BASE_URL}/repos/{org}/{repo}/commits/{branch}"
        resp = _api_request("GET", url)
        if isinstance(resp["body"], dict):
            return resp["body"].get("sha", "")
    elif SCM_PROVIDER == "gitlab":
        project = urllib.parse.quote(f"{org}/{repo}", safe="")
        url  = f"{SCM_BASE_URL}/api/v4/projects/{project}/repository/commits/{branch}"
        resp = _api_request("GET", url)
        if isinstance(resp["body"], dict):
            return resp["body"].get("id", "")
    elif SCM_PROVIDER == "bitbucket_cloud":
        url  = f"{SCM_BASE_URL}/repositories/{org}/{repo}/commits/{branch}?pagelen=1"
        resp = _api_request("GET", url)
        if isinstance(resp["body"], dict):
            vals = resp["body"].get("values", [])
            if vals:
                return vals[0].get("hash", "")
    elif SCM_PROVIDER == "bitbucket_server":
        url  = f"{SCM_BASE_URL}/rest/api/1.0/projects/{org}/repos/{repo}/commits?until={branch}&limit=1"
        resp = _api_request("GET", url)
        if isinstance(resp["body"], dict):
            vals = resp["body"].get("values", [])
            if vals:
                return vals[0].get("id", "")
    return ""


# ============================================================
# Tool Functions
# ============================================================

def git_clone(repo_url: str, dest_dir: str, branch: str, single_branch: bool) -> dict:
    """Clones a git repository via HTTPS to a local directory.

    Args:
        repo_url: Full HTTPS repository URL (credentials embedded if needed).
        dest_dir: Local destination directory name for the cloned repo.
        branch: Branch or tag name to checkout.
        single_branch: If true, clone only the specified branch.

    Returns:
        dict: Dictionary with 'status' and 'message' keys.
    """
    try:
        cmd = ["git", "-c", "credential.helper=", "clone", "--branch", branch]
        if single_branch:
            cmd.append("--single-branch")
        cmd.extend([repo_url, dest_dir])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
        if result.returncode == 0:
            return {"status": "success", "message": f"Successfully cloned to {dest_dir} (branch: {branch})"}
        # Sanitasi token dari error message agar tidak bocor di log
        err_msg = re.sub(r"://[^@]+@", "://<redacted>@", result.stderr.strip())
        return {"status": "error", "message": f"Git clone failed: {err_msg}"}
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "Git clone timed out after 120 seconds."}
    except Exception as e:
        return {"status": "error", "message": f"Error: {e}"}


def scm_create_branch_api(org: str, repo: str, existing_branch: str, new_branch: str) -> dict:
    """Creates a new branch via SCM REST API (GitHub / GitLab / Bitbucket).

    Args:
        org: Organization or project name.
        repo: Repository name.
        existing_branch: Source branch to base the new branch on.
        new_branch: Name of the new branch to create.

    Returns:
        dict: Dictionary with 'status' and 'message' keys.
    """
    try:
        sha = _get_head_sha(org, repo, existing_branch)
        if not sha:
            return {"status": "error", "message": f"Could not resolve SHA for branch '{existing_branch}'."}

        if SCM_PROVIDER == "github":
            resp = _github_create_branch(org, repo, new_branch, sha)
        elif SCM_PROVIDER == "gitlab":
            resp = _gitlab_create_branch(org, repo, new_branch, existing_branch)
        elif SCM_PROVIDER == "bitbucket_cloud":
            resp = _bitbucket_cloud_create_branch(org, repo, new_branch, sha)
        elif SCM_PROVIDER == "bitbucket_server":
            resp = _bitbucket_server_create_branch(org, repo, new_branch, sha)
        else:
            return {"status": "error", "message": f"Unsupported SCM provider: {SCM_PROVIDER}"}

        if resp["status_code"] in (200, 201):
            return {"status": "success", "message": f"Branch '{new_branch}' created from '{existing_branch}' via {SCM_PROVIDER} API."}
        return {"status": "error", "message": f"API returned {resp['status_code']}: {resp['body']}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def scm_create_pull_request_api(org: str, repo: str, source_branch: str, dest_branch: str, title: str, body: str) -> dict:
    """Creates a pull/merge request via SCM REST API.

    Args:
        org: Organization or project name.
        repo: Repository name.
        source_branch: Branch containing the changes.
        dest_branch: Target branch to merge into.
        title: Title of the pull request.
        body: Description of the pull request.

    Returns:
        dict: Dictionary with 'status', 'message', and 'url' keys.
    """
    try:
        if SCM_PROVIDER == "github":
            url  = f"{SCM_BASE_URL}/repos/{org}/{repo}/pulls"
            resp = _api_request("POST", url, {
                "title": title, "body": body,
                "head": source_branch, "base": dest_branch
            })
            if resp["status_code"] in (200, 201):
                pr_url = resp["body"].get("html_url", "N/A")
                return {"status": "success", "message": f"PR created: {pr_url}", "url": pr_url}

        elif SCM_PROVIDER == "gitlab":
            project = urllib.parse.quote(f"{org}/{repo}", safe="")
            url  = f"{SCM_BASE_URL}/api/v4/projects/{project}/merge_requests"
            resp = _api_request("POST", url, {
                "title": title, "description": body,
                "source_branch": source_branch, "target_branch": dest_branch
            })
            if resp["status_code"] in (200, 201):
                mr_url = resp["body"].get("web_url", "N/A")
                return {"status": "success", "message": f"MR created: {mr_url}", "url": mr_url}

        elif SCM_PROVIDER == "bitbucket_cloud":
            url  = f"{SCM_BASE_URL}/repositories/{org}/{repo}/pullrequests"
            resp = _api_request("POST", url, {
                "title": title, "description": body,
                "source": {"branch": {"name": source_branch}},
                "destination": {"branch": {"name": dest_branch}}
            })
            if resp["status_code"] in (200, 201):
                pr_url = resp["body"].get("links", {}).get("html", {}).get("href", "N/A")
                return {"status": "success", "message": f"PR created: {pr_url}", "url": pr_url}

        elif SCM_PROVIDER == "bitbucket_server":
            url  = f"{SCM_BASE_URL}/rest/api/1.0/projects/{org}/repos/{repo}/pull-requests"
            resp = _api_request("POST", url, {
                "title": title, "description": body,
                "fromRef": {"id": f"refs/heads/{source_branch}"},
                "toRef":   {"id": f"refs/heads/{dest_branch}"},
                "reviewers": []
            })
            if resp["status_code"] in (200, 201):
                pr_url = resp["body"].get("links", {}).get("self", [{}])[0].get("href", "N/A")
                return {"status": "success", "message": f"PR created: {pr_url}", "url": pr_url}

        return {"status": "error", "message": f"API returned {resp['status_code']}: {resp['body']}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def git_status(work_dir: str) -> dict:
    """Shows the git status of a repository.

    Args:
        work_dir: Path to the git repository directory.

    Returns:
        dict: Dictionary with 'status', 'branch', 'changes', and 'last_commit' keys.
    """
    try:
        branch_r = subprocess.run(["git", "branch", "--show-current"], cwd=work_dir, capture_output=True, text=True)
        status_r = subprocess.run(["git", "status", "--short"],         cwd=work_dir, capture_output=True, text=True)
        log_r    = subprocess.run(["git", "log", "-1", "--oneline"],    cwd=work_dir, capture_output=True, text=True)
        return {
            "status": "success",
            "branch": branch_r.stdout.strip(),
            "changes": status_r.stdout.strip() or "(clean - no changes)",
            "last_commit": log_r.stdout.strip()
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
        n      = min(int(count), 20)
        result = subprocess.run(
            ["git", "log", f"-{n}", "--oneline", "--decorate"],
            cwd=work_dir, capture_output=True, text=True
        )
        if result.returncode == 0:
            return {"status": "success", "log": result.stdout.strip()}
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
        result = subprocess.run(["git", "branch", "-a"], cwd=work_dir, capture_output=True, text=True)
        if result.returncode == 0:
            branches = [b.strip() for b in result.stdout.strip().split("\n") if b.strip()]
            return {"status": "success", "branches": branches}
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
        with open(file_path, "r") as f:
            content = f.read()
        return {"status": "success", "content": content}
    except Exception as e:
        return {"status": "error", "content": f"Error reading file: {e}"}


def run_shell_command(command: str, work_dir: str) -> dict:
    """Runs a safe read-only shell command in a specified working directory.

    Args:
        command: The shell command to execute (e.g. 'ls -la', 'cat README.md').
        work_dir: Directory to run the command in.

    Returns:
        dict: Dictionary with 'status', 'stdout', and 'stderr' keys.
    """
    allowed_prefixes = [
        "ls", "cat", "head", "tail", "wc", "find", "tree",
        "git log", "git diff", "git show", "git branch", "git tag", "git remote"
    ]
    if not any(command.strip().startswith(p) for p in allowed_prefixes):
        return {"status": "error", "stdout": "", "stderr": f"Command '{command}' is not allowed."}
    try:
        result = subprocess.run(command, shell=True, cwd=work_dir,
                                capture_output=True, text=True, timeout=30)
        return {
            "status": "success" if result.returncode == 0 else "error",
            "stdout": result.stdout.strip()[:2000],
            "stderr": result.stderr.strip()[:500]
        }
    except subprocess.TimeoutExpired:
        return {"status": "error", "stdout": "", "stderr": "Command timed out."}
    except Exception as e:
        return {"status": "error", "stdout": "", "stderr": str(e)}


def git_create_branch_local(work_dir: str, existing_branch: str, new_branch: str) -> dict:
    """Creates a new local branch from an existing branch and pushes it via HTTPS.

    Args:
        work_dir: Path to the git repository directory.
        existing_branch: Source branch to base the new branch on.
        new_branch: Name of the new branch to create.

    Returns:
        dict: Dictionary with 'status' and 'message' keys.
    """
    try:
        subprocess.run(["git", "fetch", "origin", existing_branch], cwd=work_dir, capture_output=True)
        subprocess.run(["git", "checkout", existing_branch],        cwd=work_dir, capture_output=True)
        subprocess.run(["git", "pull", "origin", existing_branch],  cwd=work_dir, capture_output=True)
        res = subprocess.run(["git", "checkout", "-b", new_branch], cwd=work_dir, capture_output=True, text=True)
        if res.returncode != 0:
            return {"status": "error", "message": f"Failed to create branch: {res.stderr}"}
        res_push = subprocess.run(
            ["git", "push", "-u", "origin", new_branch],
            cwd=work_dir, capture_output=True, text=True,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        )
        if res_push.returncode != 0:
            err = re.sub(r"://[^@]+@", "://<redacted>@", res_push.stderr)
            return {"status": "error", "message": f"Push failed: {err}"}
        return {"status": "success", "message": f"Branch '{new_branch}' created and pushed."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def update_yaml_image(file_path: str, new_image: str) -> dict:
    """Updates the 'image: ...' line in a YAML file with the new image.

    Args:
        file_path: Path to the YAML file.
        new_image: The new image value (e.g. 'myrepo/app:v2.0.1').

    Returns:
        dict: Dictionary with 'status' and 'message' keys.
    """
    try:
        with open(file_path, "r") as f:
            lines = f.readlines()
        updated = False
        for i, line in enumerate(lines):
            if re.search(r"^\s*-?\s*image:\s*.*$", line):
                prefix   = line[: line.find("image:")]
                lines[i] = f"{prefix}image: {new_image}\n"
                updated  = True
        if not updated:
            return {"status": "error", "message": "No 'image:' key found in the file."}
        with open(file_path, "w") as f:
            f.writelines(lines)
        return {"status": "success", "message": f"Updated image in {file_path} to '{new_image}'"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def git_commit_and_push(work_dir: str, commit_message: str) -> dict:
    """Commits all staged changes and pushes to the remote repository via HTTPS.

    Args:
        work_dir: Path to the git repository directory.
        commit_message: The commit message to use.

    Returns:
        dict: Dictionary with 'status' and 'message' keys.
    """
    try:
        subprocess.run(["git", "add", "."], cwd=work_dir, capture_output=True)
        res_commit = subprocess.run(
            ["git", "commit", "-m", commit_message],
            cwd=work_dir, capture_output=True, text=True
        )
        if "nothing to commit" in res_commit.stdout:
            return {"status": "success", "message": "No changes to commit."}
        res_push = subprocess.run(
            ["git", "push"], cwd=work_dir, capture_output=True, text=True,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        )
        if res_push.returncode != 0:
            err = re.sub(r"://[^@]+@", "://<redacted>@", res_push.stderr)
            return {"status": "error", "message": f"Push failed: {err}"}
        return {"status": "success", "message": "Committed and pushed successfully."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ============================================================
# OpenAI Tools Converter
# ============================================================

def get_openai_tools(functions):
    tools = []
    for func in functions:
        sig        = inspect.signature(func)
        properties = {}
        required   = []
        for name, param in sig.parameters.items():
            param_type = "string"
            if param.annotation == int:   param_type = "integer"
            if param.annotation == bool:  param_type = "boolean"
            # Extract per-parameter description from docstring
            doc_desc = ""
            if func.__doc__:
                match = re.search(rf"{name}:\s*(.+)", func.__doc__)
                if match:
                    doc_desc = match.group(1).strip()
            properties[name] = {"type": param_type, "description": doc_desc or f"Parameter {name}"}
            if param.default == inspect.Parameter.empty:
                required.append(name)
        tools.append({
            "type": "function",
            "function": {
                "name": func.__name__,
                "description": (func.__doc__ or "").split("\n")[0].strip(),
                "parameters": {"type": "object", "properties": properties, "required": required}
            }
        })
    return tools


# ============================================================
# Agent Runner
# ============================================================

async def run_git_agent(action: str, repo_name: str, org: str, action_kwargs: dict):
    full_repo = f"{org}/{repo_name}"
    dest_dir  = repo_name
    clone_url = _clone_url(org, repo_name)

    instruction = dedent(f"""\
        Kamu adalah seorang Git Repository Manager yang ahli mengelola repository di berbagai SCM.
        SCM Provider aktif : {SCM_PROVIDER.upper()}
        Repository target  : {full_repo}
        Local directory    : '{dest_dir}'
        Clone URL (HTTPS)  : {re.sub(r'://[^@]+@', '://<redacted>@', clone_url)}
    """)

    if action == "clone":
        ref = action_kwargs.get("ref", "main")
        instruction += dedent(f"""\
        TUGAS: Clone '{full_repo}' branch/tag '{ref}', lalu analisa strukturnya.
        Langkah:
        1. Cek apakah folder '{dest_dir}' sudah ada via list_directory pada '.'.
           - Sudah ada → skip clone, lanjut ke langkah 3.
        2. Clone via git_clone: repo_url='{clone_url}', dest_dir='{dest_dir}', branch='{ref}', single_branch=true.
        3. Jalankan git_status pada '{dest_dir}'.
        4. Jalankan list_directory pada '{dest_dir}'.
        5. Jalankan git_log: work_dir='{dest_dir}', count=5.
        6. Berikan laporan lengkap.
        """)
        user_message = f"Clone '{full_repo}' branch '{ref}' dan berikan laporan."

    elif action == "create-branch":
        existing = action_kwargs.get("existing_branch", "main")
        new_b    = action_kwargs.get("new_branch")
        instruction += dedent(f"""\
        TUGAS: Buat branch '{new_b}' dari '{existing}'.
        Langkah:
        1. Coba via scm_create_branch_api: org='{org}', repo='{repo_name}', existing_branch='{existing}', new_branch='{new_b}'.
        2. Jika API gagal, fallback ke git_create_branch_local setelah clone jika perlu.
        3. Laporkan hasil.
        """)
        user_message = f"Buat branch '{new_b}' dari '{existing}' di '{full_repo}'."

    elif action == "pull-request":
        src = action_kwargs.get("source_branch")
        dst = action_kwargs.get("dest_branch", "main")
        instruction += dedent(f"""\
        TUGAS: Buat Pull/Merge Request dari '{src}' ke '{dst}'.
        Langkah:
        1. Buat judul dan deskripsi yang informatif.
        2. Panggil scm_create_pull_request_api: org='{org}', repo='{repo_name}', source_branch='{src}', dest_branch='{dst}'.
        3. Laporkan URL PR/MR.
        """)
        user_message = f"Buat PR dari '{src}' ke '{dst}' di '{full_repo}'."

    elif action == "update-image":
        ref      = action_kwargs.get("ref", "main")
        yaml_f   = action_kwargs.get("yaml_file")
        new_img  = action_kwargs.get("new_image")
        instruction += dedent(f"""\
        TUGAS: Update image YAML dan push.
        Langkah:
        1. Cek/clone repo branch '{ref}' jika belum ada.
        2. Panggil update_yaml_image: file_path='{dest_dir}/{yaml_f}', new_image='{new_img}'.
        3. Panggil git_commit_and_push: work_dir='{dest_dir}', commit_message='chore: update image to {new_img}'.
        4. Laporkan hasil.
        """)
        user_message = f"Update '{yaml_f}' dengan image '{new_img}' di branch '{ref}'."
        
    elif action == "quick-pr":
        ns       = action_kwargs.get("namespace", "default")
        deploy   = action_kwargs.get("deployment")
        new_img  = action_kwargs.get("image")
        
        yaml_f   = f"manifest/production-qoinplus/{deploy}_deployment.yaml"
        safe_img = new_img.replace(":", "-").replace("/", "-")
        new_b    = f"{ns}-{deploy}-{safe_img}"
        existing = "main"
        
        instruction += dedent(f"""\
        TUGAS: Lakukan Quick PR untuk update image '{new_img}' pada deployment '{deploy}'.
        Langkah:
        1. Buat branch baru via scm_create_branch_api: org='{org}', repo='{repo_name}', existing_branch='{existing}', new_branch='{new_b}'.
        2. Jika API gagal membuat branch, coba clone repo branch '{existing}' lalu git_create_branch_local ke '{new_b}'. Jika sukses via API, langsung clone branch '{new_b}'.
        3. Clone repo (jika belum) via git_clone: repo_url='{clone_url}', dest_dir='{dest_dir}', branch='{new_b}', single_branch=true.
        4. Panggil update_yaml_image: file_path='{dest_dir}/{yaml_f}', new_image='{new_img}'.
        5. Panggil git_commit_and_push: work_dir='{dest_dir}', commit_message='chore: update {deploy} image to {new_img}'.
        6. Panggil scm_create_pull_request_api: org='{org}', repo='{repo_name}', source_branch='{new_b}', dest_branch='{existing}', title='Update {deploy} image to {new_img}', body='Automated PR to update image for {deploy} in namespace {ns}'.
        7. Laporkan hasil dan URL PR.
        """)
        user_message = f"Jalankan alur Quick PR untuk '{deploy}'."
        
    else:
        instruction += "\nTUGAS: Bantu user sesuai instruksi."
        user_message = "Mulai tugas."

    available_functions = {
        "git_clone":                    git_clone,
        "scm_create_branch_api":        scm_create_branch_api,
        "scm_create_pull_request_api":  scm_create_pull_request_api,
        "git_create_branch_local":      git_create_branch_local,
        "git_status":                   git_status,
        "git_log":                      git_log,
        "git_branch_list":              git_branch_list,
        "git_tag_list":                 git_tag_list,
        "list_directory":               list_directory,
        "read_file":                    read_file,
        "run_shell_command":            run_shell_command,
        "update_yaml_image":            update_yaml_image,
        "git_commit_and_push":          git_commit_and_push,
    }

    tools    = get_openai_tools(list(available_functions.values()))
    client   = AsyncOpenAI(api_key=LITELLM_MASTER_KEY, base_url=LITELLM_BASE_URL)
    messages = [
        {"role": "system", "content": instruction},
        {"role": "user",   "content": user_message}
    ]

    # Print summary
    print(f"📦 Repository : {full_repo}")
    print(f"🔌 SCM        : {SCM_PROVIDER.upper()}  ({SCM_BASE_URL})")
    print(f"📂 Dest Dir   : {dest_dir}")
    print(f"⚡ Action     : {action}")
    if action == "clone":           print(f"🌿 Branch/Tag : {action_kwargs.get('ref','main')}")
    elif action == "create-branch": print(f"✨ New Branch : {action_kwargs.get('new_branch')}")
    elif action == "pull-request":  print(f"🔀 {action_kwargs.get('source_branch')} → {action_kwargs.get('dest_branch','main')}")
    elif action == "update-image":  print(f"🐳 New Image  : {action_kwargs.get('new_image')}")
    elif action == "quick-pr":
        print(f"🚀 Quick PR   : {action_kwargs.get('deployment')} → {action_kwargs.get('image')}")
    print(f"🤖 Memulai Git Manager AI Agent ({MODEL_NAME})...\n")

    final_report = ""
    for _ in range(15):
        response     = await client.chat.completions.create(
            model=MODEL_NAME, messages=messages, tools=tools, tool_choice="auto"
        )
        resp_msg     = response.choices[0].message
        messages.append(resp_msg)

        if resp_msg.content:
            print(f"\n{resp_msg.content}")
            final_report = resp_msg.content

        if resp_msg.tool_calls:
            for tc in resp_msg.tool_calls:
                func_name = tc.function.name
                try:
                    func_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    func_args = {}
                print(f"  🔧 {func_name}({func_args})")
                func   = available_functions.get(func_name)
                result = func(**func_args) if func else {"status": "error", "message": f"Tool {func_name} not found"}
                print(f"  ✅ {func_name} → {result.get('status','?')}")
                messages.append({
                    "role": "tool", "tool_call_id": tc.id,
                    "name": func_name, "content": json.dumps(result)
                })
        else:
            break

    print("\n######################")
    print("📋 Status Akhir:")
    if os.path.isdir(dest_dir):
        print(f"   ✅ Repository tersedia di: {os.path.abspath(dest_dir)}")
    else:
        print(f"   ℹ️  Repository tidak diklone secara lokal.")
    return final_report


# ============================================================
# Health Check / Pre-flight Diagnostics
# ============================================================

def run_check():
    """
    Menjalankan pemeriksaan menyeluruh terhadap semua requirement:
      1. Python packages
      2. Environment variables (.env)
      3. Binary tools (git)
      4. SCM API access & token permissions
      5. LiteLLM Gateway status & model availability
    """
    import shutil

    # ANSI colors (graceful fallback jika terminal tidak support)
    _use_color = sys.stdout.isatty() or os.environ.get("FORCE_COLOR")
    def _c(code, text): return f"\033[{code}m{text}\033[0m" if _use_color else text
    OK    = _c("32", "✅ OK")
    WARN  = _c("33", "⚠️  WARN")
    FAIL  = _c("31", "❌ FAIL")
    INFO  = _c("36", "ℹ️  INFO")
    SKIP  = _c("90", "⏭  SKIP")
    HDR   = lambda t: _c("1;34", t)

    results  = []   # list of (section, item, status_tag, detail)
    failures = 0
    warnings = 0

    def rec(section, item, tag, detail=""):
        nonlocal failures, warnings
        if tag == FAIL: failures += 1
        if tag == WARN: warnings += 1
        results.append((section, item, tag, detail))

    # ----------------------------------------------------------
    # 1. Python Packages
    # ----------------------------------------------------------
    sec = "Python Packages"
    required_pkgs = {
        "openai":    "pip install openai",
        "dotenv":    "pip install python-dotenv",
    }
    optional_pkgs = {
        "fastapi":   "pip install fastapi   (hanya untuk mode server)",
        "uvicorn":   "pip install uvicorn   (hanya untuk mode server)",
    }
    for pkg, hint in required_pkgs.items():
        try:
            __import__(pkg)
            rec(sec, f"import {pkg}", OK)
        except ImportError:
            rec(sec, f"import {pkg}", FAIL, hint)

    for pkg, hint in optional_pkgs.items():
        try:
            __import__(pkg)
            rec(sec, f"import {pkg}", OK, "optional")
        except ImportError:
            rec(sec, f"import {pkg}", WARN, hint)

    # ----------------------------------------------------------
    # 2. Environment Variables
    # ----------------------------------------------------------
    sec = "Environment Variables"

    # Deteksi .env file
    env_file_found = os.path.isfile(".env")
    rec(sec, ".env file", OK if env_file_found else WARN,
        ".env ditemukan" if env_file_found else "File .env tidak ada — menggunakan env system / default")

    # Wajib ada
    required_env = {
        "SCM_PROVIDER":       (SCM_PROVIDER,       "github | gitlab | bitbucket_cloud | bitbucket_server"),
        "SCM_ORG":            (SCM_ORG,            "nama organisasi / project / workspace"),
        "SCM_TOKEN":          (SCM_TOKEN,           "Personal Access Token / App Password"),
        "LITELLM_BASE_URL":   (LITELLM_BASE_URL,    "base URL gateway LiteLLM"),
        "LITELLM_MASTER_KEY": (LITELLM_MASTER_KEY,  "master key LiteLLM"),
        "MODEL_NAME":         (MODEL_NAME,          "nama model AI yang digunakan"),
    }
    for var, (val, desc) in required_env.items():
        if val and val not in ("MyOrg",):
            # Tampilkan sebagian nilai untuk konfirmasi tanpa expose secret
            if "TOKEN" in var or "KEY" in var:
                display = f"{val[:4]}{'*' * max(0, len(val) - 8)}{val[-4:]}" if len(val) > 8 else "****"
            else:
                display = val
            rec(sec, var, OK, display)
        else:
            tag = FAIL if var in ("SCM_TOKEN", "LITELLM_MASTER_KEY") else WARN
            rec(sec, var, tag, f"Belum diset — {desc}")

    # Opsional tapi penting untuk clone HTTPS
    scm_username_ok = bool(SCM_USERNAME)
    rec(sec, "SCM_USERNAME",
        OK if scm_username_ok else WARN,
        SCM_USERNAME if scm_username_ok else "Kosong — clone HTTPS mungkin gagal jika repo private")

    # Validasi nilai SCM_PROVIDER
    valid_providers = {"github", "gitlab", "bitbucket_cloud", "bitbucket_server"}
    if SCM_PROVIDER not in valid_providers:
        rec(sec, "SCM_PROVIDER nilai", FAIL,
            f"'{SCM_PROVIDER}' tidak valid. Harus salah satu: {', '.join(sorted(valid_providers))}")
    else:
        rec(sec, "SCM_PROVIDER nilai", OK, f"'{SCM_PROVIDER}' dikenali")

    # SCM_BASE_URL
    rec(sec, "SCM_BASE_URL", INFO, SCM_BASE_URL + (" (auto-default)" if not os.environ.get("SCM_BASE_URL") else ""))

    # ----------------------------------------------------------
    # 3. Binary Tools
    # ----------------------------------------------------------
    sec = "Binary Tools"

    git_path = shutil.which("git")
    if git_path:
        try:
            gv = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=5)
            rec(sec, "git", OK, f"{gv.stdout.strip()}  ({git_path})")
        except Exception as e:
            rec(sec, "git", WARN, f"ditemukan tapi error: {e}")
    else:
        rec(sec, "git", FAIL, "git tidak ditemukan di PATH — install git terlebih dahulu")

    # git config user (diperlukan untuk commit)
    try:
        name_r  = subprocess.run(["git", "config", "--global", "user.name"],  capture_output=True, text=True, timeout=5)
        email_r = subprocess.run(["git", "config", "--global", "user.email"], capture_output=True, text=True, timeout=5)
        git_name  = name_r.stdout.strip()
        git_email = email_r.stdout.strip()
        if git_name and git_email:
            rec(sec, "git config user", OK, f"{git_name} <{git_email}>")
        else:
            rec(sec, "git config user", WARN,
                "user.name / user.email belum di-set — diperlukan untuk `git commit`\n"
                "         → git config --global user.name 'Nama'\n"
                "         → git config --global user.email 'email@domain.com'")
    except Exception:
        rec(sec, "git config user", WARN, "Tidak dapat membaca git config")

    # ----------------------------------------------------------
    # 4. SCM API Access
    # ----------------------------------------------------------
    sec = "SCM API Access"

    def _check_scm_api():
        """Cek koneksi dan izin token ke SCM API."""
        if not SCM_TOKEN:
            rec(sec, "API auth", FAIL, "SCM_TOKEN kosong — tidak bisa melakukan API call")
            return

        # Endpoint "whoami" per provider
        if SCM_PROVIDER == "github":
            url  = f"{SCM_BASE_URL}/user"
            resp = _api_request("GET", url)
            sc   = resp["status_code"]
            body = resp["body"]
            if sc == 200 and isinstance(body, dict):
                login  = body.get("login", "?")
                scopes = body.get("X-OAuth-Scopes", "")   # tidak selalu ada di body
                rec(sec, "API connectivity", OK, f"Terautentikasi sebagai: {login}")
                # Cek rate limit sekaligus scopes
                rl = _api_request("GET", f"{SCM_BASE_URL}/rate_limit")
                if rl["status_code"] == 200 and isinstance(rl["body"], dict):
                    core = rl["body"].get("resources", {}).get("core", {})
                    remaining = core.get("remaining", "?")
                    limit     = core.get("limit", "?")
                    rec(sec, "API rate limit", OK if remaining != 0 else WARN,
                        f"{remaining}/{limit} requests remaining")
                # Cek scope token (tersedia di header, tidak di body — cek via repos)
                # Proxy: coba list 1 repo di org
                repos_url  = f"{SCM_BASE_URL}/orgs/{SCM_ORG}/repos?per_page=1"
                repos_resp = _api_request("GET", repos_url)
                if repos_resp["status_code"] == 200:
                    rec(sec, "Token: read:org / repo", OK, f"Dapat mengakses repo di org '{SCM_ORG}'")
                elif repos_resp["status_code"] == 404:
                    # Coba sebagai user repo (bukan org)
                    user_repos = _api_request("GET", f"{SCM_BASE_URL}/users/{SCM_ORG}/repos?per_page=1")
                    if user_repos["status_code"] == 200:
                        rec(sec, "Token: repo access", OK, f"'{SCM_ORG}' adalah user, bukan org — OK")
                    else:
                        rec(sec, "Token: repo access", WARN,
                            f"Org/user '{SCM_ORG}' tidak ditemukan atau token tidak punya izin")
                elif repos_resp["status_code"] == 401:
                    rec(sec, "Token: repo access", FAIL, "Token tidak valid / expired")
                elif repos_resp["status_code"] == 403:
                    rec(sec, "Token: repo access", WARN,
                        "Token tidak punya izin baca repo org — butuh scope: repo atau read:org")
                else:
                    rec(sec, "Token: repo access", WARN,
                        f"HTTP {repos_resp['status_code']}: {str(repos_resp['body'])[:120]}")
            elif sc == 401:
                rec(sec, "API connectivity", FAIL, "HTTP 401 — Token tidak valid atau expired")
            else:
                rec(sec, "API connectivity", FAIL, f"HTTP {sc}: {str(body)[:150]}")

        elif SCM_PROVIDER == "gitlab":
            url  = f"{SCM_BASE_URL}/api/v4/user"
            resp = _api_request("GET", url)
            sc   = resp["status_code"]
            body = resp["body"]
            if sc == 200 and isinstance(body, dict):
                rec(sec, "API connectivity", OK, f"Terautentikasi sebagai: {body.get('username','?')}")
                # Cek akses ke namespace / group
                ns_url  = f"{SCM_BASE_URL}/api/v4/groups/{urllib.parse.quote(SCM_ORG, safe='')}?simple=true"
                ns_resp = _api_request("GET", ns_url)
                if ns_resp["status_code"] == 200:
                    rec(sec, "Token: group access", OK, f"Grup '{SCM_ORG}' dapat diakses")
                else:
                    # Coba sebagai personal namespace
                    user_ns = _api_request("GET", f"{SCM_BASE_URL}/api/v4/users?username={SCM_ORG}")
                    if user_ns["status_code"] == 200 and isinstance(user_ns["body"], list) and user_ns["body"]:
                        rec(sec, "Token: namespace access", OK, f"'{SCM_ORG}' adalah user namespace")
                    else:
                        rec(sec, "Token: group/namespace", WARN,
                            f"Namespace '{SCM_ORG}' tidak ditemukan atau token tidak punya akses")
            elif sc == 401:
                rec(sec, "API connectivity", FAIL, "HTTP 401 — Token tidak valid (PRIVATE-TOKEN)")
            else:
                rec(sec, "API connectivity", FAIL, f"HTTP {sc}: {str(body)[:150]}")

        elif SCM_PROVIDER == "bitbucket_cloud":
            url  = f"{SCM_BASE_URL}/user"
            resp = _api_request("GET", url)
            sc   = resp["status_code"]
            body = resp["body"]
            if sc == 200 and isinstance(body, dict):
                rec(sec, "API connectivity", OK,
                    f"Terautentikasi sebagai: {body.get('display_name', body.get('username','?'))}")
                ws_resp = _api_request("GET", f"{SCM_BASE_URL}/workspaces/{SCM_ORG}")
                if ws_resp["status_code"] == 200:
                    rec(sec, "Token: workspace access", OK, f"Workspace '{SCM_ORG}' dapat diakses")
                else:
                    rec(sec, "Token: workspace access", WARN,
                        f"Workspace '{SCM_ORG}' tidak ditemukan atau tidak punya izin")
            elif sc == 401:
                rec(sec, "API connectivity", FAIL,
                    "HTTP 401 — Periksa SCM_USERNAME dan SCM_TOKEN (App Password)")
            else:
                rec(sec, "API connectivity", FAIL, f"HTTP {sc}: {str(body)[:150]}")

        elif SCM_PROVIDER == "bitbucket_server":
            url  = f"{SCM_BASE_URL}/rest/api/1.0/application-properties"
            resp = _api_request("GET", url)
            sc   = resp["status_code"]
            body = resp["body"]
            if sc == 200 and isinstance(body, dict):
                ver = body.get("version", "?")
                rec(sec, "API connectivity", OK, f"Bitbucket Server v{ver} dapat dijangkau")
                proj_resp = _api_request("GET", f"{SCM_BASE_URL}/rest/api/1.0/projects/{SCM_ORG}")
                if proj_resp["status_code"] == 200:
                    rec(sec, "Token: project access", OK, f"Project '{SCM_ORG}' dapat diakses")
                elif proj_resp["status_code"] == 401:
                    rec(sec, "Token: project access", FAIL, "HTTP 401 — Token tidak valid")
                elif proj_resp["status_code"] == 403:
                    rec(sec, "Token: project access", WARN,
                        "HTTP 403 — Token tidak punya izin ke project ini")
                elif proj_resp["status_code"] == 404:
                    rec(sec, "Token: project access", WARN, f"Project '{SCM_ORG}' tidak ditemukan")
                else:
                    rec(sec, "Token: project access", WARN, f"HTTP {proj_resp['status_code']}")
            elif sc == 0:
                rec(sec, "API connectivity", FAIL,
                    f"Tidak dapat terhubung ke {SCM_BASE_URL} — periksa SCM_BASE_URL dan jaringan")
            else:
                rec(sec, "API connectivity", FAIL, f"HTTP {sc}: {str(body)[:150]}")
        else:
            rec(sec, "API connectivity", FAIL, f"Provider '{SCM_PROVIDER}' tidak dikenali")

    _check_scm_api()

    # ----------------------------------------------------------
    # 5. LiteLLM Gateway
    # ----------------------------------------------------------
    sec = "LiteLLM / AI Gateway"

    # 5a. Cek /health endpoint
    health_url = LITELLM_BASE_URL.rstrip("/").replace("/v1", "") + "/health"
    try:
        req = urllib.request.Request(
            health_url,
            headers={"Authorization": f"Bearer {LITELLM_MASTER_KEY}"},
            method="GET"
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            raw  = r.read().decode()
            data = json.loads(raw) if raw else {}
            rec(sec, "Gateway /health", OK,
                f"HTTP {r.status} — " + (data.get("status", raw[:80]) if isinstance(data, dict) else raw[:80]))
    except urllib.error.HTTPError as e:
        rec(sec, "Gateway /health", WARN, f"HTTP {e.code} — gateway ada tapi /health error")
    except urllib.error.URLError as e:
        rec(sec, "Gateway /health", FAIL,
            f"Tidak dapat terhubung ke {health_url}\n"
            f"         Pastikan LiteLLM Gateway berjalan: {e.reason}")

    # 5b. Cek /models endpoint
    models_url = LITELLM_BASE_URL.rstrip("/") + "/models"
    available_models = []
    try:
        req = urllib.request.Request(
            models_url,
            headers={"Authorization": f"Bearer {LITELLM_MASTER_KEY}"},
            method="GET"
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            raw  = r.read().decode()
            data = json.loads(raw) if raw else {}
            if isinstance(data, dict) and "data" in data:
                available_models = [m.get("id", "?") for m in data["data"]]
                rec(sec, "Gateway /models", OK, f"{len(available_models)} model tersedia")
            else:
                rec(sec, "Gateway /models", WARN, f"Response tidak terduga: {raw[:100]}")
    except urllib.error.HTTPError as e:
        if e.code == 401:
            rec(sec, "Gateway /models", FAIL,
                "HTTP 401 — LITELLM_MASTER_KEY salah atau tidak diset")
        else:
            rec(sec, "Gateway /models", WARN, f"HTTP {e.code}")
    except urllib.error.URLError as e:
        rec(sec, "Gateway /models", FAIL, f"Tidak dapat terhubung: {e.reason}")
    except Exception as e:
        rec(sec, "Gateway /models", WARN, str(e))

    # 5c. Cek apakah MODEL_NAME tersedia
    if available_models:
        if MODEL_NAME in available_models:
            rec(sec, f"Model '{MODEL_NAME}'", OK, "Terdaftar di gateway")
        else:
            # partial match (beberapa gateway expose alias)
            partial = [m for m in available_models if MODEL_NAME in m or m in MODEL_NAME]
            if partial:
                rec(sec, f"Model '{MODEL_NAME}'", WARN,
                    f"Tidak exact match, tapi ada kandidat: {', '.join(partial[:3])}")
            else:
                rec(sec, f"Model '{MODEL_NAME}'", WARN,
                    f"Model tidak ditemukan di /models. Model yang ada: {', '.join(available_models[:5])}"
                    + (" ..." if len(available_models) > 5 else ""))
    elif MODEL_NAME:
        rec(sec, f"Model '{MODEL_NAME}'", SKIP, "Tidak dapat verifikasi (list model gagal)")

    # 5d. Liveness test: kirim pesan singkat ke model
    try:
        llm_url  = LITELLM_BASE_URL.rstrip("/") + "/chat/completions"
        payload  = json.dumps({
            "model": MODEL_NAME,
            "max_tokens": 8,
            "messages": [{"role": "user", "content": "reply: OK"}]
        }).encode()
        req = urllib.request.Request(
            llm_url,
            data=payload,
            headers={
                "Authorization": f"Bearer {LITELLM_MASTER_KEY}",
                "Content-Type": "application/json"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            raw  = r.read().decode()
            data = json.loads(raw)
            reply = data.get("choices", [{}])[0].get("message", {}).get("content") or ""
            reply = reply.strip()
            rec(sec, "LLM liveness test", OK, f"Model merespons: \"{reply[:60]}\"")
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            body = json.loads(raw)
            msg  = body.get("error", {}).get("message", raw[:150]) if isinstance(body, dict) else raw[:150]
        except Exception:
            msg = raw[:150]
        rec(sec, "LLM liveness test", FAIL, f"HTTP {e.code}: {msg}")
    except urllib.error.URLError as e:
        rec(sec, "LLM liveness test", FAIL, f"Koneksi gagal: {e.reason}")
    except Exception as e:
        rec(sec, "LLM liveness test", FAIL, str(e))

    # ----------------------------------------------------------
    # Print Report
    # ----------------------------------------------------------
    print()
    print(HDR("=" * 62))
    print(HDR("  Git Manager AI Agent — Pre-flight Check"))
    print(HDR("=" * 62))

    current_sec = None
    for (section, item, tag, detail) in results:
        if section != current_sec:
            print()
            print(HDR(f"  [{section}]"))
            current_sec = section
        detail_str = f"  → {detail}" if detail else ""
        print(f"    {tag:<28}  {item}{detail_str}")

    print()
    print(HDR("=" * 62))
    summary_tag = OK if (failures == 0 and warnings == 0) else (WARN if failures == 0 else FAIL)
    print(f"  {summary_tag}  Ringkasan: {failures} failure(s), {warnings} warning(s)")
    print(HDR("=" * 62))
    print()

    if failures > 0:
        print(_c("31", "  ❌ Ada masalah kritis yang harus diperbaiki sebelum agent dapat berjalan."))
        print()
    elif warnings > 0:
        print(_c("33", "  ⚠️  Ada peringatan. Agent mungkin berjalan tapi beberapa fitur bisa gagal."))
        print()
    else:
        print(_c("32", "  ✅ Semua pemeriksaan lulus. Agent siap digunakan!"))
        print()

    sys.exit(1 if failures > 0 else 0)


# ============================================================
# FastAPI Server Mode
# ============================================================

def run_server():
    import uvicorn
    from fastapi import FastAPI, HTTPException, Body
    from pydantic import BaseModel, Field
    from typing import Optional, Dict, Any

    app = FastAPI(
        title="GitOps AI Agent API (Multi-SCM)",
        description=(
            "API untuk mengelola repository Git secara otonom melalui AI Agent.\n\n"
            f"**SCM Provider aktif**: `{SCM_PROVIDER.upper()}`  \n"
            f"**SCM Base URL**: `{SCM_BASE_URL}`"
        ),
        version="2.0.0",
    )

    class AgentRequest(BaseModel):
        action:        str                      = Field(..., description="clone | create-branch | pull-request | update-image | quick-pr")
        repo_name:     str                      = Field(..., description="Nama repository")
        org:           Optional[str]            = Field(DEFAULT_ORG, description="Organisasi / project")
        action_kwargs: Optional[Dict[str, Any]] = Field(default={}, description="Parameter ekstra per aksi")

    @app.post("/api/run")
    async def api_run(req: AgentRequest = Body(..., openapi_examples={
        "Clone": {"summary": "Clone", "value": {
            "action": "clone", "repo_name": "my-service", "org": DEFAULT_ORG,
            "action_kwargs": {"ref": "main"}
        }},
        "Create Branch": {"summary": "Create Branch", "value": {
            "action": "create-branch", "repo_name": "my-service", "org": DEFAULT_ORG,
            "action_kwargs": {"existing_branch": "main", "new_branch": "feature/my-feature"}
        }},
        "Pull Request": {"summary": "Pull Request", "value": {
            "action": "pull-request", "repo_name": "my-service", "org": DEFAULT_ORG,
            "action_kwargs": {"source_branch": "feature/my-feature", "dest_branch": "main"}
        }},
        "Update Image": {"summary": "Update Image", "value": {
            "action": "update-image", "repo_name": "gitops-k8s", "org": DEFAULT_ORG,
            "action_kwargs": {"ref": "main", "yaml_file": "deployment.yaml", "new_image": "app:v2.0.0"}
        }},
        "Quick PR": {"summary": "Quick PR", "value": {
            "action": "quick-pr", "repo_name": "gitops", "org": DEFAULT_ORG,
            "action_kwargs": {"namespace": "default", "deployment": "qoinplus-api", "image": "registry/qoinplus-api:v1.2.3"}
        }},
    })):
        try:
            report = await run_git_agent(req.action, req.repo_name, req.org or DEFAULT_ORG, req.action_kwargs or {})
            return {"status": "success", "scm_provider": SCM_PROVIDER, "report": report}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    print("🚀 Starting Web API on http://0.0.0.0:8888")
    print("📚 Swagger UI: http://localhost:8888/docs")
    uvicorn.run(app, host="0.0.0.0", port=8888)


# ============================================================
# Interactive / CLI Entry Point
# ============================================================

def main():
    if len(sys.argv) > 1 and sys.argv[1].lower() == "server":
        run_server()
        return

    if len(sys.argv) > 1 and sys.argv[1].lower() == "check":
        run_check()
        return

    org    = DEFAULT_ORG
    action = "clone"
    action_kwargs = {}

    # Non-interactive mode: python agent_git.py <repo> [branch]
    if len(sys.argv) >= 2 and sys.argv[1].lower() not in ("init",):
        repo_name     = sys.argv[1]
        action_kwargs = {"ref": sys.argv[2] if len(sys.argv) > 2 else "main"}
    else:
        # Interactive mode
        print("🚀 Git Manager AI Agent — Interactive Mode")
        print(f"   SCM Provider : {SCM_PROVIDER.upper()}")
        print(f"   SCM Base URL : {SCM_BASE_URL}\n")
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

            org_in = input(f"Organisasi [{DEFAULT_ORG}]: ").strip()
            if org_in: org = org_in

            if choice == "2":
                action       = "create-branch"
                exist_b      = input("Existing branch [main]: ").strip() or "main"
                new_b        = input("Nama branch baru: ").strip()
                if not new_b: print("❌ Nama branch baru wajib."); sys.exit(1)
                action_kwargs = {"existing_branch": exist_b, "new_branch": new_b}

            elif choice == "3":
                action   = "pull-request"
                src_b    = input("Source branch: ").strip()
                if not src_b: print("❌ Source branch wajib."); sys.exit(1)
                dst_b    = input("Destination branch [main]: ").strip() or "main"
                action_kwargs = {"source_branch": src_b, "dest_branch": dst_b}

            elif choice == "4":
                action  = "update-image"
                ref_b   = input("Branch [main]: ").strip() or "main"
                yaml_f  = input("Path file YAML (misal: deployment.yaml): ").strip()
                if not yaml_f: print("❌ Path YAML wajib."); sys.exit(1)
                img     = input("Image baru (misal: app:v2.0.0): ").strip()
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
                action        = "clone"
                ref           = input("Branch/Tag [main]: ").strip() or "main"
                action_kwargs = {"ref": ref}

        except EOFError:
            print("\n❌ Input dibatalkan."); sys.exit(1)

    try:
        asyncio.run(run_git_agent(action, repo_name, org, action_kwargs))
    except KeyboardInterrupt:
        print("\n⚠️ Dihentikan oleh pengguna.")
    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {e}")
        print(f"\n💡 Pastikan:")
        print(f"   → LiteLLM Gateway berjalan di {LITELLM_BASE_URL}")
        print(f"   → SCM_TOKEN sudah di-set di .env")
        print(f"   → git sudah terinstall")


if __name__ == "__main__":
    main()
