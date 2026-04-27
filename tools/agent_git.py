#!/usr/bin/env python3
"""
Git Manager AI Agent — CLI Entry Point (A2A Architecture)
==========================================================
Thin wrapper around agents.cli for backward compatibility.
Use `mantools` command after `pip install mantools`.

Usage:
    python agent_git.py <repo_name> [branch/tag]
    python agent_git.py server
    python agent_git.py check
    python agent_git.py config
    python agent_git.py config set KEY VALUE [--local]
    python agent_git.py config init
"""

import os
os.environ["NETRC"] = "/dev/null"

from agents.cli import main

if __name__ == "__main__":
    main()
