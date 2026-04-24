"""
BaseAgent — Abstract base class for all AI agents.
====================================================
Menyediakan:
  - LLM tool-calling loop (DRY, tidak perlu ditulis ulang per agent)
  - Injection of Config, SCMClient, GitTools
  - Template method pattern: subclass hanya override:
      * name, description
      * get_tools()
      * build_instruction()
      * build_user_message()
      * print_summary() (optional)
"""

import os
import re
import json
from abc import ABC, abstractmethod
from textwrap import dedent
from typing import Dict, List, Callable

from openai import AsyncOpenAI

from agents.config import Config
from agents.scm_client import SCMClient
from agents.git_tools import GitTools
from agents.llm_tools import get_openai_tools


class BaseAgent(ABC):
    """Abstract base class for tool-calling AI agents.

    Subclasses implement domain-specific behavior; the LLM
    interaction loop is fully handled here (DRY).
    """

    def __init__(self, config: Config, repo_name: str, org: str = None,
                 action_kwargs: dict = None):
        self.cfg        = config
        self.repo_name  = repo_name
        self.org        = org or config.default_org
        self.kwargs     = action_kwargs or {}

        # Shared services (injected, not global)
        self.scm    = SCMClient(config)
        self.tools  = GitTools(config, self.scm)

        # Derived
        self.full_repo = f"{self.org}/{self.repo_name}"
        self.dest_dir  = repo_name
        self.clone_url = self.scm.clone_url(self.org, self.repo_name)

    # ----------------------------------------------------------------
    # Template Methods (subclasses override these)
    # ----------------------------------------------------------------

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable agent name (e.g. 'Clone Agent')."""
        ...

    @property
    def description(self) -> str:
        """Optional description for documentation."""
        return ""

    @abstractmethod
    def get_tool_functions(self) -> List[Callable]:
        """Return the list of tool functions this agent can use."""
        ...

    @abstractmethod
    def build_instruction(self) -> str:
        """Build the system prompt / instruction for the LLM."""
        ...

    @abstractmethod
    def build_user_message(self) -> str:
        """Build the initial user message for the LLM."""
        ...

    def print_summary(self):
        """Print CLI summary before running. Override for custom output."""
        print(f"📦 Repository : {self.full_repo}")
        print(f"🔌 SCM        : {self.cfg.scm_provider.upper()}  ({self.cfg.scm_base_url})")
        print(f"📂 Dest Dir   : {self.dest_dir}")
        print(f"⚡ Agent      : {self.name}")

    # ----------------------------------------------------------------
    # Shared Helpers
    # ----------------------------------------------------------------

    def _base_instruction(self) -> str:
        """Common instruction prefix for all agents."""
        return dedent(f"""\
            Kamu adalah seorang Git Repository Manager yang ahli mengelola repository di berbagai SCM.
            SCM Provider aktif : {self.cfg.scm_provider.upper()}
            Repository target  : {self.full_repo}
            Local directory    : '{self.dest_dir}'
            Clone URL (HTTPS)  : {re.sub(r'://[^@]+@', '://<redacted>@', self.clone_url)}
        """)

    # ----------------------------------------------------------------
    # LLM Tool-Calling Loop (DRY — shared by all agents)
    # ----------------------------------------------------------------

    async def run(self, max_iterations: int = 15) -> str:
        """Execute the agent's LLM loop with tool calling.

        Returns:
            str: Final report from the LLM.
        """
        # Build tools mapping
        tool_funcs = self.get_tool_functions()
        available_functions: Dict[str, Callable] = {f.__name__: f for f in tool_funcs}
        openai_tools = get_openai_tools(tool_funcs)

        # Build messages
        instruction  = self.build_instruction()
        user_message = self.build_user_message()

        client = AsyncOpenAI(
            api_key=self.cfg.litellm_master_key,
            base_url=self.cfg.litellm_base_url,
        )
        messages = [
            {"role": "system", "content": instruction},
            {"role": "user",   "content": user_message},
        ]

        # Print summary
        self.print_summary()
        print(f"🤖 Memulai {self.name} ({self.cfg.model_name})...\n")

        final_report = ""
        for _ in range(max_iterations):
            response = await client.chat.completions.create(
                model=self.cfg.model_name,
                messages=messages,
                tools=openai_tools,
                tool_choice="auto",
            )
            resp_msg = response.choices[0].message
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
                    func = available_functions.get(func_name)
                    result = func(**func_args) if func else {
                        "status": "error", "message": f"Tool {func_name} not found"
                    }
                    print(f"  ✅ {func_name} → {result.get('status', '?')}")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": func_name,
                        "content": json.dumps(result),
                    })
            else:
                break

        print("\n######################")
        print("📋 Status Akhir:")
        if os.path.isdir(self.dest_dir):
            print(f"   ✅ Repository tersedia di: {os.path.abspath(self.dest_dir)}")
        else:
            print(f"   ℹ️  Repository tidak diklone secara lokal.")
        return final_report
