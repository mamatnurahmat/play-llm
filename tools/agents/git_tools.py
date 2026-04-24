"""
Git Tools — Pure functions for local git operations.
======================================================
Semua function bersifat stateless dan mengembalikan dict
agar dapat langsung di-serialize ke JSON untuk LLM tool calling.
"""

import os
import re
import subprocess

from agents.config import Config
from agents.scm_client import SCMClient


class GitTools:
    """Collection of git tool functions bound to a Config + SCMClient.

    Usage:
        tools = GitTools(config, scm_client)
        result = tools.clone(repo_url, dest_dir, branch="main")
    """

    def __init__(self, config: Config, scm_client: SCMClient):
        self.cfg = config
        self.scm = scm_client

    # ----------------------------------------------------------------
    # Clone
    # ----------------------------------------------------------------

    def git_clone(self, repo_url: str, dest_dir: str, branch: str, single_branch: bool) -> dict:
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
            err_msg = re.sub(r"://[^@]+@", "://<redacted>@", result.stderr.strip())
            return {"status": "error", "message": f"Git clone failed: {err_msg}"}
        except subprocess.TimeoutExpired:
            return {"status": "error", "message": "Git clone timed out after 120 seconds."}
        except Exception as e:
            return {"status": "error", "message": f"Error: {e}"}

    # ----------------------------------------------------------------
    # Branch (API + local)
    # ----------------------------------------------------------------

    def scm_create_branch_api(self, org: str, repo: str, existing_branch: str, new_branch: str) -> dict:
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
            return self.scm.create_branch(org, repo, existing_branch, new_branch)
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def git_create_branch_local(self, work_dir: str, existing_branch: str, new_branch: str) -> dict:
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

    # ----------------------------------------------------------------
    # Pull Request
    # ----------------------------------------------------------------

    def scm_create_pull_request_api(self, org: str, repo: str, source_branch: str,
                                     dest_branch: str, title: str, body: str) -> dict:
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
            return self.scm.create_pull_request(org, repo, source_branch, dest_branch, title, body)
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # ----------------------------------------------------------------
    # Info / Read-only
    # ----------------------------------------------------------------

    def git_status(self, work_dir: str) -> dict:
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

    def git_log(self, work_dir: str, count: int) -> dict:
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
            return {"status": "error", "log": result.stderr.strip()}
        except Exception as e:
            return {"status": "error", "log": str(e)}

    def git_branch_list(self, work_dir: str) -> dict:
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

    def git_tag_list(self, work_dir: str) -> dict:
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

    # ----------------------------------------------------------------
    # File / Shell
    # ----------------------------------------------------------------

    def list_directory(self, dir_path: str) -> dict:
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

    def read_file(self, file_path: str) -> dict:
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

    def run_shell_command(self, command: str, work_dir: str) -> dict:
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

    # ----------------------------------------------------------------
    # YAML Image Update + Commit
    # ----------------------------------------------------------------

    def update_yaml_image(self, file_path: str, new_image: str) -> dict:
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
                    prefix = line[: line.find("image:")]
                    lines[i] = f"{prefix}image: {new_image}\n"
                    updated = True
            if not updated:
                return {"status": "error", "message": "No 'image:' key found in the file."}
            with open(file_path, "w") as f:
                f.writelines(lines)
            return {"status": "success", "message": f"Updated image in {file_path} to '{new_image}'"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def git_commit_and_push(self, work_dir: str, commit_message: str) -> dict:
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
