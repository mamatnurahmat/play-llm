"""
BranchAgent — Agent untuk membuat branch baru.
================================================
"""

from textwrap import dedent
from typing import List, Callable

from agents.base_agent import BaseAgent


class BranchAgent(BaseAgent):

    @property
    def name(self) -> str:
        return "Branch Agent"

    @property
    def description(self) -> str:
        return "Membuat branch baru dari existing branch."

    def get_tool_functions(self) -> List[Callable]:
        return [
            self.tools.scm_create_branch_api,
            self.tools.git_create_branch_local,
            self.tools.git_clone,
            self.tools.git_status,
        ]

    def build_instruction(self) -> str:
        existing = self.kwargs.get("existing_branch", "main")
        new_b    = self.kwargs.get("new_branch")
        return self._base_instruction() + dedent(f"""\
        TUGAS: Buat branch '{new_b}' dari '{existing}'.
        Langkah:
        1. Coba via scm_create_branch_api: org='{self.org}', repo='{self.repo_name}', existing_branch='{existing}', new_branch='{new_b}'.
        2. Jika API gagal, fallback ke git_create_branch_local setelah clone jika perlu.
        3. Laporkan hasil.
        """)

    def build_user_message(self) -> str:
        existing = self.kwargs.get("existing_branch", "main")
        new_b    = self.kwargs.get("new_branch")
        return f"Buat branch '{new_b}' dari '{existing}' di '{self.full_repo}'."

    def print_summary(self):
        super().print_summary()
        print(f"✨ New Branch : {self.kwargs.get('new_branch')}")
