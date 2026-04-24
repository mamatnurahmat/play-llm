"""
CloneAgent — Agent untuk clone dan analisa repository.
========================================================
"""

from textwrap import dedent
from typing import List, Callable

from agents.base_agent import BaseAgent


class CloneAgent(BaseAgent):

    @property
    def name(self) -> str:
        return "Clone Agent"

    @property
    def description(self) -> str:
        return "Clone repository dan analisa strukturnya."

    def get_tool_functions(self) -> List[Callable]:
        return [
            self.tools.git_clone,
            self.tools.git_status,
            self.tools.git_log,
            self.tools.git_branch_list,
            self.tools.git_tag_list,
            self.tools.list_directory,
            self.tools.read_file,
            self.tools.run_shell_command,
        ]

    def build_instruction(self) -> str:
        ref = self.kwargs.get("ref", "main")
        return self._base_instruction() + dedent(f"""\
        TUGAS: Clone '{self.full_repo}' branch/tag '{ref}', lalu analisa strukturnya.
        Langkah:
        1. Cek apakah folder '{self.dest_dir}' sudah ada via list_directory pada '.'.
           - Sudah ada → skip clone, lanjut ke langkah 3.
        2. Clone via git_clone: repo_url='{self.clone_url}', dest_dir='{self.dest_dir}', branch='{ref}', single_branch=true.
        3. Jalankan git_status pada '{self.dest_dir}'.
        4. Jalankan list_directory pada '{self.dest_dir}'.
        5. Jalankan git_log: work_dir='{self.dest_dir}', count=5.
        6. Berikan laporan lengkap.
        """)

    def build_user_message(self) -> str:
        ref = self.kwargs.get("ref", "main")
        return f"Clone '{self.full_repo}' branch '{ref}' dan berikan laporan."

    def print_summary(self):
        super().print_summary()
        print(f"🌿 Branch/Tag : {self.kwargs.get('ref', 'main')}")
