"""
LLM Tools — OpenAI function-calling tools converter.
=====================================================
Utility untuk mengonversi Python callable menjadi
OpenAI tools schema secara otomatis dari docstring + type hints.
"""

import inspect
import re
from typing import Callable, List


def get_openai_tools(functions: List[Callable]) -> list:
    """Convert a list of Python callables into OpenAI-compatible tool definitions.

    Args:
        functions: List of callable objects with docstrings.

    Returns:
        list: OpenAI tool definitions (list of dicts).
    """
    tools = []
    for func in functions:
        sig = inspect.signature(func)
        properties = {}
        required = []
        for name, param in sig.parameters.items():
            # Skip 'self' parameter for bound methods
            if name == "self":
                continue
            param_type = "string"
            if param.annotation == int:
                param_type = "integer"
            if param.annotation == bool:
                param_type = "boolean"
            # Extract per-parameter description from docstring
            doc_desc = ""
            if func.__doc__:
                match = re.search(rf"{name}:\s*(.+)", func.__doc__)
                if match:
                    doc_desc = match.group(1).strip()
            properties[name] = {"type": param_type, "description": doc_desc or f"Parameter {name}"}
            if param.default == inspect.Parameter.empty:
                required.append(name)
        tools.append({
            "type": "function",
            "function": {
                "name": func.__name__,
                "description": (func.__doc__ or "").split("\n")[0].strip(),
                "parameters": {"type": "object", "properties": properties, "required": required}
            }
        })
    return tools
