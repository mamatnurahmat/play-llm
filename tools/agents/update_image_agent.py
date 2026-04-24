"""
UpdateImageAgent — Agent untuk update image di YAML dan push.
===============================================================
"""

from textwrap import dedent
from typing import List, Callable

from agents.base_agent import BaseAgent


class UpdateImageAgent(BaseAgent):

    @property
    def name(self) -> str:
        return "Update Image Agent"

    @property
    def description(self) -> str:
        return "Update image di file YAML, commit dan push."

    def get_tool_functions(self) -> List[Callable]:
        return [
            self.tools.git_clone,
            self.tools.git_status,
            self.tools.update_yaml_image,
            self.tools.git_commit_and_push,
            self.tools.list_directory,
            self.tools.read_file,
        ]

    def build_instruction(self) -> str:
        ref     = self.kwargs.get("ref", "main")
        yaml_f  = self.kwargs.get("yaml_file")
        new_img = self.kwargs.get("new_image")
        return self._base_instruction() + dedent(f"""\
        TUGAS: Update image YAML dan push.
        Langkah:
        1. Cek/clone repo branch '{ref}' jika belum ada.
        2. Panggil update_yaml_image: file_path='{self.dest_dir}/{yaml_f}', new_image='{new_img}'.
        3. Panggil git_commit_and_push: work_dir='{self.dest_dir}', commit_message='chore: update image to {new_img}'.
        4. Laporkan hasil.
        """)

    def build_user_message(self) -> str:
        yaml_f  = self.kwargs.get("yaml_file")
        new_img = self.kwargs.get("new_image")
        ref     = self.kwargs.get("ref", "main")
        return f"Update '{yaml_f}' dengan image '{new_img}' di branch '{ref}'."

    def print_summary(self):
        super().print_summary()
        print(f"🐳 New Image  : {self.kwargs.get('new_image')}")
