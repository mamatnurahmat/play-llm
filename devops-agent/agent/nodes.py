import json
import os
from langchain_core.messages import AIMessage, ToolMessage, SystemMessage
from litellm import completion

from .state import AgentState
from .tools import TOOLS

SYSTEM_PROMPT = """Kamu adalah DevOps Agent yang ahli dalam:
- GitOps: ArgoCD, Flux, Git-based deployments, reconciliation
- Kubernetes: workloads, networking, storage, RBAC, troubleshooting
- CI/CD: GitHub Actions, Jenkins, Tekton, pipeline design patterns
- Deployment strategies: canary, blue-green, rolling update, rollback
- Tools: Helm, Kustomize, kubectl, Skaffold

Gaya komunikasi:
- Jawab dalam Bahasa Indonesia kecuali diminta lain
- Gunakan contoh konkret dan perintah yang bisa langsung dipakai
- Kalau relevan, sertakan snippet YAML atau command
- Jika tidak tahu sesuatu yang spesifik, akui dan arahkan ke dokumentasi resmi

Saat menjawab, pertimbangkan untuk menggunakan tools yang tersedia untuk memberikan jawaban yang lebih detail dan akurat."""

TOOL_MAP = {t.name: t for t in TOOLS}
# Saat LITELLM_BASE_URL di-set (proxy mode), model harus prefix "openai/"
MODEL = os.getenv("LITELLM_MODEL", "openai/gemini-1.5-flash")
LITELLM_BASE_URL = os.getenv("LITELLM_BASE_URL", "").rstrip("/")
LITELLM_API_KEY = os.getenv("LITELLM_MASTER_KEY") or os.getenv("OPENAI_API_KEY", "")


def _build_litellm_tools():
    tools = []
    for t in TOOLS:
        schema = t.args_schema.schema() if t.args_schema else {"type": "object", "properties": {}}
        tools.append({
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": schema,
            },
        })
    return tools


LITELLM_TOOLS = _build_litellm_tools()


def call_model(state: AgentState) -> dict:
    messages = list(state["messages"])

    # Inject system prompt if not present
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages

    # Convert to litellm format
    lm_messages = []
    for m in messages:
        if isinstance(m, SystemMessage):
            lm_messages.append({"role": "system", "content": m.content})
        elif isinstance(m, AIMessage):
            msg = {"role": "assistant", "content": m.content or ""}
            if m.additional_kwargs.get("tool_calls"):
                msg["tool_calls"] = m.additional_kwargs["tool_calls"]
            lm_messages.append(msg)
        elif isinstance(m, ToolMessage):
            lm_messages.append({
                "role": "tool",
                "content": str(m.content),
                "tool_call_id": m.tool_call_id,
            })
        else:
            lm_messages.append({"role": "user", "content": str(m.content)})

    # Kirim ke LiteLLM Proxy jika LITELLM_BASE_URL di-set
    extra_kwargs = {}
    if LITELLM_BASE_URL:
        extra_kwargs["api_base"] = LITELLM_BASE_URL
        extra_kwargs["api_key"] = LITELLM_API_KEY

    response = completion(
        model=MODEL,
        messages=lm_messages,
        tools=LITELLM_TOOLS,
        tool_choice="auto",
        **extra_kwargs,
    )

    msg = response.choices[0].message
    tool_calls = getattr(msg, "tool_calls", None)

    ai_msg = AIMessage(
        content=msg.content or "",
        additional_kwargs={"tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in tool_calls
        ]} if tool_calls else {},
    )

    return {"messages": [ai_msg]}


def call_tools(state: AgentState) -> dict:
    last = state["messages"][-1]
    tool_calls = last.additional_kwargs.get("tool_calls", [])
    results = []

    for tc in tool_calls:
        name = tc["function"]["name"]
        args = json.loads(tc["function"]["arguments"])
        tool = TOOL_MAP.get(name)
        if tool:
            output = tool.invoke(args)
        else:
            output = f"Tool '{name}' tidak ditemukan."

        results.append(ToolMessage(content=str(output), tool_call_id=tc["id"]))

    return {"messages": results}


def should_continue(state: AgentState) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.additional_kwargs.get("tool_calls"):
        return "call_tools"
    return "end"
