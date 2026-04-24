"""
PRAgent — Agent untuk membuat Pull/Merge Request.
===================================================
"""

from textwrap import dedent
from typing import List, Callable

from agents.base_agent import BaseAgent


class PRAgent(BaseAgent):

    @property
    def name(self) -> str:
        return "PR Agent"

    @property
    def description(self) -> str:
        return "Membuat Pull/Merge Request via SCM API."

    def get_tool_functions(self) -> List[Callable]:
        return [
            self.tools.scm_create_pull_request_api,
        ]

    def build_instruction(self) -> str:
        src = self.kwargs.get("source_branch")
        dst = self.kwargs.get("dest_branch", "main")
        return self._base_instruction() + dedent(f"""\
        TUGAS: Buat Pull/Merge Request dari '{src}' ke '{dst}'.
        Langkah:
        1. Buat judul dan deskripsi yang informatif.
        2. Panggil scm_create_pull_request_api: org='{self.org}', repo='{self.repo_name}', source_branch='{src}', dest_branch='{dst}'.
        3. Laporkan URL PR/MR.
        """)

    def build_user_message(self) -> str:
        src = self.kwargs.get("source_branch")
        dst = self.kwargs.get("dest_branch", "main")
        return f"Buat PR dari '{src}' ke '{dst}' di '{self.full_repo}'."

    def print_summary(self):
        super().print_summary()
        src = self.kwargs.get("source_branch")
        dst = self.kwargs.get("dest_branch", "main")
        print(f"🔀 {src} → {dst}")
