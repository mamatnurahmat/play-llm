"""
FastAPI Server — REST API mode for the GitOps AI Agent.
========================================================
Menyediakan endpoint /api/run dengan Swagger UI dan
sample payload untuk semua action.
"""

from agents.config import Config

# Registry: maps action name → agent class
_AGENT_REGISTRY = {}


def _register_agents():
    """Lazy import and register all agent classes."""
    from agents.clone_agent import CloneAgent
    from agents.branch_agent import BranchAgent
    from agents.pr_agent import PRAgent
    from agents.update_image_agent import UpdateImageAgent
    from agents.quick_pr_agent import QuickPRAgent

    return {
        "clone":        CloneAgent,
        "create-branch": BranchAgent,
        "pull-request": PRAgent,
        "update-image": UpdateImageAgent,
        "quick-pr":     QuickPRAgent,
    }


def run_server(config: Config):
    """Start FastAPI server with Swagger UI."""
    import uvicorn
    from fastapi import FastAPI, HTTPException, Body
    from pydantic import BaseModel, Field
    from typing import Optional, Dict, Any

    agent_registry = _register_agents()
    default_org = config.default_org

    app = FastAPI(
        title="GitOps AI Agent API (Multi-SCM)",
        description=(
            "API untuk mengelola repository Git secara otonom melalui AI Agent.\n\n"
            f"**SCM Provider aktif**: `{config.scm_provider.upper()}`  \n"
            f"**SCM Base URL**: `{config.scm_base_url}`"
        ),
        version="3.0.0",
    )

    class AgentRequest(BaseModel):
        action:        str                      = Field(..., description="clone | create-branch | pull-request | update-image | quick-pr")
        repo_name:     str                      = Field(..., description="Nama repository")
        org:           Optional[str]            = Field(default_org, description="Organisasi / project")
        action_kwargs: Optional[Dict[str, Any]] = Field(default={}, description="Parameter ekstra per aksi")

    @app.post("/api/run")
    async def api_run(req: AgentRequest = Body(..., openapi_examples={
        "Clone": {"summary": "Clone Repository", "value": {
            "action": "clone", "repo_name": "my-service", "org": default_org,
            "action_kwargs": {"ref": "main"}
        }},
        "Create Branch": {"summary": "Create Branch", "value": {
            "action": "create-branch", "repo_name": "my-service", "org": default_org,
            "action_kwargs": {"existing_branch": "main", "new_branch": "feature/my-feature"}
        }},
        "Pull Request": {"summary": "Create Pull Request", "value": {
            "action": "pull-request", "repo_name": "my-service", "org": default_org,
            "action_kwargs": {"source_branch": "feature/my-feature", "dest_branch": "main"}
        }},
        "Update Image": {"summary": "Update Image YAML", "value": {
            "action": "update-image", "repo_name": "gitops-k8s", "org": default_org,
            "action_kwargs": {"ref": "main", "yaml_file": "deployment.yaml", "new_image": "app:v2.0.0"}
        }},
        "Quick PR": {"summary": "Quick PR (Branch → Update → PR)", "value": {
            "action": "quick-pr", "repo_name": "gitops", "org": default_org,
            "action_kwargs": {"namespace": "default", "deployment": "qoinplus-api", "image": "registry/qoinplus-api:v1.2.3"}
        }},
    })):
        agent_cls = agent_registry.get(req.action)
        if not agent_cls:
            raise HTTPException(status_code=400, detail=f"Unknown action: {req.action}. "
                                f"Available: {', '.join(agent_registry.keys())}")
        try:
            agent = agent_cls(
                config=config,
                repo_name=req.repo_name,
                org=req.org or default_org,
                action_kwargs=req.action_kwargs or {},
            )
            report = await agent.run()
            return {"status": "success", "scm_provider": config.scm_provider, "agent": agent.name, "report": report}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/agents")
    async def list_agents():
        """List all available agent actions."""
        return {
            "agents": [
                {"action": action, "name": cls.__name__, "description": cls.__doc__ or ""}
                for action, cls in agent_registry.items()
            ]
        }

    print("🚀 Starting Web API on http://0.0.0.0:8888")
    print("📚 Swagger UI: http://localhost:8888/docs")
    uvicorn.run(app, host="0.0.0.0", port=8888)
