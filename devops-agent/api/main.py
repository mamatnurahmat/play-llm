import os
import sys
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from langchain_core.messages import HumanMessage, AIMessage

# Tambahkan parent dir ke path agar bisa import 'agent'
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent import devops_agent

app = FastAPI(title="DevOps Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str
    history: Optional[List[dict]] = []

class ChatResponse(BaseModel):
    response: str
    tool_calls_used: List[str]

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    try:
        # Build messages from history
        messages = []
        for h in req.history:
            if h["role"] == "user":
                messages.append(HumanMessage(content=h["content"]))
            else:
                messages.append(AIMessage(content=h["content"]))
        
        messages.append(HumanMessage(content=req.message))

        # Run agent
        result = devops_agent.invoke({"messages": messages})
        
        # Extract last AIMessage
        last_msg = result["messages"][-1]
        
        # Get tool names used in the whole run (optional, for UI)
        tool_names = []
        for m in result["messages"]:
            if isinstance(m, AIMessage) and m.additional_kwargs.get("tool_calls"):
                for tc in m.additional_kwargs["tool_calls"]:
                    tool_names.append(tc["function"]["name"])

        return ChatResponse(
            response=last_msg.content,
            tool_calls_used=list(set(tool_names))
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
