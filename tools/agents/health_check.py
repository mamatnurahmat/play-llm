"""
HealthChecker — Pre-flight diagnostics.
=========================================
Memvalidasi seluruh requirement sebelum agent dijalankan:
  1. Python packages
  2. Environment variables
  3. Binary tools (git)
  4. SCM API access & token permissions
  5. LiteLLM Gateway status & model availability
"""

import os
import sys
import json
import shutil
import subprocess
import urllib.request
import urllib.error
import urllib.parse

from agents.config import Config
from agents.scm_client import SCMClient


class HealthChecker:
    """Pre-flight check runner.

    Usage:
        checker = HealthChecker(config)
        checker.run()  # prints report, exits with code
    """

    def __init__(self, config: Config):
        self.cfg = config
        self.scm = SCMClient(config)

        # ANSI colors
        self._use_color = sys.stdout.isatty() or os.environ.get("FORCE_COLOR")
        self.results  = []
        self.failures = 0
        self.warnings = 0

    def _c(self, code, text):
        return f"\033[{code}m{text}\033[0m" if self._use_color else text

    @property
    def OK(self):   return self._c("32", "✅ OK")
    @property
    def WARN(self): return self._c("33", "⚠️  WARN")
    @property
    def FAIL(self): return self._c("31", "❌ FAIL")
    @property
    def INFO(self): return self._c("36", "ℹ️  INFO")
    @property
    def SKIP(self): return self._c("90", "⏭  SKIP")

    def _hdr(self, text):
        return self._c("1;34", text)

    def _rec(self, section, item, tag, detail=""):
        if tag == self.FAIL:
            self.failures += 1
        if tag == self.WARN:
            self.warnings += 1
        self.results.append((section, item, tag, detail))

    # ----------------------------------------------------------------
    # Check Sections
    # ----------------------------------------------------------------

    def _check_packages(self):
        sec = "Python Packages"
        required = {"openai": "pip install openai", "dotenv": "pip install python-dotenv"}
        optional = {"fastapi": "pip install fastapi   (hanya untuk mode server)",
                     "uvicorn": "pip install uvicorn   (hanya untuk mode server)"}

        for pkg, hint in required.items():
            try:
                __import__(pkg)
                self._rec(sec, f"import {pkg}", self.OK)
            except ImportError:
                self._rec(sec, f"import {pkg}", self.FAIL, hint)

        for pkg, hint in optional.items():
            try:
                __import__(pkg)
                self._rec(sec, f"import {pkg}", self.OK, "optional")
            except ImportError:
                self._rec(sec, f"import {pkg}", self.WARN, hint)

    def _check_env(self):
        sec = "Environment Variables"

        env_file_found = os.path.isfile(".env")
        self._rec(sec, ".env file", self.OK if env_file_found else self.WARN,
                  ".env ditemukan" if env_file_found else "File .env tidak ada — menggunakan env system / default")

        required_env = {
            "SCM_PROVIDER":       (self.cfg.scm_provider,       "github | gitlab | bitbucket_cloud | bitbucket_server"),
            "SCM_ORG":            (self.cfg.scm_org,            "nama organisasi / project / workspace"),
            "SCM_TOKEN":          (self.cfg.scm_token,          "Personal Access Token / App Password"),
            "LITELLM_BASE_URL":   (self.cfg.litellm_base_url,   "base URL gateway LiteLLM"),
            "LITELLM_MASTER_KEY": (self.cfg.litellm_master_key, "master key LiteLLM"),
            "MODEL_NAME":         (self.cfg.model_name,         "nama model AI yang digunakan"),
        }
        for var, (val, desc) in required_env.items():
            if val and val not in ("MyOrg",):
                if "TOKEN" in var or "KEY" in var:
                    display = f"{val[:4]}{'*' * max(0, len(val) - 8)}{val[-4:]}" if len(val) > 8 else "****"
                else:
                    display = val
                self._rec(sec, var, self.OK, display)
            else:
                tag = self.FAIL if var in ("SCM_TOKEN", "LITELLM_MASTER_KEY") else self.WARN
                self._rec(sec, var, tag, f"Belum diset — {desc}")

        scm_username_ok = bool(self.cfg.scm_username)
        self._rec(sec, "SCM_USERNAME",
                  self.OK if scm_username_ok else self.WARN,
                  self.cfg.scm_username if scm_username_ok else "Kosong — clone HTTPS mungkin gagal jika repo private")

        valid_providers = {"github", "gitlab", "bitbucket_cloud", "bitbucket_server"}
        if self.cfg.scm_provider not in valid_providers:
            self._rec(sec, "SCM_PROVIDER nilai", self.FAIL,
                      f"'{self.cfg.scm_provider}' tidak valid. Harus salah satu: {', '.join(sorted(valid_providers))}")
        else:
            self._rec(sec, "SCM_PROVIDER nilai", self.OK, f"'{self.cfg.scm_provider}' dikenali")

        self._rec(sec, "SCM_BASE_URL", self.INFO,
                  self.cfg.scm_base_url + (" (auto-default)" if not os.environ.get("SCM_BASE_URL") else ""))

    def _check_binaries(self):
        sec = "Binary Tools"

        git_path = shutil.which("git")
        if git_path:
            try:
                gv = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=5)
                self._rec(sec, "git", self.OK, f"{gv.stdout.strip()}  ({git_path})")
            except Exception as e:
                self._rec(sec, "git", self.WARN, f"ditemukan tapi error: {e}")
        else:
            self._rec(sec, "git", self.FAIL, "git tidak ditemukan di PATH — install git terlebih dahulu")

        try:
            name_r  = subprocess.run(["git", "config", "--global", "user.name"],  capture_output=True, text=True, timeout=5)
            email_r = subprocess.run(["git", "config", "--global", "user.email"], capture_output=True, text=True, timeout=5)
            git_name  = name_r.stdout.strip()
            git_email = email_r.stdout.strip()
            if git_name and git_email:
                self._rec(sec, "git config user", self.OK, f"{git_name} <{git_email}>")
            else:
                self._rec(sec, "git config user", self.WARN,
                          "user.name / user.email belum di-set — diperlukan untuk `git commit`\n"
                          "         → git config --global user.name 'Nama'\n"
                          "         → git config --global user.email 'email@domain.com'")
        except Exception:
            self._rec(sec, "git config user", self.WARN, "Tidak dapat membaca git config")

    def _check_scm_api(self):
        sec = "SCM API Access"

        if not self.cfg.scm_token:
            self._rec(sec, "API auth", self.FAIL, "SCM_TOKEN kosong — tidak bisa melakukan API call")
            return

        p    = self.cfg.scm_provider
        base = self.cfg.scm_base_url

        if p == "github":
            resp = self.scm.api_request("GET", f"{base}/user")
            sc, body = resp["status_code"], resp["body"]
            if sc == 200 and isinstance(body, dict):
                self._rec(sec, "API connectivity", self.OK, f"Terautentikasi sebagai: {body.get('login', '?')}")
                rl = self.scm.api_request("GET", f"{base}/rate_limit")
                if rl["status_code"] == 200 and isinstance(rl["body"], dict):
                    core = rl["body"].get("resources", {}).get("core", {})
                    remaining = core.get("remaining", "?")
                    limit     = core.get("limit", "?")
                    self._rec(sec, "API rate limit", self.OK if remaining != 0 else self.WARN,
                              f"{remaining}/{limit} requests remaining")
                repos_resp = self.scm.api_request("GET", f"{base}/orgs/{self.cfg.scm_org}/repos?per_page=1")
                if repos_resp["status_code"] == 200:
                    self._rec(sec, "Token: read:org / repo", self.OK, f"Dapat mengakses repo di org '{self.cfg.scm_org}'")
                elif repos_resp["status_code"] == 404:
                    user_repos = self.scm.api_request("GET", f"{base}/users/{self.cfg.scm_org}/repos?per_page=1")
                    if user_repos["status_code"] == 200:
                        self._rec(sec, "Token: repo access", self.OK, f"'{self.cfg.scm_org}' adalah user, bukan org — OK")
                    else:
                        self._rec(sec, "Token: repo access", self.WARN,
                                  f"Org/user '{self.cfg.scm_org}' tidak ditemukan atau token tidak punya izin")
                elif repos_resp["status_code"] == 401:
                    self._rec(sec, "Token: repo access", self.FAIL, "Token tidak valid / expired")
                elif repos_resp["status_code"] == 403:
                    self._rec(sec, "Token: repo access", self.WARN,
                              "Token tidak punya izin baca repo org — butuh scope: repo atau read:org")
                else:
                    self._rec(sec, "Token: repo access", self.WARN,
                              f"HTTP {repos_resp['status_code']}: {str(repos_resp['body'])[:120]}")
            elif sc == 401:
                self._rec(sec, "API connectivity", self.FAIL, "HTTP 401 — Token tidak valid atau expired")
            else:
                self._rec(sec, "API connectivity", self.FAIL, f"HTTP {sc}: {str(body)[:150]}")

        elif p == "gitlab":
            resp = self.scm.api_request("GET", f"{base}/api/v4/user")
            sc, body = resp["status_code"], resp["body"]
            if sc == 200 and isinstance(body, dict):
                self._rec(sec, "API connectivity", self.OK, f"Terautentikasi sebagai: {body.get('username', '?')}")
                ns_url  = f"{base}/api/v4/groups/{urllib.parse.quote(self.cfg.scm_org, safe='')}?simple=true"
                ns_resp = self.scm.api_request("GET", ns_url)
                if ns_resp["status_code"] == 200:
                    self._rec(sec, "Token: group access", self.OK, f"Grup '{self.cfg.scm_org}' dapat diakses")
                else:
                    user_ns = self.scm.api_request("GET", f"{base}/api/v4/users?username={self.cfg.scm_org}")
                    if user_ns["status_code"] == 200 and isinstance(user_ns["body"], list) and user_ns["body"]:
                        self._rec(sec, "Token: namespace access", self.OK, f"'{self.cfg.scm_org}' adalah user namespace")
                    else:
                        self._rec(sec, "Token: group/namespace", self.WARN,
                                  f"Namespace '{self.cfg.scm_org}' tidak ditemukan atau token tidak punya akses")
            elif sc == 401:
                self._rec(sec, "API connectivity", self.FAIL, "HTTP 401 — Token tidak valid (PRIVATE-TOKEN)")
            else:
                self._rec(sec, "API connectivity", self.FAIL, f"HTTP {sc}: {str(body)[:150]}")

        elif p == "bitbucket_cloud":
            resp = self.scm.api_request("GET", f"{base}/user")
            sc, body = resp["status_code"], resp["body"]
            if sc == 200 and isinstance(body, dict):
                self._rec(sec, "API connectivity", self.OK,
                          f"Terautentikasi sebagai: {body.get('display_name', body.get('username', '?'))}")
                ws_resp = self.scm.api_request("GET", f"{base}/workspaces/{self.cfg.scm_org}")
                if ws_resp["status_code"] == 200:
                    self._rec(sec, "Token: workspace access", self.OK, f"Workspace '{self.cfg.scm_org}' dapat diakses")
                else:
                    self._rec(sec, "Token: workspace access", self.WARN,
                              f"Workspace '{self.cfg.scm_org}' tidak ditemukan atau tidak punya izin")
            elif sc == 401:
                self._rec(sec, "API connectivity", self.FAIL,
                          "HTTP 401 — Periksa SCM_USERNAME dan SCM_TOKEN (App Password)")
            else:
                self._rec(sec, "API connectivity", self.FAIL, f"HTTP {sc}: {str(body)[:150]}")

        elif p == "bitbucket_server":
            resp = self.scm.api_request("GET", f"{base}/rest/api/1.0/application-properties")
            sc, body = resp["status_code"], resp["body"]
            if sc == 200 and isinstance(body, dict):
                ver = body.get("version", "?")
                self._rec(sec, "API connectivity", self.OK, f"Bitbucket Server v{ver} dapat dijangkau")
                proj_resp = self.scm.api_request("GET", f"{base}/rest/api/1.0/projects/{self.cfg.scm_org}")
                if proj_resp["status_code"] == 200:
                    self._rec(sec, "Token: project access", self.OK, f"Project '{self.cfg.scm_org}' dapat diakses")
                elif proj_resp["status_code"] == 401:
                    self._rec(sec, "Token: project access", self.FAIL, "HTTP 401 — Token tidak valid")
                elif proj_resp["status_code"] == 403:
                    self._rec(sec, "Token: project access", self.WARN,
                              "HTTP 403 — Token tidak punya izin ke project ini")
                elif proj_resp["status_code"] == 404:
                    self._rec(sec, "Token: project access", self.WARN, f"Project '{self.cfg.scm_org}' tidak ditemukan")
                else:
                    self._rec(sec, "Token: project access", self.WARN, f"HTTP {proj_resp['status_code']}")
            elif sc == 0:
                self._rec(sec, "API connectivity", self.FAIL,
                          f"Tidak dapat terhubung ke {base} — periksa SCM_BASE_URL dan jaringan")
            else:
                self._rec(sec, "API connectivity", self.FAIL, f"HTTP {sc}: {str(body)[:150]}")
        else:
            self._rec(sec, "API connectivity", self.FAIL, f"Provider '{p}' tidak dikenali")

    def _check_llm_gateway(self):
        sec = "LiteLLM / AI Gateway"

        # Health endpoint
        health_url = self.cfg.litellm_base_url.rstrip("/").replace("/v1", "") + "/health"
        try:
            req = urllib.request.Request(
                health_url,
                headers={"Authorization": f"Bearer {self.cfg.litellm_master_key}"},
                method="GET"
            )
            with urllib.request.urlopen(req, timeout=8) as r:
                raw  = r.read().decode()
                data = json.loads(raw) if raw else {}
                self._rec(sec, "Gateway /health", self.OK,
                          f"HTTP {r.status} — " + (data.get("status", raw[:80]) if isinstance(data, dict) else raw[:80]))
        except urllib.error.HTTPError as e:
            self._rec(sec, "Gateway /health", self.WARN, f"HTTP {e.code} — gateway ada tapi /health error")
        except urllib.error.URLError as e:
            self._rec(sec, "Gateway /health", self.FAIL,
                      f"Tidak dapat terhubung ke {health_url}\n"
                      f"         Pastikan LiteLLM Gateway berjalan: {e.reason}")

        # Models endpoint
        models_url = self.cfg.litellm_base_url.rstrip("/") + "/models"
        available_models = []
        try:
            req = urllib.request.Request(
                models_url,
                headers={"Authorization": f"Bearer {self.cfg.litellm_master_key}"},
                method="GET"
            )
            with urllib.request.urlopen(req, timeout=8) as r:
                raw  = r.read().decode()
                data = json.loads(raw) if raw else {}
                if isinstance(data, dict) and "data" in data:
                    available_models = [m.get("id", "?") for m in data["data"]]
                    self._rec(sec, "Gateway /models", self.OK, f"{len(available_models)} model tersedia")
                else:
                    self._rec(sec, "Gateway /models", self.WARN, f"Response tidak terduga: {raw[:100]}")
        except urllib.error.HTTPError as e:
            if e.code == 401:
                self._rec(sec, "Gateway /models", self.FAIL,
                          "HTTP 401 — LITELLM_MASTER_KEY salah atau tidak diset")
            else:
                self._rec(sec, "Gateway /models", self.WARN, f"HTTP {e.code}")
        except urllib.error.URLError as e:
            self._rec(sec, "Gateway /models", self.FAIL, f"Tidak dapat terhubung: {e.reason}")
        except Exception as e:
            self._rec(sec, "Gateway /models", self.WARN, str(e))

        # Model availability
        model = self.cfg.model_name
        if available_models:
            if model in available_models:
                self._rec(sec, f"Model '{model}'", self.OK, "Terdaftar di gateway")
            else:
                partial = [m for m in available_models if model in m or m in model]
                if partial:
                    self._rec(sec, f"Model '{model}'", self.WARN,
                              f"Tidak exact match, tapi ada kandidat: {', '.join(partial[:3])}")
                else:
                    self._rec(sec, f"Model '{model}'", self.WARN,
                              f"Model tidak ditemukan di /models. Model yang ada: {', '.join(available_models[:5])}"
                              + (" ..." if len(available_models) > 5 else ""))
        elif model:
            self._rec(sec, f"Model '{model}'", self.SKIP, "Tidak dapat verifikasi (list model gagal)")

        # Liveness test
        try:
            llm_url = self.cfg.litellm_base_url.rstrip("/") + "/chat/completions"
            payload = json.dumps({
                "model": model,
                "max_tokens": 8,
                "messages": [{"role": "user", "content": "reply: OK"}]
            }).encode()
            req = urllib.request.Request(
                llm_url, data=payload,
                headers={
                    "Authorization": f"Bearer {self.cfg.litellm_master_key}",
                    "Content-Type": "application/json"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                raw  = r.read().decode()
                data = json.loads(raw)
                reply = data.get("choices", [{}])[0].get("message", {}).get("content") or ""
                reply = reply.strip()
                self._rec(sec, "LLM liveness test", self.OK, f'Model merespons: "{reply[:60]}"')
        except urllib.error.HTTPError as e:
            raw = e.read().decode()
            try:
                body = json.loads(raw)
                msg = body.get("error", {}).get("message", raw[:150]) if isinstance(body, dict) else raw[:150]
            except Exception:
                msg = raw[:150]
            self._rec(sec, "LLM liveness test", self.FAIL, f"HTTP {e.code}: {msg}")
        except urllib.error.URLError as e:
            self._rec(sec, "LLM liveness test", self.FAIL, f"Koneksi gagal: {e.reason}")
        except Exception as e:
            self._rec(sec, "LLM liveness test", self.FAIL, str(e))

    # ----------------------------------------------------------------
    # Run All Checks
    # ----------------------------------------------------------------

    def run(self):
        """Run all checks and print report. Exits with code 1 on failure."""
        self._check_packages()
        self._check_env()
        self._check_binaries()
        self._check_scm_api()
        self._check_llm_gateway()

        # Print report
        print()
        print(self._hdr("=" * 62))
        print(self._hdr("  Git Manager AI Agent — Pre-flight Check"))
        print(self._hdr("=" * 62))

        current_sec = None
        for (section, item, tag, detail) in self.results:
            if section != current_sec:
                print()
                print(self._hdr(f"  [{section}]"))
                current_sec = section
            detail_str = f"  → {detail}" if detail else ""
            print(f"    {tag:<28}  {item}{detail_str}")

        print()
        print(self._hdr("=" * 62))
        summary_tag = self.OK if (self.failures == 0 and self.warnings == 0) else (
            self.WARN if self.failures == 0 else self.FAIL)
        print(f"  {summary_tag}  Ringkasan: {self.failures} failure(s), {self.warnings} warning(s)")
        print(self._hdr("=" * 62))
        print()

        if self.failures > 0:
            print(self._c("31", "  ❌ Ada masalah kritis yang harus diperbaiki sebelum agent dapat berjalan."))
            print()
        elif self.warnings > 0:
            print(self._c("33", "  ⚠️  Ada peringatan. Agent mungkin berjalan tapi beberapa fitur bisa gagal."))
            print()
        else:
            print(self._c("32", "  ✅ Semua pemeriksaan lulus. Agent siap digunakan!"))
            print()

        sys.exit(1 if self.failures > 0 else 0)
