# Architecture Deep Dive: Graph, State, Nodes & Tools

Dokumen ini menjelaskan arsitektur internal DevOps Agent secara mendalam — bagaimana LangGraph
mengorkestrasikan alur pikiran AI, cara State menyimpan konteks percakapan, peran setiap Node,
dan bagaimana Tools dipanggil secara otomatis oleh LLM.

---

## Daftar Isi

1. [Gambaran Besar](#1-gambaran-besar)
2. [State — Memori Agent](#2-state--memori-agent)
3. [Graph — Mesin Orkestrator](#3-graph--mesin-orkestrator)
4. [Nodes — Unit Eksekusi](#4-nodes--unit-eksekusi)
5. [Tools — Kemampuan Tambahan](#5-tools--kemampuan-tambahan)
6. [Alur Lengkap Sebuah Pertanyaan](#6-alur-lengkap-sebuah-pertanyaan)
7. [Cara Menambah Tool Baru](#7-cara-menambah-tool-baru)

---

## 1. Gambaran Besar

DevOps Agent dibangun di atas **LangGraph** — framework untuk membangun LLM workflow
sebagai *stateful directed graph*. Berbeda dengan simple chain (A → B → C), LangGraph
memungkinkan *loop*, *branching*, dan *conditional routing* berdasarkan output LLM.

```
┌─────────────────────────────────────────────────────┐
│                    LangGraph Graph                   │
│                                                      │
│   ┌───────────┐        ┌─────────────────────────┐  │
│   │           │ ya, ada │                         │  │
│   │  [agent]  ├────────►     [action]             │  │
│   │ call_model│ tool    │     call_tools           │  │
│   │           │ calls   │                         │  │
│   └─────┬─────┘        └────────────┬────────────┘  │
│         │ tidak ada                 │               │
│         │ tool calls   ◄────────────┘               │
│         ▼             kembali ke agent              │
│       [END]                                         │
└─────────────────────────────────────────────────────┘
```

**Komponen utama:**

| Komponen | File | Peran |
|---|---|---|
| `AgentState` | `agent/state.py` | Mendefinisikan struktur data yang mengalir di graph |
| `StateGraph` | `agent/graph.py` | Merakit graph: nodes + edges |
| `call_model` | `agent/nodes.py` | Node LLM — memanggil Gemini via LiteLLM Proxy |
| `call_tools` | `agent/nodes.py` | Node eksekusi tool yang dipilih LLM |
| `should_continue` | `agent/nodes.py` | Router — apakah perlu memanggil tool atau selesai |
| `TOOLS` | `agent/tools.py` | 4 fungsi knowledge base DevOps |

---

## 2. State — Memori Agent

**File:** `agent/state.py`

```python
from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage
import operator

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
```

### Apa itu State?

State adalah **satu-satunya data yang mengalir di antara semua node** dalam graph.
Setiap node menerima State sebagai input dan mengembalikan *sebagian* State yang diperbarui.

### Mengapa `Annotated[..., operator.add]`?

Ini adalah *reducer* — instruksi kepada LangGraph tentang **cara menggabungkan** output node
dengan State yang ada.

| Tanpa reducer | Dengan `operator.add` |
|---|---|
| Node baru **menimpa** seluruh `messages` | Node baru **menambahkan** pesan ke daftar yang ada |
| Percakapan hilang setiap step | Percakapan terakumulasi sepanjang sesi |

**Contoh konkret:**

```
Step 1 — State awal:
messages = [HumanMessage("Apa itu GitOps?")]

Step 2 — Setelah call_model:
messages = [
    HumanMessage("Apa itu GitOps?"),
    AIMessage("GitOps adalah...", tool_calls=[{name: "explain_gitops_concept"}])
]
                 ↑ pesan lama tetap ada, pesan baru di-append

Step 3 — Setelah call_tools:
messages = [
    HumanMessage("Apa itu GitOps?"),
    AIMessage("GitOps adalah...", tool_calls=[...]),
    ToolMessage("GitOps menggunakan Git sebagai single source of truth...")
]

Step 4 — Setelah call_model (putaran kedua):
messages = [
    HumanMessage("Apa itu GitOps?"),
    AIMessage("GitOps adalah...", tool_calls=[...]),
    ToolMessage("GitOps menggunakan Git sebagai single source of truth..."),
    AIMessage("Berdasarkan penjelasan tersebut, GitOps adalah...")
]
                 ↑ jawaban akhir yang dikirim ke user
```

### Tipe Pesan dalam State

```python
# Pesan dari user
HumanMessage(content="Apa itu ArgoCD?")

# Pesan dari LLM (bisa mengandung tool_calls)
AIMessage(
    content="",
    additional_kwargs={
        "tool_calls": [{
            "id": "call_abc123",
            "type": "function",
            "function": {
                "name": "explain_gitops_concept",
                "arguments": '{"concept": "argocd"}'
            }
        }]
    }
)

# Hasil eksekusi tool
ToolMessage(
    content="Argo CD adalah declarative GitOps CD tool...",
    tool_call_id="call_abc123"   # harus cocok dengan id di AIMessage
)

# System prompt (disuntikkan di awal, tidak terlihat user)
SystemMessage(content="Kamu adalah DevOps Agent yang ahli dalam...")
```

---

## 3. Graph — Mesin Orkestrator

**File:** `agent/graph.py`

```python
from langgraph.graph import StateGraph, END
from .state import AgentState
from .nodes import call_model, call_tools, should_continue

def create_graph():
    workflow = StateGraph(AgentState)

    # Daftarkan nodes
    workflow.add_node("agent", call_model)
    workflow.add_node("action", call_tools)

    # Entry point: selalu mulai dari node "agent"
    workflow.set_entry_point("agent")

    # Conditional edge: setelah "agent", tanya should_continue()
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "call_tools": "action",  # ada tool calls → ke "action"
            "end": END               # tidak ada → selesai
        }
    )

    # Edge tetap: setelah "action" selalu kembali ke "agent"
    workflow.add_edge("action", "agent")

    return workflow.compile()

devops_agent = create_graph()
```

### Anatomi Graph

```
             set_entry_point("agent")
                     │
                     ▼
            ┌────────────────┐
            │    "agent"     │  ← Node terdaftar: call_model
            │  (call_model)  │
            └───────┬────────┘
                    │
                    │  add_conditional_edges("agent", should_continue, {...})
                    │
           ┌────────┴───────────┐
    "end"  │                    │ "call_tools"
           ▼                    ▼
         [END]        ┌────────────────┐
                      │   "action"     │  ← Node terdaftar: call_tools
                      │  (call_tools)  │
                      └───────┬────────┘
                              │
                              │  add_edge("action", "agent")
                              │
                              └──────────────► kembali ke "agent"
```

### Tipe Edge

| Tipe | Fungsi | Contoh dalam kode |
|---|---|---|
| **Fixed edge** | Selalu pergi ke node tertentu | `add_edge("action", "agent")` |
| **Conditional edge** | Pilih tujuan berdasarkan output fungsi router | `add_conditional_edges("agent", should_continue, {...})` |
| **Entry point** | Mendefinisikan node pertama yang dieksekusi | `set_entry_point("agent")` |
| **END** | Sentinel khusus LangGraph untuk mengakhiri eksekusi | `"end": END` |

### Mengapa Loop?

Loop `agent → action → agent` memungkinkan agent menggunakan **banyak tool dalam satu percakapan**,
atau bahkan memanggil tool secara berantai. Contoh:

```
User: "Jelaskan ArgoCD dan berikan contoh kubectl rollout"
  │
  ├─► agent: LLM memutuskan perlu 2 tool sekaligus
  ├─► action: explain_gitops_concept("argocd") + get_kubectl_commands("rollout")
  └─► agent: LLM merangkai kedua hasil jadi jawaban kohesif
```

---

## 4. Nodes — Unit Eksekusi

**File:** `agent/nodes.py`

Ada 3 fungsi kunci: `call_model`, `call_tools`, dan `should_continue`.

---

### 4.1 `call_model` — Node LLM

```python
MODEL = os.getenv("LITELLM_MODEL", "openai/gemini-1.5-flash")
LITELLM_BASE_URL = os.getenv("LITELLM_BASE_URL", "").rstrip("/")
LITELLM_API_KEY  = os.getenv("LITELLM_MASTER_KEY") or os.getenv("OPENAI_API_KEY", "")

def call_model(state: AgentState) -> dict:
    messages = list(state["messages"])

    # 1. Suntikkan system prompt di awal jika belum ada
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages

    # 2. Konversi LangChain message objects → format dict LiteLLM/OpenAI
    lm_messages = [...]  # lihat kode lengkap

    # 3. Panggil LLM via LiteLLM (routing ke proxy 193.1.1.3:8888)
    extra_kwargs = {}
    if LITELLM_BASE_URL:
        extra_kwargs["api_base"] = LITELLM_BASE_URL
        extra_kwargs["api_key"]  = LITELLM_API_KEY

    response = completion(
        model=MODEL,
        messages=lm_messages,
        tools=LITELLM_TOOLS,     # ← kirim definisi tools ke LLM
        tool_choice="auto",      # ← LLM bebas memutuskan pakai tool atau tidak
        **extra_kwargs,
    )

    # 4. Kemas respons LLM sebagai AIMessage
    msg = response.choices[0].message
    ai_msg = AIMessage(
        content=msg.content or "",
        additional_kwargs={"tool_calls": [...]} if msg.tool_calls else {},
    )

    return {"messages": [ai_msg]}  # ← reducer operator.add akan append ini
```

**Yang terjadi di LLM:**

Saat `tools=LITELLM_TOOLS` dan `tool_choice="auto"` dikirim ke LLM, model menerima:
```json
{
  "messages": [...],
  "tools": [
    {"type": "function", "function": {"name": "explain_gitops_concept", "description": "...", "parameters": {...}}},
    {"type": "function", "function": {"name": "explain_kubernetes_resource", ...}},
    ...
  ],
  "tool_choice": "auto"
}
```

LLM kemudian memutuskan:
- **Jawab langsung** → kembalikan `content` biasa (tidak ada `tool_calls`)
- **Pakai tool** → kembalikan `tool_calls` berisi nama tool + argumen yang diinginkan

---

### 4.2 `call_tools` — Node Eksekusi Tool

```python
TOOL_MAP = {t.name: t for t in TOOLS}  # {"explain_gitops_concept": <fungsi>, ...}

def call_tools(state: AgentState) -> dict:
    last = state["messages"][-1]                          # AIMessage terakhir
    tool_calls = last.additional_kwargs.get("tool_calls", [])
    results = []

    for tc in tool_calls:
        name = tc["function"]["name"]                     # nama tool yang diminta LLM
        args = json.loads(tc["function"]["arguments"])    # argumen yang disiapkan LLM

        tool = TOOL_MAP.get(name)
        if tool:
            output = tool.invoke(args)                    # eksekusi fungsi Python
        else:
            output = f"Tool '{name}' tidak ditemukan."

        results.append(ToolMessage(
            content=str(output),
            tool_call_id=tc["id"]   # ← wajib cocok, agar LLM tahu hasil milik tool call mana
        ))

    return {"messages": results}
```

**Penting:** LLM *tidak* mengeksekusi kode Python secara langsung. LLM hanya mengembalikan
**nama tool dan argumen** dalam bentuk JSON. `call_tools` yang benar-benar menjalankan
fungsi Python-nya, lalu mengirim hasilnya kembali ke LLM.

```
LLM → "saya mau pakai explain_gitops_concept dengan concept='argocd'"
          ↓ (tidak dieksekusi LLM)
call_tools → TOOL_MAP["explain_gitops_concept"].invoke({"concept": "argocd"})
           → "Argo CD adalah declarative GitOps CD tool..."
          ↓
LLM menerima hasil dan merangkainya jadi jawaban
```

---

### 4.3 `should_continue` — Router / Edge Kondisional

```python
def should_continue(state: AgentState) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.additional_kwargs.get("tool_calls"):
        return "call_tools"   # → graph routing ke node "action"
    return "end"              # → graph routing ke END
```

Fungsi ini **tidak mengubah State** — hanya mengembalikan string sebagai sinyal routing.
String tersebut dicocokkan dengan mapping di `add_conditional_edges`:

```python
{"call_tools": "action", "end": END}
 ↑                ↑        ↑
 nilai return  → node tujuan
```

---

## 5. Tools — Kemampuan Tambahan

**File:** `agent/tools.py`

Tools adalah fungsi Python biasa yang dibungkus dekorator `@tool` dari LangChain.
Dekorator ini secara otomatis:
1. Membuat JSON schema dari type hints dan docstring
2. Mendaftarkan fungsi agar bisa dipanggil oleh LLM

```python
from langchain_core.tools import tool

@tool
def explain_gitops_concept(concept: str) -> str:
    """Jelaskan konsep GitOps seperti: flux, argocd, reconciliation, drift detection, pull vs push deployment."""
    # ↑ Docstring ini menjadi "description" yang dikirim ke LLM
    # ↑ LLM membaca ini untuk memutuskan kapan tool ini relevan

    knowledge = {
        "argocd": "Argo CD adalah...",
        "flux": "Flux adalah...",
        ...
    }
    ...
```

### 4 Tools yang Tersedia

| Tool | Parameter | Topik yang Dicakup |
|---|---|---|
| `explain_gitops_concept` | `concept: str` | flux, argocd, reconciliation, drift detection, pull vs push |
| `explain_kubernetes_resource` | `resource: str` | pod, deployment, service, ingress, hpa, pvc, configmap, secret, namespace, rbac, networkpolicy |
| `explain_cicd_pattern` | `pattern: str` | github actions, jenkins, tekton, helm, kustomize, canary, blue-green, rollback, pipeline stages |
| `get_kubectl_commands` | `operation: str` | debug, logs, exec, scale, rollout, port-forward, top |

### Bagaimana LLM "Tahu" Kapan Pakai Tool?

LLM membaca `name` dan `description` setiap tool. Saat user bertanya sesuatu yang relevan,
LLM secara otomatis membuat keputusan:

```
User: "Jelaskan canary deployment"

LLM berpikir:
  - Ada tool "explain_cicd_pattern" dengan description "Jelaskan pola CI/CD: ... canary ..."
  - Pertanyaan ini cocok → gunakan tool ini
  - Argumen yang tepat: {"pattern": "canary"}

Output LLM:
  tool_calls: [{name: "explain_cicd_pattern", arguments: '{"pattern": "canary"}'}]
```

---

## 6. Alur Lengkap Sebuah Pertanyaan

Mari trace alur untuk pertanyaan: **"Apa perbedaan ArgoCD dan Flux?"**

```
┌─────────────────────────────────────────────────────────────────────┐
│ POST /chat {"message": "Apa perbedaan ArgoCD dan Flux?"}            │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│ api/main.py                                                         │
│                                                                     │
│ messages = [HumanMessage("Apa perbedaan ArgoCD dan Flux?")]         │
│ result = devops_agent.invoke({"messages": messages})                │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│ GRAPH — Step 1: Entry point "agent" (call_model)                    │
│                                                                     │
│ State masuk:                                                        │
│   messages: [HumanMessage("Apa perbedaan ArgoCD dan Flux?")]        │
│                                                                     │
│ → Suntik SystemMessage di depan                                     │
│ → Kirim ke LiteLLM Proxy (http://193.1.1.3:8888)                   │
│ → LLM memutuskan: perlu 2 tool calls                                │
│                                                                     │
│ State keluar (reducer append):                                      │
│   messages: [                                                       │
│     HumanMessage("Apa perbedaan ArgoCD dan Flux?"),                 │
│     AIMessage(content="", tool_calls=[                              │
│       {id:"c1", name:"explain_gitops_concept", args:{concept:"argocd"}},│
│       {id:"c2", name:"explain_gitops_concept", args:{concept:"flux"}}   │
│     ])                                                              │
│   ]                                                                 │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼ should_continue() → "call_tools"
┌─────────────────────────────────────────────────────────────────────┐
│ GRAPH — Step 2: "action" (call_tools)                               │
│                                                                     │
│ → Eksekusi explain_gitops_concept({concept: "argocd"})              │
│   → return "Argo CD adalah declarative GitOps CD tool..."           │
│                                                                     │
│ → Eksekusi explain_gitops_concept({concept: "flux"})                │
│   → return "Flux adalah GitOps operator untuk Kubernetes..."        │
│                                                                     │
│ State keluar (reducer append):                                      │
│   messages: [                                                       │
│     HumanMessage(...),                                              │
│     AIMessage(tool_calls=[...]),                                    │
│     ToolMessage(content="Argo CD adalah...", tool_call_id="c1"),    │
│     ToolMessage(content="Flux adalah...", tool_call_id="c2"),       │
│   ]                                                                 │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  add_edge("action", "agent")
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│ GRAPH — Step 3: "agent" (call_model) — putaran kedua                │
│                                                                     │
│ → LLM menerima seluruh history (termasuk 2 ToolMessage)             │
│ → LLM merangkai jawaban kohesif membandingkan ArgoCD vs Flux        │
│ → Tidak ada tool_calls lagi                                         │
│                                                                     │
│ State keluar:                                                       │
│   messages: [..., AIMessage(content="ArgoCD dan Flux keduanya...")]  │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼ should_continue() → "end"
                             [END]
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│ api/main.py mengembalikan:                                          │
│   {                                                                 │
│     "response": "ArgoCD dan Flux keduanya adalah GitOps tools...",  │
│     "tool_calls_used": ["explain_gitops_concept"]                   │
│   }                                                                 │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 7. Cara Menambah Tool Baru

Menambah kemampuan baru ke agent sangat mudah — cukup 2 langkah:

### Langkah 1: Definisikan fungsi di `agent/tools.py`

```python
@tool
def explain_monitoring_tool(tool_name: str) -> str:
    """Jelaskan monitoring tools: prometheus, grafana, alertmanager, loki, jaeger, datadog."""
    knowledge = {
        "prometheus": (
            "Prometheus: sistem monitoring time-series open-source. "
            "Pull-based: scrape metrics dari /metrics endpoint. "
            "PromQL untuk query. AlertManager untuk alerting. "
            "Cocok dipadukan dengan Grafana untuk visualisasi."
        ),
        "grafana": (
            "Grafana: platform visualisasi data. "
            "Support banyak datasource: Prometheus, Loki, InfluxDB, PostgreSQL. "
            "Dashboard-as-code via JSON atau Grafonnet. "
            "Fitur: alerting, annotations, templating variables."
        ),
        "loki": (
            "Loki: log aggregation system dari Grafana Labs. "
            "Like Prometheus tapi untuk logs. "
            "Label-based indexing (hemat storage). "
            "Query dengan LogQL. Cocok dipadukan Promtail/Alloy sebagai log shipper."
        ),
    }
    key = tool_name.lower()
    for k, v in knowledge.items():
        if k in key:
            return v
    return f"Tool monitoring '{tool_name}': gunakan dokumentasi resmi untuk referensi lengkap."
```

### Langkah 2: Tambahkan ke daftar `TOOLS`

```python
TOOLS = [
    explain_gitops_concept,
    explain_kubernetes_resource,
    explain_cicd_pattern,
    get_kubectl_commands,
    explain_monitoring_tool,   # ← tambahkan di sini
]
```

Tidak perlu mengubah `graph.py`, `nodes.py`, atau `state.py`. Graph akan otomatis mengirimkan
definisi tool baru ke LLM pada request berikutnya.

### Rebuild container setelah perubahan:

```bash
docker compose up -d --build api
```

---

## Referensi

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [LangChain Tools](https://python.langchain.com/docs/concepts/tools/)
- [LiteLLM Proxy](https://docs.litellm.ai/docs/proxy/quick_start)
- [OpenAI Function Calling](https://platform.openai.com/docs/guides/function-calling)
