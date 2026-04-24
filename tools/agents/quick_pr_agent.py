"""
QuickPRAgent — Orchestrator agent (A2A pattern).
==================================================
Menggabungkan alur: Create Branch → Clone → Update Image → Commit → PR
dalam satu agent call. Ini adalah contoh A2A di mana satu agent
mengorkestrasi langkah-langkah yang sebelumnya dilakukan oleh agent lain.
"""

from textwrap import dedent
from typing import List, Callable

from agents.base_agent import BaseAgent


class QuickPRAgent(BaseAgent):
    """Orchestrator agent that combines branch → update → PR in one flow.

    Required action_kwargs:
        namespace:  Kubernetes namespace (default: "default")
        deployment: Deployment name
        image:      New container image (e.g. "registry/app:v1.2.3")
    """

    @property
    def name(self) -> str:
        return "Quick PR Agent"

    @property
    def description(self) -> str:
        return "Automated: Create Branch → Update Image → Commit → Create PR"

    # Derived properties from kwargs
    @property
    def namespace(self) -> str:
        return self.kwargs.get("namespace", "default")

    @property
    def deployment(self) -> str:
        return self.kwargs.get("deployment", "")

    @property
    def image(self) -> str:
        return self.kwargs.get("image", "")

    @property
    def yaml_file(self) -> str:
        return f"manifest/production-qoinplus/{self.deployment}_deployment.yaml"

    @property
    def branch_name(self) -> str:
        safe_img = self.image.replace(":", "-").replace("/", "-")
        return f"{self.namespace}-{self.deployment}-{safe_img}"

    def get_tool_functions(self) -> List[Callable]:
        return [
            self.tools.scm_create_branch_api,
            self.tools.git_create_branch_local,
            self.tools.git_clone,
            self.tools.git_status,
            self.tools.update_yaml_image,
            self.tools.git_commit_and_push,
            self.tools.scm_create_pull_request_api,
            self.tools.list_directory,
            self.tools.read_file,
        ]

    def build_instruction(self) -> str:
        return self._base_instruction() + dedent(f"""\
        TUGAS: Lakukan Quick PR untuk update image '{self.image}' pada deployment '{self.deployment}'.
        Langkah:
        1. Buat branch baru via scm_create_branch_api: org='{self.org}', repo='{self.repo_name}', existing_branch='main', new_branch='{self.branch_name}'.
        2. Jika API gagal membuat branch, coba clone repo branch 'main' lalu git_create_branch_local ke '{self.branch_name}'. Jika sukses via API, langsung clone branch '{self.branch_name}'.
        3. Clone repo (jika belum) via git_clone: repo_url='{self.clone_url}', dest_dir='{self.dest_dir}', branch='{self.branch_name}', single_branch=true.
        4. Panggil update_yaml_image: file_path='{self.dest_dir}/{self.yaml_file}', new_image='{self.image}'.
        5. Panggil git_commit_and_push: work_dir='{self.dest_dir}', commit_message='chore: update {self.deployment} image to {self.image}'.
        6. Panggil scm_create_pull_request_api: org='{self.org}', repo='{self.repo_name}', source_branch='{self.branch_name}', dest_branch='main', title='Update {self.deployment} image to {self.image}', body='Automated PR to update image for {self.deployment} in namespace {self.namespace}'.
        7. Laporkan hasil dan URL PR.
        """)

    def build_user_message(self) -> str:
        return f"Jalankan alur Quick PR untuk '{self.deployment}'."

    def print_summary(self):
        super().print_summary()
        print(f"🚀 Quick PR   : {self.deployment} → {self.image}")
        print(f"📝 Branch     : {self.branch_name}")
        print(f"📄 YAML       : {self.yaml_file}")
