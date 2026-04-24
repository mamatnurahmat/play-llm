"""
SCMClient — Unified SCM REST API client.
==========================================
Mendukung GitHub, GitLab, Bitbucket Cloud & Server.
Tidak bergantung pada CLI apapun, hanya menggunakan urllib.
"""

import json
import base64
import urllib.request
import urllib.error
import urllib.parse
from typing import Optional

from agents.config import Config


class SCMClient:
    """Multi-provider SCM API client.

    Usage:
        client = SCMClient(config)
        sha = client.get_head_sha("MyOrg", "my-repo", "main")
        client.create_branch("MyOrg", "my-repo", "main", "feature/x")
    """

    def __init__(self, config: Config):
        self.cfg = config

    # ----------------------------------------------------------------
    # Low-level HTTP
    # ----------------------------------------------------------------

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.cfg.scm_token:
            if self.cfg.scm_provider == "github":
                headers["Authorization"] = f"Bearer {self.cfg.scm_token}"
                headers["X-GitHub-Api-Version"] = "2022-11-28"
            elif self.cfg.scm_provider == "gitlab":
                headers["PRIVATE-TOKEN"] = self.cfg.scm_token
            elif self.cfg.scm_provider in ("bitbucket_cloud", "bitbucket_server"):
                creds = base64.b64encode(
                    f"{self.cfg.scm_username}:{self.cfg.scm_token}".encode()
                ).decode()
                headers["Authorization"] = f"Basic {creds}"
        return headers

    def api_request(self, method: str, url: str, data: dict = None) -> dict:
        """Generic HTTPS request. Returns {status_code, body}."""
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=body, headers=self._headers(), method=method.upper())
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

    # ----------------------------------------------------------------
    # Clone URL Builder
    # ----------------------------------------------------------------

    def clone_url(self, org: str, repo: str) -> str:
        """Build authenticated clone URL."""
        if self.cfg.scm_username and self.cfg.scm_token:
            creds = f"{urllib.parse.quote(self.cfg.scm_username)}:{urllib.parse.quote(self.cfg.scm_token)}"
        else:
            creds = None

        host, path = self._resolve_host_path(org, repo)
        scheme = "https"
        if creds:
            return f"{scheme}://{creds}@{host}/{path}"
        return f"{scheme}://{host}/{path}"

    def _resolve_host_path(self, org: str, repo: str) -> tuple:
        p = self.cfg.scm_provider
        base = self.cfg.scm_base_url

        if p == "github":
            return "github.com", f"{org}/{repo}.git"
        elif p == "gitlab":
            host = base.replace("https://", "").replace("http://", "").rstrip("/")
            return host, f"{org}/{repo}.git"
        elif p == "bitbucket_cloud":
            return "bitbucket.org", f"{org}/{repo}.git"
        elif p == "bitbucket_server":
            host = base.replace("https://", "").replace("http://", "").split("/")[0]
            return host, f"scm/{org}/{repo}.git"
        else:
            return "github.com", f"{org}/{repo}.git"

    # ----------------------------------------------------------------
    # Branch Operations
    # ----------------------------------------------------------------

    def get_head_sha(self, org: str, repo: str, branch: str) -> str:
        """Get latest commit SHA for a branch."""
        p = self.cfg.scm_provider
        base = self.cfg.scm_base_url

        if p == "github":
            resp = self.api_request("GET", f"{base}/repos/{org}/{repo}/commits/{branch}")
            if isinstance(resp["body"], dict):
                return resp["body"].get("sha", "")
        elif p == "gitlab":
            project = urllib.parse.quote(f"{org}/{repo}", safe="")
            resp = self.api_request("GET", f"{base}/api/v4/projects/{project}/repository/commits/{branch}")
            if isinstance(resp["body"], dict):
                return resp["body"].get("id", "")
        elif p == "bitbucket_cloud":
            resp = self.api_request("GET", f"{base}/repositories/{org}/{repo}/commits/{branch}?pagelen=1")
            if isinstance(resp["body"], dict):
                vals = resp["body"].get("values", [])
                if vals:
                    return vals[0].get("hash", "")
        elif p == "bitbucket_server":
            resp = self.api_request("GET", f"{base}/rest/api/1.0/projects/{org}/repos/{repo}/commits?until={branch}&limit=1")
            if isinstance(resp["body"], dict):
                vals = resp["body"].get("values", [])
                if vals:
                    return vals[0].get("id", "")
        return ""

    def create_branch(self, org: str, repo: str, existing_branch: str, new_branch: str) -> dict:
        """Create a branch via SCM API. Returns {status, message}."""
        sha = self.get_head_sha(org, repo, existing_branch)
        if not sha:
            return {"status": "error", "message": f"Could not resolve SHA for branch '{existing_branch}'."}

        p = self.cfg.scm_provider
        base = self.cfg.scm_base_url

        if p == "github":
            resp = self.api_request("POST", f"{base}/repos/{org}/{repo}/git/refs",
                                    {"ref": f"refs/heads/{new_branch}", "sha": sha})
        elif p == "gitlab":
            project = urllib.parse.quote(f"{org}/{repo}", safe="")
            resp = self.api_request("POST", f"{base}/api/v4/projects/{project}/repository/branches",
                                    {"branch": new_branch, "ref": existing_branch})
        elif p == "bitbucket_cloud":
            resp = self.api_request("POST", f"{base}/repositories/{org}/{repo}/refs/branches",
                                    {"name": new_branch, "target": {"hash": sha}})
        elif p == "bitbucket_server":
            resp = self.api_request("POST", f"{base}/rest/api/1.0/projects/{org}/repos/{repo}/branches",
                                    {"name": new_branch, "startPoint": sha})
        else:
            return {"status": "error", "message": f"Unsupported SCM provider: {p}"}

        if resp["status_code"] in (200, 201):
            return {"status": "success", "message": f"Branch '{new_branch}' created from '{existing_branch}' via {p} API."}
        return {"status": "error", "message": f"API returned {resp['status_code']}: {resp['body']}"}

    # ----------------------------------------------------------------
    # Pull / Merge Request
    # ----------------------------------------------------------------

    def create_pull_request(self, org: str, repo: str, source_branch: str,
                            dest_branch: str, title: str, body: str) -> dict:
        """Create a PR/MR via SCM API. Returns {status, message, url}."""
        p = self.cfg.scm_provider
        base = self.cfg.scm_base_url

        try:
            if p == "github":
                resp = self.api_request("POST", f"{base}/repos/{org}/{repo}/pulls", {
                    "title": title, "body": body,
                    "head": source_branch, "base": dest_branch
                })
                if resp["status_code"] in (200, 201):
                    pr_url = resp["body"].get("html_url", "N/A")
                    return {"status": "success", "message": f"PR created: {pr_url}", "url": pr_url}

            elif p == "gitlab":
                project = urllib.parse.quote(f"{org}/{repo}", safe="")
                resp = self.api_request("POST", f"{base}/api/v4/projects/{project}/merge_requests", {
                    "title": title, "description": body,
                    "source_branch": source_branch, "target_branch": dest_branch
                })
                if resp["status_code"] in (200, 201):
                    mr_url = resp["body"].get("web_url", "N/A")
                    return {"status": "success", "message": f"MR created: {mr_url}", "url": mr_url}

            elif p == "bitbucket_cloud":
                resp = self.api_request("POST", f"{base}/repositories/{org}/{repo}/pullrequests", {
                    "title": title, "description": body,
                    "source": {"branch": {"name": source_branch}},
                    "destination": {"branch": {"name": dest_branch}}
                })
                if resp["status_code"] in (200, 201):
                    pr_url = resp["body"].get("links", {}).get("html", {}).get("href", "N/A")
                    return {"status": "success", "message": f"PR created: {pr_url}", "url": pr_url}

            elif p == "bitbucket_server":
                resp = self.api_request("POST", f"{base}/rest/api/1.0/projects/{org}/repos/{repo}/pull-requests", {
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
